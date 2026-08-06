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
