"""Unit tests for the `the-loop sessions` operator surface (issue-98).

Covers the subcommands added on top of register/attach/close: the joined table,
`show`, `pause`/`resume` (including the GitHub-label mirror), and `prune`.
"""

import json

import pytest

from the_loop.cli import main
from the_loop.commands import iter_commands, sessions_cmd
from the_loop.labels import LabelResult
from the_loop.sessions import PauseStore, Session, SessionRegistry, WorkItemRef

REF = "github:octo/repo#15"


@pytest.fixture
def paths(tmp_path):
    """Registry / pause / poll-state paths, none of which exist yet."""
    return {
        "registry": str(tmp_path / "sessions"),
        "pause": str(tmp_path / "paused.json"),
        "poll": str(tmp_path / "poll-state.json"),
    }


@pytest.fixture(autouse=True)
def _no_gh(monkeypatch):
    """Label writes must not shell out in unit tests unless a test asks."""

    class _Silent:
        def __init__(self, *args, **kwargs):
            pass

        def add(self, work_item, label):
            return LabelResult(ok=True, changed=True, detail="label added")

        def remove(self, work_item, label):
            return LabelResult(ok=True, changed=True, detail="label removed")

    monkeypatch.setattr(sessions_cmd, "GitHubLabeler", _Silent)


def register(paths, ref=REF, **kwargs):
    kwargs.setdefault("harness", "claude")
    kwargs.setdefault("harness_session_id", "uuid-1")
    kwargs.setdefault("cwd", "/tmp/work")
    SessionRegistry(paths["registry"]).register(
        Session(work_item=WorkItemRef.parse(ref), **kwargs), force=True
    )


def poll_state(paths, items):
    with open(paths["poll"], "w") as handle:
        json.dump({"items": items}, handle)


def list_argv(paths, *extra):
    return [
        "sessions",
        "list",
        "--registry-dir",
        paths["registry"],
        "--pause-file",
        paths["pause"],
        "--poll-state-file",
        paths["poll"],
        *extra,
    ]


def test_labels_command_is_registered():
    assert "labels" in {c.name for c in iter_commands()}


def test_list_is_empty_but_successful_when_nothing_is_tracked(paths, capsys):
    assert main(list_argv(paths)) == 0
    captured = capsys.readouterr()
    assert captured.out.strip().startswith("Work item")
    assert "nothing tracked" in captured.err


def test_list_joins_the_registry_and_the_poller_ledger(paths, capsys):
    register(paths)
    poll_state(
        paths,
        {
            REF: {"lastPolledAt": "2026-07-25T10:00:00Z"},
            "github:octo/repo#16": {"spawn": {"attempts": 3, "gaveUp": True}},
        },
    )
    assert main(list_argv(paths, "--format", "json")) == 0
    rows = {row["ref"]: row for row in json.loads(capsys.readouterr().out)}
    assert rows[REF]["status"] == "active"
    assert rows[REF]["tracked"] is True
    assert rows["github:octo/repo#16"]["status"] == "spawn-failed"
    assert rows["github:octo/repo#16"]["spawnAttempts"] == 3


def test_list_filters_by_status(paths, capsys):
    register(paths)
    register(paths, ref="github:octo/repo#16", status="closed")
    assert main(list_argv(paths, "--status", "closed", "--format", "json")) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [row["ref"] for row in rows] == ["github:octo/repo#16"]


def test_pause_then_resume_round_trip(paths, capsys):
    register(paths)
    assert (
        main(
            [
                "sessions",
                "pause",
                "--work-item",
                REF,
                "--pause-file",
                paths["pause"],
                "--reason",
                "waiting",
            ]
        )
        == 0
    )
    assert "paused" in capsys.readouterr().out
    assert PauseStore(paths["pause"]).is_paused(REF) is True

    assert main(list_argv(paths, "--format", "json")) == 0
    row = json.loads(capsys.readouterr().out)[0]
    assert row["status"] == "paused"
    assert row["pauseReason"] == "waiting"

    assert (
        main(["sessions", "resume", "--work-item", REF, "--pause-file", paths["pause"]])
        == 0
    )
    assert PauseStore(paths["pause"]).is_paused(REF) is False


def test_pause_does_not_require_a_session(paths):
    assert (
        main(["sessions", "pause", "--work-item", REF, "--pause-file", paths["pause"]])
        == 0
    )
    assert PauseStore(paths["pause"]).is_paused(REF) is True


def test_repeated_pause_and_resume_are_reported_no_ops(paths, capsys):
    argv = ["sessions", "pause", "--work-item", REF, "--pause-file", paths["pause"]]
    assert main(argv) == 0
    capsys.readouterr()
    assert main(argv) == 0
    assert "already paused" in capsys.readouterr().out
    resume = ["sessions", "resume", "--work-item", REF, "--pause-file", paths["pause"]]
    assert main(resume) == 0
    capsys.readouterr()
    assert main(resume) == 0
    assert "was not paused" in capsys.readouterr().out


