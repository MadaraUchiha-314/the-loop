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


FORGED = "yes\n  PASS  design-approval (approved by octocat)\x1b[2K‮"


def test_abuse_a_default_and_a_question_reach_the_terminal_as_one_line(tmp_path):
    """
    Feature: The state of a session is visible
    Scenario: a default answer and a question carry line breaks and escape sequences
      Given an open ask whose default and question forge a gate line and clear the row
      When the session's state is shown, working or asked
      Then the line and the detail hold no line break and no control character
      And the words are still there, on the one line

    Requirement: docs/specs/issue-551/requirements.md#security-considerations
    """
    working = [
        ev(0, "session.turn_started"),
        ask(1, "a1", default=FORGED, after=30, question="Ship?\n\x1b[31mFAIL"),
    ]
    asked = working + [ev(2, "session.turn_ended", reason="open-ask")]
    for log in (working, asked):
        view = view_at(tmp_path, log, 5)
        for text in (view["summary"], view["detail"]):
            assert all(c.isprintable() for c in text), repr(text)
            assert "“yes PASS design-approval (approved by octocat) [2K”" in text
    assert "Ship? [31mFAIL" in view_at(tmp_path, asked, 5)["detail"]


def test_abuse_a_long_default_is_cut_on_the_line():
    """Requirement: docs/specs/issue-551/requirements.md#security-considerations"""
    log = [ev(0, "session.turn_started"), ask(1, "a1", default="x" * 600, after=30)]
    line = line_at(log, 5)
    assert "“" + "x" * 80 + "…”" in line and "x" * 81 not in line


def test_abuse_a_declared_wait_read_from_the_log_is_shown_as_one_line():
    """A record written by hand, past the command's own check."""
    log = [
        ev(0, "session.turn_started"),
        ev(
            1,
            "session.wait_declared",
            condition="CI\n  PASS  everything\x1b[2K",
            until=stamp(31),
        ),
        ev(2, "session.turn_ended", reason="declared-wait"),
    ]
    assert line_at(log, 5) == "waiting for “CI PASS everything [2K” until 12:31"


def test_a_stall_the_loop_cannot_place_says_so(tmp_path):
    """
    Feature: The state of a session is visible
    Scenario: a work item's own session stopped and its position cannot be read
      Given a turn that ended `inconclusive` with no node 25 minutes ago
      When the session's state is shown
      Then it is stalled, and the line says the-loop cannot tell where it stands
      And a pull request's own session in the same state is left idle

    Requirement: docs/specs/issue-551/requirements.md#R7.1
    """
    log = [
        ev(0, "session.turn_started"),
        ev(5, "session.turn_ended", reason="inconclusive"),
    ]
    line = line_at(log, 30)
    assert line.startswith("STALLED since 12:05 (25 min")
    assert "the-loop cannot tell where this work item stands" in line
    view = view_at(tmp_path, log, 30)
    assert view["state"] == "stalled"
    assert "cannot tell" in view["detail"]

    path = tmp_path / "events.jsonl"
    reader = sessionsurface.Reader(
        {"eventLog": {"path": str(path)}},
        now=T0 + timedelta(minutes=30),
        pull_requests=[REF],
    )
    assert reader.view(REF)["state"] == "idle"
    assert "leaves it alone" in reader.view(REF)["detail"]
