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
