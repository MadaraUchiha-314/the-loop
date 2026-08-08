"""The graph assigns; the session works (issue-172, PR #173 review).

Everything else in the loop is the graph *judging* — gates over artifacts,
edges on outcomes. This hook is the graph *initiating*: on entering an agent
node it renders that node's assignment — where the work item stands, what to
produce, and exactly how to report back — and delivers it straight into the
session bound to the loop, without waiting for a GitHub event to carry it.
That closes the owner's "who is in charge?" arrow: graph assigns → session
works → session claims (`the-loop graph complete …`) → graph verdicts → graph
assigns the next node.

The hook itself owns none of the transport. The **daemon** injects a delivery
callable into the runtime's config (``assignmentDeliver``, bound by GraphLink
to the work item and — for an inner loop — its PR number); the callable is the
dispatcher's, which resolves the bound endpoint and pastes into its tmux
session. Where no callable is injected — ``the-loop graph complete`` run by
the session itself, ``the-loop check``, any CLI path — the hook skips: the
claiming session is already reading the command's JSON envelope, which names
the next node, so pushing a second copy at it would deliver every assignment
twice.

Best-effort by design: a failed delivery is reported and never blocks the
node. The assignment is convenience for the worker; the state it describes is
durable in ``graph-state.json`` and re-rendered into every event prompt, so a
lost paste costs a nudge, never the process.
"""

from __future__ import annotations

import logging

from ..contract import HookContext, HookResult
from ..registry import hook

logger = logging.getLogger("the-loop.graph")

__all__ = ["deliver_assignment", "render_assignment"]


def render_assignment(ctx: HookContext) -> str:
    """The assignment text for the node just entered — the graph's own voice.

    Composed only from the-loop's vocabulary (node fields and the work item's
    id); no event payload text can reach it.
    """
    node = ctx.node
    item_id = ctx.work_item.id
    pr_number = ctx.config.get("assignmentPr")
    scope = (
        f"pull request #{pr_number}'s pdlc-pr-loop on {item_id}"
        if pr_number is not None
        else item_id
    )
    lines = [
        f"the-loop assignment for {scope}:",
        f"  you are now at node: {ctx.node_id}"
        + (f" (phase: {node.get('phase')})" if node.get("phase") else ""),
    ]
    produces = [str(p) for p in (node.get("produces") or [])]
    if produces:
        lines.append(f"  produce: {', '.join(produces)}")
    if node.get("command"):
        lines.append(f"  work it with: `/the-loop:{node.get('command')} {item_id}`")
    if node.get("actor") == "human":
        # A human gate is announced, never assigned: the work here is somebody
        # else's, and a session told to "report back when done" at one would
        # claim a decision it does not get to make (issue-177 put the very
        # first node of the outer loop in this position).
        lines.append(
            "  this node is a HUMAN gate — the loop is waiting for an "
            "authorized person on the ticket. Do not claim it; do not start "
            "the work it gates."
        )
    else:
        claim_suffix = f" --pr {pr_number}" if pr_number is not None else ""
        lines.append(
            "  when this node's work is done, report back: "
            f"`the-loop graph complete {item_id}{claim_suffix}`"
        )
    lines.append("  (assigned by the-loop's graph — not part of any event payload)")
    return "\n".join(lines)


@hook("deliver-assignment")
def deliver_assignment(ctx: HookContext) -> HookResult:
    """Push the entered node's assignment into the loop's bound session.

    Skips without a delivery channel — that is not a failure, it is the CLI
    path, where the claiming session reads the same facts from the command's
    envelope. A channel that reports a failed delivery also yields a skip, with
    the reason: the assignment must never gate the node it announces.
    """
    name = "deliver-assignment"
    deliver = ctx.config.get("assignmentDeliver")
    if not callable(deliver):
        return HookResult.skipped(
            name, "no delivery channel (CLI path — the claim envelope carries this)"
        )
    text = render_assignment(ctx)
    try:
        delivered = bool(deliver(text))
    except Exception as exc:  # noqa: BLE001 — assignment push never gates the node
        logger.warning("assignment delivery for %s failed: %s", ctx.node_id, exc)
        return HookResult.skipped(name, f"delivery failed: {exc}")
    if not delivered:
        return HookResult.skipped(name, "no live session to deliver into")
    return HookResult.ok(name, delivered=True)
