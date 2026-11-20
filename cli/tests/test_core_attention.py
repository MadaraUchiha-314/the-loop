"""Unit tests for the needs-attention aggregation (issue-161, T3, R6.3)."""

import json
from datetime import datetime, timedelta, timezone

from the_loop.core import attention
from the_loop.control import ControlStore
from the_loop.sessions.registry import Session, SessionRegistry
from the_loop.state import layout_from_config, legacy_layout
from the_loop.workitem import POLL, WorkItemRef, WorkItemStore


REF = "github:octo/repo#5"
ARMED = "github:octo/repo#6"


def _config(tmp_path):
    return {"state": {"root": str(tmp_path / ".the-loop")}}


def _iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _hours_ago(hours):
    return _iso(datetime.now(timezone.utc) - timedelta(hours=hours))


def test_attention_surfaces_paused_armed_and_errors(tmp_path):
    config = _config(tmp_path)
    layout = layout_from_config(config)

    registry = SessionRegistry(layout.local_dir)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(tmp_path),
        )
    )
    registry.pause(REF)

    control = ControlStore(layout.portable_dir, legacy=legacy_layout(layout))
    control.record(ARMED, "start", source="cli", actor="tester")

    log = tmp_path / ".the-loop" / "logs" / "events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        json.dumps(
            {
                "ts": _hours_ago(1),
                "event": "dispatch.failed",
                "level": "error",
                "work_item": ARMED,
            }
        )
        + "\n"
    )

    items = attention.list_attention(config)
    kinds = {(i["kind"], i["workItem"]) for i in items}
    assert ("session-paused", REF) in kinds
    assert ("armed-without-session", ARMED) in kinds
    assert ("recent-error", ARMED) in kinds
    # The error entry carries its raw timestamp so a dashboard can render age
    # instead of a bare ISO string (issue-283 B5).
    error = next(i for i in items if i["kind"] == "recent-error")
    assert error["at"]


def test_attention_ages_out_stale_errors(tmp_path):
    """issue-283 B5 — an error older than the recency window is not 'recent'.

    Feature: Attention age-out
      Scenario: A six-day-old poll error no longer cries wolf
        Given an error event older than RECENT_ERROR_MAX_AGE_HOURS
        When the attention surface is listed
        Then no recent-error entry is reported for it
    """
    config = _config(tmp_path)
    _log(
        tmp_path,
        [
            {
                "ts": _hours_ago(attention.RECENT_ERROR_MAX_AGE_HOURS + 2),
                "event": "poll.item_error",
                "level": "error",
                "work_item": REF,
            }
        ],
    )
    assert not [
        i for i in attention.list_attention(config) if i["kind"] == "recent-error"
    ]


def test_attention_clears_a_poll_error_once_the_item_polls_clean(tmp_path):
    """issue-283 B5 — a clean poll after a poll error clears the entry.

    Feature: Attention age-out
      Scenario: The next successful cycle clears the flag
        Given a recent poll.item_error for a work item
        And the item's portable record shows a newer successful poll
        When the attention surface is listed
        Then no recent-error entry is reported for it
    """
    config = _config(tmp_path)
    layout = layout_from_config(config)
    _log(
        tmp_path,
        [
            {
                "ts": _hours_ago(2),
                "event": "poll.item_error",
                "level": "error",
                "work_item": REF,
            }
        ],
    )
    store = WorkItemStore(layout.portable_dir)
    store.write_section(REF, POLL, {"lastPolledAt": _hours_ago(1)})
    assert not [
        i for i in attention.list_attention(config) if i["kind"] == "recent-error"
    ]

    # A non-poll error is NOT cleared by a poll stamp — only aged out.
    _log(
        tmp_path,
        [
            {
                "ts": _hours_ago(2),
                "event": "dispatch.failed",
                "level": "error",
                "work_item": REF,
            }
        ],
    )
    assert [i for i in attention.list_attention(config) if i["kind"] == "recent-error"]


