"""Unit tests for the derived state of a session (issue-551, R4, R6, R7).

One test per arrow of the state diagram in docs/specs/issue-551/design.md
§ "The state of a session", then the budget, the asks, and the two things every
caller leans on: the derivation never acts twice, and it never raises.
"""

import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from the_loop.core import sessionstate
from the_loop.core.sessionstate import Due, derive
from the_loop.watchconfig import AsksConfig, WatchdogConfig

REF = "github:acme/widgets#7"
T0 = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)

#: Short numbers so that a scenario reads in minutes.
WATCHDOG = WatchdogConfig(idle_seconds=600, max_nudges=2, max_wait_seconds=3600)
ASKS = AsksConfig(reminder_seconds=7200)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def stamp(minutes: float) -> str:
    """The event log's own timestamp form (``eventlog._utcnow``)."""
    return at(minutes).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def ev(minutes: float, event: str, **fields) -> dict:
    """One record as ``EventLog.emit`` stores it."""
    return {
        "ts": stamp(minutes),
        "source": "test",
        "event": event,
        "level": "info",
        "pid": 1,
        "work_item": REF,
        **fields,
    }


def started(minutes: float, node: str = "implementation") -> dict:
    return ev(minutes, "session.turn_started", node=node)


def ended(minutes: float, reason: str, node: str = "implementation") -> dict:
    return ev(
        minutes, "session.turn_ended", node=node, node_status="block", reason=reason
    )


def state_at(events, minutes: float, watchdog=WATCHDOG, asks=ASKS):
    return derive(events, now=at(minutes), watchdog=watchdog, asks=asks, work_item=REF)


def acts(state) -> list:
    return [due.act for due in state.due]


def stall_id(minutes: float) -> str:
    return f"{REF}@{stamp(minutes)}"


# -- [*] → not watched, [*] → Working --------------------------------------------


def test_legacy_log_without_turn_records_is_not_watched():
    """
    Feature: a session the hooks never reported is left alone
      Scenario: an event log written before issue-551
        Given spawn, dispatch and graph records, and no turn record
        When the state is derived, however long ago they were written
        Then the session is not watched and nothing is owed

    Requirement: docs/specs/issue-551/requirements.md R4.6; design § Fail-closed
    """
    log = [
        ev(0, "session.spawned"),
        ev(1, "dispatch.succeeded", via="tmux"),
        ev(2, "graph.advanced", node="design", to="implementation"),
    ]
    state = state_at(log, 60 * 24)
    assert state.state == "not-watched"
    assert state.due == ()
    assert (state.since, state.idle_since, state.stall_id) == (None, None, None)


def test_legacy_empty_log_is_not_watched():
    assert state_at([], 0).state == "not-watched"
    assert state_at([], 0).due == ()


def test_legacy_stall_records_alone_never_owe_a_nudge():
    """A nudge needs a turn's end to count from; a stray stall record is not one."""
    log = [ev(0, "session.nudged", stall_id=stall_id(0), node="implementation")]
    state = state_at(log, 600)
    assert state.state == "not-watched"
    assert state.due == ()


def test_turn_started_means_working():
    """
    Feature: the watcher never touches a working session
      Scenario: the last turn record is a start
        Given a turn that started three hours ago and has not ended
        When the state is derived
        Then the session is working since the start, and nothing is owed

    Requirement: docs/specs/issue-551/requirements.md R4.6
    """
    state = state_at([started(0, node="design")], 180)
    assert (state.state, state.node, state.since) == ("working", "design", stamp(0))
    assert state.due == ()
    assert state.idle_since is None


# -- Working → Waiting -----------------------------------------------------------


@pytest.mark.parametrize("reason", ["human-gate", "complete", "graph-wait"])
def test_a_wait_on_a_person_or_the_graph_has_no_time_limit(reason):
    """Requirement: R4.6 — design: "Waiting on a human gate … has no time limit"."""
    state = state_at([started(0), ended(5, reason)], 60 * 24 * 7)
    assert (state.state, state.reason, state.since) == ("waiting", reason, stamp(5))
    assert state.until is None
    assert state.due == ()


def test_an_open_ask_waits_without_limit():
    log = [
        started(0),
        ev(4, "session.awaiting_input", question="Which region?", ask_id="a1"),
        ended(5, "open-ask"),
    ]
    state = state_at(log, 100)
    assert (state.state, state.reason, state.until) == ("waiting", "open-ask", None)
    assert state.open_ask is not None
    assert (state.open_ask.ask_id, state.open_ask.question) == ("a1", "Which region?")
    assert state.open_ask.asked_at == stamp(4)


def test_a_declared_wait_waits_until_its_end_time():
    log = [
        started(0),
        ev(4, "session.wait_declared", condition="CI on #552", until=stamp(34)),
        ended(5, "declared-wait"),
    ]
    state = state_at(log, 30)
    assert (state.state, state.until) == ("waiting", stamp(34))
    assert state.declared_wait is not None
    assert state.declared_wait.condition == "CI on #552"
    assert state.declared_wait.until == stamp(34)
    assert state.due == ()


def test_background_work_waits_until_the_wait_limit():
    state = state_at([started(0), ended(5, "background-work")], 60)
    assert (state.state, state.until) == ("waiting", stamp(65))
    assert state.due == ()


# -- Working → Idle --------------------------------------------------------------


@pytest.mark.parametrize(
    "reason", ["exit-met", "gate-gave-up", "inconclusive", "a-reason-from-the-future"]
)
def test_a_turn_that_ends_with_work_owed_is_idle_from_its_end(reason):
    """An unknown reason is idle too: a newer writer must not hide a stall."""
    state = state_at([started(0), ended(5, reason)], 9)
    assert (state.state, state.reason) == ("idle", reason)
    assert (state.since, state.idle_since) == (stamp(5), stamp(5))
    assert state.stall_id is None
    assert state.due == ()


def test_a_turn_end_without_a_reason_is_idle():
    record = ev(5, "session.turn_ended", node="implementation")
    assert state_at([started(0), record], 9).state == "idle"


