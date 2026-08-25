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

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import events as core_events
from . import sessions as core_sessions
from . import workitems as core_workitems

#: How long a ``recent-error`` stays on the attention surface (issue-283 B5).
#: Errors older than this are no longer "recent": the retries that produced
#: them have long since moved on, and a board that reports them forever cries
#: wolf — the inbox must converge to empty when nothing needs a human.
RECENT_ERROR_MAX_AGE_HOURS = 24.0


def _recent_error_cutoff(now: Optional[datetime] = None) -> str:
    moment = now or datetime.now(timezone.utc)
    cutoff = moment - timedelta(hours=RECENT_ERROR_MAX_AGE_HOURS)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


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

    records = core_workitems.list_work_items(config)
    for record in records:
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

    # Recent errors age out (issue-283 B5): only errors from the last
    # RECENT_ERROR_MAX_AGE_HOURS are "recent", and a ``poll.*`` error whose work
    # item has since polled clean — its record's ``poll.lastPolledAt`` is newer
    # than the error, and a cycle that failed the item skips that stamp — is
    # cleared rather than reported. Only the poller's own errors get the
    # clean-poll clear: other sources emit asynchronously, so a same-cycle stamp
    # could hide a live failure; those rely on the age-out alone. ``at`` carries
    # the raw timestamp so the dashboard can render age instead of a bare ISO
    # string.
    polled_clean: Dict[str, str] = {}
    for record in records:
        stamp = str((record.get("poll") or {}).get("lastPolledAt") or "")
        if stamp and record.get("ref"):
            polled_clean[str(record["ref"])] = stamp
    for event in core_events.query_events(
        log_path, min_level="error", since=_recent_error_cutoff(), limit=20
    ):
        ref = event.get("work_item") or ",".join(event.get("work_items") or [])
        ts = str(event.get("ts") or "")
        polls_clean = (
            str(event.get("event") or "").startswith("poll.")
            and ref
            and ts
            and polled_clean.get(str(ref), "") > ts
        )
        if polls_clean:
            continue
        items.append(
            {
                "workItem": ref or "",
                "kind": "recent-error",
                "detail": f"{event.get('event')} at {event.get('ts')}",
                "at": ts,
            }
        )
    return items
