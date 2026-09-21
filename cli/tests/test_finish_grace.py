"""Integration: a session at its endgame finishes before the close path ends it
(issue-405 P2).

The real :class:`Dispatcher` handling a routed close event over the ``FakeTmux``
double and a stub graph coupling that answers the one question the close path
now asks — where does the work item's pointer stand? — so each scenario sets
the endgame explicitly. Spec: docs/specs/issue-405/testing-plan.md T3, T4.
"""

from __future__ import annotations

import time

from conftest import FakeTmux
from test_routing import (
    REF,
    make_dispatcher,
    make_session,
    routed_issue_closed,
    wait_until,
)
from the_loop import eventlog
from the_loop.graphlink import GraphContext
from the_loop.webhook.dispatcher import TmuxConfig
from the_loop.webhook.router import extract_work_items
from the_loop.webhook.dispatcher import RoutedEvent

TARGET = "loop-octo-repo-15"


def _context(node="complete", status="in-progress", terminal=True, merged=False):
    return GraphContext(
        current_node=node,
        phase=node,
        status=status,
        reason="",
        messages=(),
        next_command="finish-tasks",
        actor="agent",
        terminal=terminal,
        delivered_by_merge=merged,
    )


class StubLink:
    """The graph coupling as the close path sees it: one context per read, the
    write hooks the close path calls recorded and otherwise inert."""

    def __init__(self, context):
        self.context_value = context
        self.calls = []

    def context(self, work_item, cwd):
        self.calls.append(("context", work_item.ref))
        return self.context_value

    def on_close(self, work_item, cwd):
        self.calls.append(("close", work_item.ref))

    def on_cleanup(self, work_item, cwd, reason=""):
        self.calls.append(("cleanup", work_item.ref))

    def on_pr_state(self, *args, **kwargs):
        pass

    def on_pr_close(self, *args, **kwargs):
        pass


def _setup(tmp_path, monkeypatch, context, grace=300.0):
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(
        tmp_path,
        tmux,
        tmux_config=TmuxConfig(finish_grace_seconds=grace),
        authorized_users=["octocat"],
    )
    link = StubLink(context)
    monkeypatch.setattr(dispatcher, "graphlink", link)
    session = make_session(cwd=str(tmp_path))
    session.tmux_target = TARGET
    registry.register(session)
    emitted = []
    monkeypatch.setattr(
        eventlog, "emit", lambda event, level="info", **f: emitted.append((event, f))
    )
    return tmux, registry, dispatcher, link, emitted


def _closed(delivery="ic-1"):
    routed = routed_issue_closed(delivery=delivery)
    routed.payload["sender"] = {"login": "octocat"}
    return routed


def _reopened(delivery="ir-1"):
    payload = {
        "action": "reopened",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15},
        "sender": {"login": "octocat"},
    }
    return RoutedEvent(
        event="issues",
        action="reopened",
        delivery_id=delivery,
        work_items=extract_work_items("issues", payload),
        payload=payload,
    )


def _events(emitted, name):
    return [fields for event, fields in emitted if event == name]


# -- R2.1: the closure is held ---------------------------------------------------------


def test_a_closure_at_the_terminal_node_is_held_and_the_harness_kept_running(
    tmp_path, monkeypatch
):
    """
    Feature: a session at its endgame finishes before the close path ends it
      Scenario: the issue closes while the session is at its terminal node
        Given a live session whose work item's pointer stands on `complete`,
              its exit not yet recorded
        When the issue closes upstream (a merge's `Closes #N`)
        Then the closure is held: the record stays live, the harness is not ended,
             the checkout and the stamp are untouched
        And `session.closing` records the reason, the node and the grace

    Requirement: docs/specs/issue-405/bugfix.md R2.1 (P2)
    """
    tmux, registry, dispatcher, link, emitted = _setup(
        tmp_path, monkeypatch, _context()
    )
    dispatcher.handle(_closed())
    dispatcher.stop()

    assert registry.find_by_work_item(REF) is not None, "still live"
    assert tmux.terminated == [] and tmux.kills == []
    assert dispatcher.control_store.ended(REF) is None
    assert dispatcher.is_closing(REF)
    (closing,) = _events(emitted, "session.closing")
    assert closing["work_item"] == REF and closing["reason"] == "issue-closed"
    assert closing["node"] == "complete" and closing["grace_seconds"] == 300.0
    assert _events(emitted, "session.autoclosed") == []
    assert ("cleanup", REF) not in link.calls


