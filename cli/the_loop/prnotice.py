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
    "no-separate-checkout": (
        "there is no routing.workspace.root, so it has no checkout of its own"
    ),
    "workspace-failed": "its checkout could not be prepared",
    "shared-worktree": "its checkout resolved to this session's own working tree",
    "harness-unavailable": "the harness could not be started for it",
    "hook-refused": "a session_spawn lifecycle hook refused it",
}

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
    owns_events = (
        "This session now receives this pull request's events; work it here."
    )
    if transition == "spawned":
        what = f"{pr} was given a session of its own ({_code(target)})."
        means = (
            "Its events and its inner loop (pdlc-pr-loop) run there from now on; "
            "you are told here when it finishes, closes or escalates."
        )
    elif transition == "declined":
        phrase = DECLINE_REASONS.get(reason, "unspecified")
        what = f"{pr} was not given a session of its own: {phrase}."
        means = owns_events
    elif transition == "spawn-failed":
        what = f"Starting a session for {pr} failed."
        means = owns_events
    elif transition == "respawned":
        what = f"{pr}'s session had died and was respawned ({_code(target)})."
        means = "It carries on with its inner loop; nothing is needed from you."
    elif transition == "respawn-failed":
        what = f"{pr}'s session had died and could not be respawned."
        means = (
            "Its events will be retried; if this repeats, look at the session or "
            "escalate on the work item."
        )
    elif transition == "completed":
        what = f"{pr}'s inner loop (pdlc-pr-loop) reached `complete` at its review."
        means = (
            "The daemon is re-checking `await-inner-loops` on your current node; "
            "if it passes you will receive the next node's assignment."
        )
    elif transition == "merged":
        what = f"{pr} merged. Its inner loop (pdlc-pr-loop) is complete."
        means = (
            "The daemon is re-checking `await-inner-loops` on your current node; "
            "if it passes you will receive the next node's assignment."
        )
    elif transition == "closed":
        what = f"{pr} was closed without merging. Its inner loop did not finish."
        if outer_waits:
            means = (
                f"Your current node, {_code(outer)}, waits on `await-inner-loops` "
                "and will keep waiting on this pull request until you reopen it, "
                "replace it, or escalate on the work item."
            )
        else:
            means = (
                f"Your current node is {_code(outer)}. Decide whether this pull "
                "request's work is still needed."
            )
    else:  # escalated
        what = f"{pr}'s inner loop escalated at {_code(inner)}."
        means = (
            "Its session needs a decision it could not make; read the pull "
            "request's thread and escalate on the work item if it needs a person."
        )
    return "\n".join(
        [
            "## the-loop: pull-request session notice",
            "",
            f"Work item: {work_item.ref} · Pull request: {pr} · "
            f"Transition: {transition}",
            "",
            what,
            means,
            "",
            "This notice is informational. It moves no graph pointer; "
            "`the-loop graph status` shows where the work item stands.",
        ]
    )
