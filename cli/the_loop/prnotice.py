"""The notice a work item's session gets when one of its pull-request sessions
changes state (issue-538).

A pull request delivering a work item may get a tmux session of its own
(``sessionPerPr``, issue-258/260). Until issue-538 the work item's session heard
nothing when that session was spawned, declined, failed, finished, closed or
escalated. The dispatcher now pastes one notice per transition into it; this
module is the notice's **text**, and nothing else.

It is a pure function over **typed, bounded** inputs, on purpose: the paste is a
prompt-injection surface, and the way to keep payload text out of it is to give
the renderer no parameter that could carry any. Refs are parsed
:class:`~the_loop.sessions.WorkItemRef` values, a decline reason is a code
looked up in a fixed table, and the remaining identifiers (a tmux target, graph
node ids) are filtered to a narrow character class — they come from the
daemon's own registry and compiled graph, but the renderer does not rely on
that.

A notice moves nothing. The outer loop still advances only on its own exit
chain (``await-inner-loops`` reading the inner state files) — the one-way rule
of ``docs/capabilities/process-graph.md``.
"""

from __future__ import annotations

import string
from typing import Dict, Tuple

from . import prompts
from .sessions import WorkItemRef

__all__ = ["DECLINE_REASONS", "TRANSITIONS", "render"]

#: Every transition a notice can report, in lifecycle order.
TRANSITIONS: Tuple[str, ...] = (
    "spawned",
    "declined",
    "spawn-failed",
    "respawned",
    "respawn-failed",
    "completed",
    "merged",
    "closed",
    "escalated",
)

#: Why a pull request was not given a session of its own — the codes the
#: dispatcher itself chose, each with the one phrase a notice may say about it.
DECLINE_REASONS: Dict[str, str] = {
    code: prompts.load(f"prnotice/decline/{code}", inline=True)
    for code in (
        "no-separate-checkout",
        "workspace-failed",
        "shared-worktree",
        "harness-unavailable",
        "hook-refused",
    )
}


def _text(name: str, /, **slots: object) -> str:
    """One sentence of a notice, from ``prompts/prnotice/`` (issue-540)."""
    return prompts.render(f"prnotice/{name}", inline=True, **slots)


_IDENTIFIER_CHARS = string.ascii_letters + string.digits + "._:/#-"
_IDENTIFIER_MAX = 120


def _identifier(value: str) -> str:
    """Keep ``[A-Za-z0-9._:/#-]`` and at most 120 characters of ``value``."""
    kept = "".join(ch for ch in str(value or "") if ch in _IDENTIFIER_CHARS)
    return kept[:_IDENTIFIER_MAX]


def _code(value: str) -> str:
    return f"`{value}`" if value else "(unknown)"


def render(
    transition: str,
    work_item: WorkItemRef,
    pull_request: WorkItemRef,
    *,
    tmux_target: str = "",
    reason: str = "",
    outer_node: str = "",
    outer_waits: bool = False,
    inner_node: str = "",
) -> str:
    """The notice for one transition of ``pull_request``'s session.

    Raises :class:`ValueError` for a transition not in :data:`TRANSITIONS`, so a
    call site with a typo fails its test instead of pasting a malformed notice.
    """
    if transition not in TRANSITIONS:
        raise ValueError(f"unknown pull-request session transition {transition!r}")
    pr = pull_request.ref
    target = _identifier(tmux_target)
    outer = _identifier(outer_node)
    inner = _identifier(inner_node)
    owns_events = _text("owns-events")
    if transition == "spawned":
        what = _text("what-spawned", pr=pr, target=_code(target))
        means = _text("means-spawned")
    elif transition == "declined":
        phrase = DECLINE_REASONS.get(reason) or _text("decline/unspecified")
        what = _text("what-declined", pr=pr, phrase=phrase)
        means = owns_events
    elif transition == "spawn-failed":
        what = _text("what-spawn-failed", pr=pr)
        means = owns_events
    elif transition == "respawned":
        what = _text("what-respawned", pr=pr, target=_code(target))
        means = _text("means-respawned")
    elif transition == "respawn-failed":
        what = _text("what-respawn-failed", pr=pr)
        means = _text("means-respawn-failed")
    elif transition == "completed":
        what = _text("what-completed", pr=pr)
        means = _text("means-rechecking")
    elif transition == "merged":
        what = _text("what-merged", pr=pr)
        means = _text("means-rechecking")
    elif transition == "closed":
        what = _text("what-closed", pr=pr)
        if outer_waits:
            means = _text("means-closed-waiting", outer=_code(outer))
        else:
            means = _text("means-closed", outer=_code(outer))
    else:  # escalated
        what = _text("what-escalated", pr=pr, inner=_code(inner))
        means = _text("means-escalated")
    return _text(
        "notice",
        work_item=work_item.ref,
        pr=pr,
        transition=transition,
        what=what,
        means=means,
    )
