"""Unit tests for standing sessions' declaration, ref grammar and record store (issue-277, T1).

The three things a standing session *is* before anything runs. What it *does* — spawn,
resume, stop, say — is `test_standing_integration.py`'s.
"""

from __future__ import annotations

import json

import pytest

from the_loop import standing
from the_loop.standing import (
    RUNNING,
    STOPPED,
    StandingConfig,
    StandingRecord,
    StandingRegistry,
    parse_standing_ref,
    standing_ref,
    tmux_target_for,
)
from the_loop.workitem import WorkItemRef


def _config(**block):
    return {
        "routing": {
            "defaultHarness": "claude",
            "harnessArgs": {"claude": ["--permission-mode", "acceptEdits"]},
            "spawnWorkdir": "/srv/checkouts",
        },
        "standingSessions": block,
    }


# -- the ref grammar -------------------------------------------------------------


@pytest.mark.parametrize(
    "ref", ["standing:supervisor", "standing:triage-bot", "standing:a", "standing:x9"]
)
def test_a_standing_ref_parses_to_its_name(ref):
    assert parse_standing_ref(ref) == ref.split(":", 1)[1]


@pytest.mark.parametrize(
    "ref",
    [
        "github:octo/repo#5",
        "standing:",
        "standing:-leading-hyphen",
        "standing:Upper",
        "standing:has space",
        "standing:owner/repo#1",
        "standing:" + "x" * 41,
        "",
    ],
)
def test_anything_else_is_not_a_standing_ref(ref):
    assert parse_standing_ref(ref) is None


def test_the_two_namespaces_cannot_address_each_other():
    """The security property of the split (design §Security): neither parser
    accepts the other's strings, so no crafted ref crosses over."""
    assert parse_standing_ref("github:octo/repo#5") is None
    with pytest.raises(ValueError):
        WorkItemRef.parse(standing_ref("supervisor"))


def test_a_standing_tmux_target_cannot_collide_with_a_work_item_slug():
    # Every work-item target ends in -<digits> and carries its provider, so the
    # only collision would need a provider called "standing".
    work_item = WorkItemRef.parse("github:standing/foo#1")
    assert f"loop-{work_item.slug}" != tmux_target_for("foo")
    assert tmux_target_for("foo") == "loop-standing-foo"


# -- the declaration -------------------------------------------------------------


def test_an_absent_block_parses_to_a_disabled_config():
    parsed = StandingConfig.from_mapping({})
    assert parsed.enabled is False
    assert parsed.sessions == ()


def test_an_entry_inherits_harness_args_and_cwd_from_routing():
    parsed = StandingConfig.from_mapping(
        _config(enabled=True, sessions=[{"name": "supervisor"}])
    )
    entry = parsed.get("supervisor")
    assert entry is not None
    assert entry.harness == "claude"
    assert entry.harness_args == ("--permission-mode", "acceptEdits")
    assert entry.cwd == "/srv/checkouts"
    assert entry.auto_start is True


def test_an_explicit_empty_harness_args_means_none_not_inherit():
    """Omitted and `[]` are different answers, and the difference is the point:
    `[]` is how one session gets a narrower surface than the rest."""
    parsed = StandingConfig.from_mapping(
        _config(enabled=True, sessions=[{"name": "narrow", "harnessArgs": []}])
    )
    narrow = parsed.get("narrow")
    assert narrow is not None and narrow.harness_args == ()


@pytest.mark.parametrize(
    "name", ["Supervisor", "-lead", "has space", "under_score", "", "x" * 41]
)
def test_a_name_that_is_not_tmux_and_filename_safe_is_refused(name):
    with pytest.raises(ValueError) as excinfo:
        StandingConfig.from_mapping(_config(sessions=[{"name": name}]))
    assert "name" in str(excinfo.value)


def test_a_duplicate_name_refuses_the_block_naming_both_positions():
    with pytest.raises(ValueError) as excinfo:
        StandingConfig.from_mapping(
            _config(sessions=[{"name": "a"}, {"name": "b"}, {"name": "a"}])
        )
    message = str(excinfo.value)
    assert "sessions[2]" in message and "sessions[0]" in message


