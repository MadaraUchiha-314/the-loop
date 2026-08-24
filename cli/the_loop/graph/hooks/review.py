"""The brief gate — the review loop's own first phase (issue-279).

**No brief, no review.** When the-loop is asked to review a pull request,
"the-loop review" alone never cuts it: a review that does not know what the
reviewer cares about answers nothing. The `review-brief` node is
`required: true` in `pdlc-review-loop` — the structural mirror of the
contribution loop's `goal-definition` (issue-185): the loop cannot begin
without a named, authorized human stating the brief.

The expected shape, anywhere in one comment (the arming `the-loop review`
comment itself qualifies) — at least one section with at least one bullet,
drop the sections you don't need::

    Questions:
    - does the retry change alter the public client API?
    Angles:
    - concurrency around the session registry
    Validations:
    - run the poller integration suite against this branch

Two rules, inherited from `feedback.py` and load-bearing here exactly as they
are at every other human gate:

* **Only authorized authors' text is read at all** — and the-loop's own
  self-marked comments are dropped before authorization is even considered, so
  the harness cannot brief its own review. Fail closed: an empty
  ``authorizedUsers`` accepts no brief, ever.
* **The reply produces a fact, never a destination.** The parsed brief is
  frozen into graph state as a decision with provenance (the same mechanism
  that freezes the contribution goal) and echoed in a confirmation comment;
  the routing stays with the graph's one declared ``briefed`` edge. An
  injected "brief" cannot choose phases, name paths, or reach an argv — the
  session runs its ``Validations:`` under its ordinary untrusted-content
  rules, exactly as it reads the diff itself.

The gate reads the event's comments **and** re-reads the whole thread, for the
same reason ``classify-goal`` does: the comment most likely to carry the brief
— the arming comment — is consumed by the control path and never forwarded as
an event, so thread state is the only place it can be found.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from ...authz import mark_self_authored
from ..contract import HookContext, HookResult
from ..registry import hook
from .feedback import _authorized_comments
from .goal import _resolve, _thread_comments

logger = logging.getLogger("the-loop.graph")

#: The marker the entry hook leaves in its own template comment, so the posting
#: is idempotent across redelivered spawns.
BRIEF_REQUEST_MARKER = "<!-- the-loop:review-brief-request -->"

#: Where the answered-ness of this gate is recorded in ``GraphState.decisions``.
DECISION_KEY = "review-brief"

#: The three sections a brief may carry, in the order the issue names them:
#: the questions the reviewer has, the angles they are interested in, the
#: validations they want run.
SECTIONS = ("questions", "angles", "validations")

#: A section marker line — `Questions:` / `Angles:` / `Validations:`, with the
#: same bold/heading decoration tolerance the goal gate's markers have.
_SECTION_LINE = re.compile(
    r"^\s*(?:[#>*_\s]*)(?P<section>questions|angles|validations)"
    r"(?:\*\*|__)?\s*:?\s*(?:\*\*|__)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

#: One brief bullet — plain or checkboxed, checkbox state ignored.
_BULLET_LINE = re.compile(r"^\s*[-*]\s*(?:\[[ xX]\]\s*)?(?P<text>\S.*?)\s*$")

#: A template placeholder bullet (`- <what you want answered …>`), so the
#: posted template itself — quoted back, or filled only partially — never
#: parses as a brief through its own examples.
_PLACEHOLDER = re.compile(r"^<.*>$")


def _bullets(body: str, start: int) -> List[str]:
    """The bullet list following ``start``, stopping at the first non-bullet."""
    items: List[str] = []
    for line in body[start:].splitlines():
        if not line.strip():
            if items:
                break  # the list ended; a later paragraph is not a bullet
            continue
        item = _BULLET_LINE.match(line)
        if item is None:
            break
        text = item.group("text")
        if not _PLACEHOLDER.match(text):
            items.append(text)
    return items


def parse_brief(body: str) -> Optional[Dict[str, List[str]]]:
    """``{"questions": […], "angles": […], "validations": […]}`` — or ``None``.

    At least one of the three sections must carry at least one bullet; a
    reviewer states only what they need and the empty sections come back as
    empty lists. Pure and side-effect free, so the accepted shape is testable
    without a thread.
    """
    text = str(body or "")
    found: Dict[str, List[str]] = {section: [] for section in SECTIONS}
    matched = False
    for marker in _SECTION_LINE.finditer(text):
        matched = True
        section = marker.group("section").lower()
        found[section] = _bullets(text, marker.end()) or found[section]
    if not matched or not any(found[section] for section in SECTIONS):
        return None
    return found


def _latest_brief(ctx: HookContext) -> Optional[Dict[str, Any]]:
    """The most recent authorized brief — event comments included.

    Thread order first, then the event's own comments (which are newer than
    any fetched snapshot); the last parseable statement wins, so a reviewer
    can restate the brief and the restatement is what freezes.
    """
    found: Optional[Dict[str, Any]] = None
    for comment in _thread_comments(ctx) + _authorized_comments(ctx):
        parsed = parse_brief(comment["body"])
        if parsed is not None:
            found = {**parsed, "by": f"@{str(comment['author']).lstrip('@')}"}
    return found


def _request_body(ctx: HookContext) -> str:
    lines = [
        "🤖 _the-loop_ — **what should this review look at?**",
        "",
        "the-loop was asked to review this thread. It will not start until an "
        "authorized user states the review's brief — in one comment, in this "
        "shape (keep the sections you need, drop the rest; at least one bullet "
        "in at least one section):",
        "",
        "```",
        "Questions:",
        "- <what you want answered about this change>",
        "Angles:",
        "- <the perspectives to review from — correctness, security, "
        "performance, API shape, …>",
        "Validations:",
        "- <what to run or prove — commands, scenarios, invariants>",
        "```",
        "",
        "The brief becomes the review's contract: it is frozen with your name "
        "on it, every question gets an answer, every angle gets examined, and "
        "every validation gets run (or a stated reason it could not be). "
        "Follow-ups are welcome after each round; the review ends when you say "
        "it is done. If your `the-loop review` comment already contained this "
        "block, nothing more is needed.",
        "",
        BRIEF_REQUEST_MARKER,
    ]
    return mark_self_authored("\n".join(lines))


def _already_requested(ctx: HookContext) -> bool:
    try:
        data = _resolve(ctx).call("list-comments", ref=ctx.work_item.ref)
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not list comments for %s: %s", ctx.work_item.ref, exc)
        return False
    return any(
        isinstance(c, dict) and BRIEF_REQUEST_MARKER in str(c.get("body") or "")
        for c in (data.get("comments") or [])
    )


@hook("post-review-brief")
def post_review_brief(ctx: HookContext) -> HookResult:
    """Ask the thread for a brief (entry hook) — unless one is already there.

    Best-effort like every outbound hook: a GitHub outage must not wedge the
    review at its first node with no way to answer. The gate stays waiting
    either way, and a later entry re-posts.
    """
    name = "post-review-brief"
    if _latest_brief(ctx) is not None:
        # The fast path: the brief rode in with the arming comment, so asking
        # again would be noise on the thread under review.
        return HookResult.ok(name, posted=False, reason="brief already stated")
    if _already_requested(ctx):
        return HookResult.ok(name, posted=False, reason="already asked")
    try:
        _resolve(ctx).call(
            "add-comment", ref=ctx.work_item.ref, body=_request_body(ctx)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not post the review-brief request: %s", exc)
        return HookResult.ok(name, posted=False, error=str(exc))
    return HookResult.ok(name, posted=True)


def _confirmation(brief: Dict[str, Any]) -> str:
    lines = [
        "🤖 _the-loop_ — **review brief recorded**",
        "",
        f"Reviewing against, as stated by {brief['by']}:",
        "",
    ]
    titles = {
        "questions": "Questions",
        "angles": "Angles",
        "validations": "Validations",
    }
    for section in SECTIONS:
        items = brief.get(section) or []
        if not items:
            continue
        lines.append(f"> **{titles[section]}:**")
        lines += [f"> - {item}" for item in items]
        lines.append(">")
    if lines[-1] == ">":
        lines.pop()
    lines += [
        "",
        "This brief is now the review's contract. the-loop reviews the change "
        "against it and posts its findings here; reply with follow-ups for "
        "another round, or say the review is done to end it.",
    ]
    return mark_self_authored("\n".join(lines))


@hook("classify-review-brief")
def classify_review_brief(ctx: HookContext) -> HookResult:
    """Read the authorized brief; freeze it and release the gate — or wait.

    The returned brief is a *fact* the runtime records with provenance under
    ``decisions["review-brief"]``; the outcome (``briefed``) is what the
    graph's one declared edge routes on.
    """
    name = "classify-review-brief"
    if (ctx.decisions or {}).get(DECISION_KEY):
        # Already answered. Re-asking would make `the-loop check` report every
        # review item as stuck at its first node forever.
        return HookResult(
            status="pass",
            hook=name,
            data={"outcome": "briefed", "decision": DECISION_KEY},
        )
    brief = _latest_brief(ctx)
    if brief is None:
        return HookResult.waiting(
            name,
            "waiting for an authorized user to state the review brief "
            "(`Questions:` / `Angles:` / `Validations:` bullet lists — at "
            "least one section, in one comment)",
        )
    try:
        _resolve(ctx).call(
            "add-comment", ref=ctx.work_item.ref, body=_confirmation(brief)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not post the brief confirmation: %s", exc)
    return HookResult(
        status="pass",
        hook=name,
        data={"outcome": "briefed", "decision": DECISION_KEY, "brief": brief},
    )
