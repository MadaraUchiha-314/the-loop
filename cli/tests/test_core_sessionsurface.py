"""The `session:` line and the `session` object, as the status surfaces show a
derived state (issue-551, Requirement 7).

Feature: The state of a session is visible
Requirement: docs/specs/issue-551/requirements.md
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from the_loop.core import sessionstate, sessionsurface
from the_loop.watchconfig import AsksConfig, WatchdogConfig

REF = "github:octo/repo#5"
T0 = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def stamp(minutes: float) -> str:
    moment = T0 + timedelta(minutes=minutes)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def ev(minutes: float, event: str, **fields):
    return {"ts": stamp(minutes), "event": event, "work_item": REF, **fields}


def ask(minutes: float, ask_id: str, default: str = "", after: float = 0, **fields):
    record = ev(minutes, "session.awaiting_input", ask_id=ask_id, **fields)
    record.setdefault("question", "Move the screenshots?")
    if default:
        record["default"] = default
    if after:
        record["default_at"] = stamp(minutes + after)
    return record


def state_at(log, minutes: float):
    return sessionstate.derive(
        log,
        now=T0 + timedelta(minutes=minutes),
        watchdog=WatchdogConfig(),
        asks=AsksConfig(),
        work_item=REF,
    )


def line_at(log, minutes: float) -> str:
    return sessionsurface.summary(
        state_at(log, minutes), T0 + timedelta(minutes=minutes)
    )


def view_at(tmp_path, log, minutes: float):
    path = tmp_path / "events.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in log))
    reader = sessionsurface.Reader(
        {"eventLog": {"path": str(path)}}, now=T0 + timedelta(minutes=minutes)
    )
    return reader.view(REF)


def test_a_working_session_shows_the_default_of_its_open_ask(tmp_path):
    """
    Feature: The state of a session is visible
    Scenario: the session asked with a default and carried on working
      Given an open ask with a default due at 12:31
      And a turn that started after the ask
      When the session's state is shown
      Then the line gives the working state and then the default and its time
      And the `session` object's detail carries the same clause

    Requirement: docs/specs/issue-551/requirements.md#R7.3
    """
    log = [
        ev(0, "session.turn_started"),
        ask(1, "a1", default="Move it.", after=30),
        ev(2, "session.turn_ended", reason="open-ask"),
        ev(3, "session.turn_started"),
    ]
    clause = "asked 12:01, default “Move it.” at 12:31"
    assert line_at(log, 5) == f"working (turn running since 12:03); {clause}"
    view = view_at(tmp_path, log, 5)
    assert view["state"] == "working"
    assert view["summary"] == f"working (turn running since 12:03); {clause}"
    assert view["detail"] == clause


def test_an_idle_and_a_stalled_session_show_the_default_too():
    """Requirement: docs/specs/issue-551/requirements.md#R7.3"""
    log = [
        ev(0, "session.turn_started"),
        ask(1, "a1", default="Move it.", after=60),
        ev(5, "session.turn_ended", reason="exit-met", node="build"),
    ]
    clause = "asked 12:01, default “Move it.” at 13:01"
    assert line_at(log, 9) == f"idle at build since 12:05 (4 min); {clause}"
    assert line_at(log, 30).startswith("STALLED at build since 12:05 (25 min, ")
    assert line_at(log, 30).endswith(f"; {clause}")


def test_an_asked_session_reads_as_before():
    """Requirement: docs/specs/issue-551/requirements.md#R7.3"""
    log = [
        ev(0, "session.turn_started"),
        ask(1, "a1", default="Move it.", after=30),
        ev(2, "session.turn_ended", reason="open-ask"),
    ]
    assert line_at(log, 5) == "asked 12:01; default “Move it.” at 12:31"
    log[1] = ask(1, "a1")
    assert line_at(log, 5) == "asked 12:01; waiting for an answer"


def test_several_open_asks_show_the_one_due_first_and_count_the_rest(tmp_path):
    """
    Feature: The state of a session is visible
    Scenario: three asks are open at once
      Given a question with no default, one due at 13:02 and one due at 12:33
      Then the line shows the one due at 12:33 and `+2 more`

    Requirement: docs/specs/issue-551/requirements.md#R7.3
    """
    log = [
        ev(0, "session.turn_started"),
        ask(1, "a1"),
        ask(2, "a2", default="Later one.", after=60),
        ask(3, "a3", default="Sooner one.", after=30),
    ]
    clause = "asked 12:03, default “Sooner one.” at 12:33 +2 more"
    assert line_at(log, 5) == f"working (turn running since 12:00); {clause}"
    assert view_at(tmp_path, log, 5)["detail"] == clause
    log.append(ev(4, "session.turn_ended", reason="open-ask"))
    assert line_at(log, 5) == "asked 12:03; default “Sooner one.” at 12:33 +2 more"


def test_an_ask_with_no_default_adds_nothing_to_a_working_line():
    log = [ev(0, "session.turn_started"), ask(1, "a1")]
    assert line_at(log, 5) == "working (turn running since 12:00)"