# -- Waiting → Idle: the wait lapses ---------------------------------------------


def test_an_expired_declared_wait_is_idle_from_its_end_time():
    """Requirement: R4.8 — idle from the moment the wait expired, not the turn's end."""
    log = [
        started(0),
        ev(4, "session.wait_declared", condition="CI", until=stamp(34)),
        ended(5, "declared-wait"),
    ]
    state = state_at(log, 40)
    assert (state.state, state.idle_since, state.since) == (
        "idle",
        stamp(34),
        stamp(34),
    )
    assert state.declared_wait is None
    assert state_at(log, 44).stall_id == f"{REF}@{stamp(34)}"


def test_a_declared_wait_is_never_believed_past_the_wait_limit():
    """Abuse case 4: a record that states a longer wait still ends at the limit."""
    log = [
        started(0),
        ev(4, "session.wait_declared", condition="CI", until=stamp(60 * 24)),
        ended(5, "declared-wait"),
    ]
    assert state_at(log, 63).state == "waiting"
    state = state_at(log, 65)
    assert (state.state, state.idle_since) == ("idle", stamp(64))


@pytest.mark.parametrize("until", [None, "", "soon", 17])
def test_a_declared_wait_without_a_readable_end_is_idle_from_the_turns_end(until):
    log = [
        started(0),
        ev(4, "session.wait_declared", condition="CI", until=until),
        ended(5, "declared-wait"),
    ]
    state = state_at(log, 9)
    assert (state.state, state.idle_since) == ("idle", stamp(5))


def test_a_wait_declared_in_an_earlier_turn_does_not_cover_this_one():
    """Design: "A declared wait covers one stop"."""
    log = [
        started(0),
        ev(1, "session.wait_declared", condition="CI", until=stamp(50)),
        ended(2, "declared-wait"),
        started(3),
        ended(5, "declared-wait"),
    ]
    state = state_at(log, 9)
    assert (state.state, state.idle_since) == ("idle", stamp(5))


def test_background_work_past_the_wait_limit_is_idle_from_the_limit():
    state = state_at([started(0), ended(5, "background-work")], 70)
    assert (state.state, state.idle_since) == ("idle", stamp(65))


@pytest.mark.parametrize(
    "closer",
    ["session.reply_sent", "session.ask_answered", "session.ask_default_taken"],
)
def test_a_closed_ask_with_no_turn_since_is_idle_from_the_close(closer):
    log = [
        started(0),
        ev(4, "session.awaiting_input", question="Which?", ask_id="a1"),
        ended(5, "open-ask"),
        ev(40, closer, ask_id="a1"),
    ]
    state = state_at(log, 45)
    assert (state.state, state.idle_since) == ("idle", stamp(40))
    assert state.open_ask is None


def test_an_open_ask_reason_with_no_ask_on_record_is_idle():
    state = state_at([started(0), ended(5, "open-ask")], 9)
    assert (state.state, state.idle_since) == ("idle", stamp(5))


# -- Idle → Stalled → Notified ---------------------------------------------------


def test_idle_past_the_threshold_is_stalled_and_owes_the_first_nudge():
    """Requirement: R4.1."""
    log = [started(0), ended(5, "exit-met")]
    assert state_at(log, 14.9).state == "idle"
    state = state_at(log, 15)
    assert state.state == "stalled"
    assert state.stall_id == stall_id(5)
    assert state.since == stamp(5)
    assert (state.nudges_spent, state.notified) == (0, False)
    assert state.due == (Due("nudge", stall_id=stall_id(5)),)


def test_a_second_nudge_is_owed_one_threshold_after_the_first():
    """Requirement: R4.3 — the first nudge was delivered and no turn started."""
    log = [
        started(0),
        ended(5, "exit-met"),
        ev(15, "session.nudged", stall_id=stall_id(5), node="implementation", nudge=1),
    ]
    assert state_at(log, 24).due == ()
    state = state_at(log, 25)
    assert state.nudges_spent == 1
    assert acts(state) == ["nudge"]


def test_the_notice_is_owed_once_the_nudges_are_spent():
    """Requirement: R4.4."""
    log = [
        started(0),
        ended(5, "exit-met"),
        ev(15, "session.nudged", stall_id=stall_id(5), nudge=1),
        ev(25, "session.nudged", stall_id=stall_id(5), nudge=2),
    ]
    assert state_at(log, 34).due == ()
    state = state_at(log, 35)
    assert (state.nudges_spent, state.notified) == (2, False)
    assert state.due == (Due("notify", stall_id=stall_id(5)),)

    log.append(ev(35, "session.stalled", stall_id=stall_id(5), idle_since=stamp(5)))
    later = state_at(log, 60 * 24)
    assert (later.state, later.notified) == ("stalled", True)
    assert later.due == ()


def test_a_nudge_and_the_record_that_its_paste_failed_are_one_nudge():
    """Requirement: R4.3 — one attempt is one unit of the budget. The watcher
    records a nudge before it pastes, and a second time when the paste failed."""
    nudge = dict(stall_id=stall_id(5), node="implementation", nudge=1)
    log = [
        started(0),
        ended(5, "exit-met"),
        ev(15, "session.nudged", **nudge),
        ev(15.01, "session.nudged", **nudge, delivered=False),
    ]
    assert state_at(log, 24).due == ()
    state = state_at(log, 25)
    assert state.nudges_spent == 1 and acts(state) == ["nudge"]


def test_a_lone_failed_nudge_record_still_spends_the_budget():
    """An older log holds one record per failed nudge, with nothing before it."""
    log = [
        started(0),
        ended(5, "exit-met"),
        ev(15, "session.nudged", stall_id=stall_id(5), nudge=1, delivered=False),
        ev(25, "session.nudged", stall_id=stall_id(5), nudge=2, delivered=False),
    ]
    assert state_at(log, 26).nudges_spent == 2


def test_no_nudges_configured_goes_straight_to_the_notice():
    watchdog = WatchdogConfig(idle_seconds=600, max_nudges=0)
    state = state_at([started(0), ended(5, "exit-met")], 15, watchdog=watchdog)
    assert acts(state) == ["notify"]