def test_declaring_both_prompt_sources_refuses_the_entry():
    with pytest.raises(ValueError) as excinfo:
        StandingConfig.from_mapping(
            _config(sessions=[{"name": "a", "prompt": "hi", "promptFile": "/tmp/x"}])
        )
    assert "promptFile" in str(excinfo.value)


def test_a_non_list_sessions_key_is_refused():
    with pytest.raises(ValueError):
        StandingConfig.from_mapping(_config(sessions="supervisor"))


def test_a_non_mapping_block_is_refused():
    with pytest.raises(ValueError):
        StandingConfig.from_mapping({"standingSessions": ["supervisor"]})


def test_the_slack_binding_defaults_to_off_and_no_channel():
    parsed = StandingConfig.from_mapping(_config(sessions=[{"name": "a"}]))
    entry = parsed.get("a")
    assert entry is not None
    assert entry.slack.enabled is False
    assert entry.slack.channel == ""


def test_a_prompt_file_is_read_at_start_time(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("watch everything", encoding="utf-8")
    parsed = StandingConfig.from_mapping(
        _config(sessions=[{"name": "a", "promptFile": str(brief)}])
    )
    entry = parsed.get("a")
    assert entry is not None and entry.boot_text() == "watch everything"


def test_an_unreadable_prompt_file_names_the_path(tmp_path):
    parsed = StandingConfig.from_mapping(
        _config(sessions=[{"name": "a", "promptFile": str(tmp_path / "gone.md")}])
    )
    entry = parsed.get("a")
    assert entry is not None
    with pytest.raises(ValueError) as excinfo:
        entry.boot_text()
    assert "gone.md" in str(excinfo.value)


# -- the record store ------------------------------------------------------------


def test_a_record_round_trips(tmp_path):
    registry = StandingRegistry(tmp_path / "standing")
    registry.write(
        StandingRecord(
            name="supervisor",
            harness="claude",
            harness_session_id="conv-1",
            cwd=str(tmp_path),
            status=RUNNING,
            slack_channel="C1",
            slack_thread="1712.1",
        )
    )
    read = registry.read("supervisor")
    assert read is not None
    assert read.harness_session_id == "conv-1"
    assert read.tmux_target == "loop-standing-supervisor"
    assert read.slack_thread == "1712.1"
    assert read.is_running


def test_a_write_stamps_created_at_once(tmp_path):
    registry = StandingRegistry(tmp_path / "standing")
    first = registry.write(StandingRecord(name="a"))
    assert first.created_at
    second = registry.write(
        StandingRecord(name="a", created_at=first.created_at, status=STOPPED)
    )
    assert second.created_at == first.created_at


def test_a_hand_edited_tmux_target_is_ignored(tmp_path):
    """The target is derived from the name, never trusted from the file — so a
    corrupted record cannot aim a kill at another tmux session."""
    root = tmp_path / "standing"
    root.mkdir(parents=True)
    (root / "a.json").write_text(
        json.dumps({"name": "a", "tmuxTarget": "loop-github-octo-repo-5"}),
        encoding="utf-8",
    )
    read = StandingRegistry(root).read("a")
    assert read is not None and read.tmux_target == "loop-standing-a"


def test_an_unreadable_record_is_skipped_not_fatal(tmp_path):
    root = tmp_path / "standing"
    root.mkdir(parents=True)
    (root / "broken.json").write_text("{not json", encoding="utf-8")
    StandingRegistry(root).write(StandingRecord(name="fine"))
    names = [record.name for record in StandingRegistry(root).list()]
    assert names == ["fine"]


def test_an_invalid_name_never_becomes_a_path(tmp_path):
    registry = StandingRegistry(tmp_path / "standing")
    for name in ("../escape", "a/b", ""):
        with pytest.raises(ValueError):
            registry.path_for(name)


def test_listing_an_absent_directory_is_empty(tmp_path):
    assert StandingRegistry(tmp_path / "nope").list() == []


def test_delete_reports_whether_there_was_anything_to_delete(tmp_path):
    registry = StandingRegistry(tmp_path / "standing")
    registry.write(StandingRecord(name="a"))
    assert registry.delete("a") is True
    assert registry.delete("a") is False


def test_the_module_exports_what_the_surfaces_import():
    for symbol in standing.__all__:
        assert hasattr(standing, symbol), symbol
