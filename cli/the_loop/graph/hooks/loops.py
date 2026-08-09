"""The seam between the two loops (issue-172, PR #173 review).

The **outer** loop (``pdlc-work-item-loop``) walks a work item through the
PDLC. The **inner** loop (``pdlc-pr-loop``) walks one pull request through the
subset that delivers a component, in service of the work item. They meet at
exactly one point: the outer ``implementation`` node *waits for the inner loops
to finish* — the owner's phrasing on PR #173, verbatim — before the work item
moves on to verification across all the PRs.

``await-inner-loops`` is that wait, expressed the way every other gate in the
graph is expressed: a hook over checked-in files. Each inner loop keeps its
state at ``docs/specs/<id>/pr-loops/<pr-number>/graph-state.json`` — beside the
outer ``graph-state.json``, on the work item's branch, surviving machine and
session changes for the same reasons (decision-041). The hook reads those
files and nothing else: no registry, no GitHub, no network, so ``the-loop
check`` in CI evaluates it identically to the daemon.

A work item with **no** inner loops passes vacuously. That is load-bearing: a
single-repo work item whose agent commits from the work item's own session —
every work item before issue-172, and every simple one after it — never waits
on a loop nobody started.

**Several repositories, one work item (issue-183).** The outer loop runs in the
repository the ticket was created in — the *origin* repository — and that is
where the one spec chain lives, so a pull request in a *contributing*
repository keeps its inner state under the same spec directory, qualified by
its repository: ``pr-loops/<owner>__<repo>/pr-<n>/``. Two layouts rather than
one, deliberately: an origin-repo PR keeps the shipped ``pr-loops/pr-<n>/``
path, so no work item in flight has to be migrated to gain the feature.

The vacuous pass has one gap that only shows up across repositories — a
contribution that was *planned* and never opened is indistinguishable from one
that was never planned. So a work item may **declare** the repositories it
contributes to, in ``execution-log.md``'s front matter (``repos:``), and this
gate then holds until each of them has an inner loop. Declaring nothing keeps
the pre-issue-183 behaviour exactly.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Sequence, Tuple

from ..contract import HookContext, HookResult, Message
from ..frontmatter import read_front_matter
from ..registry import hook

__all__ = [
    "PR_LOOPS_DIRNAME",
    "await_inner_loops",
    "declared_repos",
    "inner_loop_state_dir",
    "repo_state_key",
]

#: Where a work item's inner-loop states live, under its spec directory.
PR_LOOPS_DIRNAME = "pr-loops"

#: The inner loop's terminal success node. One constant, shared by the hook
#: that reads inner states and the code that advances them, so "finished"
#: cannot mean two different things.
INNER_COMPLETE_NODE = "complete"

#: One segment of a repository path (``owner``, ``repo``, or a GHE ``host``).
#: Deliberately narrow: this value becomes a **directory name**, and it arrives
#: from a webhook payload or an operator's ``--pr-repo`` argument.
_REPO_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")


def repo_state_key(repo: str) -> str:
    """``owner/repo`` (or ``host/owner/repo``) → ``owner__repo`` — or raise.

    The trust boundary between a repository name and the filesystem (issue-183).
    A payload may say anything, so this **rejects** rather than sanitizes: a
    name quietly rewritten into a valid one would file one repository's
    inner-loop state under another repository's name, which is worse than a
    refusal. At least two segments, each ``[A-Za-z0-9._-]+``, and never ``.``
    or ``..`` — which that class would otherwise admit.
    """
    parts = str(repo).strip().split("/")
    if len(parts) < 2:
        raise ValueError(f"repository must be <owner>/<repo>: {repo!r}")
    for part in parts:
        if part in (".", "..") or not _REPO_SEGMENT.fullmatch(part):
            raise ValueError(f"unusable repository segment {part!r} in {repo!r}")
    return "__".join(parts)


def inner_loop_state_dir(spec_dir: Path, pr_number: int, repo: str = "") -> Path:
    """One PR's inner-loop state directory, under the work item's spec directory.

    ``<spec_dir>/pr-loops/pr-<n>`` for a pull request in the **origin**
    repository — the shipped layout, unchanged — and
    ``<spec_dir>/pr-loops/<owner>__<repo>/pr-<n>`` for one in a contributing
    repository (issue-183). Keyed by number alone within a repository, because a
    PR's number is unique there; qualified across repositories, because it is
    not unique between them.
    """
    root = spec_dir / PR_LOOPS_DIRNAME
    if repo:
        root = root / repo_state_key(repo)
    return root / f"pr-{int(pr_number)}"


def declared_repos(spec_dir: Path) -> List[str]:
    """The repositories this work item says it contributes to (issue-183).

    ``execution-log.md``'s front-matter ``repos:`` — checked in, human-authored,
    and read exactly like every other gate input: no network, no registry. An
    absent or non-list value is *no declaration*, not an empty one, and the gate
    behaves as it did before this key existed.
    """
    raw = read_front_matter(spec_dir / "execution-log.md").get("repos")
    if not isinstance(raw, list):
        return []
    return [str(entry).strip() for entry in raw if str(entry).strip()]


def _inner_states(spec_dir: Path) -> List[Tuple[str, str]]:
    """``(inner-loop label, current node)`` per readable inner state, sorted.

    The label is the state directory's path under ``pr-loops/`` — ``pr-16`` for
    the origin repository, ``octo__infra/pr-7`` for a contributing one — so a
    waiting message names the loop unambiguously.

    An unreadable state file counts as *not finished* rather than being
    skipped: a corrupt inner loop must hold the outer gate (loudly, naming the
    PR) — skipping it would let the outer loop advance past work whose record
    is damaged, which is the silent-pass shape issue-124 exists to prevent.
    """
    root = spec_dir / PR_LOOPS_DIRNAME
    if not root.is_dir():
        return []
    paths = sorted(root.glob("pr-*/graph-state.json")) + sorted(
        root.glob("*/pr-*/graph-state.json")
    )
    found: List[Tuple[str, str]] = []
    for state_path in paths:
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            current = str(data.get("currentNode", "")) if isinstance(data, dict) else ""
        except (OSError, json.JSONDecodeError):
            current = ""
        found.append((state_path.parent.relative_to(root).as_posix(), current))
    return sorted(set(found))


def _repos_without_a_loop(
    declared: Sequence[str], states: Sequence[Tuple[str, str]], origin: str
) -> Tuple[List[str], bool]:
    """Declared repositories that have no inner loop at all, and whether the
    origin repository is unknown while it mattered.

    A declared repository is matched to its loops by :func:`repo_state_key`: the
    origin repository owns the **top-level** ``pr-<n>`` loops, every other
    repository owns its own subdirectory. Without a configured origin
    (``ticketing.github``) a top-level loop cannot be attributed to any
    repository, so the declaration goes unsatisfied and the caller says why —
    guessing which loop was meant is how a gate passes on the wrong evidence.
    """
    origin_key = ""
    if origin:
        try:
            origin_key = repo_state_key(origin)
        except ValueError:
            origin_key = ""
    top_level = [label for label, _ in states if "/" not in label]
    missing: List[str] = []
    origin_unknown = False
    for repo in declared:
        key = repo_state_key(repo)  # a malformed declaration raises: see the hook
        if origin_key and key == origin_key:
            found = bool(top_level)
        else:
            found = any(label.startswith(f"{key}/") for label, _ in states)
            if not found and not origin_key and top_level:
                origin_unknown = True
        if not found:
            missing.append(repo)
    return missing, origin_unknown


@hook("await-inner-loops")
def await_inner_loops(ctx: HookContext) -> HookResult:
    """PASS when every started inner loop has finished and every declared
    repository has one; WAIT naming the rest.

    Vacuously PASS when no inner loop was ever started **and** the work item
    declared no contributing repositories — the pre-issue-172 single-session
    work item, unchanged.

    Two outcomes other than PASS, and the distinction is deliberate:

    * **WAIT** for an unfinished loop or a declared repository with no loop yet.
      Neither is a fault; both are work in progress, and the outer loop's
      posture toward work in progress is patience (the same reason a human gate
      is a ``wait``).
    * **BLOCK** for a ``repos:`` entry that is not a usable repository name.
      That *is* a fault — in a checked-in file, authored by a person — and
      waiting for it would wait forever (issue-183).
    """
    name = "await-inner-loops"
    spec_dir = ctx.work_item.spec_dir
    states = _inner_states(spec_dir)
    declared = declared_repos(spec_dir)
    try:
        missing, origin_unknown = _repos_without_a_loop(
            declared, states, str(ctx.config.get("originRepo") or "")
        )
    except ValueError as exc:
        return HookResult(
            status="block",
            hook=name,
            messages=[
                Message(
                    text=(
                        f"execution-log.md declares a repository the-loop cannot "
                        f"use: {exc}. `repos:` entries are <owner>/<repo>."
                    ),
                    path=str(spec_dir / "execution-log.md"),
                )
            ],
            data={"declared": list(declared)},
        )
    pending = [label for label, current in states if current != INNER_COMPLETE_NODE]
    if not pending and not missing:
        return HookResult.ok(name, inner_loops=len(states), declared=len(declared))
    parts: List[str] = []
    if pending:
        parts.append(
            f"waiting for {len(pending)} inner loop(s) to finish: {', '.join(pending)}"
        )
    if missing:
        parts.append(
            f"{len(missing)} declared repository(ies) have no inner loop yet: "
            f"{', '.join(missing)}"
        )
    if origin_unknown:
        parts.append(
            "the origin repository is unknown (set `ticketing.github.owner`/"
            "`.repo`), so pr-loops/pr-<n>/ cannot be attributed to a repository"
        )
    return HookResult(
        status="wait",
        hook=name,
        messages=[
            Message(
                text=(
                    "; ".join(parts) + " — each pull request completes its "
                    "pdlc-pr-loop (docs/specs/<id>/pr-loops/) before the work "
                    "item moves past implementation"
                ),
                severity="info",
            )
        ],
        data={
            "inner_loops": len(states),
            "pending": pending,
            "missing_repos": missing,
        },
    )
