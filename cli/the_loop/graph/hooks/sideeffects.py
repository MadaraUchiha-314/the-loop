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
from ..integrations import IntegrationError
from ..registry import hook

logger = logging.getLogger("the-loop.graph")

__all__ = [
    "log_entry",
    "notify",
    "publish_artifact",
    "request_review",
    "set_phase_label",
]


def _integration(ctx: HookContext, target: str):
    """The provider, resolved at call time.

    Imported inside the function for the reason ``selection.py`` spells out: a
    module-level ``from ..integrations import resolve`` binds the name *here*, so
    the seam every other caller and every test patches
    (``the_loop.graph.integrations.resolve``) silently did not apply to this
    module — which is how a test of ``set-phase-label`` reached the real GitHub
    API instead of its fake (issue-194).
    """
    from ..integrations import resolve

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


@hook("publish-artifact")
def publish_artifact(ctx: HookContext) -> HookResult:
    """Post an artifact's content to the work item's thread — the review surface
    of a repository that never adopted the-loop (issue-185, PR #187 review).

    In an initialized repository the artifact is checked in and reviewable
    there, so this hook does nothing — the gate comment (``request-review``)
    already points at it. In an **uninitialized** repository the spec tree is
    excluded from git (``Runtime.start``), so the file exists only in the
    working checkout and no human can see it: the thread is where the plan and
    its verification results must land. Re-posting on each entry is deliberate —
    a gate looped back through ``changes-requested`` shows the *revised*
    artifact, and each post is one comment the requester asked for, not bloat.

    Best-effort by contract: an outage or a missing file (planning declared
    away) records and continues — ``validate-artifacts`` remains the gate.
    """
    name = "publish-artifact"
    if ctx.config.get("repoInitialized") is not False:
        return HookResult.skipped(
            name, "the repository carries the artifact; it is reviewable there"
        )
    artifact = str(ctx.params.get("artifact") or "")
    if not artifact:
        return HookResult.skipped(name, "no artifact named")
    path = ctx.work_item.spec_dir / artifact
    if not path.is_file():
        return HookResult.skipped(name, f"no {artifact} for this work item")
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("could not read %s: %s", path, exc)
        return HookResult.ok(name, posted=False, error=str(exc))
    body = mark_self_authored(
        f"🤖 _the-loop_ — **`{artifact}`** for `{ctx.work_item.id}`.\n\n"
        "This repository does not carry the-loop's config, so the artifact is "
        "working state — kept out of git — and this comment is its review "
        "surface.\n\n---\n\n" + content
    )
    # Deliberately bound at call time, not import time (the goal/selection
    # hooks' rule): the test seam and any embedder patch
    # ``graph.integrations.resolve``, and a module-level binding would slip
    # past them.
    from ..integrations import resolve

    try:
        resolve("github", ctx.config).call(
            "add-comment", ref=ctx.work_item.ref, body=body
        )
    except IntegrationError as exc:
        logger.warning("could not publish %s: %s", artifact, exc)
        return HookResult.ok(name, posted=False, error=str(exc))
    return HookResult.ok(name, posted=True, artifact=artifact)


def _recipients(ctx: HookContext, event: str) -> List[str]:
    """Roles for ``event`` — resolved only through notifications.events (R5.7)."""
    events = (ctx.config.get("notifications") or {}).get("events") or {}
    roles = events.get(event) or ctx.params.get("roles") or []
    return [str(r) for r in roles]


@hook("notify")
def notify(ctx: HookContext) -> HookResult:
    """Notify the configured roles. Never wedges the graph if a channel is down.

    Posts through the **channels** layer (issue-245, owner's convergence call on
    PR #267): the graph's notification is one more outbound event, filtered by
    each channel's ``events`` allow-list — so an operator subscribes their Slack
    channel to ``phase-approval-pending`` and friends, and the reply path those
    channels carry works for notifications too. The incoming-webhook integration
    this hook used to call is gone (`the-loop migrate-config`).
    """
    name = "notify"
    event = str(ctx.params.get("event") or "phase-approval-pending")
    roles = _recipients(ctx, event)
    if not roles:
        return HookResult.skipped(name, f"no roles configured for {event}")
    text = (
        f"the-loop: {ctx.work_item.id} is at *{ctx.node_id}* ({event}). "
        f"Roles: {', '.join(roles)}"
    )
    # Call-time import, the `_integration` rule: the test seam and any embedder
    # patch the channels module, and a module-level binding would slip past them.
    from ...channels.broadcast import broadcast

    results = broadcast(event, ctx.work_item.ref, text, cli_config=ctx.config)
    if not results:
        return HookResult.skipped(
            name,
            f"no channel subscribed to {event} — add it to channels.slack.events",
        )
    delivered = any(result.ok for result in results)
    errors = "; ".join(result.error for result in results if not result.ok)
    if not delivered:
        logger.warning("notification not delivered: %s", errors)
        return HookResult.ok(name, delivered=False, roles=roles, error=errors)
    return HookResult.ok(name, delivered=True, roles=roles)
