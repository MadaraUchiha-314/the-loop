"""Tests for the CLI half of execution control (issue-106).

``the-loop sessions start|pause|resume|stop`` applies the same command an
authorized user issues by keyword, and mirrors it back to the work item as a
comment carrying that keyword — marked as the-loop's own so the daemon never
reads it back. Driven through ``the_loop.cli.main`` with the ``gh``-shelling
comment poster stubbed; the registry and control store are real, on tmp paths.

Since issue-161 the implementation lives in :mod:`the_loop.core.sessions` and
the command renders it, so the seams stubbed here are core's: the comment
poster it imported, and the dispatcher factory it borrows from the poller.
"""

import json

import pytest

from the_loop.authz import is_self_authored
from the_loop.control import ControlStore, parse_command, ControlConfig
from the_loop.cli import main
from the_loop.commands import poll as poll_cmd
from the_loop.core import sessions as core_sessions
from the_loop.sessions import Session, SessionRegistry, WorkItemRef

REF = "github:octo/repo#15"


@pytest.fixture
def posted(monkeypatch):
    """Capture the paper-trail comment instead of shelling out to ``gh``."""
    calls = []

    def fake_post(item, body, gh_binary="gh", **kwargs):
        calls.append((item.ref, body, gh_binary))
        return True, ""

    monkeypatch.setattr(core_sessions, "post_issue_comment", fake_post)
    return calls


@pytest.fixture
def registry(tmp_path):
    return SessionRegistry(tmp_path / "local")


def store_for(tmp_path):
    """The portable half, where the CLI invocations below are pointed."""
    return ControlStore(str(tmp_path / "portable"))


def register(registry, status="active", tmux_target=""):
    return registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-0",
            cwd=".",
            status=status,
            tmux_target=tmux_target,
        ),
        force=True,
    )


def run(command, tmp_path, *extra):
    return main(
        [
            "sessions",
            command,
            "--work-item",
            REF,
            "--registry-dir",
            str(tmp_path / "local"),
            "--portable-dir",
            str(tmp_path / "portable"),
            *extra,
        ]
    )


# -- pause / resume -------------------------------------------------------------


def test_pause_suspends_the_session_and_records_it(tmp_path, registry, posted):
    register(registry)
    assert run("pause", tmp_path) == 0
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "paused"
    record = store_for(tmp_path).get(REF)
    assert record is not None
    assert (record.command, record.source) == ("pause", "cli")


def test_resume_reactivates_a_paused_session(tmp_path, registry, posted):
    register(registry, status="paused")
    assert run("resume", tmp_path) == 0
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "active"


def test_resuming_something_that_is_not_paused_reports_it(tmp_path, registry, posted):
    register(registry)
    assert run("resume", tmp_path) == 1
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "active"


def test_resuming_nothing_does_not_arm_the_work_item(tmp_path, registry, posted):
    # Arming commands are recorded only when they act (owner decision, PR #107).
    assert run("resume", tmp_path) == 1
    assert store_for(tmp_path).get(REF) is None


def test_pausing_a_work_item_with_no_session_still_records_the_intent(
    tmp_path, registry, posted
):
    # Nothing to suspend, but the record is what a later start/spawn consults.
    assert run("pause", tmp_path) == 1
    assert store_for(tmp_path).start_requested(REF) is False


def test_start_resumes_a_paused_session_rather_than_spawning(
    tmp_path, registry, posted, monkeypatch
):
    def explode(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("a paused session must be resumed, not re-spawned")

    monkeypatch.setattr(poll_cmd, "_build_dispatcher", explode)
    register(registry, status="paused")
    assert run("start", tmp_path) == 0
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "active"
    assert store_for(tmp_path).start_requested(REF) is True


def test_start_on_a_running_session_is_a_no_op(tmp_path, registry, posted, monkeypatch):
    monkeypatch.setattr(
        poll_cmd,
        "_build_dispatcher",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not spawn")),
    )
    register(registry)
    assert run("start", tmp_path) == 0
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "active"


# -- stop -----------------------------------------------------------------------


def test_stop_closes_the_session_through_the_dispatcher(
    tmp_path, registry, posted, monkeypatch
):
    closed = []

    class FakeDispatcher:
        def close_session(self, session, routed=None, reason=""):
            closed.append((session.work_item.ref, reason))
            SessionRegistry(tmp_path / "local").close(session.work_item)

        def stop(self, timeout=None):
            pass

    monkeypatch.setattr(
        poll_cmd, "_build_dispatcher", lambda *a, **k: (FakeDispatcher(), None)
    )
    register(registry)
    assert run("stop", tmp_path) == 0
    assert closed and closed[0][0] == REF
    assert registry.find_by_work_item(REF) is None
    assert store_for(tmp_path).start_requested(REF) is False


def test_stop_without_a_session_records_the_disarm(tmp_path, registry, posted):
    assert run("stop", tmp_path) == 1
    record = store_for(tmp_path).get(REF)
    assert record is not None and record.command == "stop"


# -- the paper trail ------------------------------------------------------------


def test_every_action_is_mirrored_to_the_ticket_with_the_same_keyword(
    tmp_path, registry, posted
):
    register(registry)
    run("pause", tmp_path)
    ref, body, _ = posted[0]
    assert ref == REF
    assert parse_command(body, ControlConfig()).command == "pause"


def test_the_mirrored_comment_is_marked_as_the_loops_own(tmp_path, registry, posted):
    # Otherwise the daemon reads its own comment back and re-applies the command.
    register(registry)
    run("pause", tmp_path)
    assert is_self_authored(posted[0][1])


def test_no_comment_skips_the_paper_trail(tmp_path, registry, posted):
    register(registry)
    assert run("pause", tmp_path, "--no-comment") == 0
    assert posted == []
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "paused"


def test_a_failing_gh_does_not_undo_the_local_action(
    tmp_path, registry, monkeypatch, capsys
):
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment",
        lambda *a, **k: (False, "gh exited 1: nope"),
    )
    register(registry)
    assert run("pause", tmp_path) == 0
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "paused"
    assert "could not comment" in capsys.readouterr().err


def test_a_malformed_work_item_is_refused(tmp_path, posted):
    assert main(["sessions", "pause", "--work-item", "nonsense"]) == 2
    assert posted == []


# -- list -----------------------------------------------------------------------


def test_list_shows_the_status_and_the_last_control_command(
    tmp_path, registry, posted, capsys
):
    register(registry)
    run("pause", tmp_path)
    capsys.readouterr()
    main(
        [
            "sessions",
            "list",
            "--registry-dir",
            str(tmp_path / "local"),
            "--portable-dir",
            str(tmp_path / "portable"),
        ]
    )
    out = capsys.readouterr().out
    assert "paused" in out
    assert "pause (cli)" in out


def test_list_json_carries_the_control_record(tmp_path, registry, posted, capsys):
    register(registry)
    run("pause", tmp_path)
    capsys.readouterr()
    main(
        [
            "sessions",
            "list",
            "--format",
            "json",
            "--registry-dir",
            str(tmp_path / "local"),
            "--portable-dir",
            str(tmp_path / "portable"),
        ]
    )
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["status"] == "paused"
    assert rows[0]["control"]["command"] == "pause"
