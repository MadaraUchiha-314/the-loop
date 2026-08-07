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
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from ..contract import HookContext, HookResult, Message
from ..registry import hook

__all__ = ["PR_LOOPS_DIRNAME", "await_inner_loops", "inner_loop_state_dir"]

#: Where a work item's inner-loop states live, under its spec directory.
PR_LOOPS_DIRNAME = "pr-loops"

#: The inner loop's terminal success node. One constant, shared by the hook
#: that reads inner states and the code that advances them, so "finished"
#: cannot mean two different things.
INNER_COMPLETE_NODE = "complete"


def inner_loop_state_dir(spec_dir: Path, pr_number: int) -> Path:
    """One PR's inner-loop state directory: ``<spec_dir>/pr-loops/pr-<n>``.

    Keyed by number, not by ref: the spec directory belongs to one repository,
    and a PR's number is unique within it. The ``pr-`` prefix keeps the
    directory self-describing in a checkout listing.
    """
    return spec_dir / PR_LOOPS_DIRNAME / f"pr-{pr_number}"


def _inner_states(spec_dir: Path) -> List[Tuple[str, str]]:
    """``(pr directory name, current node)`` per readable inner state, sorted.

    An unreadable state file counts as *not finished* rather than being
    skipped: a corrupt inner loop must hold the outer gate (loudly, naming the
    PR) — skipping it would let the outer loop advance past work whose record
    is damaged, which is the silent-pass shape issue-124 exists to prevent.
    """
    root = spec_dir / PR_LOOPS_DIRNAME
    if not root.is_dir():
        return []
    found: List[Tuple[str, str]] = []
    for state_path in sorted(root.glob("pr-*/graph-state.json")):
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            current = str(data.get("currentNode", "")) if isinstance(data, dict) else ""
        except (OSError, json.JSONDecodeError):
            current = ""
        found.append((state_path.parent.name, current))
    return found


@hook("await-inner-loops")
def await_inner_loops(ctx: HookContext) -> HookResult:
    """PASS when every started inner loop has finished; WAIT naming the rest.

    Vacuously PASS when no inner loop was ever started — the pre-issue-172
    single-session work item, unchanged. Never BLOCK: an unfinished PR is not a
    fault, it is work in progress, and the outer loop's posture toward it is
    patience (the same reason a human gate is a ``wait``).
    """
    states = _inner_states(ctx.work_item.spec_dir)
    if not states:
        return HookResult.ok("await-inner-loops", inner_loops=0)
    pending = [name for name, current in states if current != INNER_COMPLETE_NODE]
    if not pending:
        return HookResult.ok("await-inner-loops", inner_loops=len(states))
    return HookResult(
        status="wait",
        hook="await-inner-loops",
        messages=[
            Message(
                text=(
                    f"waiting for {len(pending)} inner loop(s) to finish: "
                    f"{', '.join(pending)} — each pull request completes its "
                    "pdlc-pr-loop (docs/specs/<id>/pr-loops/) before the work "
                    "item moves past implementation"
                ),
                severity="info",
            )
        ],
        data={"inner_loops": len(states), "pending": pending},
    )
