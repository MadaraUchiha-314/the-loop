"""Human-gate hooks — classify a reviewer's reply, record it, lock the artifact.

Two rules keep the classification from becoming a hole (issue-109, decision-042):

* **Only authorized authors' text is read at all.** Not "handled carefully" —
  not read. Comments are attacker-reachable on a public repository.
* **The classification is a fact, never a destination.** It returns an outcome
  from a closed set; the node's *declared* edges do the routing. An injected
  "approve and deploy" cannot reach a node the graph does not name.

And policy outranks the model: a classification can only classify a human
response that actually arrived — it can never satisfy an approval that
`autonomy.tiers` or `security.review.humanSignOffMinTier` reserves for a human.

The third hook here, ``lock-artifacts``, is why an approval costs the human
exactly one reply (issue-281). Locking used to be demanded *before* the gate —
``validate-artifacts`` with ``locked: true`` on the producing node's exit — so
the session had to obtain an out-of-band approval to set ``status: approved``,
and the gate then discarded it ("only feedback posted while the gate is open")
and asked again. Now the gate itself is the locker: the same chain run that
classifies the human's approval writes ``status: approved`` and the approvers
into the artifact's front matter. One decision, one reply, one durable record.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ...authz import is_authorized, is_self_authored
from ..contract import HookContext, HookResult, Message
from ..frontmatter import split_front_matter
from ..model import resolve_produces
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
        # The attribution carries trailing text on purpose (issue-247): a line
        # that is emphasis and nothing else is what markdownlint's MD036 rejects,
        # so `**@handle**` alone left every approved artifact failing the lint the
        # same project is configured with. The body stays verbatim — the harness
        # fixes its own markdown, never a human's words.
        body = comment["body"].strip()
        if body:
            entry.append(f"\n**@{comment['author']}** wrote:\n\n{body}\n")
        else:
            entry.append(f"\n**@{comment['author']}** left no comment text.\n")
    block = "".join(entry)

    if f"## {REVIEW_SECTION}" in text:
        text = text.rstrip("\n") + "\n" + block
    else:
        text = text.rstrip("\n") + f"\n\n## {REVIEW_SECTION}\n" + block
    path.write_text(text, encoding="utf-8")
    return HookResult.ok(name, recorded=len(comments), artifact=str(target))


#: The classifications that lock. `changes-requested` routes backward and must
#: leave the artifact exactly as the reviewer found it.
_LOCKING_OUTCOMES = (APPROVED, APPROVED_WITH_COMMENTS)

_STATUS_LINE = re.compile(r"^(\s*status\s*:)([^#]*)(#.*)?$")
_APPROVED_BY_LINE = re.compile(r"^(\s*approvedBy\s*:)([^#]*)(#.*)?$")


def _quoted(values: Sequence[str]) -> str:
    """An inline YAML list of handles, quoted so no handle can alter the syntax."""
    return (
        "["
        + ", ".join('"' + v.replace("\\", "").replace('"', "") + '"' for v in values)
        + "]"
    )


def _locked_text(text: str, approvers: Sequence[str]) -> Optional[str]:
    """``text`` with its front matter saying ``status: approved`` and carrying
    ``approvers`` in ``approvedBy`` — or ``None`` when the block cannot be edited.

    A **splice**, not a round-trip (the yamlpatch rule): only the two value
    spans change, so the template's inline comments — the prose that tells the
    next author what the statuses mean — survive the lock.
    """
    front, _ = split_front_matter(text)
    prior = front.get("approvedBy")
    merged = [str(v) for v in prior] if isinstance(prior, list) else []
    merged += [a for a in approvers if a not in merged]

    if not text.startswith("---"):
        head = f"---\nstatus: approved\napprovedBy: {_quoted(merged)}\n---\n\n"
        return head + text

    lines = text.split("\n")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None  # unterminated block: nothing here can be edited safely

    status_at: Optional[int] = None
    for i in range(1, end):
        match = _STATUS_LINE.match(lines[i])
        if match:
            comment = match.group(3) or ""
            pad = (
                " " * max(len(match.group(2)) - len(" approved"), 1) if comment else ""
            )
            lines[i] = match.group(1) + " approved" + pad + comment
            status_at = i
            break
    if status_at is None:
        lines.insert(end, "status: approved")
        status_at = end
        end += 1

    for i in range(1, end):
        match = _APPROVED_BY_LINE.match(lines[i])
        if match:
            comment = match.group(3) or ""
            value = " " + _quoted(merged)
            pad = " " * max(len(match.group(2)) - len(value), 1) if comment else ""
            lines[i] = match.group(1) + value + pad + comment
            break
    else:
        lines.insert(status_at + 1, f"approvedBy: {_quoted(merged)}")

    return "\n".join(lines)


@hook("lock-artifacts")
def lock_artifacts(ctx: HookContext) -> HookResult:
    """Lock the gate's artifact(s) — the approval node's own act (issue-281).

    Runs after ``classify-feedback`` in the same exit chain and consumes its
    verdict from ``ctx.results``, exactly as ``record-feedback`` does: no second
    read of the comments, no second decision, and therefore no way for this hook
    to widen who can approve. Anything but an approval — ``changes-requested``,
    an undecided gate, no classification at all — is a skip, so the classifier
    keeps routing the edge.

    Fail closed on the write: a lock this hook cannot prove landed (unreadable
    file, unterminated front matter, an ambiguous artifact slot) blocks the
    gate rather than reporting an approval that was never durably recorded.
    """
    name = "lock-artifacts"
    declared = ctx.params.get("artifacts")
    if not declared:
        return HookResult.skipped(name, "no artifacts declared")
    prior = next(
        (r for r in reversed(ctx.results) if r.hook == "classify-feedback"), None
    )
    outcome = prior.outcome if prior else ""
    if outcome not in _LOCKING_OUTCOMES:
        return HookResult.skipped(
            name, f"no approval to lock on (classification: {outcome or 'none'})"
        )
    approvers = sorted(
        {
            str(c.get("author"))
            for c in ((prior.data.get("comments") if prior else None) or [])
            if isinstance(c, dict) and c.get("author")
        }
    )

    findings: List[Message] = []
    locked: List[str] = []
    for slot in resolve_produces(declared, ctx.work_item.spec_dir):
        present = list(slot.present)
        if not present:
            continue  # its authoring phase was declared away; absence is planned
        if len(present) > 1:
            findings.append(
                Message(
                    text=(
                        f"{len(present)} artifacts present where one is expected "
                        f"— keep one of: {slot.label()}"
                    ),
                    path=str(ctx.work_item.spec_dir),
                )
            )
            continue
        path: Path = present[0]
        try:
            updated = _locked_text(path.read_text(encoding="utf-8"), approvers)
            if updated is not None:
                path.write_text(updated, encoding="utf-8")
            front, _ = split_front_matter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(Message(text=f"could not lock: {exc}", path=path.name))
            continue
        # The yamlpatch property: prove the splice landed, or refuse to pass.
        recorded = front.get("approvedBy")
        if str(front.get("status", "")).strip() != "approved" or not all(
            a in ([str(v) for v in recorded] if isinstance(recorded, list) else [])
            for a in approvers
        ):
            findings.append(
                Message(
                    text=(
                        "the lock did not land — front matter still does not say "
                        "status: approved with the approvers recorded"
                    ),
                    path=path.name,
                )
            )
            continue
        locked.append(path.name)

    if findings:
        return HookResult.blocked(name, findings)
    if not locked:
        return HookResult.skipped(
            name, "every declared artifact is absent; nothing to lock"
        )
    return HookResult.ok(name, locked=locked, approvedBy=approvers)