def test_pause_rejects_a_malformed_ref(paths, capsys):
    assert (
        main(
            ["sessions", "pause", "--work-item", "nope", "--pause-file", paths["pause"]]
        )
        == 2
    )
    assert "invalid work-item ref" in capsys.readouterr().err


def test_pause_mirrors_the_label_unless_no_label(paths, monkeypatch, capsys):
    seen = []

    class _Recording:
        def __init__(self, *args, **kwargs):
            pass

        def add(self, work_item, label):
            seen.append(("add", work_item.ref, label))
            return LabelResult(ok=True, changed=True)

        def remove(self, work_item, label):
            seen.append(("remove", work_item.ref, label))
            return LabelResult(ok=True, changed=True)

    monkeypatch.setattr(sessions_cmd, "GitHubLabeler", _Recording)
    base = ["--work-item", REF, "--pause-file", paths["pause"]]
    assert main(["sessions", "pause"] + base) == 0
    assert seen == [("add", REF, "the-loop: paused")]
    assert main(["sessions", "resume"] + base) == 0
    assert seen[-1][0] == "remove"

    seen.clear()
    assert main(["sessions", "pause"] + base + ["--no-label"]) == 0
    assert seen == []


def test_a_failed_label_write_still_pauses_locally(paths, monkeypatch, capsys):
    class _Broken:
        def __init__(self, *args, **kwargs):
            pass

        def add(self, work_item, label):
            return LabelResult(ok=False, error="HTTP 403")

        def remove(self, work_item, label):
            return LabelResult(ok=False, error="HTTP 403")

    monkeypatch.setattr(sessions_cmd, "GitHubLabeler", _Broken)
    assert (
        main(["sessions", "pause", "--work-item", REF, "--pause-file", paths["pause"]])
        == 0
    )
    captured = capsys.readouterr()
    assert PauseStore(paths["pause"]).is_paused(REF) is True
    assert "could not add" in captured.err
    assert "gh issue edit 15" in captured.err  # the manual fallback


def show_argv(paths, ref=REF, *extra):
    return [
        "sessions",
        "show",
        "--work-item",
        ref,
        "--registry-dir",
        paths["registry"],
        "--pause-file",
        paths["pause"],
        "--poll-state-file",
        paths["poll"],
        *extra,
    ]


def test_show_prints_the_detail_block(paths, capsys):
    register(paths, runner="tmux", tmux_target="loop-x", pr_ref="github:octo/repo#20")
    assert main(show_argv(paths)) == 0
    out = capsys.readouterr().out
    assert "Work item" in out and REF in out
    assert "github:octo/repo#20" in out


def test_show_as_json(paths, capsys):
    register(paths)
    assert main(show_argv(paths, REF, "--format", "json")) == 0
    assert json.loads(capsys.readouterr().out)["ref"] == REF


def test_show_reports_an_unknown_work_item(paths, capsys):
    assert main(show_argv(paths)) == 1
    assert "nothing recorded" in capsys.readouterr().err


def test_prune_removes_closed_records_only(paths, capsys):
    register(paths)
    register(paths, ref="github:octo/repo#16", status="closed")
    assert main(["sessions", "prune", "--registry-dir", paths["registry"]]) == 0
    refs = [s.work_item.ref for s in SessionRegistry(paths["registry"]).list_sessions()]
    assert refs == [REF]
    assert "removed 1 record" in capsys.readouterr().out


def test_prune_dry_run_removes_nothing(paths, capsys):
    register(paths, status="closed")
    assert (
        main(["sessions", "prune", "--dry-run", "--registry-dir", paths["registry"]])
        == 0
    )
    assert SessionRegistry(paths["registry"]).list_sessions()
    assert "would remove" in capsys.readouterr().out


def test_prune_keeps_a_retained_tmux_transcript(paths, monkeypatch, capsys):
    register(paths, ref=REF, status="closed", runner="tmux", tmux_target="loop-x")

    class _Tmux:
        def is_available(self):
            return True

        def has_session(self, target):
            return True

    monkeypatch.setattr(sessions_cmd, "TmuxRunner", _Tmux)
    assert main(["sessions", "prune", "--registry-dir", paths["registry"]]) == 0
    assert SessionRegistry(paths["registry"]).list_sessions()
    assert "retained transcript" in capsys.readouterr().out

    assert (
        main(
            [
                "sessions",
                "prune",
                "--include-retained",
                "--registry-dir",
                paths["registry"],
            ]
        )
        == 0
    )
    assert SessionRegistry(paths["registry"]).list_sessions() == []
