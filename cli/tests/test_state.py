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


# -- the local record is a map of sessions keyed by ref (issue-368) ------------


def _v1_record(tmp_path):
    """A registry record in the pre-issue-368 shape, as an older release wrote it."""
    import json

    path = tmp_path / "github-octo-repo-15.json"
    path.write_text(
        json.dumps(
            {
                "workItem": {
                    "ref": "github:octo/repo#15",
                    "provider": "github",
                    "owner": "octo",
                    "repo": "repo",
                    "number": 15,
                },
                "url": "https://github.com/octo/repo/issues/15",
                "harness": "claude",
                "harnessSessionId": "s-0",
                "cwd": "/w/issue-15",
                "status": "active",
                "tmuxTarget": "loop-github-octo-repo-15",
                "recentDeliveries": ["d1"],
                "pullRequests": [
                    {
                        "workItem": {
                            "ref": "github:octo/lib#7",
                            "provider": "github",
                            "owner": "octo",
                            "repo": "lib",
                            "number": 7,
                        },
                        "url": "https://github.com/octo/lib/pull/7",
                        "harness": "claude",
                        "harnessSessionId": "s-1",
                        "cwd": "/w/pr-7",
                        "status": "active",
                        "tmuxTarget": "loop-github-octo-lib-7",
                        "recentDeliveries": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_the_record_is_a_map_of_sessions_keyed_by_the_ref_each_serves(tmp_path):
    """R5.1 — the ref is the key, and the only thing this file knows about a PR."""
    import json

    from the_loop.sessions import Session, SessionRegistry, WorkItemRef

    registry = SessionRegistry(tmp_path)
    registry.register(
        Session(
            work_item=WorkItemRef.parse("github:octo/repo#15"),
            harness="claude",
            harness_session_id="s-0",
            cwd="/w/issue-15",
        )
    )
    registry.link_pull_request("github:octo/repo#15", "github:octo/lib#7")

    record = json.loads((tmp_path / "github-octo-repo-15.json").read_text())
    assert record["workItem"] == "github:octo/repo#15"
    assert set(record["sessions"]) == {"github:octo/repo#15", "github:octo/lib#7"}
    entry = record["sessions"]["github:octo/lib#7"]
    # Nothing about the pull request itself: that is the repository's, recorded
    # once in work-item-state.json and joined by this key.
    for leaked in ("url", "owner", "repo", "number", "workItem", "provider"):
        assert leaked not in entry, (
            f"{leaked} is the repository's fact, not this file's"
        )


def test_a_pre_issue_368_record_is_read_and_rewritten_as_a_map(tmp_path):
    """R8.1 — read old, write new; nothing migrates in bulk and nothing is lost."""
    import json

    from the_loop.sessions import SessionRegistry

    path = _v1_record(tmp_path)
    registry = SessionRegistry(tmp_path)
    record = registry.find_by_work_item("github:octo/repo#15")
    assert record is not None and record.harness_session_id == "s-0"
    assert [pr.work_item.ref for pr in record.pull_requests] == ["github:octo/lib#7"]
    assert record.pull_requests[0].harness_session_id == "s-1"
    assert registry.record_owning("github:octo/lib#7") is not None

    registry.touch("github:octo/repo#15", delivery_id="d2")
    rewritten = json.loads(path.read_text())
    assert rewritten["version"] == 2
    assert set(rewritten["sessions"]) == {"github:octo/repo#15", "github:octo/lib#7"}
    assert "pullRequests" not in rewritten


def test_a_read_cursor_lives_with_the_handles(tmp_path):
    """R5.1 — what THIS deployment mirrored is a statement about this machine."""
    from the_loop.sessions import Session, SessionRegistry, WorkItemRef

    registry = SessionRegistry(tmp_path)
    registry.register(
        Session(
            work_item=WorkItemRef.parse("github:octo/repo#15"),
            harness="claude",
            harness_session_id="s-0",
            cwd="/w",
        )
    )
    assert registry.cursor("github:octo/repo#15", "slack", "1700.1") == ""
    assert registry.advance_cursor("github:octo/repo#15", "slack", "1700.1", "1700.9")
    assert registry.cursor("github:octo/repo#15", "slack", "1700.1") == "1700.9"
    # A work item with no record here has nowhere to keep one, and needs none.
    assert not registry.advance_cursor("github:octo/other#1", "slack", "1.1", "1.2")