def test_a_stall_that_cannot_name_its_node_gets_the_notice_without_a_nudge():
    """Design § Fail-closed: the nudge names the node, so without one it is not sent."""
    log = [
        ev(0, "session.turn_started"),
        ev(5, "session.turn_ended", reason="exit-met"),
    ]
    assert acts(state_at(log, 15)) == ["notify"]


def test_a_turn_that_ended_with_no_readable_position_owes_nothing():
    """Requirement: R4.6 — `inconclusive` with no node is the-loop not knowing
    where the work item stands. That is not evidence of work owed."""
    log = [
        ev(0, "session.turn_started"),
        ev(5, "session.turn_ended", reason="inconclusive"),
    ]
    state = state_at(log, 60 * 24)
    assert (state.state, state.reason, state.node) == ("idle", "inconclusive", "")
    assert (state.due, state.stall_id) == ((), None)
    assert state.idle_since == stamp(5)
    assert "cannot tell" in sessionstate.session_view(state)["detail"]


def test_an_inconclusive_end_that_names_its_node_is_still_watched():
    log = [started(0), ended(5, "inconclusive")]
    assert acts(state_at(log, 15)) == ["nudge"]


def test_a_watchdog_switched_off_shows_the_stall_and_owes_nothing():
    """Requirement: R4.12."""
    watchdog = WatchdogConfig(enabled=False, idle_seconds=600)
    state = state_at([started(0), ended(5, "exit-met")], 60, watchdog=watchdog)
    assert state.state == "stalled"
    assert state.due == ()


# -- the pointer moved after the turn ended --------------------------------------


def moved(minutes: float, to: str, node: str = "design-approval") -> dict:
    return ev(minutes, "graph.advanced", node=node, to=to, outcome="approved")


def test_a_gate_answered_with_no_turn_after_it_is_idle_at_the_new_node():
    """Requirement: R4.1, R4.8 — a person approved the gate, the pointer moved
    to an agent's node and the assignment started no turn. The session no
    longer waits on a person; it is idle from the advance."""
    log = [
        started(0, "design-approval"),
        ended(5, "human-gate", "design-approval"),
        moved(8, "implementation"),
    ]
    state = state_at(log, 9)
    assert (state.state, state.node) == ("idle", "implementation")
    assert (state.since, state.idle_since) == (stamp(8), stamp(8))
    assert state.reason == "pointer-moved"
    late = state_at(log, 18)
    assert late.due == (Due("nudge", stall_id=stall_id(8)),)
    assert state_at(log + [started(8.5, "implementation")], 30).state == "working"


def test_a_wait_the_graph_reported_ends_when_the_pointer_moves():
    log = [started(0), ended(5, "graph-wait"), moved(8, "verification")]
    assert acts(state_at(log, 18)) == ["nudge"]
    assert acts(state_at([started(0), ended(5, "graph-wait")], 60 * 24)) == []


def test_a_pointer_moved_onto_a_human_gate_still_waits_for_the_person():
    """A human node is parked as it is entered, which is how the log says
    whose node it is."""
    log = [
        started(0),
        ended(5, "graph-wait"),
        ev(7.9, "graph.parked", node="design-approval", via="entry"),
        moved(8, "design-approval", node="design"),
    ]
    state = state_at(log, 60 * 24)
    assert (state.state, state.reason) == ("waiting", "human-gate")
    assert (state.node, state.since, state.due) == ("design-approval", stamp(8), ())
    # The gate is left again for an agent's node: the park no longer counts.
    log.append(moved(20, "implementation"))
    assert state_at(log, 31).state == "stalled"


def test_the_node_is_where_the_pointer_last_went():
    """Requirement: R4.2 — the nudge names the node the work item is on now,
    and a node the session never ended a turn on has no exit it could have
    met."""
    log = [started(0), ended(5, "exit-met"), moved(6, "verification")]
    state = state_at(log, 16)
    assert (state.node, state.reason) == ("verification", "pointer-moved")
    assert state.due == (Due("nudge", stall_id=stall_id(6)),)
    forced = [started(0), ended(5, "exit-met"), ev(6, "graph.forced", to="design")]
    assert state_at(forced, 16).node == "design"
    working = [started(0), moved(1, "verification")]
    assert state_at(working, 2).node == "verification"
    # A move before the turn record says nothing new.
    assert state_at([moved(-1, "x"), started(0), ended(5, "exit-met")], 16).node == (
        "implementation"
    )


def test_a_wait_with_a_limit_outlives_a_pointer_move():
    log = [
        started(0),
        ev(1, "session.wait_declared", condition="CI", until=stamp(40)),
        ended(2, "declared-wait"),
        moved(3, "verification"),
    ]
    state = state_at(log, 20)
    assert (state.state, state.reason, state.node) == (
        "waiting",
        "declared-wait",
        "verification",
    )


def test_an_unknown_position_stays_unknown_when_a_pointer_moves():
    log = [
        ev(0, "session.turn_started"),
        ev(5, "session.turn_ended", reason="inconclusive"),
        moved(8, "implementation"),
    ]
    state = state_at(log, 60 * 24)
    assert (state.state, state.node, state.due) == ("idle", "", ())


# -- the budget is the node visit's ----------------------------------------------


def one_empty_turn_per_nudge():
    """Abuse case 5: each nudge is answered with a turn that does nothing."""
    return [
        started(0),
        ended(5, "exit-met"),
        ev(15, "session.nudged", stall_id=stall_id(5), nudge=1),
        started(15.1),
        ended(16, "exit-met"),
        ev(26, "session.nudged", stall_id=stall_id(16), nudge=2),
        started(26.1),
        ended(27, "exit-met"),
    ]


def test_a_new_idle_period_on_the_same_node_inherits_what_was_spent():
    log = one_empty_turn_per_nudge()
    assert state_at(log, 36).state == "idle"
    state = state_at(log, 37)
    assert (state.state, state.nudges_spent) == ("stalled", 2)
    assert state.stall_id == stall_id(27)
    assert "nudge" not in acts(state)
    assert Due("notify", stall_id=stall_id(27)) in state.due

    log += [
        ev(37, "session.stalled", stall_id=stall_id(27), idle_since=stamp(27)),
        started(50),
        ended(51, "exit-met"),
    ]
    spent = state_at(log, 60 * 24)
    assert spent.notified is True
    assert [a for a in acts(spent) if a in ("nudge", "notify")] == []


