"""The quiz gates — ``post-quiz-attestation`` and ``quiz-attested`` (issue-488).

``spec-quiz`` (before code generation) and ``code-quiz`` (before review is
requested) are HUMAN nodes: the agent node before each wrote an explainer and a
quiz and left a record naming where it was published; these two hooks then ask
the author to read it and take the quiz, and wait for them to say so.

**Ticking the box is the answer.** The entry hook posts one comment carrying a
single checkbox and a marker naming the node, its round and — for the spec quiz
— a digest of the spec files. The exit hook passes once that box is ticked by an
**authorized** user. Who ticked is read from GitHub's GraphQL edit history
(``userContentEdits``), never from the comment's author (the-loop) or a webhook
payload: phase-selection's "the reply is the signature" rule rested on REST
being unable to say who edited a comment (``selection.py``), which GraphQL can.
The latest edit decides; anything that cannot be attributed — no history, a
deleted account, a failed query — keeps the gate waiting (decision-143).

**A typed reply is the fallback.** An authorized comment that itself carries the
ticked attestation line passes too — Jira cannot say who edited a comment, and
a missed edit should never strand the author.

The quiz is self-attested by design: the-loop records *who said they took it*,
never a score.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple
from urllib.parse import urlparse

from ... import eventlog
from ...authz import is_authorized, is_self_authored, mark_self_authored
from ...quizmarks import (
    ATTESTATIONS,
    QUIZ_MARKER_PREFIX,
    READ_ONLY,
    UNVERIFIED,
    attestation_ticked,
    is_quiz_comment,
)
from ...quizmarks import quiz_marker as _marker
from ..contract import HookContext, HookResult, Message
from ..integrations.base import OperationUnsupported
from ..registry import hook

logger = logging.getLogger("the-loop.graph.quiz")

__all__ = [
    "ATTESTATIONS",
    "QUIZ_MARKER_PREFIX",
    "attestation_ticked",
    "is_quiz_comment",
    "spec_digest",
]

_TITLES = {"spec-quiz": "Spec quiz", "code-quiz": "Code quiz"}

_LOCATION = re.compile(r"^\|\s*Location\s*\|\s*(?P<value>[^|]+?)\s*\|\s*$", re.M)

_DEPTH = re.compile(r"^\|\s*Depth\s*\|\s*`?(?P<value>[a-z]+)`?\s*\|\s*$", re.M)

_GITHUB_BLOB = re.compile(
    r"^/(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/(?P<branch>[^/]+)/(?P<path>.+)$"
)

_SAFE = re.compile(r"^[A-Za-z0-9._/-]+$")


# --------------------------------------------------------------------- parsing


def spec_digest(spec_dir: Path, names: Sequence[str]) -> str:
    """The first 12 hex of sha256 over the named files' bytes, in order.

    ``a|b`` names one artifact by either of its accepted names (the first that
    exists counts); an absent artifact contributes nothing. No file at all is
    ``-`` — there is nothing to be stale against.
    """
    digest = hashlib.sha256()
    seen = False
    for name in names:
        for candidate in str(name).split("|"):
            path = Path(spec_dir) / candidate.strip()
            if path.is_file():
                digest.update(candidate.strip().encode() + b"\0" + path.read_bytes())
                seen = True
                break
    return digest.hexdigest()[:12] if seen else "-"


def _record_micro(path: Path) -> bool:
    """Does the record say ``micro`` — a page with no quiz (R2.7)?

    Only that exact value counts: an unfilled template row (``micro · standard
    · deep``) is not a depth, and the quiz line is the safer default.
    """
    try:
        found = _DEPTH.search(path.read_text(encoding="utf-8"))
    except OSError:
        return False
    return bool(found) and found.group("value") == "micro"


def _record_location(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    found = _LOCATION.search(text)
    value = found.group("value").strip() if found else ""
    # The template's own placeholder is not a location: a record copied and
    # never filled in must block, not link the author to "<…>".
    return "" if value.startswith("<") else value


# -------------------------------------------------------------------- targets


def _resolve(ctx: HookContext):
    """The work item's integration, resolved at call time (see selection.py)."""
    from ..integrations import integration_for

    return integration_for(ctx.work_item.ref, ctx.config)


