"""The closure keeps a terminal record before the checkout goes (issue-452).

Dispatcher-level tests: a real :class:`Dispatcher` and a real graph coupling
over a checkout under ``tmp_path`` (a ``git init`` with the work item's own
``origin``, because the coupling refuses a foreign checkout — issue-113 A6),
holding a real ``work-item-state.json``. Checkout removal is the one seam:
``_cleanup_workspace`` deletes the directory, so a record that was not read
*before* it would be missing.

Requirement: docs/specs/issue-452/bugfix.md R1
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import FakeTmux
from test_routing import REF, make_dispatcher, make_session, routed_issue_closed
from the_loop import archive
from the_loop.webhook.router import RoutedEvent

ITEM = "issue-15"

COMPLETED = {
    "currentNode": "complete",
    "phase": "complete",
    "nodes": {"complete": {"outcome": "pass", "exitedAt": "2026-10-02T22:29:41+00:00"}},
    "skips": {"brainstorming": {"via": "phase-selection", "by": "octocat"}},
    "pullRequests": [{"ref": "github:octo/repo#16", "state": "merged"}],
}
MID_FLIGHT = {"currentNode": "implementation", "nodes": {"implementation": {}}}


def _checkout(root: Path, state: dict) -> Path:
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "remote",
            "add",
            "origin",
            "https://github.com/octo/repo.git",
        ],
        check=True,
    )
    spec = root / "docs" / "specs" / ITEM
    (spec / "evidence").mkdir(parents=True)
    (spec / "evidence" / "verification.md").write_text("ok")
    (spec / "work-item-state.json").write_text(json.dumps({"workItem": ITEM, **state}))
    return root


def _removing_checkouts(dispatcher) -> list:
    """Make the close path delete the checkout, as `keepCheckoutOnClose: false` does."""
    removed = []

    def remove(session, payload):
        shutil.rmtree(session.cwd)
        removed.append(session.cwd)
        return True

    dispatcher._cleanup_workspace = remove
    return removed


def _closed(state_reason: str = "completed") -> RoutedEvent:
    event = routed_issue_closed()
    event.payload["issue"]["state_reason"] = state_reason
    return event


@pytest.fixture
def setup(tmp_path):
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    return registry, dispatcher


def test_the_closure_stamps_the_terminal_record_before_the_checkout_goes(
    tmp_path, setup
):
    """
    Feature: the closure keeps a durable terminal record
      Scenario: a completed work item's ticket closes
        Given a session whose checkout records a claimed `complete` node
        When the ticket closes and the close path removes the checkout
        Then the ended stamp says completed and carries the terminal record

    Requirement: docs/specs/issue-452/bugfix.md R1.1, R1.2, R1.7
    """
    registry, dispatcher = setup
    checkout = _checkout(tmp_path / "wt", COMPLETED)
    registry.register(make_session(cwd=str(checkout)))
    removed = _removing_checkouts(dispatcher)

    dispatcher.handle(_closed())
    dispatcher.stop()

    assert removed == [str(checkout.resolve())]
    assert not checkout.exists()
    ended = dispatcher.control_store.ended(REF)
    assert ended is not None
    assert ended["outcome"] == archive.COMPLETED
    terminal = ended["terminal"]
    assert (terminal["node"], terminal["completed"]) == ("complete", True)
    assert terminal["selections"]["skipped"] == ["brainstorming"]
    assert terminal["pullRequests"][0]["state"] == "merged"
    assert terminal["evidence"] == ["verification.md"]
    # The issue-329 facts are unchanged.
    assert (ended["state"], ended["kind"], ended["reason"]) == (
        "closed",
        "issue",
        "issue-closed",
    )


def test_a_not_planned_close_of_a_mid_flight_item_is_cancelled(tmp_path, setup):
    """R1.2 — the provider's `state_reason` tells a cancellation from a completion."""
    registry, dispatcher = setup
    registry.register(make_session(cwd=str(_checkout(tmp_path / "wt", MID_FLIGHT))))
    _removing_checkouts(dispatcher)

    dispatcher.handle(_closed("not_planned"))
    dispatcher.stop()

    ended = dispatcher.control_store.ended(REF)
    assert ended["outcome"] == archive.CANCELLED
    assert ended["terminal"]["node"] == "implementation"
    assert ended["terminal"]["completed"] is False