@pytest.mark.parametrize(
    "reset",
    [
        ev(28, "graph.advanced", node="implementation", to="verification"),
        ev(28, "graph.forced", to="verification"),
        ev(28, "session.reply_sent", actor="rohith"),
        ev(28, "session.ask_answered", ask_id="a1", actor="rohith"),
        # A person's comment the dispatcher delivered: the record names them.
        ev(28, "dispatch.succeeded", via="tmux", actor="rohith"),
    ],
    ids=lambda record: record["event"],
)
def test_the_budget_resets_when_the_pointer_moves_or_a_person_is_delivered(reset):
    log = one_empty_turn_per_nudge() + [reset, started(29), ended(30, "exit-met")]
    state = state_at(log, 40)
    assert (state.nudges_spent, state.notified) == (0, False)
    assert Due("nudge", stall_id=stall_id(30)) in state.due


def test_a_daemon_delivery_does_not_reset_the_budget():
    """`dispatch.succeeded` also records a CI event and the watcher's own paste."""
    log = one_empty_turn_per_nudge() + [
        ev(28, "dispatch.succeeded", via="tmux", gh_event="check_run"),
        ev(28, "dispatch.succeeded", via="tmux", actor=""),
        ev(28, "dispatch.succeeded", via="tmux", actor=None),
        ev(28, "graph.assignment_delivered"),
        started(29),
        ended(30, "exit-met"),
    ]
    state = state_at(log, 40)
    assert state.nudges_spent == 2
    assert "nudge" not in acts(state)


# -- Idle / Waiting / Stalled / Notified → Working -------------------------------


@pytest.mark.parametrize("reason", ["exit-met", "human-gate", "background-work"])
def test_turn_started_after_an_idle_or_waiting_turn_end_is_working(reason):
    state = state_at([started(0), ended(5, reason), started(8)], 300)
    assert (state.state, state.since) == ("working", stamp(8))
    assert state.due == ()


def test_turn_started_ends_a_nudged_stall():
    """Requirement: R4.5, R4.9 — only a turn's start ends a stall."""
    log = [
        started(0),
        ended(5, "exit-met"),
        ev(15, "session.nudged", stall_id=stall_id(5), nudge=1),
    ]
    assert "end-stall" not in acts(state_at(log, 16))
    log.append(started(17))
    state = state_at(log, 18)
    assert state.state == "working"
    assert state.due == (Due("end-stall", stall_id=stall_id(5), idle_seconds=720),)


def test_turn_started_ends_a_notified_stall_even_with_the_watchdog_off():
    """A stall made before the switch was turned off is still closed (R4.5)."""
    log = [
        started(0),
        ended(5, "exit-met"),
        ev(15, "session.stalled", stall_id=stall_id(5), idle_since=stamp(5)),
        started(41),
    ]
    off = WatchdogConfig(enabled=False)
    state = state_at(log, 42, watchdog=off)
    assert state.due == (Due("end-stall", stall_id=stall_id(5), idle_seconds=2160),)


def test_an_event_that_starts_no_turn_does_not_end_the_stall():
    """Requirement: R4.9; abuse case 2 — a refused comment starts no turn."""
    log = [
        started(0),
        ended(5, "exit-met"),
        ev(15, "session.nudged", stall_id=stall_id(5), nudge=1),
        ev(16, "dispatch.dropped", reason="unauthorized"),
        ev(17, "dispatch.succeeded", via="tmux"),
    ]
    state = state_at(log, 25)
    assert state.state == "stalled"
    assert state.stall_id == stall_id(5)
    assert acts(state) == ["nudge"]


def test_a_stall_is_ended_once():
    log = [
        started(0),
        ended(5, "exit-met"),
        ev(15, "session.nudged", stall_id=stall_id(5), nudge=1),
        started(17),
        ev(17.5, "session.stall_ended", stall_id=stall_id(5), idle_seconds=720),
    ]
    assert state_at(log, 18).due == ()


# -- asks ------------------------------------------------------------------------


def ask(minutes: float, **fields) -> dict:
    return ev(minutes, "session.awaiting_input", question="Move T5?", **fields)


def test_a_default_is_taken_at_its_time():
    """Requirement: R6.2."""
    log = [ask(0, ask_id="a1", default="Move it.", default_at=stamp(30))]
    early = state_at(log, 29)
    assert early.due == ()
    assert early.open_ask is not None
    assert (early.open_ask.default, early.open_ask.default_at) == (
        "Move it.",
        stamp(30),
    )
    assert state_at(log, 30).due == (Due("take-default", ask_id="a1"),)


def test_a_default_time_shows_as_the_end_of_an_ask_wait():
    log = [
        started(0),
        ask(1, ask_id="a1", default="Move it.", default_at=stamp(31)),
        ended(2, "open-ask"),
    ]
    assert state_at(log, 5).until == stamp(31)


@pytest.mark.parametrize(
    "fields",
    [
        {"default": "Move it."},
        {"default": "Move it.", "default_at": "in a while"},
        {"default": "Move it.", "default_at": 1700000000},
        {"default_at": stamp(30)},
        {"default": "", "default_at": stamp(30)},
    ],
)
def test_a_default_without_a_readable_time_is_never_taken(fields):
    """Design § Fail-closed. Such an ask is a question with no deadline."""
    log = [ask(0, ask_id="a1", **fields)]
    state = state_at(log, 60 * 24 * 30, asks=AsksConfig(reminder_seconds=0))
    assert state.due == ()
    assert state.open_ask is not None and state.open_ask.default_at is None


