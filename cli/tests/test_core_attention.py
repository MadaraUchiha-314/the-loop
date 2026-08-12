"""Unit tests for the needs-attention aggregation (issue-161, T3, R6.3)."""

import json

from the_loop.core import attention
from the_loop.control import ControlStore
from the_loop.sessions.registry import Session, SessionRegistry
from the_loop.state import layout_from_config, legacy_layout
from the_loop.workitem import WorkItemRef


REF = "github:octo/repo#5"
ARMED = "github:octo/repo#6"


def _config(tmp_path):
    return {"state": {"root": str(tmp_path / ".the-loop")}}


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
                "ts": "2026-08-05T01:00:00Z",
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