def _log(tmp_path, records):
    log = tmp_path / ".the-loop" / "logs" / "events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("".join(json.dumps(r) + "\n" for r in records))


def _ask(ref, ts, question="Which auth mode?"):
    return {
        "ts": ts,
        "event": "session.awaiting_input",
        "level": "info",
        "work_item": ref,
        "question": question,
    }


def _reply(ref, ts):
    return {"ts": ts, "event": "session.reply_sent", "level": "info", "work_item": ref}


def test_attention_reports_an_open_question(tmp_path):
    """issue-208 R3.1 — the same open/answered rule as the dashboard's model."""
    config = _config(tmp_path)
    _log(tmp_path, [_ask(REF, "2026-08-12T10:00:00.000Z")])
    items = attention.list_attention(config)
    waiting = [i for i in items if i["kind"] == "awaiting-input"]
    assert waiting == [
        {
            "workItem": REF,
            "kind": "awaiting-input",
            "detail": "agent is waiting for input: Which auth mode?",
        }
    ]


def test_attention_closes_a_question_once_a_reply_is_newer(tmp_path):
    config = _config(tmp_path)
    _log(
        tmp_path,
        [
            _ask(REF, "2026-08-12T10:00:00.000Z"),
            _reply(REF, "2026-08-12T10:05:00.000Z"),
        ],
    )
    assert not [
        i for i in attention.list_attention(config) if i["kind"] == "awaiting-input"
    ]


def test_attention_reopens_a_question_asked_after_the_last_reply(tmp_path):
    config = _config(tmp_path)
    _log(
        tmp_path,
        [
            _ask(REF, "2026-08-12T10:00:00.000Z"),
            _reply(REF, "2026-08-12T10:05:00.000Z"),
            _ask(REF, "2026-08-12T10:10:00.000Z", question="And the port?"),
        ],
    )
    waiting = [
        i for i in attention.list_attention(config) if i["kind"] == "awaiting-input"
    ]
    assert len(waiting) == 1
    assert "And the port?" in waiting[0]["detail"]


PR = "github:octo/repo#7"


def _armed_with_nested_pr(tmp_path, pr_status="active"):
    """A labeled PR, armed by the label, whose session is nested under its issue."""
    config = _config(tmp_path)
    layout = layout_from_config(config)

    registry = SessionRegistry(layout.local_dir)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(tmp_path),
        )
    )
    endpoint = registry.link_pull_request(REF, PR)
    assert endpoint is not None
    if pr_status != "active":
        endpoint.status = pr_status
        registry.save_endpoint(REF, endpoint)

    # The poller flushes a ledger under the PR's own ref, and the label arms it.
    ControlStore(layout.portable_dir, legacy=legacy_layout(layout)).record(
        PR, "start", source="comment", actor="maintainer"
    )
    return config


def test_a_nested_pull_request_endpoint_counts_as_a_session(tmp_path):
    """issue-302 — a linked PR is worked under its issue, not stalled.

    Feature: Attention liveness
      Scenario: A labeled pull request whose session is nested under its issue
        Given an armed pull request linked to a work item with a live session
        And the pull request's own endpoint is nested under that record
        When the attention surface is listed
        Then no armed-without-session entry is reported for the pull request
    """
    config = _armed_with_nested_pr(tmp_path)
    assert not [
        i
        for i in attention.list_attention(config)
        if i["kind"] == "armed-without-session" and i["workItem"] == PR
    ]


def test_a_closed_nested_endpoint_still_reports_no_session(tmp_path):
    """issue-302, abuse case A3 — only a live endpoint answers for the ref.

    Feature: Attention liveness
      Scenario: The pull request's endpoint was closed with its pull request
        Given an armed pull request whose nested endpoint is closed
        When the attention surface is listed
        Then an armed-without-session entry is reported for the pull request
    """
    config = _armed_with_nested_pr(tmp_path, pr_status="closed")
    assert [
        i
        for i in attention.list_attention(config)
        if i["kind"] == "armed-without-session" and i["workItem"] == PR
    ]