@pytest.mark.parametrize(
    "closer",
    ["session.reply_sent", "session.ask_answered", "session.ask_default_taken"],
)
def test_a_closed_ask_owes_no_default(closer):
    """Requirement: R6.3 — and a default is taken once."""
    log = [
        ask(0, ask_id="a1", default="Move it.", default_at=stamp(30)),
        ev(20, closer, ask_id="a1"),
    ]
    state = state_at(log, 60)
    assert state.open_ask is None
    assert state.due == ()


def test_a_closing_record_for_another_ask_leaves_this_one_open():
    log = [
        ask(0, ask_id="a1"),
        ev(5, "session.ask_default_taken", ask_id="a1"),
        ask(10, ask_id="a2", default="Yes.", default_at=stamp(40)),
        ev(11, "session.ask_default_taken", ask_id="a1"),
    ]
    state = state_at(log, 41)
    assert state.due == (Due("take-default", ask_id="a2"),)


def two_asks():
    """Ask A with a default due at minute 30, then ask B ten minutes later."""
    return [
        started(0),
        ask(1, ask_id="A", default="Move it.", default_at=stamp(30)),
        ask(10, ask_id="B"),
        ended(11, "open-ask"),
    ]


def test_every_open_ask_is_tracked_and_owed_its_own_act():
    """Requirement: R6.2, R6.7 — a second ask does not hide the first one's
    deadline."""
    log = two_asks()
    early = state_at(log, 29)
    assert [a.ask_id for a in early.open_asks] == ["A", "B"]
    assert early.open_ask is not None and early.open_ask.ask_id == "B"
    assert early.due == ()
    assert state_at(log, 31).due == (Due("take-default", ask_id="A"),)
    # Both are owed at once when both are late.
    assert state_at(log, 131).due == (
        Due("take-default", ask_id="A"),
        Due("remind", ask_id="B"),
    )


def test_a_default_taken_closes_only_its_own_ask():
    log = two_asks() + [ev(31, "session.ask_default_taken", ask_id="A")]
    state = state_at(log, 32)
    assert [a.ask_id for a in state.open_asks] == ["B"]
    assert (state.state, state.reason, state.until) == ("waiting", "open-ask", None)
    assert state.due == ()
    log.append(ev(131, "session.ask_reminded", ask_id="B"))
    assert state_at(log, 60 * 24).open_asks[0].reminded is True


@pytest.mark.parametrize(
    "answer",
    [
        ev(20, "session.reply_sent", actor="rohith"),
        ev(20, "session.ask_answered", ask_id="B", actor="rohith"),
        ev(20, "session.ask_answered", ask_id="A", actor="rohith"),
        ev(20, "session.ask_answered", actor="rohith"),
    ],
    ids=["reply", "answered-B", "answered-A", "answered-no-id"],
)
def test_a_persons_answer_closes_every_open_ask(answer):
    """Requirement: R6.3 — a person spoke, so no default is taken after it,
    whichever ask the record names."""
    state = state_at(two_asks() + [answer], 60 * 24)
    assert state.open_asks == () and state.open_ask is None
    # Nothing is owed for an ask; the session is idle from the answer on.
    assert acts(state) == ["nudge"]
    assert (state.state, state.idle_since) == ("stalled", stamp(20))


def test_a_default_taken_on_this_node_visit_is_spent():
    """Requirement: R6.2 — one default per visit to a node: a session cannot
    renew a timed ask for ever on the same node. The window is the nudge
    budget's: the pointer moving, or a person's event, opens a new one."""
    log = [started(0), ask(1, ask_id="A", default="Go.", default_at=stamp(30))]
    assert state_at(log, 40).default_spent is False
    log.append(ev(31, "session.ask_default_taken", ask_id="A"))
    assert state_at(log, 40).default_spent is True
    # Asking again does not renew it.
    log.append(ask(41, ask_id="B", default="Go.", default_at=stamp(80)))
    assert state_at(log, 50).default_spent is True
    for reset in (
        ev(60, "graph.advanced", node="implementation", to="verification"),
        ev(60, "session.reply_sent", actor="rohith"),
        ev(60, "dispatch.succeeded", via="tmux", actor="rohith"),
    ):
        assert state_at(log + [reset], 70).default_spent is False
    daemon = ev(60, "dispatch.succeeded", via="tmux", gh_event="check_run")
    assert state_at(log + [daemon], 70).default_spent is True


def test_legacy_ask_without_an_id_is_named_by_its_time_and_closed_by_a_reply():
    log = [ask(0)]
    state = state_at(log, 5)
    assert state.state == "not-watched"
    assert state.open_ask is not None and state.open_ask.ask_id == stamp(0)
    log.append(ev(6, "session.reply_sent", actor="rohith"))
    assert state_at(log, 7).open_ask is None


def test_legacy_ask_without_an_id_is_shown_and_owes_nothing():
    """Requirement: R6.10 — an ask recorded before asks had ids may have been
    answered on the ticket with nothing recording it. It is still listed, and
    the-loop neither reminds anyone of it nor takes a default for it."""
    plain = state_at([ask(0)], 60 * 24)
    assert plain.open_ask is not None and plain.open_ask.legacy is True
    assert plain.due == ()
    timed = state_at([ask(0, default="Yes.", default_at=stamp(30))], 60 * 24)
    assert timed.open_ask is not None and timed.open_ask.legacy is True
    assert timed.due == ()
    assert state_at([ask(0, ask_id="a1")], 5).open_ask.legacy is False


def test_a_reminder_is_owed_once_for_an_ask_without_a_default():
    """Requirement: R6.7."""
    log = [ask(0, ask_id="a1")]
    assert state_at(log, 119).due == ()
    assert state_at(log, 120).due == (Due("remind", ask_id="a1"),)
    log.append(ev(120, "session.ask_reminded", ask_id="a1"))
    state = state_at(log, 60 * 24)
    assert state.due == ()
    assert state.open_ask is not None and state.open_ask.reminded is True


def test_no_reminder_when_the_interval_is_zero_or_the_ask_has_a_deadline():
    assert (
        state_at([ask(0, ask_id="a1")], 600, asks=AsksConfig(reminder_seconds=0)).due
        == ()
    )
    log = [ask(0, ask_id="a1", default="Yes.", default_at=stamp(60 * 24))]
    assert state_at(log, 600).due == ()


