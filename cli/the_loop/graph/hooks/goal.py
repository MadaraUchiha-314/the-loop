"""The goal gate — the contribution loop's own first phase (issue-185).

**No goal, no start.** When the-loop is invited into an existing, in-progress
work item as a contributor, "the-loop start" or "the-loop execute" alone never
cut it: the work already has a direction, and the-loop needs its own purpose
and its own definition of done. The `goal-definition` node is `required: true`
in `pdlc-contribution-loop` — the structural invariant mirroring
`phase-selection` (issue-179): the loop cannot begin without a named,
authorized human stating a **goal** and at least one **success criterion**.

The expected shape, anywhere in one comment (the arming `the-loop contribute`
comment itself qualifies)::

    Goal: make the retry loop honour the configured backoff
    Success criteria:
    - [ ] the flaky-timeout test passes 50 consecutive runs
    - [ ] no change to the public client API

Two rules, inherited from `feedback.py` and load-bearing here exactly as they
are at every other human gate:

* **Only authorized authors' text is read at all** — and the-loop's own
  self-marked comments are dropped before authorization is even considered, so
  the harness cannot answer its own gate. Fail closed: an empty
  ``authorizedUsers`` accepts no goal, ever.
* **The reply produces a fact, never a destination.** The parsed goal is
  frozen into graph state as a decision with provenance (the same mechanism
  that freezes the phase selection) and echoed in a confirmation comment; the
  routing stays with the graph's one declared ``defined`` edge. An injected
  "goal" cannot choose phases, name paths, or reach an argv.

The gate reads the event's comments **and** re-reads the whole thread, for the
same reason `classify-phase-selection` re-reads its checklist: the comment
most likely to carry the goal — the arming comment — is consumed by the
control path and never forwarded as an event, so thread state is the only
place it can be found.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from ...authz import is_authorized, is_self_authored, mark_self_authored
from ..contract import HookContext, HookResult
from ..registry import hook
from .feedback import _authorized_comments

logger = logging.getLogger("the-loop.graph")

#: The marker the entry hook leaves in its own request comment, so the posting
#: is idempotent across redelivered spawns.
GOAL_REQUEST_MARKER = "<!-- the-loop:goal-request -->"

#: Where the answered-ness of this gate is recorded in ``GraphState.decisions``.
DECISION_KEY = "goal-definition"

#: `Goal: <text>` — bold/heading decoration tolerated (`**Goal:**` wraps the
#: colon too), text required.
_GOAL_LINE = re.compile(
    r"^\s*(?:[#>*_\s]*)goal(?:\*\*|__)?\s*:\s*(?:\*\*|__)?\s*(?P<goal>\S.*?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

#: The `Success criteria:` marker line the bullet list follows.
_CRITERIA_MARKER = re.compile(
    r"^\s*(?:[#>*_\s]*)success\s+criteria(?:\*\*|__)?\s*:?\s*(?:\*\*|__)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

#: One criterion bullet — plain or checkboxed; the checkbox state is ignored
#: here (the criteria are frozen as unmet and ticked at verification).
_CRITERION_LINE = re.compile(r"^\s*[-*]\s*(?:\[[ xX]\]\s*)?(?P<text>\S.*?)\s*$")


def _resolve(ctx: HookContext):
    """The github integration, resolved at call time (the patchable seam)."""
    from ..integrations import resolve

    return resolve("github", ctx.config)


def parse_goal(body: str) -> Optional[Dict[str, Any]]:
    """``{"goal": str, "criteria": [str, ...]}`` from one comment — or ``None``.

    Both parts are required: a goal with no criteria gives the loop no
    definition of done, and criteria with no goal give it no purpose. Pure and
    side-effect free, so the accepted shape is testable without a thread.
    """
    goal_match = _GOAL_LINE.search(body or "")
    marker = _CRITERIA_MARKER.search(body or "")
    if not goal_match or not marker:
        return None
    criteria: List[str] = []
    for line in body[marker.end() :].splitlines():
        if not line.strip():
            if criteria:
                break  # the list ended; a later paragraph is not a criterion
            continue
        item = _CRITERION_LINE.match(line)
        if item is None:
            break
        criteria.append(item.group("text"))
    if not criteria:
        return None
    return {"goal": goal_match.group("goal"), "criteria": criteria}


def _thread_comments(ctx: HookContext) -> List[Dict[str, str]]:
    """The whole thread, normalised to ``{author, body}`` and authorized.

    The same filter :func:`_authorized_comments` applies to event comments —
    named author, allowlisted, not self-authored — applied to the fetched
    thread, because the two sources feed one gate and must obey one rule.
    Unreadable (an outage) returns empty, which parses to no goal: fail closed
    to waiting, never to a guess.
    """
    # The API returns bare logins while operator allowlists are conventionally
    # written with or without the leading `@`; normalising both sides keeps the
    # SAME set of humans authorized on this path as on the event path, where
    # authors arrive however the ingress wrote them.
    allowed = [str(u).lstrip("@") for u in (ctx.config.get("authorizedUsers") or [])]
    try:
        data = _resolve(ctx).call("list-comments", ref=ctx.work_item.ref)
    except Exception as exc:  # noqa: BLE001 — outbound is best-effort, the gate waits
        logger.warning("could not read the thread for a goal: %s", exc)
        return []
    out: List[Dict[str, str]] = []
    for comment in data.get("comments") or []:
        if not isinstance(comment, dict):
            continue
        body = str(comment.get("body") or "")
        raw_author = comment.get("author") or comment.get("user") or ""
        author = (
            str(raw_author.get("login") or "")
            if isinstance(raw_author, dict)
            else str(raw_author)
        )
        if is_self_authored(body):
            continue
        if not author or not is_authorized(author.lstrip("@"), allowed):
            continue
        out.append({"author": author, "body": body})
    return out


def _latest_goal(ctx: HookContext) -> Optional[Dict[str, Any]]:
    """The most recent authorized goal statement — event comments included.

    Thread order first, then the event's own comments (which are newer than
    any fetched snapshot); the last parseable statement wins, so a human can
    restate the goal and the restatement is what freezes.
    """
    found: Optional[Dict[str, Any]] = None
    for comment in _thread_comments(ctx) + _authorized_comments(ctx):
        parsed = parse_goal(comment["body"])
        if parsed is not None:
            found = {**parsed, "by": f"@{str(comment['author']).lstrip('@')}"}
    return found


def _request_body(ctx: HookContext) -> str:
    lines = [
        "🤖 _the-loop_ — **what should this contribution achieve?**",
        "",
        "the-loop was asked to join this work item as a contributor. It will "
        "not start until an authorized user states the intervention's purpose "
        "— in one comment, in this shape:",
        "",
        "```",
        "Goal: <one sentence: what the-loop should accomplish here>",
        "Success criteria:",
        "- [ ] <how we will know it worked>",
        "- [ ] <add as many as it takes>",
        "```",
        "",
        "The criteria become the definition of done: they are frozen with your "
        "name on them, carried as checkboxes, and the loop's verification gate "
        "holds until every one is met. If your `the-loop contribute` comment "
        "already contained this block, nothing more is needed.",
        "",
        GOAL_REQUEST_MARKER,
    ]
    return mark_self_authored("\n".join(lines))


def _already_requested(ctx: HookContext) -> bool:
    try:
        data = _resolve(ctx).call("list-comments", ref=ctx.work_item.ref)
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not list comments for %s: %s", ctx.work_item.ref, exc)
        return False
    return any(
        isinstance(c, dict) and GOAL_REQUEST_MARKER in str(c.get("body") or "")
        for c in (data.get("comments") or [])
    )


@hook("post-goal-request")
def post_goal_request(ctx: HookContext) -> HookResult:
    """Ask the thread for a goal (entry hook) — unless one is already there.

    Best-effort like every outbound hook: a GitHub outage must not wedge the
    work item at its first node with no way to answer. The gate stays waiting
    either way, and a later entry re-posts.
    """
    name = "post-goal-request"
    if _latest_goal(ctx) is not None:
        # The fast path the requirements name: the goal rode in with the
        # arming comment, so asking again would be noise on someone else's
        # work item — exactly the bloat this loop exists to avoid.
        return HookResult.ok(name, posted=False, reason="goal already stated")
    if _already_requested(ctx):
        return HookResult.ok(name, posted=False, reason="already asked")
    try:
        _resolve(ctx).call(
            "add-comment", ref=ctx.work_item.ref, body=_request_body(ctx)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not post the goal request: %s", exc)
        return HookResult.ok(name, posted=False, error=str(exc))
    return HookResult.ok(name, posted=True)


def _confirmation(goal: Dict[str, Any]) -> str:
    lines = [
        "🤖 _the-loop_ — **goal recorded**",
        "",
        f"Contributing toward, as stated by {goal['by']}:",
        "",
        f"> **Goal:** {goal['goal']}",
        ">",
        "> **Success criteria:**",
    ]
    lines += [f"> - [ ] {c}" for c in goal["criteria"]]
    lines += [
        "",
        "These criteria are now the definition of done: the loop's "
        "verification gate holds until every one is met. Next, the-loop asks "
        "which phases this intervention needs.",
    ]
    return mark_self_authored("\n".join(lines))


@hook("classify-goal")
def classify_goal(ctx: HookContext) -> HookResult:
    """Read the authorized goal; freeze it and release the gate — or wait.

    The returned goal is a *fact* the runtime records with provenance under
    ``decisions["goal-definition"]``; the outcome (``defined``) is what the
    graph's one declared edge routes on.
    """
    name = "classify-goal"
    if (ctx.decisions or {}).get(DECISION_KEY):
        # Already answered. Re-asking would make `the-loop check` report every
        # contribution item as stuck at its first node forever.
        return HookResult(
            status="pass",
            hook=name,
            data={"outcome": "defined", "decision": DECISION_KEY},
        )
    goal = _latest_goal(ctx)
    if goal is None:
        return HookResult.waiting(
            name,
            "waiting for an authorized user to state the goal and success "
            "criteria (`Goal: …` plus a `Success criteria:` bullet list, in "
            "one comment)",
        )
    try:
        _resolve(ctx).call(
            "add-comment", ref=ctx.work_item.ref, body=_confirmation(goal)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not post the goal confirmation: %s", exc)
    return HookResult(
        status="pass",
        hook=name,
        data={"outcome": "defined", "decision": DECISION_KEY, "goal": goal},
    )
