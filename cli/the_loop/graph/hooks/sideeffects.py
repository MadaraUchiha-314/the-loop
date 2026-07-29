"""Side-effecting hooks — labels, log entries, review requests, notifications.

All ordinary hooks, so what the-loop ships and what could later be added are the
same kind of thing. Each is best-effort by contract: a Slack outage or a GitHub
hiccup records and continues rather than wedging the graph (R6.12) — except
where the hook *is* the transition.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import List

from ...authz import mark_self_authored
from ..contract import HookContext, HookResult
from ..integrations import IntegrationError, resolve
from ..registry import hook

logger = logging.getLogger("the-loop.graph")

__all__ = ["log_entry", "notify", "request_review", "set_phase_label"]


def _integration(ctx: HookContext, target: str):
    return resolve(target, ctx.config)


@hook("set-phase-label")
def set_phase_label(ctx: HookContext) -> HookResult:
    """Keep the ticket's phase label in sync (R5.5, R9.2).

    A node without a `phase` declares no label, and creates none — labels stay
    coarse while graph state carries the fine detail.
    """
    name = "set-phase-label"
    phase = str(ctx.node.get("phase") or "")
    if not phase:
        return HookResult.skipped(name, "node declares no phase label")
    prefix = str(ctx.config.get("phaseLabelPrefix", "loop:"))
    label = f"{prefix}{phase}"
    try:
        _integration(ctx, "github").call(
            "set-labels", ref=ctx.work_item.ref, labels=[label]
        )
    except IntegrationError as exc:
        logger.warning("could not sync %s: %s", label, exc)
        return HookResult.ok(name, label=label, applied=False, error=str(exc))
    return HookResult.ok(name, label=label, applied=True)


@hook("log-entry")
def log_entry(ctx: HookContext) -> HookResult:
    """Append a checkpoint to the work item's execution log."""
    name = "log-entry"
    path = ctx.work_item.spec_dir / "execution-log.md"
    if not path.is_file():
        return HookResult.skipped(name, "no execution log for this work item")
    heading = f"\n### {date.today().isoformat()} — {ctx.boundary} {ctx.node_id}\n"
    body = f"\n- **Node:** {ctx.node_id}\n- **Boundary:** {ctx.boundary}\n"
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(heading + body)
    except OSError as exc:
        logger.warning("could not append to %s: %s", path, exc)
        return HookResult.ok(name, appended=False, error=str(exc))
    return HookResult.ok(name, appended=True)


@hook("request-review")
def request_review(ctx: HookContext) -> HookResult:
    """Ask for the review that this gate is waiting on.

    Posted with the-loop's self-authored marker, so the poller never reads its
    own request back as new input.
    """
    name = "request-review"
    body = mark_self_authored(
        f"🤖 _the-loop_ — **{ctx.node_id}** is ready for review.\n\n"
        f"Work item `{ctx.work_item.id}` has reached a human gate. Reply with an "
        "approval, an approval with comments, or the changes you want."
    )
    try:
        _integration(ctx, "github").call(
            "add-comment", ref=ctx.work_item.ref, body=body
        )
    except IntegrationError as exc:
        logger.warning("could not request review: %s", exc)
        return HookResult.ok(name, posted=False, error=str(exc))
    return HookResult.ok(name, posted=True)


def _recipients(ctx: HookContext, event: str) -> List[str]:
    """Roles for ``event`` — resolved only through notifications.events (R5.7)."""
    events = (ctx.config.get("notifications") or {}).get("events") or {}
    roles = events.get(event) or ctx.params.get("roles") or []
    return [str(r) for r in roles]


@hook("notify")
def notify(ctx: HookContext) -> HookResult:
    """Notify the configured roles. Never wedges the graph if a channel is down."""
    name = "notify"
    event = str(ctx.params.get("event") or "phase-approval-pending")
    roles = _recipients(ctx, event)
    if not roles:
        return HookResult.skipped(name, f"no roles configured for {event}")
    text = (
        f"the-loop: {ctx.work_item.id} is at *{ctx.node_id}* ({event}). "
        f"Roles: {', '.join(roles)}"
    )
    try:
        _integration(ctx, "slack").call("post-message", text=text)
    except IntegrationError as exc:
        logger.warning("notification not delivered: %s", exc)
        return HookResult.ok(name, delivered=False, roles=roles, error=str(exc))
    return HookResult.ok(name, delivered=True, roles=roles)