def test_ask_acts_ignore_the_watchdog_switch_and_the_turn_state():
    log = [started(0), ask(1, ask_id="a1", default="Yes.", default_at=stamp(31))]
    off = WatchdogConfig(enabled=False)
    state = state_at(log, 31, watchdog=off)
    assert state.state == "working"
    assert state.due == (Due("take-default", ask_id="a1"),)


# -- what the stop check reads ---------------------------------------------------


def test_a_wait_declared_in_the_running_turn_covers_its_stop():
    log = [
        started(0),
        ev(4, "session.wait_declared", condition="CI on #552", until=stamp(34)),
    ]
    state = state_at(log, 5)
    assert state.state == "working"
    assert state.declared_wait is not None
    assert state.declared_wait.covers_stop is True
    assert (state.declared_wait.condition, state.declared_wait.until) == (
        "CI on #552",
        stamp(34),
    )
    # Past its end it excuses nothing.
    late = state_at(log, 35).declared_wait
    assert late is not None and late.covers_stop is False


def test_a_wait_already_spent_on_a_stop_covers_no_other():
    """Abuse case 4: a second stop on an old wait is refused."""
    log = [
        started(0),
        ev(4, "session.wait_declared", condition="CI", until=stamp(34)),
        ended(5, "declared-wait"),
    ]
    waiting = state_at(log, 6).declared_wait
    assert waiting is not None and waiting.covers_stop is False
    log.append(started(7))
    assert state_at(log, 8).declared_wait is None


# -- never twice, never a crash --------------------------------------------------


def _record_of(due: Due, minutes: float) -> dict:
    """The record the watcher writes after performing ``due``."""
    if due.act == "nudge":
        return ev(minutes, "session.nudged", stall_id=due.stall_id, nudge=1)
    if due.act == "notify":
        return ev(minutes, "session.stalled", stall_id=due.stall_id)
    if due.act == "end-stall":
        return ev(
            minutes,
            "session.stall_ended",
            stall_id=due.stall_id,
            idle_seconds=due.idle_seconds,
        )
    if due.act == "take-default":
        return ev(minutes, "session.ask_default_taken", ask_id=due.ask_id)
    assert due.act == "remind"
    return ev(minutes, "session.ask_reminded", ask_id=due.ask_id)


@pytest.mark.parametrize(
    "log,minutes",
    [
        ([started(0), ended(5, "exit-met")], 15),
        (
            [
                started(0),
                ended(5, "exit-met"),
                ev(15, "session.nudged", stall_id=stall_id(5)),
                ev(25, "session.nudged", stall_id=stall_id(5)),
            ],
            35,
        ),
        (
            [
                started(0),
                ended(5, "exit-met"),
                ev(15, "session.nudged", stall_id=stall_id(5)),
                started(16),
            ],
            17,
        ),
        ([ask(0, ask_id="a1", default="Yes.", default_at=stamp(30))], 30),
        ([ask(0, ask_id="a1")], 120),
    ],
    ids=["nudge", "notify", "end-stall", "take-default", "remind"],
)
def test_an_act_on_record_is_never_owed_again(log, minutes):
    """
    Feature: a restart repeats nothing
      Scenario: the watcher restarts right after it acted
        Given the record the watcher wrote for an act
        When the state is derived again at the same moment
        Then that act is not owed

    Requirement: docs/specs/issue-551/requirements.md R4.10, R6.10
    """
    first = state_at(log, minutes)
    assert len(first.due) == 1
    replayed = log + [_record_of(first.due[0], minutes)]
    assert state_at(replayed, minutes).due == ()
    assert state_at(replayed, minutes + 1).due == ()


def test_at_most_one_of_nudge_and_notice_is_owed_at_a_time():
    log = [started(0), ended(5, "exit-met")]
    for minutes in range(5, 200):
        state = state_at(log, minutes)
        stall_acts = [a for a in acts(state) if a in ("nudge", "notify")]
        assert len(stall_acts) <= 1
        log += [_record_of(due, minutes) for due in state.due]
    assert [r["event"] for r in log[2:]] == [
        "session.nudged",
        "session.nudged",
        "session.stalled",
    ]


@pytest.mark.parametrize(
    "junk",
    [
        None,
        "a line",
        17,
        [],
        {},
        {"event": "session.turn_started"},
        {"ts": None, "event": "session.turn_started", "work_item": REF},
        {"ts": 12, "event": "session.turn_ended", "reason": "exit-met"},
        {"ts": "yesterday", "event": "session.turn_started"},
        {"ts": stamp(1), "event": ["session.turn_started"]},
        {"ts": stamp(1)},
    ],
)
def test_a_malformed_record_is_skipped(junk):
    log = [started(0), junk, ended(5, "exit-met"), junk]
    state = state_at(log, 15)
    assert (state.state, state.idle_since) == ("stalled", stamp(5))


def test_wrongly_typed_fields_do_not_raise():
    log = [
        ev(0, "session.turn_started", node=["x"]),
        ev(1, "session.awaiting_input", question={"q": 1}, ask_id=7, default=3),
        ev(2, "session.wait_declared", condition=9, until=[]),
        ev(3, "session.turn_ended", node=4, reason={"r": 1}),
        ev(4, "session.nudged", stall_id=5, nudge="x"),
        ev(5, "session.stalled", stall_id=None, idle_since=3),
        ev(6, "session.stall_ended", stall_id={}),
        ev(7, "session.ask_reminded", ask_id=[]),
        ev(8, "session.nudged", stall_id="no-at-sign"),
        started(9),
    ]
    state = state_at(log, 10)
    assert state.state == "working"
    # A stall whose start cannot be read is still ended, with no duration.
    assert state.due == (Due("end-stall", stall_id="no-at-sign", idle_seconds=None),)


def test_a_naive_now_is_read_as_utc():
    log = [started(0), ended(5, "exit-met")]
    naive = at(15).replace(tzinfo=None)
    state = derive(log, now=naive, watchdog=WATCHDOG, asks=ASKS, work_item=REF)
    assert state.state == "stalled"


