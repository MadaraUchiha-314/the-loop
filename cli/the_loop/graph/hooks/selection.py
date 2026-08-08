"""Phase selection — the work item's own first phase (issue-177).

**The loop asks which phases this work item needs, and an authorized human
answers on the ticket.** the-loop posts one checklist naming every phase; the
user replies with the list, unticking what this item does not need, and says
``the-loop execute``. Only then does the graph start walking the phases.

Why a comment rather than a label (owner's call, PR #178 review). A label rides
GitHub's *own* permission model, which is not the-loop's: the loop already knows
who may direct it — `routing.authorizedUsers`, the same boundary `the-loop
start` and every human gate answer to — and a label channel would have quietly
introduced a second, weaker one. Labels also have to be created in every
consuming repository before they can be used, which is setup work for a
mechanism that should just be a conversation.

**Ticking happens in place, and the reply is the signature** (owner's call, PR
#178). The user ticks boxes on the-loop's own comment — the natural ergonomics —
and then an *authorized* user says the execute keyword. GitHub cannot tell us who
edited a comment, so the tick state alone would be an unattributable
instruction; what makes it authorized is that a named, allowlisted human says
"execute" over it. At that moment the selection is **frozen**: the resolved
graph is written to the work item's state and pushed to the portable session
record, so what the loop will walk is a recorded fact rather than a live comment
anyone can keep editing. A checklist inside the execute comment itself wins over
the boxes, for anyone who prefers to be explicit.

Two rules, inherited from `feedback.py` and load-bearing here:

* **Only an authorized author may execute.** The same `authorizedUsers` boundary
  every human gate uses, and the-loop's own self-marked comments are dropped
  before authorization is even considered — so the harness cannot answer its own
  gate.
* **The reply produces a fact, never a destination.** It yields the set of
  phases to skip, filtered against the graph's own `skippable` vocabulary;
  protected phases named in a reply are refused and said so out loud.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple

from ...authz import mark_self_authored
from ..contract import HookContext, HookResult
from ..registry import hook
from .feedback import _authorized_comments

logger = logging.getLogger("the-loop.graph")

#: What an authorized user says once the checklist is filled in — the DEFAULT;
#: the operator's `routing.control.keywords.execute` wins where it is set
#: (issue-177, owner review), because this is a control word like `start` and
#: belongs to the same configurable vocabulary.
EXECUTE_KEYWORD = "the-loop execute"


def _execute_keyword(ctx: HookContext) -> str:
    configured = str((ctx.config or {}).get("executeKeyword") or "").strip()
    return configured or EXECUTE_KEYWORD


#: `- [x] design` / `- [ ] design` — one phase line of the checklist. The token
#: is a node id, so what the user reads is what the graph routes on.
_CHECK_LINE = re.compile(
    r"^\s*[-*]\s*\[(?P<mark>[ xX])\]\s*`?(?P<token>[A-Za-z0-9][A-Za-z0-9._-]*)`?",
    re.MULTILINE,
)

#: The marker the entry hook leaves in its own comment, so the posting is
#: idempotent across redelivered spawns: a second entry finds it and does not
#: post a duplicate checklist.
SELECTION_MARKER = "<!-- the-loop:phase-selection -->"

#: Where the answered-ness of this gate is recorded in ``GraphState.decisions``.
DECISION_KEY = "phase-selection"


def _resolve(ctx: HookContext):
    """The github integration, resolved at call time.

    Imported inside the function on purpose: a module-level ``from ..
    integrations import resolve`` binds the name here, so the seam every other
    caller (and every test) patches would silently not apply to this module.
    """
    from ..integrations import resolve

    return resolve("github", ctx.config)


def _phase_rows(ctx: HookContext) -> Tuple[List[str], List[str]]:
    """(skippable, protected) node ids of the loop this work item is walking.

    Read from **the runtime's own compiled graph** (``ctx.graph``), never a
    re-loaded shipped default: the checklist a user sees, the vocabulary their
    reply is validated against and the nodes the pointer will route around must
    be one list, and they differ between the outer loop, the inner PR loop and
    any graph a caller passed in. With no graph in context there is nothing
    truthful to offer, so both lists are empty and the gate simply asks for
    `the-loop execute`.
    """
    graph = ctx.graph
    if graph is None:
        return [], []
    skippable = [n.id for n in graph.ordered() if n.skippable]
    # Every non-skippable node the item will actually walk — deliberately NOT
    # filtered by `phase`: most of the review chain (`security-review`,
    # `human-approval`, …) carries no phase label, and listing only the ones
    # that do would under-report the floor to the very person deciding how
    # light this work item gets to be.
    protected = [
        n.id
        for n in graph.ordered()
        if not n.skippable and not n.terminal and n.id != ctx.node_id
    ]
    return skippable, protected


def _checklist_body(ctx: HookContext) -> str:
    skippable, protected = _phase_rows(ctx)
    keyword = _execute_keyword(ctx)
    lines = [
        "🤖 _the-loop_ — **which phases does this work item need?**",
        "",
        "Before the loop starts, tell it what this item actually needs. "
        "**Untick anything this work item does not need — right here on this "
        f"comment — then reply `{keyword}`.** The tick state at that moment is "
        "frozen and becomes the graph this item walks.",
        "",
    ]
    lines += [f"- [x] {node}" for node in skippable]
    lines += [""]
    if protected:
        lines += [
            "These phases always run and are not selectable — they are what keeps "
            "a lighter work item honest:",
            "",
        ]
        lines += [f"- {node}" for node in protected]
        lines += [""]
    lines += [
        "A doc fix usually needs none of the selectable phases; a feature "
        f"usually needs all of them. Reply `{keyword}` with the boxes untouched "
        "to run the full process.",
        "",
        f"You can also put the list in the reply itself — a checklist in the "
        f"`{keyword}` comment wins over the boxes above. Either way the "
        "**authorization is your reply**: the tick state is a proposal, and "
        "saying the keyword is what makes it yours.",
        "",
        SELECTION_MARKER,
    ]
    return mark_self_authored("\n".join(lines))


def _already_posted(ctx: HookContext) -> bool:
    """Has this work item's checklist already gone up? (idempotent entry)"""
    try:
        data = _resolve(ctx).call("list-comments", ref=ctx.work_item.ref)
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not list comments for %s: %s", ctx.work_item.ref, exc)
        return False
    for comment in data.get("comments") or []:
        if isinstance(comment, dict) and SELECTION_MARKER in str(
            comment.get("body") or ""
        ):
            return True
    return False


