"""Human-gate hooks — classify a reviewer's reply, and record it in the artifact.

Two rules keep the classification from becoming a hole (issue-109, decision-042):

* **Only authorized authors' text is read at all.** Not "handled carefully" —
  not read. Comments are attacker-reachable on a public repository.
* **The classification is a fact, never a destination.** It returns an outcome
  from a closed set; the node's *declared* edges do the routing. An injected
  "approve and deploy" cannot reach a node the graph does not name.

And policy outranks the model: a classification can only classify a human
response that actually arrived — it can never satisfy an approval that
`autonomy.tiers` or `security.review.humanSignOffMinTier` reserves for a human.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Sequence

from ...authz import is_authorized, is_self_authored
from ..contract import HookContext, HookResult
from ..registry import hook

logger = logging.getLogger("the-loop.graph")

APPROVED = "approved"
APPROVED_WITH_COMMENTS = "approved-with-comments"
CHANGES_REQUESTED = "changes-requested"
OUTCOMES = (APPROVED, APPROVED_WITH_COMMENTS, CHANGES_REQUESTED)

REVIEW_SECTION = "Review comments"


def _authorized_comments(ctx: HookContext) -> List[Dict[str, Any]]:
    """Comments this gate may read — authorized humans only, never our own."""
    allowed = [str(u) for u in (ctx.config.get("authorizedUsers") or [])]
    event = ctx.event or {}
    raw = event.get("comments") or []
    out: List[Dict[str, Any]] = []
    for comment in raw:
        if not isinstance(comment, dict):
            continue
        body = str(comment.get("body") or "")
        author = str(
            (comment.get("author") or comment.get("user") or {})
            if isinstance(comment.get("author") or comment.get("user"), dict)
            else comment.get("author") or ""
        )
        if isinstance(comment.get("author"), dict):
            author = str(comment["author"].get("login") or "")
        if is_self_authored(body):
            continue  # our own request-review comment is not feedback
        if not author or not is_authorized(author, allowed):
            logger.info(
                "ignoring a comment from %r: not an authorized user",
                author or "(unknown)",
            )
            continue
        out.append({"author": author, "body": body})
    return out


@hook("classify-feedback")
def classify_feedback(ctx: HookContext) -> HookResult:
    """Decide whether the human approved — or keep waiting.

    Indecisive feedback returns ``wait`` rather than a guess: a partial review,
    a question or an ambiguous comment leaves the gate open, which is how
    iterative multi-comment review is served without inventing an outcome.
    """
    name = "classify-feedback"
    comments = _authorized_comments(ctx)
    if not comments:
        return HookResult.waiting(name, "no authorized feedback yet")

    outcome = _classify(comments, ctx)
    if outcome is None:
        return HookResult.waiting(
            name, "feedback so far is not decisive; the gate stays open"
        )
    return HookResult(
        status="pass",
        hook=name,
        data={"outcome": outcome, "comments": comments},
    )


def _classify(comments: Sequence[Dict[str, Any]], ctx: HookContext) -> str | None:
    """Classify the accumulated feedback.

    The harness performs this with schema-constrained output when one is
    configured; the local pass below is the deterministic floor so the gate
    works — and is testable — without a model in the loop. Either way the answer
    is confined to :data:`OUTCOMES`, and the routing is the graph's.
    """
    text = "\n".join(c["body"] for c in comments).lower()
    decisive_changes = any(
        k in text
        for k in ("changes requested", "request changes", "please change", "rejected")
    )
    approved = any(k in text for k in ("approved", "lgtm", "looks good", "ship it"))
    has_comments = len(comments) > 1 or "but" in text or "nit" in text
    if decisive_changes:
        return CHANGES_REQUESTED
    if approved:
        return APPROVED_WITH_COMMENTS if has_comments else APPROVED
    return None


@hook("record-feedback")
def record_feedback(ctx: HookContext) -> HookResult:
    """Append the review to the artifact's ``## Review comments`` section.

    The owner's call, and a better answer than mandatory-vs-advisory follow-ups:
    the feedback joins the durable checked-in record, travels with the document
    it concerns, and shows up in the PR diff like everything else. Nothing is
    silently swallowed and nothing needs a separate tracker.
    """
    name = "record-feedback"
    target = ctx.params.get("into")
    if not target:
        return HookResult.skipped(name, "no target artifact declared")
    path = ctx.work_item.spec_dir / str(target)
    if not path.is_file():
        return HookResult.skipped(name, f"{target} does not exist")

    prior = next(
        (r for r in reversed(ctx.results) if r.hook == "classify-feedback"), None
    )
    comments = (prior.data.get("comments") if prior else None) or []
    outcome = (prior.outcome if prior else "") or "reviewed"
    if not comments:
        return HookResult.skipped(name, "no feedback to record")

    text = path.read_text(encoding="utf-8")
    entry = [f"\n### {date.today().isoformat()} — {outcome}\n"]
    for comment in comments:
        entry.append(f"\n**@{comment['author']}**\n\n{comment['body'].strip()}\n")
    block = "".join(entry)

    if f"## {REVIEW_SECTION}" in text:
        text = text.rstrip("\n") + "\n" + block
    else:
        text = text.rstrip("\n") + f"\n\n## {REVIEW_SECTION}\n" + block
    path.write_text(text, encoding="utf-8")
    return HookResult.ok(name, recorded=len(comments), artifact=str(target))