# -- R2.2: the claim, or the deadline, finishes it ------------------------------------


def test_the_completion_claim_ends_the_grace_early(tmp_path, monkeypatch):
    """
    Feature: a session at its endgame finishes before the close path ends it
      Scenario: the session claims `graph complete` during the grace
        Given a held closure
        When the work item's state records the terminal node as exited
        Then the next sweep closes the session exactly as an immediate close does
        And `session.autoclosed` says `finished: true` with the seconds waited

    Requirement: docs/specs/issue-405/bugfix.md R2.2 (P2)
    """
    tmux, registry, dispatcher, link, emitted = _setup(
        tmp_path, monkeypatch, _context()
    )
    dispatcher.handle(_closed())
    assert dispatcher.sweep_closing() == 1, "still held: nothing claimed, no deadline"
    assert tmux.terminated == []

    link.context_value = _context(status="complete")
    assert dispatcher.sweep_closing() == 0
    dispatcher.stop()

    assert registry.find_by_work_item(REF) is None
    assert set(tmux.terminated) == {TARGET}
    assert dispatcher.control_store.ended(REF) is not None
    (closed,) = _events(emitted, "session.autoclosed")
    assert closed["finished"] is True and closed["waited_seconds"] >= 0
    assert closed["reason"] == "issue-closed"
    assert ("cleanup", REF) in link.calls
    assert not dispatcher.is_closing(REF)


def test_the_grace_running_out_ends_it_regardless(tmp_path, monkeypatch):
    """R2.2: the deadline closes a session that never claimed — bounded."""
    tmux, registry, dispatcher, link, emitted = _setup(
        tmp_path, monkeypatch, _context(), grace=120.0
    )
    dispatcher.handle(_closed())
    assert dispatcher.sweep_closing(now=time.monotonic() + 119.0) == 1
    assert dispatcher.sweep_closing(now=time.monotonic() + 121.0) == 0
    dispatcher.stop()

    assert registry.find_by_work_item(REF) is None
    assert set(tmux.terminated) == {TARGET}
    (closed,) = _events(emitted, "session.autoclosed")
    assert closed["finished"] is False and closed["waited_seconds"] >= 120


def test_the_sweeper_thread_finishes_a_held_closure_on_its_own(tmp_path, monkeypatch):
    """R2.1, R2.2: neither daemon has to call the sweep — the dispatcher's own
    thread does, at its interval, and exits once nothing is held."""
    tmux, registry, dispatcher, link, emitted = _setup(
        tmp_path, monkeypatch, _context()
    )
    dispatcher.close_sweep_interval_seconds = 0.02
    dispatcher.handle(_closed())
    assert registry.find_by_work_item(REF) is not None
    link.context_value = _context(status="complete")
    assert wait_until(lambda: registry.find_by_work_item(REF) is None)
    dispatcher.stop()
    assert set(tmux.terminated) == {TARGET}
    assert _events(emitted, "session.autoclosed")[0]["finished"] is True


# -- R2.3: everything else closes at once ---------------------------------------------


def test_a_pointer_off_the_terminal_node_closes_at_once(tmp_path, monkeypatch):
    """
    Feature: a session at its endgame finishes before the close path ends it
      Scenario: the issue is closed as wontfix mid-implementation
        Given a live session whose pointer stands on `implementation`
        When the issue closes
        Then the session is closed immediately, as before

    Requirement: docs/specs/issue-405/bugfix.md R2.3 (P2)
    """
    tmux, registry, dispatcher, link, emitted = _setup(
        tmp_path, monkeypatch, _context(node="implementation", terminal=False)
    )
    dispatcher.handle(_closed())
    dispatcher.stop()
    assert registry.find_by_work_item(REF) is None
    assert set(tmux.terminated) == {TARGET}
    assert _events(emitted, "session.closing") == []
    (closed,) = _events(emitted, "session.autoclosed")
    assert "finished" not in closed and "waited_seconds" not in closed


def test_a_terminal_node_already_exited_closes_at_once(tmp_path, monkeypatch):
    """R2.3: a session that already claimed completion has nothing to finish."""
    tmux, registry, dispatcher, link, emitted = _setup(
        tmp_path, monkeypatch, _context(status="complete")
    )
    dispatcher.handle(_closed())
    dispatcher.stop()
    assert registry.find_by_work_item(REF) is None
    assert _events(emitted, "session.closing") == []


