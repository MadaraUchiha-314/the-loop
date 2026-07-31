"""Unit tests for the generated-state layout (issue-106, reorganised in issue-128)."""

from the_loop.state import (
    DEFAULT_STATE_ROOT,
    StateLayout,
    layout_from_config,
    legacy_layout,
)


def test_the_default_root_places_both_halves_under_it():
    layout = StateLayout()
    assert layout.root == DEFAULT_STATE_ROOT
    assert layout.portable_dir == ".the-loop/portable"
    assert layout.local_dir == ".the-loop/local"
    assert layout.event_log == ".the-loop/logs/events.jsonl"
    assert layout.pidfile == ".the-loop/gh-webhook.pid"


def test_the_two_halves_are_separate_trees():
    # The whole point of issue-128: one directory is tracked in git and one is
    # never, so neither may be nested inside the other.
    layout = StateLayout(root="/srv/loop")
    assert layout.portable_dir == "/srv/loop/portable"
    assert layout.local_dir == "/srv/loop/local"
    assert not layout.local_dir.startswith(layout.portable_dir)
    assert not layout.portable_dir.startswith(layout.local_dir)


def test_one_root_relocates_everything():
    layout = StateLayout(root="/var/lib/the-loop")
    for path in (
        layout.event_log,
        layout.pidfile,
        layout.portable_dir,
        layout.local_dir,
    ):
        assert path.startswith("/var/lib/the-loop/")


def test_layout_from_config_reads_state_root():
    assert layout_from_config({"state": {"root": "/tmp/x"}}).root == "/tmp/x"


def test_layout_from_config_falls_back_on_anything_missing():
    for config in ({}, None, {"state": {}}, {"state": {"root": "  "}}):
        assert layout_from_config(config).root == DEFAULT_STATE_ROOT


# -- the upgrade shim -----------------------------------------------------------


def test_legacy_layout_points_at_the_pre_128_locations():
    legacy = legacy_layout(StateLayout(root="/srv/loop"))
    assert legacy.sessions_dir == "/srv/loop/sessions"
    assert legacy.control_dir == "/srv/loop/sessions/control"
    assert legacy.poll_state == "/srv/loop/sessions/poll-state.json"
    # And the pre-issue-106 file, still honoured so an upgrade never re-baselines.
    assert legacy.pre_106_poll_state == ".the-loop/poll-state.json"