# -- the loader ------------------------------------------------------------------


def _write(path, records):
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")


def test_load_groups_the_records_that_matter_by_work_item(tmp_path):
    other = "github:acme/widgets#8"
    path = tmp_path / "events.jsonl"
    _write(
        path,
        [
            started(0),
            {**started(1), "work_item": other},
            ev(2, "dispatch.succeeded"),
            {"ts": stamp(3), "event": "receiver.started"},
            ended(4, "exit-met"),
            # Kept only when it names the person whose event it delivered.
            ev(5, "dispatch.succeeded", actor="rohith"),
        ],
    )
    with open(path, "a", encoding="utf-8") as handle:
        handle.write('{"ts": "torn line\n')
    grouped = sessionstate.load(path)
    assert set(grouped) == {REF, other}
    assert [r["event"] for r in grouped[REF]] == [
        "session.turn_started",
        "session.turn_ended",
        "dispatch.succeeded",
    ]
    assert state_at(grouped[REF], 20).state == "stalled"
    assert state_at(grouped.get("github:acme/widgets#9", []), 20).state == "not-watched"


def test_a_persons_event_on_a_pull_request_resets_that_sessions_budget(tmp_path):
    """Requirement: R4.3 — the delivery is logged under the work item with the
    pull request as its `endpoint`. The person spoke to the pull request's
    session, so that is the budget their event renews."""
    pull = "github:acme/widgets#12"
    spent = one_empty_turn_per_nudge()
    path = tmp_path / "events.jsonl"
    _write(
        path,
        spent
        + [{**record, "work_item": pull} for record in spent]
        + [ev(28, "dispatch.succeeded", via="tmux", actor="rohith", endpoint=pull)],
    )
    grouped = sessionstate.load(path)
    assert grouped[pull][-1]["event"] == "dispatch.succeeded"
    assert grouped[REF][-1]["event"] == "session.turn_ended"
    outer = state_at(grouped[REF], 40)
    inner = derive(
        grouped[pull], now=at(40), watchdog=WATCHDOG, asks=ASKS, work_item=pull
    )
    assert (outer.nudges_spent, inner.nudges_spent) == (2, 0)
    # The same record handed straight to the derivation is not the outer's.
    assert state_at(spent + grouped[pull][-1:], 40).nudges_spent == 2


def test_load_parses_no_line_of_a_type_it_does_not_read(tmp_path, monkeypatch):
    """Requirement: testing-plan T7 — most of a busy log is other subsystems'
    records. They are passed over as text; none is parsed."""
    path = tmp_path / "events.jsonl"
    kinds = ["comment.agent", "poller.cycle", "dispatch.succeeded", "graph.blocked"]
    _write(
        path,
        [ev(index / 60, kinds[index % 4], body="x" * 100) for index in range(50_000)],
    )
    parsed = []
    real = json.loads
    monkeypatch.setattr(
        json, "loads", lambda text, **kw: parsed.append(1) or real(text)
    )
    assert sessionstate.load(path) == {}
    assert parsed == []


def test_load_for_one_work_item_parses_only_its_lines(tmp_path, monkeypatch):
    other = "github:acme/widgets#70"
    path = tmp_path / "events.jsonl"
    _write(
        path,
        [started(0), ended(5, "exit-met")]
        + [{**started(index), "work_item": other} for index in range(100)]
        + [ev(6, "dispatch.succeeded", actor="rohith", work_item=other, endpoint=REF)],
    )
    parsed = []
    real = json.loads
    monkeypatch.setattr(
        json, "loads", lambda text, **kw: parsed.append(1) or real(text)
    )
    grouped = sessionstate.load(path, work_item=REF)
    assert set(grouped) == {REF} and len(parsed) == 3
    assert grouped[REF] == sessionstate.load(path)[REF]


def test_load_reads_a_log_written_with_spaces_and_survives_bad_bytes(tmp_path):
    path = tmp_path / "events.jsonl"
    with open(path, "wb") as handle:
        handle.write(json.dumps(started(0)).encode() + b"\n")
        handle.write(b'{"event": "session.turn_ended", \xff\xfe broken\n')
        handle.write(b'["session.turn_ended"]\n')
        handle.write(json.dumps(ended(5, "exit-met")).encode() + b"\n")
    assert [r["event"] for r in sessionstate.load(path)[REF]] == [
        "session.turn_started",
        "session.turn_ended",
    ]


def test_load_of_a_missing_log_is_empty(tmp_path):
    assert sessionstate.load(tmp_path / "absent.jsonl") == {}


