"""Core capability: what needs attention (issue-161, R6.3).

Derived, never stored: paused sessions, recent delivery/dispatch failures from
the event log, armed work items with no live session, and sessions waiting on a
human answer (`session.awaiting_input` not yet closed by a `session.reply_sent`
— issue-208). Graph-gate waits are
repo-scoped (they live in each checkout's graph state), so they surface through
``graphs.check`` per work item; this module aggregates only what the machine's
own state can answer.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import events as core_events
from . import sessions as core_sessions
from . import workitems as core_workitems


def list_attention(config: Optional[dict] = None) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []

    sessions = core_sessions.list_sessions(config=config)
    by_ref = {s["ref"]: s for s in sessions}
    for session in sessions:
        if session["status"] == "paused":
            last = (session.get("control") or {}).get("command") or "unknown"
            items.append(
                {
                    "workItem": session["ref"],
                    "kind": "session-paused",
                    "detail": f"session paused (last control: {last})",
                }
            )

    for record in core_workitems.list_work_items(config):
        control = record.get("control") or {}
        armed = control.get("command") in ("start", "resume")
        live = by_ref.get(record.get("ref", ""), {}).get("status") in (
            "active",
            "paused",
        )
        if armed and not live:
            items.append(
                {
                    "workItem": record["ref"],
                    "kind": "armed-without-session",
                    "detail": "start recorded but no live session on this machine",
                }
            )

    from ..state import layout_from_config

    log_path = layout_from_config(config or {}).event_log if config else None

    # A question asked through `the-loop ask` is open until a reply through the
    # control plane is at least as new (issue-208). The SAME open/answered rule
    # the dashboard implements in ui/src/api/model.ts::awaitingInput — change
    # one and the other is a reviewable change, or the two surfaces disagree.
    asked: Dict[str, Dict[str, Any]] = {}
    answered: Dict[str, str] = {}
    for event in core_events.query_events(
        log_path,
        types=["session.awaiting_input", "session.reply_sent"],
        limit=0,
    ):
        ref = str(event.get("work_item") or "")
        if not ref:
            continue
        if event.get("event") == "session.awaiting_input":
            asked[ref] = event
        else:
            answered[ref] = str(event.get("ts", ""))
    for ref, event in asked.items():
        reply_ts = answered.get(ref)
        if reply_ts is not None and reply_ts >= str(event.get("ts", "")):
            continue
        question = str(event.get("question") or "").strip()
        items.append(
            {
                "workItem": ref,
                "kind": "awaiting-input",
                "detail": (
                    f"agent is waiting for input: {question}"
                    if question
                    else "agent is waiting for input"
                ),
            }
        )

    for event in core_events.query_events(log_path, min_level="error", limit=20):
        ref = event.get("work_item") or ",".join(event.get("work_items") or [])
        items.append(
            {
                "workItem": ref or "",
                "kind": "recent-error",
                "detail": f"{event.get('event')} at {event.get('ts')}",
            }
        )
    return items