def _state(ctx: HookContext):
    try:
        from ..state import WorkItemState

        return WorkItemState.load(ctx.work_item.spec_dir, ctx.work_item.id)
    except Exception:  # noqa: BLE001 — a missing/corrupt state is "no PRs, round 1"
        return None


def _round(ctx: HookContext) -> int:
    """How many times this node has been entered — its marker's ``round``.

    A code quiz walked again after `human-approval` asked for changes is a new
    round: a fresh comment is posted, and a box ticked in an earlier round is
    not an answer about the code as it is now.
    """
    state = _state(ctx)
    rec = getattr(state, "nodes", {}).get(ctx.node_id) if state is not None else None
    return max(1, int(getattr(rec, "attempts", 0) or 0))


def _targets(ctx: HookContext, where: str) -> List[str]:
    """Where the comment goes: the ticket, or every delivering pull request."""
    if where != "pull-requests":
        return [ctx.work_item.ref]
    state = _state(ctx)
    prs = list(getattr(state, "pull_requests", []) or []) if state is not None else []
    refs = [pr.ref for pr in prs if getattr(pr, "state", "open") == "open"]
    return refs or [ctx.work_item.ref]


def _comments(ctx: HookContext, ref: str) -> List[Mapping[str, Any]]:
    data = _resolve(ctx).call("list-comments", ref=ref)
    return [c for c in data.get("comments") or [] if isinstance(c, Mapping)]


def _author(comment: Mapping[str, Any]) -> str:
    raw = comment.get("author") or comment.get("user") or ""
    return str(raw.get("login") or "") if isinstance(raw, Mapping) else str(raw)


def _ours(
    comments: Iterable[Mapping[str, Any]], node: str, allowed: Sequence[str]
) -> List[Tuple[Mapping[str, Any], Mapping[str, str]]]:
    """This node's quiz comments the-loop posted, oldest first.

    Both markers are plain text anyone who can comment could copy, so a body
    alone proves nothing: the comment must also be AUTHORED by an authorized
    login. the-loop posts under the operator's own account (decision-023), so
    its real comment passes; a look-alike from anyone else is not a quiz
    comment at all — it can neither hide the real box nor fake a stale spec.
    """
    out = []
    for comment in comments:
        body = str(comment.get("body") or "")
        marker = _marker(body)
        author = _author(comment)
        if (
            marker
            and marker["node"] == node
            and is_self_authored(body)
            and author
            and is_authorized(author, list(allowed))
        ):
            out.append((comment, marker))
    return out


# ----------------------------------------------------------------- the comment


def _repo_of(ref: str) -> Tuple[str, str]:
    body = ref.split(":", 1)[1] if ":" in ref else ref
    parts = body.partition("#")[0].split("/")
    return (parts[-2], parts[-1]) if len(parts) >= 2 else ("", "")