def test_a_completed_close_of_a_mid_flight_item_is_closed_externally(tmp_path, setup):
    """R1.3 — a ticket closed as completed is not a completed graph."""
    registry, dispatcher = setup
    registry.register(make_session(cwd=str(_checkout(tmp_path / "wt", MID_FLIGHT))))
    _removing_checkouts(dispatcher)

    dispatcher.handle(_closed("completed"))
    dispatcher.stop()

    assert dispatcher.control_store.ended(REF)["outcome"] == archive.CLOSED_EXTERNALLY


def test_a_tracked_item_with_no_live_session_reads_the_recorded_checkout(
    tmp_path, setup
):
    """R1.4 — a closed session record still names a checkout on disk."""
    registry, dispatcher = setup
    registry.register(make_session(cwd=str(_checkout(tmp_path / "wt", COMPLETED))))
    registry.close(REF)

    dispatcher.handle(_closed())
    dispatcher.stop()

    ended = dispatcher.control_store.ended(REF)
    assert ended["outcome"] == archive.COMPLETED
    assert ended["terminal"]["node"] == "complete"


def test_a_foreign_checkout_yields_no_record_and_never_completed(tmp_path, setup):
    """Fail closed — a checkout that is not the work item's own is not read."""
    registry, dispatcher = setup
    foreign = tmp_path / "foreign"
    spec = foreign / "docs" / "specs" / ITEM
    spec.mkdir(parents=True)
    (spec / "work-item-state.json").write_text(json.dumps(COMPLETED))
    registry.register(make_session(cwd=str(foreign)))

    dispatcher.handle(_closed())
    dispatcher.stop()

    ended = dispatcher.control_store.ended(REF)
    assert ended["outcome"] == archive.UNKNOWN
    assert "terminal" not in ended


def test_cleanup_backfills_a_stamp_that_has_no_terminal_record(tmp_path, setup):
    """
    Feature: the closure keeps a durable terminal record
      Scenario: cleanup of an item that closed before the change
        Given an ended stamp with no terminal record and a checkout still on disk
        When an authorized cleanup releases the item
        Then the terminal record is added before the checkout is removed

    Requirement: docs/specs/issue-452/bugfix.md R1.5
    """
    registry, dispatcher = setup
    checkout = _checkout(tmp_path / "wt", COMPLETED)
    registry.register(make_session(cwd=str(checkout)))
    registry.close(REF)
    dispatcher.control_store.record_ended(
        REF, {"state": "closed", "kind": "issue", "reason": "issue-closed"}
    )
    seen = []

    def remove(work_item):
        seen.append(dispatcher.control_store.ended(work_item).get("terminal"))
        shutil.rmtree(checkout)
        return True

    dispatcher._remove_checkout = remove

    dispatcher.cleanup_work_item(make_session().work_item, reason="test")

    assert seen and seen[0] is not None, "recorded before the checkout went"
    ended = dispatcher.control_store.ended(REF)
    assert ended["outcome"] == archive.COMPLETED
    assert ended["terminal"]["completed"] is True
    assert ended["reason"] == "issue-closed"  # the closure's own facts are kept


def test_cleanup_of_an_open_item_writes_no_stamp(tmp_path, setup):
    """Out of scope by design: cleanup of a work item that has not ended."""
    registry, dispatcher = setup
    registry.register(make_session(cwd=str(_checkout(tmp_path / "wt", COMPLETED))))
    dispatcher._remove_checkout = lambda work_item: True

    dispatcher.cleanup_work_item(make_session().work_item, reason="test")

    assert dispatcher.control_store.ended(REF) is None


# -- the critic's findings (review round 1) ---------------------------------------