def test_a_dead_pane_an_unreadable_graph_or_no_grace_close_at_once(
    tmp_path, monkeypatch
):
    """R2.3, T9: every doubt answers *close now* — today's behaviour."""
    cases = (
        ("dead pane", _context(), 300.0),
        ("unreadable graph", None, 300.0),
        ("no grace", _context(), 0.0),
    )
    for name, context, grace in cases:
        tmux, registry, dispatcher, link, emitted = _setup(
            tmp_path / name.replace(" ", "-"), monkeypatch, context, grace
        )
        if name == "dead pane":
            monkeypatch.setattr(tmux, "has_live_session", lambda target: False)
        dispatcher.handle(_closed())
        dispatcher.stop()
        assert registry.find_by_work_item(REF) is None, name
        assert set(tmux.terminated) == {TARGET}, name
        assert _events(emitted, "session.closing") == [], name


# -- R2.4: reopen and duplicates ----------------------------------------------------


def test_a_reopen_during_the_grace_cancels_the_held_closure(tmp_path, monkeypatch):
    """
    Feature: a session at its endgame finishes before the close path ends it
      Scenario: the issue is reopened during the grace
        Given a held closure
        When an issues `reopened` event arrives
        Then the held closure is cancelled and the session stays live
        And `session.closing_cancelled` records it

    Requirement: docs/specs/issue-405/bugfix.md R2.4 (P2)
    """
    tmux, registry, dispatcher, link, emitted = _setup(
        tmp_path, monkeypatch, _context()
    )
    dispatcher.handle(_closed())
    assert dispatcher.is_closing(REF)
    dispatcher.handle(_reopened())
    assert wait_until(lambda: len(tmux.delivers) == 1)
    dispatcher.stop()
    assert not dispatcher.is_closing(REF)
    assert registry.find_by_work_item(REF) is not None
    assert tmux.terminated == []
    (cancelled,) = _events(emitted, "session.closing_cancelled")
    assert cancelled["work_item"] == REF
    assert dispatcher.sweep_closing(now=time.monotonic() + 1000) == 0
    assert registry.find_by_work_item(REF) is not None, "cancelled means cancelled"


def test_a_second_close_during_the_grace_is_a_noop(tmp_path, monkeypatch):
    """R2.4: the poller re-detecting the same closure holds nothing twice."""
    tmux, registry, dispatcher, link, emitted = _setup(
        tmp_path, monkeypatch, _context()
    )
    dispatcher.handle(_closed("ic-1"))
    dispatcher.handle(_closed("ic-2"))
    dispatcher.stop()
    assert len(_events(emitted, "session.closing")) == 1
    assert dispatcher.is_closing(REF) and tmux.terminated == []


# -- R2.5: the merged flag ------------------------------------------------------------


def test_an_issue_closure_says_merged_when_its_pull_request_merged(
    tmp_path, monkeypatch
):
    """
    Feature: a session at its endgame finishes before the close path ends it
      Scenario: the issue closes after the daemon recorded its PR as merged
        Given the work item's state records a merged pull request
        When the issue closes (off the terminal node, so at once)
        Then `session.autoclosed` says `merged: true`
        And the closure stamp still says the issue was `closed`

    Requirement: docs/specs/issue-405/bugfix.md R2.5 (P2)
    """
    tmux, registry, dispatcher, link, emitted = _setup(
        tmp_path,
        monkeypatch,
        _context(node="implementation", terminal=False, merged=True),
    )
    dispatcher.handle(_closed())
    dispatcher.stop()
    (closed,) = _events(emitted, "session.autoclosed")
    assert closed["merged"] is True
    ended = dispatcher.control_store.ended(REF)
    assert ended is not None and ended["state"] == "closed"


def test_an_issue_closure_with_no_merged_pull_request_says_so(tmp_path, monkeypatch):
    tmux, registry, dispatcher, link, emitted = _setup(
        tmp_path, monkeypatch, _context(node="implementation", terminal=False)
    )
    dispatcher.handle(_closed())
    dispatcher.stop()
    assert _events(emitted, "session.autoclosed")[0]["merged"] is False


# -- T4: the knob ---------------------------------------------------------------------


def test_finish_grace_seconds_is_read_from_the_tmux_section():
    assert TmuxConfig().finish_grace_seconds == 300.0
    assert TmuxConfig.from_mapping({}).finish_grace_seconds == 300.0
    assert (
        TmuxConfig.from_mapping({"finishGraceSeconds": 12}).finish_grace_seconds == 12.0
    )
    assert (
        TmuxConfig.from_mapping({"finishGraceSeconds": 0}).finish_grace_seconds == 0.0
    )