@hook("post-phase-selection")
def post_phase_selection(ctx: HookContext) -> HookResult:
    """Ask the ticket which phases this work item needs (entry hook).

    Best-effort like every other outbound hook: a GitHub outage must not wedge
    the work item at its first node with no way to answer. The gate stays
    waiting either way, and a later entry re-posts.
    """
    name = "post-phase-selection"
    if _already_posted(ctx):
        return HookResult.ok(name, posted=False, reason="already asked")
    try:
        _resolve(ctx).call(
            "add-comment", ref=ctx.work_item.ref, body=_checklist_body(ctx)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not post the phase-selection checklist: %s", exc)
        return HookResult.ok(name, posted=False, error=str(exc))
    return HookResult.ok(name, posted=True)


def _checklist_state(ctx: HookContext) -> str:
    """The CURRENT body of the-loop's own checklist comment, ticks and all.

    This is the tick-in-place channel: whatever the boxes say at the moment an
    authorized user says the execute keyword. Unreadable or missing (an outage,
    a deleted comment) returns empty, which parses to no skips — fail-closed to
    the full process, never to a lighter one.
    """
    try:
        data = _resolve(ctx).call("list-comments", ref=ctx.work_item.ref)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read the checklist's tick state: %s", exc)
        return ""
    for comment in reversed(list(data.get("comments") or [])):
        if isinstance(comment, dict) and SELECTION_MARKER in str(
            comment.get("body") or ""
        ):
            return str(comment.get("body") or "")
    return ""


def _frozen_graph(ctx: HookContext, skips: List[str]) -> Dict[str, Any]:
    """The graph this work item will actually walk, as a record.

    The owner's third requirement (PR #178): *"The graph that's executed also
    needs to be stored in the portable part of the tracking of work items."*
    Every node in declaration order with whether it is walked or skipped — so
    the frozen shape can be read back without re-deriving it from a comment
    thread, and a reviewer can see what was agreed at selection time.
    """
    graph = ctx.graph
    nodes = []
    if graph is not None:
        for node in graph.ordered():
            nodes.append(
                {
                    "id": node.id,
                    "phase": node.phase,
                    "skipped": node.id in skips,
                    "selectable": bool(node.skippable),
                }
            )
    return {
        "loop": getattr(graph, "name", "") or "",
        "workItem": ctx.work_item.id,
        "nodes": nodes,
    }


def _parse_selection(
    body: str, skippable: List[str], protected: List[str]
) -> Tuple[List[str], List[str]]:
    """(skips, refused) from one reply's checklist.

    An **unticked** skippable phase is a skip. An unticked protected phase is
    refused and named back — silently running a phase the user asked to drop
    would be as bad as silently dropping one they asked to keep. A phase the
    reply never mentions is simply kept: the selection can only remove what it
    explicitly unticks, so a truncated or partial list fails closed toward more
    process.
    """
    skips: List[str] = []
    refused: List[str] = []
    for match in _CHECK_LINE.finditer(body):
        if match.group("mark").strip():  # ticked → the phase runs
            continue
        token = match.group("token")
        if token in skippable:
            if token not in skips:
                skips.append(token)
        elif token in protected and token not in refused:
            refused.append(token)
    return skips, refused


def _confirmation(
    ctx: HookContext, actor: str, skips: List[str], refused: List[str]
) -> str:
    lines = ["🤖 _the-loop_ — **phase selection recorded**", ""]
    if skips:
        lines += [
            f"Skipping, as declared by @{actor}: " + ", ".join(f"`{s}`" for s in skips),
            "",
            "These are declarations, not verdicts: `the-loop check` reports each "
            "as *skipped by declaration*, and every other phase still gates this "
            "work item.",
        ]
    else:
        lines.append(f"@{actor} kept every phase — the full process runs.")
    if refused:
        lines += [
            "",
            "**Refused** (these phases are not selectable and will run): "
            + ", ".join(f"`{r}`" for r in refused),
        ]
    lines += ["", "Starting the loop."]
    return mark_self_authored("\n".join(lines))


@hook("classify-phase-selection")
def classify_phase_selection(ctx: HookContext) -> HookResult:
    """Read the authorized reply; produce the skip set and release the gate.

    Waits — never guesses — until an authorized user's reply carries
    the configured execute keyword. The returned ``declaredSkips`` is a *fact* the
    runtime records with provenance; the outcome (``selected``) is what the
    graph's declared edge routes on.
    """
    name = "classify-phase-selection"
    if (ctx.decisions or {}).get(DECISION_KEY):
        # Already answered, days or commits ago. The skips it produced are in
        # graph state; re-asking would make `the-loop check` report every work
        # item as stuck at its first node forever.
        return HookResult(
            status="pass",
            hook=name,
            data={"outcome": "selected", "decision": DECISION_KEY},
        )
    keyword = _execute_keyword(ctx)
    comments = _authorized_comments(ctx)
    decisive = [c for c in comments if keyword.lower() in str(c["body"]).lower()]
    if not decisive:
        return HookResult.waiting(
            name,
            "waiting for an authorized user to choose the phases and reply "
            f"`{keyword}`",
        )

    reply = decisive[-1]  # the latest instruction wins
    skippable, protected = _phase_rows(ctx)
    # The execute comment's own checklist is explicit and wins; otherwise the
    # tick state of our checklist comment at THIS moment is the selection, and
    # saying the keyword is what makes it the replier's own.
    source = "reply"
    body = str(reply["body"])
    if not _CHECK_LINE.search(body):
        body, source = _checklist_state(ctx), "checklist"
    skips, refused = _parse_selection(body, skippable, protected)
    actor = str(reply["author"]).lstrip("@")

    try:
        _resolve(ctx).call(
            "add-comment",
            ref=ctx.work_item.ref,
            body=_confirmation(ctx, actor, skips, refused),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not post the selection confirmation: %s", exc)

    declared: Dict[str, Any] = {
        node: {"via": "selection", "token": node, "by": f"@{actor}", "reason": ""}
        for node in skips
    }
    return HookResult(
        status="pass",
        hook=name,
        data={
            "outcome": "selected",
            "declaredSkips": declared,
            "refused": refused,
            "decision": DECISION_KEY,
            "frozenGraph": _frozen_graph(ctx, skips),
            "selectionSource": source,
        },
    )