def _view_commands(location: str, ref: str) -> List[str]:
    """Copy-paste commands that open a committed explainer in a local browser.

    Built only from the owner, repository, branch and path — values the-loop
    already holds, each checked against a conservative character set — so no
    ticket text can reach a reader's shell. Nothing goes to a third-party
    renderer: one command uses the reader's own `gh` login (private repositories
    too), the other plain `curl` (public ones).
    """
    owner, repo, branch, path = "", "", "", ""
    parsed = urlparse(location)
    if parsed.scheme in ("http", "https") and parsed.netloc == "github.com":
        found = _GITHUB_BLOB.match(parsed.path)
        if found:
            owner, repo = found.group("owner"), found.group("repo")
            # A branch may hold a slash (`feat/x`), which a blob URL cannot
            # delimit — but the page always lives in the spec tree, so split
            # where `docs/specs/` begins and take the rest as the branch.
            rest = f"{found.group('branch')}/{found.group('path')}"
            cut = rest.find("/docs/specs/")
            branch, path = (
                (rest[:cut], rest[cut + 1 :])
                if cut > 0
                else (found.group("branch"), found.group("path"))
            )
    elif not parsed.scheme:
        owner, repo = _repo_of(ref)
        path = location.lstrip("./")
    if not all(_SAFE.match(v) for v in (owner, repo, path)) or (
        branch and not _SAFE.match(branch)
    ):
        return []
    out = f"/tmp/{repo}-{Path(path).stem}.html"
    query = f"?ref={branch}" if branch else ""
    raw_branch = branch or "HEAD"
    return [
        f"gh api -H 'Accept: application/vnd.github.raw' "
        f"'repos/{owner}/{repo}/contents/{path}{query}' > {out} "
        f"&& python3 -m webbrowser {out}",
        f"curl -fsSL 'https://raw.githubusercontent.com/{owner}/{repo}/{raw_branch}/{path}' "
        f"-o {out} && python3 -m webbrowser {out}",
    ]


def _quiz_body(
    node: str, location: str, round_: int, digest: str, ref: str, micro: bool = False
) -> str:
    title = _TITLES.get(node, node)
    if micro:
        # R2.7: a `micro` page has no quiz, so the box attests reading only.
        what = (
            "the spec explainer before code generation starts"
            if node == "spec-quiz"
            else "the explainer of this change before review is requested"
        )
    else:
        what = (
            "the spec explainer and take its quiz before code generation starts"
            if node == "spec-quiz"
            else "the explainer of this change and take the code quiz before "
            "review is requested"
        )
    line = (READ_ONLY if micro else ATTESTATIONS)[node]
    lines = [f"🎓 **{title}** — read {what}."]
    commands = _view_commands(location, ref)
    if commands:
        lines += [
            "",
            f"The page is committed at `{location}`. Open it rendered with one of:",
            "",
            "```sh",
            *commands,
            "```",
        ]
    else:
        lines += ["", f"**Open it:** {location}"]
    if ref.startswith("jira:"):
        # Jira cannot say who edited a comment, so a tick here could never be
        # attributed: ask for the typed line instead. Inline code, so this very
        # comment never reads as ticked.
        lines += [
            "",
            f"Reply with this line to move on: `- [x] {line}`",
            "",
            "Only a user authorized for this deployment of the-loop can answer; "
            "the quiz itself is yours alone, and the-loop records only who "
            "replied.",
        ]
    else:
        lines += [
            "",
            f"- [ ] {line}",
            "",
            "Ticking the box is enough — no reply needed. Only a user authorized "
            "for this deployment of the-loop can tick it for the work item to "
            "move on; the quiz itself is yours alone, and the-loop records only "
            "who ticked.",
        ]
    lines += ["", f"<!-- the-loop:quiz {node} round={round_} digest={digest} -->"]
    return mark_self_authored("\n".join(lines))


# ------------------------------------------------------------------ the hooks


@hook("post-quiz-attestation")
def post_quiz_attestation(ctx: HookContext) -> HookResult:
    """Ask the author to read the explainer and take the quiz (entry hook).

    Blocks when the agent node's record names no published page — a quiz
    pointing nowhere is a gate nobody can honestly answer. Posting itself is
    best-effort, like every outbound hook: an outage leaves the gate waiting,
    and ``quiz-attested`` re-posts on the next event that wakes it.
    """
    name = "post-quiz-attestation"
    node = str(ctx.params.get("node") or ctx.node_id)
    if node not in ATTESTATIONS:
        return HookResult.blocked(name, [Message(f"unknown quiz node {node!r}")])
    record = str(ctx.params.get("record") or "")
    location = _record_location(Path(ctx.work_item.spec_dir) / record) if record else ""
    if not location:
        return HookResult.blocked(
            name,
            [
                Message(
                    f"no published explainer: {record or '(no record)'} names no "
                    "`Location` — write the page and its record first",
                    path=record,
                )
            ],
        )
    names = [str(n) for n in ctx.params.get("digest") or []]
    digest = spec_digest(ctx.work_item.spec_dir, names) if names else "-"
    round_ = _round(ctx)
    where = str(ctx.params.get("on") or _WHERE[node])
    micro = _record_micro(Path(ctx.work_item.spec_dir) / record)
    posted = _post(ctx, node, location, round_, digest, where, micro)
    return HookResult.ok(name, posted=posted, round=round_, digest=digest)