def test_an_ended_item_asks_for_no_attention(tmp_path):
    """R5.4 (issue-329) — a closed work item's stale question and arming are
    suppressed, the same rule the dashboard applies to its record."""
    from the_loop.workitem import ENDED, WorkItemStore

    config = _config(tmp_path)
    layout = layout_from_config(config)
    control = ControlStore(layout.portable_dir, legacy=legacy_layout(layout))
    control.record(ARMED, "start", source="cli", actor="tester")
    control.record_ended(ARMED, {"state": "closed", "reason": "issue-closed"})
    _log(tmp_path, [_ask(ARMED, "2026-08-12T10:00:00.000Z")])
    kinds = {i["kind"] for i in attention.list_attention(config)}
    assert "awaiting-input" not in kinds and "armed-without-session" not in kinds

    # Abuse case A6: a stamp that is not a mapping fails towards showing the item.
    WorkItemStore(layout.portable_dir).write_section(ARMED, ENDED, None)
    from pathlib import Path

    path = Path(layout.portable_dir) / "github-octo-repo-6.json"
    record = json.loads(path.read_text())
    record[ENDED] = "closed"
    path.write_text(json.dumps(record))
    kinds = {i["kind"] for i in attention.list_attention(config)}
    assert {"awaiting-input", "armed-without-session"} <= kinds


# -- the derived state of a session on the attention list (issue-551, R7) --------


def _minutes_ago(minutes):
    return _iso(datetime.now(timezone.utc) - timedelta(minutes=minutes))


def _session(tmp_path, ref=REF):
    config = _config(tmp_path)
    SessionRegistry(layout_from_config(config).local_dir).register(
        Session(
            work_item=WorkItemRef.parse(ref),
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(tmp_path),
        )
    )
    return config


def _turn(ref, ts, event, **fields):
    return {"ts": ts, "event": event, "level": "info", "work_item": ref, **fields}


def _of_kind(config, kind):
    return [i for i in attention.list_attention(config) if i["kind"] == kind]


def test_a_stalled_session_is_listed_and_leaves_when_the_stall_ends(tmp_path):
    """
    Feature: the attention list shows a stall
      Scenario: a session stays idle past the threshold, then works again
        Given a live session whose turn ended 22 minutes ago with work owed
        And two nudges were sent
        When the attention list is read
        Then one `stalled` row names the node, the idle time and the nudges
        When a turn starts
        Then the row is gone, with no person's action

    Requirement: docs/specs/issue-551/requirements.md R7.1, R7.5
    """
    config = _session(tmp_path)
    idle_since = _minutes_ago(22)
    stall = f"{REF}@{idle_since}"
    log = [
        _turn(REF, _minutes_ago(30), "session.turn_started", node="self-review"),
        _turn(
            REF,
            idle_since,
            "session.turn_ended",
            node="self-review",
            reason="exit-met",
        ),
        _turn(REF, _minutes_ago(12), "session.nudged", stall_id=stall, nudge=1),
        _turn(REF, _minutes_ago(2), "session.nudged", stall_id=stall, nudge=2),
    ]
    _log(tmp_path, log)
    assert _of_kind(config, "stalled") == [
        {
            "workItem": REF,
            "kind": "stalled",
            "detail": "self-review · idle 22 min · 2 nudges",
            "at": idle_since,
        }
    ]

    _log(tmp_path, log + [_turn(REF, _minutes_ago(0), "session.turn_started")])
    assert _of_kind(config, "stalled") == []


def test_an_idle_session_within_the_threshold_is_not_listed(tmp_path):
    config = _session(tmp_path)
    _log(
        tmp_path,
        [_turn(REF, _minutes_ago(4), "session.turn_ended", reason="exit-met")],
    )
    assert _of_kind(config, "stalled") == []


