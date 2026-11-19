"""``pr-spec-current``: is each delivery PR's PR spec recorded and current?
(issue-543, decision-153)

The offline half of PR-scoped specs. ``the-loop graph pr-spec`` does the work
that needs the PR's checkout and GitHub, once, and writes ``pr-spec.json``
beside the PR's inner-loop state in the **origin** checkout. This hook re-reads
that record on every evaluation against the **current** chain, so it stays
offline and evaluates identically in the daemon and in ``the-loop check``.

Three placements, one hook:

* the inner ``pr-spec`` node's exit — the PR spec exists before implementation;
* the inner ``reviewer-briefing`` node's exit — it is still current before
  review, and a work item that became multi-PR later is caught (R1.3);
* the outer ``implementation`` node's exit — every open delivery PR has a
  current record, including PRs that walk no inner loop (R1.4, R1.6).

The hook never trusts the record's own claim that a PR spec is not required:
it re-derives applicability from ``work-item-state.json`` every time, and it
recomputes the chain digest rather than reading one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional, Tuple

from ..contract import HookContext, HookResult, Message
from ..prspec import (
    PR_SPEC_RECORD,
    PrSpecRecord,
    applicability,
    chain_digest,
    chain_parts,
    changed_files,
)
from ..registry import hook
from ..state import STATE_FILENAME, WorkItemState
from .loops import inner_loop_state_dir

__all__ = ["pr_spec_current", "record_candidates"]

NAME = "pr-spec-current"


def _parse_pr(ref: str) -> Tuple[str, int]:
    """``github:octo/api#12`` → ``("octo/api", 12)``; ``("", 0)`` if it will not parse."""
    from ...sessions import WorkItemRef

    try:
        parsed = WorkItemRef.parse(ref)
    except ValueError:
        return "", 0
    return (parsed.path if parsed.repo else ""), parsed.number


def _same(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


def record_candidates(
    spec_dir: Path, repo: str, number: int, origin: str
) -> List[Path]:
    """Every directory a PR's record may live in, in preference order.

    An origin-repository PR's inner loop uses the shipped ``pr-loops/pr-<n>``
    layout or the qualified one, depending on whether the caller passed
    ``--pr-repo`` (both spellings are accepted by ``PullRequest.from_dict``), so
    both are looked in. A repository name that fails validation yields nothing.
    """
    out: List[Path] = []
    try:
        out.append(inner_loop_state_dir(spec_dir, number, repo))
    except ValueError:
        return []
    if origin and _same(repo, origin):
        out.append(inner_loop_state_dir(spec_dir, number))
    return out


def _skipped(dirs: List[Path]) -> bool:
    """Did the PR's inner loop declare ``pr-spec`` skipped (R1.5)?

    ``pr-spec`` is the inner loop's one skippable node, so a raw read of the
    declaration is what ``Runtime.declared_skips`` would honour.
    """
    for directory in dirs:
        try:
            data = json.loads((directory / STATE_FILENAME).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        skips = data.get("skips") if isinstance(data, dict) else None
        if isinstance(skips, dict) and isinstance(skips.get("pr-spec"), dict):
            return True
    return False


def _command(item_id: str, repo: str, number: int, origin: str) -> str:
    flag = "" if _same(repo, origin) else f" --pr-repo {repo}"
    return f"`the-loop graph pr-spec {item_id} --pr {number}{flag} --checkout <PR checkout>`"


def _check_one(
    ctx: HookContext, ref: str, repo: str, number: int, origin: str
) -> Tuple[Optional[str], str]:
    """``(problem or None, prSpec verdict)`` for one delivery PR."""
    spec_dir = ctx.work_item.spec_dir
    dirs = record_candidates(spec_dir, repo, number, origin)
    if not dirs:
        return f"{ref}: its repository is not a usable name", ""
    if _skipped(dirs):
        return None, "skipped"
    path = next(
        (d / PR_SPEC_RECORD for d in dirs if (d / PR_SPEC_RECORD).is_file()), None
    )
    redo = _command(ctx.work_item.id, repo, number, origin)
    if path is None:
        return (
            f"{ref}: no PR spec is recorded. Write it in the PR's branch and run {redo}",
            "",
        )
    try:
        record = PrSpecRecord.load(path, expected_pr=ref)
    except ValueError as exc:
        return f"{ref}: the PR-spec record is not usable ({exc}); re-run {redo}", ""
    if not record.required:
        if record.reason == "spec-only" and origin and _same(repo, origin):
            return None, "spec-only"
        return (
            f"{ref}: recorded as not required ({record.reason}), but this work item "
            f"is multi-PR now; re-derive the PR spec and run {redo}",
            "",
        )
    current = chain_digest(spec_dir)
    if record.chain_digest != current:
        files = (
            changed_files(record.chain_parts, chain_parts(spec_dir))
            if record.chain_parts
            else []
        )
        since = record.source_revision[:12] or "the recorded revision"
        which = f" ({', '.join(files)})" if files else ""
        return (
            f"{ref}: stale: chain changed since `{since}`{which}. Re-derive the PR "
            f"spec and run {redo}, or record an authorized human's declaration "
            "with `--still-valid <comment URL>`",
            "",
        )
    return None, "current"


@hook(NAME)
def pr_spec_current(ctx: HookContext) -> HookResult:
    """PASS when no PR spec is required, or every one in scope is recorded and
    current; BLOCK naming each PR that is not."""
    spec_dir = ctx.work_item.spec_dir
    state = WorkItemState.load(spec_dir, ctx.work_item.id)
    origin = str(ctx.config.get("originRepo") or "")
    verdict = applicability(state.pull_requests, state.repos, origin)
    if verdict == "single-pr":
        return HookResult.ok(NAME, prSpec="not-required")

    pr_ref = str(ctx.config.get("prRef") or "")
    targets: List[Tuple[str, str, int]] = []
    if pr_ref:
        repo, number = _parse_pr(pr_ref)
        targets.append((pr_ref, repo, number))
    else:
        for row in state.pull_requests:
            if row.is_self or row.state != "open":
                continue
            targets.append((row.ref, row.repository, row.number))

    problems: List[str] = []
    verdicts: List[Any] = []
    for ref, repo, number in targets:
        if not repo or not number:
            problems.append(f"{ref}: not a pull-request ref the-loop can address")
            continue
        problem, outcome = _check_one(ctx, ref, repo, number, origin)
        if problem:
            problems.append(problem)
        verdicts.append(outcome)
    if problems:
        return HookResult.blocked(
            NAME,
            [Message(text=p, path=str(spec_dir / STATE_FILENAME)) for p in problems],
            prSpec="missing",
        )
    single = verdicts[0] if pr_ref and verdicts else "current"
    return HookResult.ok(NAME, prSpec=single, checked=len(targets))