#: Where each quiz's comment lives — the entry hook's default `on`, and where
#: the exit hook looks.
_WHERE = {"spec-quiz": "ticket", "code-quiz": "pull-requests"}


def _post(
    ctx: HookContext,
    node: str,
    location: str,
    round_: int,
    digest: str,
    where: str,
    micro: bool = False,
) -> List[str]:
    """Post this round's comment wherever it is not already. Best-effort."""
    allowed = [str(u) for u in (ctx.config.get("authorizedUsers") or [])]
    posted: List[str] = []
    for ref in _targets(ctx, where):
        try:
            already = any(
                m["round"] == str(round_) and m["digest"] == digest
                for _, m in _ours(_comments(ctx, ref), node, allowed)
            )
            if already:
                continue
            _resolve(ctx).call(
                "add-comment",
                ref=ref,
                body=_quiz_body(node, location, round_, digest, ref, micro),
            )
            posted.append(ref)
        except Exception as exc:  # noqa: BLE001 — best-effort, never wedge
            logger.warning("could not post the %s comment on %s: %s", node, ref, exc)
    return posted


@hook("quiz-attested")
def quiz_attested(ctx: HookContext) -> HookResult:
    """Pass once an authorized user ticked this round's box (exit hook).

    Reads GitHub only when an event woke the gate — `the-loop check` passes
    none and is told the gate waits, which is what it does. When this round's
    comment is on no thread it could read (the entry's post failed, and
    nothing re-enters a parked human node), it posts it again from ``record``.
    """
    name = "quiz-attested"
    node = ctx.node_id
    if node not in ATTESTATIONS:
        return HookResult.blocked(name, [Message(f"unknown quiz node {node!r}")])
    if ctx.event is None:
        return HookResult.waiting(name, "waiting for the author to tick the quiz box")
    allowed = [str(u) for u in (ctx.config.get("authorizedUsers") or [])]
    names = [str(n) for n in ctx.params.get("digest") or []]
    current = spec_digest(ctx.work_item.spec_dir, names) if names else "-"
    round_ = str(_round(ctx))

    refused: List[str] = []
    read_any, found_any = False, False
    for ref in _targets(ctx, _WHERE[node]):
        try:
            mine = [
                (c, m)
                for c, m in _ours(_comments(ctx, ref), node, allowed)
                if m["round"] == round_
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not read %s for the %s gate: %s", ref, node, exc)
            continue
        read_any = True
        if not mine:
            continue
        found_any = True
        newest = mine[-1][1]
        if names and newest["digest"] != current:
            # The spec moved under the quiz: the page the author would attest
            # to is no longer the spec. Back to the explainer for a new one.
            return HookResult.ok(
                name, outcome="stale", was=newest["digest"], now=current
            )
        # Every comment of this round counts (a retried post can leave two),
        # but only one carrying the spec as it is now.
        for comment, marker in reversed(mine):
            if names and marker["digest"] != current:
                continue
            if not attestation_ticked(str(comment.get("body") or ""), node):
                continue
            verdict = _attributed(ctx, ref, comment, node, round_, allowed)
            if verdict.get("by"):
                return HookResult.ok(
                    name,
                    decision=node,
                    attestedBy=verdict["by"],
                    attestedAt=verdict.get("at", ""),
                    comment=str(comment.get("url") or comment.get("html_url") or ""),
                    via="tick",
                )
            refused.append(verdict.get("refused") or "unknown")

    typed = _typed_attestation(ctx, node, allowed)
    if typed:
        return HookResult.ok(name, decision=node, via="reply", **typed)
    record = str(ctx.params.get("record") or "")
    if read_any and not found_any and record:
        path = Path(ctx.work_item.spec_dir) / record
        location = _record_location(path)
        micro = _record_micro(path)
        if location and _post(
            ctx, node, location, int(round_), current, _WHERE[node], micro
        ):
            return HookResult.waiting(
                name, "posted the quiz comment again — it had not landed"
            )
    if "unverified" in refused:
        return HookResult.waiting(name, UNVERIFIED, refused=refused)
    if refused:
        return HookResult.waiting(
            name,
            "the box was ticked by someone not authorized to answer",
            refused=refused,
        )
    return HookResult.waiting(name, "waiting for the author to tick the quiz box")


def _attributed(
    ctx: HookContext,
    ref: str,
    comment: Mapping[str, Any],
    node: str,
    round_: str,
    allowed: Sequence[str],
) -> Dict[str, str]:
    """Who made the latest edit — ``{"by", "at"}``, or ``{"refused": who}``.

    Re-reads the comment by id so the body judged is the one the history
    belongs to, then re-checks it is still ours, still this node's round, and
    still ticked. Fails closed on anything it cannot establish.
    """
    try:
        found = _resolve(ctx).call("comment-edits", ref=ref, id=str(comment.get("id")))
    except OperationUnsupported:
        # Jira: a tick can never be attributed, and retrying will not change
        # that — refused, not "unverified" (which is a transient fault).
        return {"refused": "unsupported"}
    except Exception as exc:  # noqa: BLE001 — unverifiable is not verified
        logger.warning("could not read who edited the %s comment: %s", node, exc)
        return {"refused": "unverified"}
    body = str(found.get("body") or "")
    marker = _marker(body)
    author = str(found.get("author") or "")
    if not (
        author
        and is_authorized(author, list(allowed))
        and is_self_authored(body)
        and marker
        and marker["node"] == node
        and marker["round"] == round_
        and attestation_ticked(body, node)
    ):
        return {"refused": "unverified"}
    edits = [e for e in found.get("edits") or [] if isinstance(e, Mapping)]
    editor = str(edits[0].get("editor") or "") if edits else ""
    # `is_authorized(None, …)` is True for CI events — an unknown editor must be
    # refused HERE, before that call can wave it through.
    if not editor or not is_authorized(editor, list(allowed)):
        logger.warning(
            "%s: quiz box on %s ticked by %r, who may not answer this gate",
            ctx.work_item.ref,
            node,
            editor or "(unknown)",
        )
        eventlog.emit(
            "graph.quiz_refused",
            level="warning",
            work_item=ctx.work_item.ref,
            node=node,
            editor=editor or None,
            comment=str(found.get("url") or comment.get("url") or "") or None,
        )
        return {"refused": editor or "unknown"}
    return {"by": editor, "at": str(edits[0].get("editedAt") or "")}


def _typed_attestation(
    ctx: HookContext, node: str, allowed: Sequence[str]
) -> Dict[str, str]:
    """An authorized comment carrying the ticked line itself — the fallback."""
    for comment in (ctx.event or {}).get("comments") or []:
        if not isinstance(comment, Mapping):
            continue
        body = str(comment.get("body") or "")
        author = _author(comment)
        if (
            is_self_authored(body)
            or not author
            or not is_authorized(author, list(allowed))
        ):
            continue
        if attestation_ticked(body, node):
            return {
                "attestedBy": author,
                "attestedAt": str(
                    comment.get("created_at") or comment.get("createdAt") or ""
                ),
                "comment": str(comment.get("url") or comment.get("html_url") or ""),
            }
    return {}
