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

**Two defaults, one gate** (issue-188). Most selectable phases are *opt-out*:
ticked by default, and unticking one removes work. A phase the shipped graph
marks ``optIn`` is *opt-in*: rendered unticked in a section of its own, and it
runs only if somebody ticks it. Same authorization, same freeze, same
provenance — the difference is who has to act for the phase to run, which is why
the two are never mixed in one list. Leaving an opt-in row alone, or never
mentioning it, means it does not run; that is the fail-closed direction for a
phase that *adds* a review rather than gating one.

**The gate answers a second question too** (issue-183, owner's call on PR #184):
*where does this work item collaborate on the outer loop* — the work item
itself, or a pull request in this repository. It belongs here for the same
reason the phases do: it is a property of **this** work item, not of the
repository (one project has both a one-repo bugfix and a three-repo migration)
and not of the operator's machine. One box, signed by the same reply, frozen
into the same record. **The default is the work item** — leave the box alone and
the requirements, design and testing plan are iterated on the ticket, which is
what keeps a multi-repo item from opening a pull request that only ever holds a
discussion. The INNER loop has no such question: a pull request's loop runs on
that pull request.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

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

#: The two surfaces the outer loop can be collaborated on (issue-183), and the
#: one that applies when nobody says otherwise. `work-item` is the ticket —
#: GitHub issue or Jira — and is the DEFAULT: a work item only opens a pull
#: request in this repository when its author asks for one.
SURFACE_PULL_REQUEST = "pull-request"
SURFACE_WORK_ITEM = "work-item"
DEFAULT_SURFACE = SURFACE_WORK_ITEM

#: The checklist token that chooses the pull-request surface. Deliberately a
#: sentence rather than a bare word: it sits among phase rows, and a reader
#: unticking boxes must never wonder whether they are dropping a phase.
SURFACE_TOKEN = "outer-loop-on-pull-request"


def _resolve(ctx: HookContext):
    """The github integration, resolved at call time.

    Imported inside the function on purpose: a module-level ``from ..
    integrations import resolve`` binds the name here, so the seam every other
    caller (and every test) patches would silently not apply to this module.
    """
    from ..integrations import resolve

    return resolve("github", ctx.config)


def _phase_rows(ctx: HookContext) -> Tuple[List[str], List[str], List[str]]:
    """(default-on, opt-in, protected) node ids of the loop being walked.

    Read from **the runtime's own compiled graph** (``ctx.graph``), never a
    re-loaded shipped default: the checklist a user sees, the vocabulary their
    reply is validated against and the nodes the pointer will route around must
    be one list, and they differ between the outer loop, the inner PR loop and
    any graph a caller passed in. With no graph in context there is nothing
    truthful to offer, so the lists are empty and the gate simply asks for
    `the-loop execute`.

    Opt-in nodes (issue-188) are ``skippable`` too — they share the whole
    declared-skip mechanism — so they are split out here rather than listed
    twice under opposite defaults.
    """
    graph = ctx.graph
    if graph is None:
        return [], [], []
    opt_in = [n.id for n in graph.ordered() if n.opt_in]
    skippable = [n.id for n in graph.ordered() if n.skippable and not n.opt_in]
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
    return skippable, opt_in, protected


def _describe(ctx: HookContext, node_id: str) -> str:
    """The node's one-line ``description``, flattened for a checklist row."""
    graph = ctx.graph
    node = graph.nodes.get(node_id) if graph is not None else None
    return " ".join(str(getattr(node, "description", "") or "").split())


def _checklist_body(ctx: HookContext) -> str:
    skippable, opt_in, protected = _phase_rows(ctx)
    keyword = _execute_keyword(ctx)
    lines = [
        "🤖 _the-loop_ — **which phases does this work item need?**",
        "",
        "Before the loop starts, tell it what this item actually needs. "
        "**Untick anything this work item does not need"
        + (", tick anything optional it does want" if opt_in else "")
        + " — right here on this "
        f"comment — then reply `{keyword}`.** The tick state at that moment is "
        "frozen and becomes the graph this item walks.",
        "",
    ]
    lines += [f"- [x] {node}" for node in skippable]
    lines += [""]
    if opt_in:
        # The other default (issue-188). Rendered unticked, in a section of its
        # own, because a reader scanning boxes must never have to work out which
        # way a given row leans: above, unticking removes work; here, ticking
        # adds it.
        lines += [
            "**Optional phases — these do NOT run unless you tick them.** They "
            "are offered, not planned:",
            "",
        ]
        for node in opt_in:
            about = _describe(ctx, node)
            lines.append(f"- [ ] {node}" + (f" — {about}" if about else ""))
        lines += [""]
    if protected:
        lines += [
            "These phases always run and are not selectable — they are what keeps "
            "a lighter work item honest:",
            "",
        ]
        lines += [f"- {node}" for node in protected]
        lines += [""]
    elif skippable:
        # No protected rows is not an empty section — it is the loudest thing
        # this comment has to say (issue-179). The outer loop protects nothing
        # but this gate, so the honesty a floor used to provide now comes from
        # the reply being signed: say that, rather than printing nothing.
        lines += [
            "**Every phase of this loop is selectable — including the reviews, the "
            "security review and the approval gate.** Nothing but this question is "
            "mandatory, so each box you untick is an omission recorded against your "
            "name: in the work item's graph state, in a confirmation comment here, "
            "and in every `the-loop check` from now on.",
            "",
        ]
    lines += [
        "**Where should the outer loop happen?** This is not a phase — it is "
        "where the requirements, design, testing plan and task list are "
        "iterated with you:",
        "",
        f"- [ ] `{SURFACE_TOKEN}` — on a pull request in this repository.",
        "",
        "Leave it unticked (the default) and they happen **on this work item**, "
        "here. Tick it and they happen on a pull request instead. Either way "
        "the artifacts are committed files linked from here, and each "
        "repository this work item contributes code to gets its own pull "
        "request for the inner loop.",
        "",
        "A doc fix usually needs little more than implementation and "
        "verification; a feature usually needs every phase. Reply "
        f"`{keyword}` with the boxes untouched "
        "to run the full process"
        + (
            " — every phase above that is already ticked, and none of the "
            "optional ones."
            if opt_in
            else "."
        ),
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


def _frozen_graph(
    ctx: HookContext,
    skips: List[str],
    surface: str = DEFAULT_SURFACE,
    opt_ins: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """The graph this work item will actually walk, as a record.

    The owner's third requirement (PR #178): *"The graph that's executed also
    needs to be stored in the portable part of the tracking of work items."*
    Every node in declaration order with whether it is walked or skipped — so
    the frozen shape can be read back without re-deriving it from a comment
    thread, and a reviewer can see what was agreed at selection time.
    """
    graph = ctx.graph
    chosen = set(opt_ins or ())
    nodes = []
    if graph is not None:
        for node in graph.ordered():
            # An opt-in node nobody ticked is not walked either (issue-188) —
            # and the record says WHICH of the two it was, so a reader can tell
            # a phase nobody asked for from a phase somebody removed.
            skipped = node.id in skips or (node.opt_in and node.id not in chosen)
            nodes.append(
                {
                    "id": node.id,
                    "phase": node.phase,
                    "skipped": skipped,
                    "selectable": bool(node.skippable),
                    "optIn": bool(node.opt_in),
                }
            )
    return {
        "loop": getattr(graph, "name", "") or "",
        "workItem": ctx.work_item.id,
        "surface": surface,
        "nodes": nodes,
    }


def _parse_selection(
    body: str, skippable: List[str], opt_in: List[str], protected: List[str]
) -> Tuple[List[str], List[str], List[str]]:
    """(skips, opt-ins, refused) from one reply's checklist.

    An **unticked** skippable phase is a skip. An unticked protected phase is
    refused and named back — silently running a phase the user asked to drop
    would be as bad as silently dropping one they asked to keep. A default-on
    phase the reply never mentions is simply kept: the selection can only remove
    what it explicitly unticks, so a truncated or partial list fails closed
    toward more process.

    An **opt-in** phase inverts only the default (issue-188): ticked selects it,
    unticked does not, and one the reply never mentions is not selected either —
    which needs no code here, because a node absent from the returned list is
    default-skipped by the runtime. So a truncated reply, an unreadable comment
    and a deleted one all fail toward *off* for these, which is the closed
    direction for a phase that adds a review rather than gating one.
    """
    skips: List[str] = []
    opt_ins: List[str] = []
    refused: List[str] = []
    for match in _CHECK_LINE.finditer(body):
        token = match.group("token")
        if token == SURFACE_TOKEN:
            # Not a phase (issue-183). An unticked surface row means "the work
            # item", never "skip a node" — and it must not fall through to the
            # refused list either, or every default selection would report a
            # phase it never asked to drop.
            continue
        ticked = bool(match.group("mark").strip())
        if token in opt_in:
            if ticked and token not in opt_ins:
                opt_ins.append(token)
            continue
        if ticked:  # ticked → the phase runs
            continue
        if token in skippable:
            if token not in skips:
                skips.append(token)
        elif token in protected and token not in refused:
            refused.append(token)
    return skips, opt_ins, refused


def _parse_surface(body: str) -> str:
    """The chosen surface from one reply's checklist — the default otherwise.

    A **ticked** surface row asks for the pull request; unticked, absent, or a
    body the-loop could not read all mean the default (the work item). Failing
    to the work item is the safe direction: it opens nothing, and issue-183's
    whole complaint is the pull request that gets opened and never merged.
    """
    for match in _CHECK_LINE.finditer(body):
        if match.group("token") != SURFACE_TOKEN:
            continue
        return SURFACE_PULL_REQUEST if match.group("mark").strip() else DEFAULT_SURFACE
    return DEFAULT_SURFACE


def _confirmation(
    ctx: HookContext,
    actor: str,
    skips: List[str],
    refused: List[str],
    surface: str = DEFAULT_SURFACE,
    opt_ins: Optional[List[str]] = None,
    offered: Optional[List[str]] = None,
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
        lines.append(
            f"@{actor} kept every phase that runs by default — the full process runs."
        )
    # The opt-in half of the same answer (issue-188). An offered phase that
    # nobody chose is said out loud too: silence about it would be
    # indistinguishable from never having been offered it.
    if opt_ins:
        lines += [
            "",
            f"Also running, as @{actor} asked: "
            + ", ".join(f"`{o}`" for o in opt_ins)
            + " — optional phases, off unless selected.",
        ]
    elif offered:
        lines += [
            "",
            "Not running (offered, not selected): "
            + ", ".join(f"`{o}`" for o in offered)
            + ".",
        ]
    if refused:
        lines += [
            "",
            "**Refused** (these phases are not selectable and will run): "
            + ", ".join(f"`{r}`" for r in refused),
        ]
    lines += [
        "",
        (
            "The outer loop happens **on a pull request** in this repository, "
            f"as @{actor} chose."
            if surface == SURFACE_PULL_REQUEST
            else "The outer loop happens **here, on this work item** (the "
            "default). Each repository this item contributes code to gets its "
            "own pull request for the inner loop."
        ),
        "",
        "Starting the loop.",
    ]
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
    skippable, opt_in, protected = _phase_rows(ctx)
    # The execute comment's own checklist is explicit and wins; otherwise the
    # tick state of our checklist comment at THIS moment is the selection, and
    # saying the keyword is what makes it the replier's own.
    source = "reply"
    body = str(reply["body"])
    if not _CHECK_LINE.search(body):
        body, source = _checklist_state(ctx), "checklist"
    skips, opt_ins, refused = _parse_selection(body, skippable, opt_in, protected)
    surface = _parse_surface(body)
    actor = str(reply["author"]).lstrip("@")

    confirmation_error = ""
    try:
        _resolve(ctx).call(
            "add-comment",
            ref=ctx.work_item.ref,
            body=_confirmation(
                ctx, actor, skips, refused, surface, opt_ins=opt_ins, offered=opt_in
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not post the selection confirmation: %s", exc)
        # Recorded, not just logged (issue-194): the runtime reads `error` off a
        # passing result and reports it. The selection itself stands — it was
        # authorized and is about to be frozen into state — but the record of it
        # that a human would read never reached the ticket.
        confirmation_error = str(exc)

    declared: Dict[str, Any] = {
        node: {"via": "selection", "token": node, "by": f"@{actor}", "reason": ""}
        for node in skips
    }
    chosen: Dict[str, Any] = {
        node: {"via": "selection", "token": node, "by": f"@{actor}"} for node in opt_ins
    }
    return HookResult(
        status="pass",
        hook=name,
        data={
            "outcome": "selected",
            "declaredSkips": declared,
            "optIns": chosen,
            "refused": refused,
            "decision": DECISION_KEY,
            "surface": surface,
            "frozenGraph": _frozen_graph(ctx, skips, surface, opt_ins=opt_ins),
            "selectionSource": source,
            **({"error": confirmation_error} if confirmation_error else {}),
        },
    )