def test_cycle_budget_fifty_sessions_over_a_large_log(tmp_path):
    """
    Feature: the watcher's cycle stays cheap
      Scenario: one tick over a busy machine
        Given 50 work items and an event log of 50,000 lines
        When one cycle loads the log once and derives every session
        Then it finishes within 2 seconds

    Requirement: docs/specs/issue-551/testing-plan.md T7
    """
    refs = [f"github:acme/widgets#{n}" for n in range(50)]
    kinds = [
        ("session.turn_started", {"node": "implementation"}),
        ("dispatch.succeeded", {"via": "tmux"}),
        ("session.turn_ended", {"node": "implementation", "reason": "exit-met"}),
        ("session.nudged", {"node": "implementation", "nudge": 1}),
        ("graph.advanced", {"node": "design", "to": "implementation"}),
        ("comment.agent", {"body": "x" * 200}),
        ("session.awaiting_input", {"question": "Which?"}),
        ("session.reply_sent", {"actor": "rohith"}),
    ]
    records = []
    for index in range(50_000):
        event, fields = kinds[index % len(kinds)]
        ref = refs[(index // len(kinds)) % len(refs)]
        record = {**ev(index / 60, event, **fields), "work_item": ref}
        if event == "session.nudged":
            record["stall_id"] = f"{ref}@{stamp(index / 60)}"
        records.append(record)
    path = tmp_path / "events.jsonl"
    _write(path, records)

    begun = time.perf_counter()
    grouped = sessionstate.load(path)
    states = [
        derive(
            grouped.get(ref, []),
            now=at(60 * 24),
            watchdog=WATCHDOG,
            asks=ASKS,
            work_item=ref,
        )
        for ref in refs
    ]
    elapsed = time.perf_counter() - begun

    assert len(states) == 50
    assert all(state.state != "not-watched" for state in states)
    assert elapsed < 2.0, f"one cycle took {elapsed:.2f}s"


# -- the `session` object of the contract ----------------------------------------


def view_at(log, minutes: float) -> dict:
    return sessionstate.session_view(state_at(log, minutes))


def test_surfaces_view_has_the_contracts_four_fields():
    view = view_at([started(0, node="design")], 5)
    assert view == {
        "state": "working",
        "node": "design",
        "since": stamp(0),
        "detail": "",
    }


def test_surfaces_not_watched_says_why():
    view = view_at([], 5)
    assert (view["state"], view["node"], view["since"]) == ("not-watched", "", None)
    assert "turn" in view["detail"]


def test_surfaces_an_open_ask_shows_as_asked_with_its_question_and_default():
    """Requirement: R7.3."""
    log = [
        started(0),
        ask(1, ask_id="a1", default="Move it.", default_at=stamp(31)),
        ended(2, "open-ask"),
    ]
    view = view_at(log, 5)
    assert view["state"] == "asked"
    assert view["since"] == stamp(2)
    for part in ("Move T5?", "Move it.", stamp(31)):
        assert part in view["detail"]

    plain = view_at([started(0), ask(1, ask_id="a1"), ended(2, "open-ask")], 5)
    assert (plain["state"], plain["detail"]) == ("asked", "Move T5?")


def test_surfaces_a_declared_wait_shows_its_condition_and_end():
    """Requirement: R7.2."""
    log = [
        started(0),
        ev(4, "session.wait_declared", condition="CI on #552", until=stamp(34)),
        ended(5, "declared-wait"),
    ]
    view = view_at(log, 6)
    assert view["state"] == "waiting"
    assert "CI on #552" in view["detail"] and stamp(34) in view["detail"]


@pytest.mark.parametrize(
    "reason", ["human-gate", "complete", "graph-wait", "background-work"]
)
def test_surfaces_every_other_wait_says_what_it_waits_for(reason):
    view = view_at([started(0), ended(5, reason)], 6)
    assert view["state"] == "waiting"
    assert view["detail"]


def test_surfaces_idle_and_stalled_carry_the_node_and_the_stall_start():
    """Requirement: R7.1."""
    log = [started(0), ended(5, "exit-met", node="self-review")]
    idle = view_at(log, 9)
    assert (idle["state"], idle["node"], idle["since"]) == (
        "idle",
        "self-review",
        stamp(5),
    )
    assert idle["detail"]

    log.append(ev(15, "session.nudged", stall_id=stall_id(5), nudge=1))
    stalled = view_at(log, 20)
    assert (stalled["state"], stalled["since"]) == ("stalled", stamp(5))
    assert "1" in stalled["detail"]

    log += [
        ev(25, "session.nudged", stall_id=stall_id(5), nudge=2),
        ev(35, "session.stalled", stall_id=stall_id(5), idle_since=stamp(5)),
    ]
    notified = view_at(log, 40)
    assert notified["state"] == "stalled"
    assert notified["detail"] != stalled["detail"]


def test_surfaces_detail_text_comes_from_the_string_catalog(monkeypatch):
    seen = []
    real = sessionstate.strings.t

    def spy(key, **values):
        seen.append(key)
        return real(key, **values)

    monkeypatch.setattr(sessionstate.strings, "t", spy)
    view_at([started(0), ended(5, "human-gate")], 6)
    assert seen and all(key.startswith("core.sessionstate.") for key in seen)


# -- the `session:` line (design/messages.html § 6) -------------------------------


def line_at(log, minutes: float) -> str:
    from the_loop.core import sessionsurface

    return sessionsurface.summary(state_at(log, minutes), at(minutes))


def test_surfaces_line_for_each_state_reads_as_the_wording_contract():
    """Requirement: R7.1–R7.3. T0 is 12:00, so minute 5 is 12:05."""
    assert line_at([], 5) == "not watched"
    assert line_at([started(3)], 5) == "working (turn running since 12:03)"

    log = [started(0), ended(5, "exit-met", node="self-review")]
    assert line_at(log, 9) == "idle at self-review since 12:05 (4 min)"
    log += [
        ev(15, "session.nudged", stall_id=stall_id(5), nudge=1),
        ev(25, "session.nudged", stall_id=stall_id(5), nudge=2),
    ]
    assert line_at(log, 27) == ("STALLED at self-review since 12:05 (22 min, 2 nudges)")
    log.append(ev(35, "session.stalled", stall_id=stall_id(5), idle_since=stamp(5)))
    assert line_at(log, 40) == (
        "STALLED at self-review since 12:05 (35 min, 2 nudges, a person was told)"
    )

    wait = [
        started(0),
        ev(4, "session.wait_declared", condition="CI on #552", until=stamp(34)),
        ended(5, "declared-wait"),
    ]
    assert line_at(wait, 6) == "waiting for “CI on #552” until 12:34"

    asked = [started(0), ask(1, ask_id="a1"), ended(2, "open-ask")]
    assert line_at(asked, 5) == "asked 12:01; waiting for an answer"
    asked[1] = ask(1, ask_id="a1", default="Move it.", default_at=stamp(31))
    assert line_at(asked, 5) == "asked 12:01; default “Move it.” at 12:31"

    gate = line_at([started(0), ended(5, "human-gate")], 6)
    assert gate.startswith("waiting") and "human gate" in gate


def test_surfaces_line_counts_one_nudge_and_names_another_day():
    log = [
        started(0),
        ended(5, "exit-met", node=""),
        ev(15, "session.nudged", stall_id=stall_id(5), nudge=1),
    ]
    # No node: the line says nothing about one. Three hours on: hours.
    assert line_at(log, 190) == "STALLED since 12:05 (3 h 5 min, 1 nudge)"
    assert "2026-11-20 12:05" in line_at(log, 60 * 24)