def test_a_second_close_delivery_keeps_the_first_ones_record(tmp_path, setup):
    """
    Feature: the closure keeps a durable terminal record
      Scenario: the webhook and the poller both deliver the closure
        Given a completed work item whose first closure stamped its record and
              whose checkout normal cleanup then removed
        When the same closure arrives again under another delivery id
        Then the stamp keeps the terminal record and the completed outcome

    Requirement: docs/specs/issue-452/bugfix.md R1.1, R1.2
    """
    registry, dispatcher = setup
    registry.register(make_session(cwd=str(_checkout(tmp_path / "wt", COMPLETED))))
    _removing_checkouts(dispatcher)
    dispatcher.handle(_closed())
    again = _closed()
    again.delivery_id = "poll-close-github:octo/repo#15-closed"

    dispatcher.handle(again)
    dispatcher.stop()

    ended = dispatcher.control_store.ended(REF)
    assert ended["outcome"] == archive.COMPLETED
    assert ended["terminal"]["node"] == "complete"


def test_an_operator_close_during_the_endgame_hold_keeps_the_record(
    tmp_path, monkeypatch
):
    """
    Feature: the closure keeps a durable terminal record
      Scenario: an operator closes the session while its closure is held
        Given a closure held for a session at `complete` (issue-405)
        When the operator closes the session, removing its checkout
        And the sweeper later finishes the held closure
        Then the stamp carries the record read before the checkout went

    Requirement: docs/specs/issue-452/bugfix.md R1.1
    """
    from test_finish_grace import TARGET, StubLink, _context
    from the_loop.webhook.dispatcher import TmuxConfig

    registry, dispatcher = make_dispatcher(
        tmp_path, FakeTmux(), tmux_config=TmuxConfig(finish_grace_seconds=300.0)
    )

    class Link(StubLink):
        def terminal_record(self, work_item, cwd):
            exists = Path(cwd).is_dir()
            return {"node": "complete", "completed": True} if exists else None

    monkeypatch.setattr(dispatcher, "graphlink", Link(_context()))
    checkout = tmp_path / "wt"
    checkout.mkdir()
    session = make_session(cwd=str(checkout))
    session.tmux_target = TARGET
    registry.register(session)
    _removing_checkouts(dispatcher)
    dispatcher.handle(_closed())
    assert dispatcher.is_closing(REF)

    live = registry.find_by_work_item(REF)
    assert live is not None
    dispatcher.close_session(live)
    assert not checkout.exists()
    import time

    dispatcher.sweep_closing(now=time.monotonic() + 400.0)
    dispatcher.stop()

    ended = dispatcher.control_store.ended(REF)
    assert ended is not None and ended["outcome"] == archive.COMPLETED
    assert ended["terminal"]["completed"] is True


def test_a_coupling_that_raises_still_closes_and_stamps(tmp_path, setup):
    """A failed read never costs a closure."""
    registry, dispatcher = setup
    registry.register(make_session(cwd=str(_checkout(tmp_path / "wt", COMPLETED))))

    def boom(work_item, cwd):
        raise RuntimeError("coupling fault")

    dispatcher.graphlink.terminal_record = boom

    dispatcher.handle(_closed())
    dispatcher.stop()

    assert registry.find_by_work_item(REF) is None
    assert dispatcher.control_store.ended(REF)["outcome"] == archive.UNKNOWN


def test_cleanup_does_not_resurrect_a_stamp_a_reopen_cleared(tmp_path, setup):
    """A reopen while cleanup reads the checkout wins: the item stays open."""
    registry, dispatcher = setup
    registry.register(make_session(cwd=str(_checkout(tmp_path / "wt", COMPLETED))))
    registry.close(REF)
    dispatcher.control_store.record_ended(REF, {"state": "closed"})
    read = dispatcher._terminal_record

    def read_while_reopened(work_item, cwd=""):
        dispatcher.control_store.clear_ended(work_item)
        return read(work_item, cwd)

    dispatcher._terminal_record = read_while_reopened
    dispatcher._remove_checkout = lambda work_item: True

    dispatcher.cleanup_work_item(make_session().work_item, reason="test")

    assert dispatcher.control_store.ended(REF) is None


def test_a_duplicate_close_is_a_cancellation(tmp_path, setup):
    registry, dispatcher = setup
    registry.register(make_session(cwd=str(_checkout(tmp_path / "wt", MID_FLIGHT))))

    dispatcher.handle(_closed("duplicate"))
    dispatcher.stop()

    assert dispatcher.control_store.ended(REF)["outcome"] == archive.CANCELLED
