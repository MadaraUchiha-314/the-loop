"""Core capability: what needs attention (issue-161, R6.3).

Derived, never stored: paused sessions, recent delivery/dispatch failures from
the event log, armed work items with no live session, and what
:mod:`sessionstate` derives from the event log: an open question, a stalled
session and — as information — a declared wait.
Graph-gate waits are
repo-scoped (they live in each checkout's work-item state), so they surface through
``graphs.check`` per work item; this module aggregates only what the machine's
own state can answer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .. import strings
from . import events as core_events
from . import sessions as core_sessions
from . import sessionsurface
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

    # One read of the event log serves every session's state.
    states = sessionsurface.Reader(config)
    sessions = core_sessions.list_sessions(config=config, states=states)
    by_ref = {s["ref"]: s for s in sessions}
    # A pull request's session is stored *nested* under the work item it
    # delivers (``pullRequests``, issue-172), never as a record of its own — so
    # asking "does this ref have a session?" against the top level alone reports
    # every linked, labeled PR as stalled forever (issue-302). A ref's own
    # record still wins, matching ``SessionRegistry.record_owning``.
    for session in sessions:
        for endpoint in session.get("pullRequests") or []:
            ref = str((endpoint.get("workItem") or {}).get("ref") or "")
            if ref:
                by_ref.setdefault(ref, endpoint)
    for session in sessions:
        if session["status"] == "paused":
            last = (session.get("control") or {}).get("command") or "unknown"
            items.append(
                {
                    "workItem": session["ref"],
                    "kind": "session-paused",
                    "detail": strings.t("core.attention.session-paused", last=last),
                }
            )

    records = core_workitems.list_work_items(config)
    # A work item that ended upstream asks for nothing (issue-329): its record
    # carries the closure stamp the close path wrote, and the SAME rule the
    # dashboard applies (ui/src/api/model.ts::buildWorkItemViews nulls the
    # question and the gate for an ended record) applies here, so the two
    # surfaces agree. Only a mapping counts — a malformed stamp reads as open.
    ended = {
        str(record.get("ref") or "")
        for record in records
        if isinstance(record.get("ended"), dict)
    }
    for record in records:
        control = record.get("control") or {}
        armed = control.get("command") in ("start", "resume")
        live = by_ref.get(record.get("ref", ""), {}).get("status") in (
            "active",
            "paused",
        )
        if armed and not live and record.get("ref") not in ended:
            items.append(
                {
                    "workItem": record["ref"],
                    "kind": "armed-without-session",
                    "detail": strings.t("core.attention.armed-without-session"),
                }
            )

    from ..state import layout_from_config

    log_path = layout_from_config(config or {}).event_log if config else None

    # Whether a question is open, and whether a session is stalled or waits, is
    # :mod:`sessionstate`'s answer: a reply or an authorized answer closes
    # every open ask, and a default being taken closes its own. The dashboard
    # mirrors the open-ask rule in ui/src/api/model.ts::awaitingInput — change
    # one and the other is a reviewable change, or the two surfaces disagree.
    active = {s["ref"] for s in sessions if s["status"] == "active"}
    # A pull request with a conversation of its own stalls like any other. It
    # is stored under its work item, and counts only once it has a terminal: a
    # pull request that is merely linked has no session to stall.
    for session in sessions:
        if session["status"] != "active":
            continue
        for endpoint in session.get("pullRequests") or []:
            ref = str((endpoint.get("workItem") or {}).get("ref") or "")
            if (
                ref
                and endpoint.get("status") == "active"
                and endpoint.get("tmuxTarget")
            ):
                active.add(ref)
    waits: List[Dict[str, Any]] = []
    for ref in states.refs:
        if ref in ended:
            continue  # the item ended; nobody is waiting for the answer
        state = states(ref)
        # One row for a work item, however many asks it has open: the one whose
        # default is due first, and a count of the others.
        ask, more = sessionsurface.shown_ask(state)
        if ask is not None:
            # The question and the default are the session's own words: shown
            # as one printable line, the question cut to fit a row.
            question = sessionsurface.one_line(ask.question)
            detail = (
                strings.t("core.attention.awaiting-input-question", question=question)
                if question
                else strings.t("core.attention.awaiting-input")
            )
            if more:
                detail = strings.t(
                    "core.attention.awaiting-input-more", detail=detail, count=more
                )
            row: Dict[str, Any] = {
                "workItem": ref,
                "kind": "awaiting-input",
                "detail": detail,
            }
            # An ask recorded without an id has no default the watcher takes.
            if ask.default_at is not None and not ask.legacy:
                row["detail"] = strings.t(
                    "core.attention.awaiting-input-default",
                    detail=detail,
                    default_at=sessionsurface.clock(ask.default_at, states.now),
                )
                row["default"] = sessionsurface.one_line(
                    ask.default, core_sessions.MAX_DEFAULT_LENGTH
                )
                row["defaultAt"] = ask.default_at
            items.append(row)
        # A turn record outlives its session, so only a live session stalls or
        # waits. Neither row is stored: each leaves when the state does.
        if ref not in active:
            continue
        if state.state == "stalled":
            items.append(
                {
                    "workItem": ref,
                    "kind": "stalled",
                    "detail": strings.t(
                        "core.attention.stalled",
                        node=state.node or "-",
                        elapsed=sessionsurface.elapsed(state.since, states.now),
                        nudges=sessionsurface.nudges(state),
                    ),
                    "at": state.since or "",
                }
            )
        wait = state.declared_wait
        if state.state == "waiting" and state.reason == "declared-wait" and wait:
            waits.append(
                {
                    "workItem": ref,
                    "kind": "declared-wait",
                    "detail": strings.t(
                        "core.attention.declared-wait",
                        condition=sessionsurface.one_line(
                            wait.condition, sessionsurface.MAX_CONDITION_SHOWN
                        ),
                        until=sessionsurface.clock(wait.until, states.now),
                    ),
                }
            )

    # Recent errors age out (issue-283 B5): only errors from the last
    # RECENT_ERROR_MAX_AGE_HOURS are "recent", and a ``poll.*`` error whose work
    # item has since polled clean — ``poll.lastPolledAt`` on the served record is
    # newer than the error (this machine's clock, joined onto the record by
    # ``core.workitems`` since issue-382, and the event log it is compared
    # against is this machine's too), and a cycle that failed the item skips that
    # stamp — is
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
                "detail": strings.t(
                    "core.attention.recent-error",
                    event=event.get("event"),
                    ts=event.get("ts"),
                ),
                "at": ts,
            }
        )
    # Information, not a call to act: a row has no severity field, so a
    # declared wait says so in its text and comes last.
    return items + waits