def test_a_stall_is_listed_only_for_a_live_session_of_an_open_item(tmp_path):
    """A turn record outlives its session; a stall with no session is nobody's."""
    stale = [_turn(REF, _hours_ago(5), "session.turn_ended", reason="exit-met")]
    _log(tmp_path, stale)
    assert _of_kind(_config(tmp_path), "stalled") == []

    config = _session(tmp_path)
    assert len(_of_kind(config, "stalled")) == 1
    control = ControlStore(
        layout_from_config(config).portable_dir,
        legacy=legacy_layout(layout_from_config(config)),
    )
    control.record_ended(REF, {"state": "closed", "reason": "issue-closed"})
    assert _of_kind(config, "stalled") == []


def test_a_declared_wait_is_listed_as_information(tmp_path):
    """Requirement: docs/specs/issue-551/requirements.md R7.2."""
    config = _session(tmp_path)
    until = _iso(datetime.now(timezone.utc) + timedelta(minutes=30))
    _log(
        tmp_path,
        [
            _turn(REF, _minutes_ago(6), "session.turn_started"),
            _turn(
                REF,
                _minutes_ago(5),
                "session.wait_declared",
                condition="CI on #552",
                until=until,
            ),
            _turn(REF, _minutes_ago(4), "session.turn_ended", reason="declared-wait"),
        ],
    )
    (row,) = _of_kind(config, "declared-wait")
    assert set(row) == {"workItem", "kind", "detail"}
    assert row["workItem"] == REF
    assert row["detail"].startswith("“CI on #552” · until ")
    assert row["detail"].endswith("(informational)")
    # Informational rows come last: the list has no severity field to carry it.
    assert attention.list_attention(config)[-1] == row
    assert _of_kind(config, "stalled") == []


def test_an_open_question_with_a_deadline_carries_its_default(tmp_path):
    """Requirement: docs/specs/issue-551/requirements.md R7.3."""
    config = _config(tmp_path)
    default_at = _iso(datetime.now(timezone.utc) + timedelta(minutes=30))
    asked = dict(
        _ask(REF, _minutes_ago(1)),
        ask_id="a1",
        default="Move T5 to after merge.",
        default_at=default_at,
    )
    _log(tmp_path, [asked])
    (row,) = _of_kind(config, "awaiting-input")
    assert row["default"] == "Move T5 to after merge."
    assert row["defaultAt"] == default_at
    assert row["detail"].startswith("agent is waiting for input: Which auth mode?")
    assert "default at " in row["detail"]

    # A question with no deadline has neither key (the contract).
    _log(tmp_path, [_ask(REF, _minutes_ago(1))])
    (plain,) = _of_kind(config, "awaiting-input")
    assert set(plain) == {"workItem", "kind", "detail"}


def test_an_answer_or_a_taken_default_closes_the_question(tmp_path):
    """The open/closed rule is the derivation's: three records close an ask."""
    config = _config(tmp_path)
    asked = dict(_ask(REF, _minutes_ago(9)), ask_id="a1")
    for closer in ("session.ask_answered", "session.ask_default_taken"):
        _log(tmp_path, [asked, _turn(REF, _minutes_ago(5), closer, ask_id="a1")])
        assert _of_kind(config, "awaiting-input") == [], closer


def test_the_event_log_is_read_once_for_the_session_states(tmp_path, monkeypatch):
    from the_loop.core import sessionstate

    config = _session(tmp_path)
    _log(tmp_path, [_ask(REF, _minutes_ago(1)), _ask(ARMED, _minutes_ago(1))])
    reads = []
    real = sessionstate.load
    monkeypatch.setattr(
        sessionstate, "load", lambda path: reads.append(path) or real(path)
    )
    assert len(_of_kind(config, "awaiting-input")) == 2
    assert len(reads) == 1
