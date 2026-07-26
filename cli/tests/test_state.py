"""Unit tests for the one-root generated-state layout (issue-106)."""

from pathlib import Path

from the_loop.state import (
    DEFAULT_STATE_ROOT,
    LEGACY_POLL_STATE,
    StateLayout,
    control_dir_for,
    layout_from_config,
    resolve_poll_state_path,
)


def test_the_default_root_reproduces_the_pre_106_paths():
    # The point of the default: an operator who sets nothing sees no move —
    # except the poll state, which the legacy fallback covers.
    layout = StateLayout()
    assert layout.root == DEFAULT_STATE_ROOT
    assert layout.sessions_dir == ".the-loop/sessions"
    assert layout.event_log == ".the-loop/logs/events.jsonl"
    assert layout.pidfile == ".the-loop/gh-webhook.pid"


def test_session_related_state_lives_together_under_sessions():
    layout = StateLayout(root="/srv/loop")
    assert layout.sessions_dir == "/srv/loop/sessions"
    assert layout.control_dir == "/srv/loop/sessions/control"
    assert layout.poll_state == "/srv/loop/sessions/poll-state.json"


def test_one_root_relocates_everything():
    layout = StateLayout(root="/var/lib/the-loop")
    assert layout.event_log.startswith("/var/lib/the-loop/")
    assert layout.pidfile.startswith("/var/lib/the-loop/")
    assert layout.sessions_dir.startswith("/var/lib/the-loop/")


def test_layout_from_config_reads_state_root():
    assert layout_from_config({"state": {"root": "/tmp/x"}}).root == "/tmp/x"


def test_layout_from_config_falls_back_on_anything_missing():
    for config in ({}, None, {"state": {}}, {"state": {"root": "  "}}):
        assert layout_from_config(config).root == DEFAULT_STATE_ROOT


def test_control_records_live_beside_the_registry_they_steer():
    assert control_dir_for("/somewhere/else/sessions") == (
        "/somewhere/else/sessions/control"
    )


# -- poll-state resolution ------------------------------------------------------


def test_a_configured_poll_state_always_wins():
    assert (
        resolve_poll_state_path("/explicit.json", StateLayout(), exists=lambda p: True)
        == "/explicit.json"
    )


def test_the_new_default_is_used_when_it_exists():
    layout = StateLayout()
    resolved = resolve_poll_state_path(
        "", layout, exists=lambda p: str(p) == layout.poll_state
    )
    assert resolved == layout.poll_state


def test_a_legacy_poll_state_is_kept_rather_than_re_baselining(caplog):
    # Adopting an empty new file would make every watched thread first-sight
    # again and re-forward its entire comment history.
    layout = StateLayout()
    resolved = resolve_poll_state_path(
        "", layout, exists=lambda p: str(p) == LEGACY_POLL_STATE
    )
    assert resolved == LEGACY_POLL_STATE
    assert any("poll state" in r.getMessage() for r in caplog.records)


def test_a_fresh_install_gets_the_new_default():
    layout = StateLayout()
    resolved = resolve_poll_state_path("", layout, exists=lambda p: False)
    assert resolved == layout.poll_state
    assert Path(resolved).parent.name == "sessions"
