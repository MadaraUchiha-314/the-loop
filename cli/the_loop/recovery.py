"""What a machine that lost its memory may still conclude (issue-363).

Three of the-loop's records live on the daemon's disk and nowhere else: the graph
pointer (``docs/specs/<id>/graph-state.json``, checked in — but on the work
item's *branch*, which an issue work item's clone does not check out), the
comment ledger and the control record (the portable record, which an operator
may or may not track). Rebuild the box and all three read as empty, and every
reader of them treated empty as *"this work item has never started"*. It then
did for eighteen running work items exactly what it does for a new ticket:
entered the graph at its first node, read the whole thread as unprocessed input,
and re-posted every gate.

This module holds the one distinction those readers were missing — **"nothing
has happened" is not "nothing is remembered here"** — and the two portable
facts that answer it. Both are written by the-loop itself, and both live with
the *work item* rather than with the machine:

* the ticket's ``loop:<phase>`` label, written by the ``set-phase-label`` hook at
  every node entry (one fixed vocabulary across every repository, issue-352); and
* the-loop's own self-authored comments, which
  :func:`the_loop.authz.is_self_authored` already recognises because the poller
  must not read its own posts back as input.

Neither is trusted to *place* a pointer — a label names a phase, not a node, and
says nothing about which gates were approved or which phases a human declared
away at selection. Both are trusted to say **stop**: the answers here can make a
caller refuse to start, refuse to re-run a command, or tell a session its
conversation is gone. Nothing here returns a node id, and nothing here grants
anything. See ``docs/specs/issue-363/design.md`` and decision-126.
"""

from __future__ import annotations

from typing import Iterable, List

from .authz import mark_self_authored
from .graph.hooks.sideeffects import PHASE_LABEL_PREFIX

__all__ = [
    "NOT_ADVANCED",
    "PHASE_LABEL_PREFIX",
    "advanced_phase",
    "context_lost",
    "context_lost_notice",
    "phase_labels",
    "recovery_prompt_notice",
]

#: Phases that are **not** evidence a work item has moved past its first node,
#: for a caller with no compiled graph to ask (the poller). ``not-started`` is
#: the vocabulary's own "nothing yet"; ``phase-selection`` is the start node of
#: both the outer loop and the contribution loop, and a pointer parked there has
#: entered nothing a re-entry could undo. A caller that *does* have a graph
#: passes its own ``start_phase`` instead — the ad-hoc loop starts at a node
#: whose phase is ``implementation``, and for that graph the label is not
#: evidence either.
NOT_ADVANCED = frozenset({"", "not-started", "phase-selection"})


def phase_labels(labels: Iterable[str]) -> List[str]:
    """The phases named by an item's ``loop:`` labels, in the order given.

    Everything else on the ticket is ignored: the auto-execute label, a
    priority, a team's own taxonomy. Case and whitespace are normalised because
    a label is typed by people as often as it is written by the-loop.
    """
    phases = []
    for label in labels or ():
        text = str(label or "").strip()
        if text.lower().startswith(PHASE_LABEL_PREFIX):
            phases.append(text[len(PHASE_LABEL_PREFIX) :].strip().lower())
    return phases


def advanced_phase(labels: Iterable[str], start_phase: str = "") -> str:
    """The first phase label that says this item has moved past its start node.

    ``""`` when there is none — an unlabelled ticket, or one labelled with
    nothing but its own start phase. ``start_phase`` is the compiled graph's
    start node's ``phase``; without it the graph-free :data:`NOT_ADVANCED`
    applies, which is what the poller (holding no graph) asks with.

    Deliberately returns the *phase*, not a node: the answer is only ever used
    as evidence that a rewind would destroy something, never to decide where to
    rewind *to*.
    """
    excluded = set(NOT_ADVANCED)
    if start_phase:
        excluded.add(str(start_phase).strip().lower())
    for phase in phase_labels(labels):
        if phase not in excluded:
            return phase
    return ""


def context_lost(labels: Iterable[str], has_agent_comment: bool) -> bool:
    """Whether the thread shows the-loop has already worked this work item.

    The caller supplies the second half — *this machine remembers nothing* —
    because what counts as memory differs by caller (a poll ledger, a session
    record, a graph pointer). Here we answer only the durable half, from the two
    facts that survive the machine.

    ``has_agent_comment`` is the stronger of the two and the reason the phase
    label is not asked alone: an item can be worked for days before its first
    label lands (a contribution loop writes none at all for its consuming
    repository), while a thread the-loop has posted on is unambiguous.
    """
    return bool(has_agent_comment) or bool(advanced_phase(labels))


def context_lost_notice(ref: str, cutoff: str) -> str:
    """The one comment posted on a work item the-loop has had to re-adopt.

    Pure, and — like :func:`the_loop.poller.poller.giveup_notice` — **unable to
    echo anything a commenter wrote**: every value it interpolates is either
    the-loop's own prose, the work item's ref, or a timestamp the-loop minted.
    That is what makes :func:`the_loop.authz.mark_self_authored` safe to apply,
    because the marker asserts authorship and must never be put on foreign text.
    """
    return mark_self_authored(
        f"🧠 **the-loop no longer has its own record of `{ref}`.**\n"
        "\n"
        "This machine is new to the work item — its session, its transcript and "
        "its notes of what had already been processed are gone (a rebuilt host, "
        "a fresh state directory, or a deliberate `the-loop reset`). The work "
        "item itself is untouched: the ticket, the thread, the branch and "
        "everything under `docs/specs/` are where they were.\n"
        "\n"
        f"**Nothing posted before {cutoff} will be acted on again.** The whole "
        "thread up to that instant — including any `the-loop` command and any "
        "approval in it — has been marked as already seen, because the-loop "
        "cannot prove it has not already run it, and running an old command "
        "twice is worse than not running it.\n"
        "\n"
        "**If something was still outstanding, post it again.** A new comment is "
        "read normally, with nothing to undo first.\n"
        "\n"
        "**The process pointer has not been moved.** the-loop will not restart a "
        "work item it can see has advanced; if this item needs its pointer "
        "re-established on this machine, an operator does it explicitly:\n"
        "\n"
        "```sh\n"
        "the-loop check <id>                 # what the artifacts say the state is\n"
        "the-loop graph force <id> --to <node> --reason <why>\n"
        "```\n"
    )


#: Handed to a spawned session whose work item has advanced but whose harness
#: conversation this machine never had. The auto-execute prompt otherwise tells
#: an agent to read the thread and start the loop, which — read by an agent with
#: no memory of days of work — produces a confident "picking up where I left
#: off" and a second draft of an artifact that already exists.
RECOVERY_NOTICE = """\
**This is a NEW conversation replacing one that was lost.** This work item has
been worked before — its ticket carries a phase label from an earlier run — but
the harness conversation, the session transcript and this machine's record of
the work item's process state are all gone. Nothing you remember about this item
exists; nothing in this prompt is a continuation.

So before you produce, post or re-post ANY artifact:

1. Find what already exists. Look for the work item's pull request and its
   branch, and read `docs/specs/<id>/` on it — `requirements.md`/`bugfix.md`,
   `design.md`, `testing-plan.md`, `tasks.md`, `execution-log.md` and
   `graph-state.json`. Read the thread from the top.
2. Reconcile the process state against them. The `the-loop process state` block
   in this prompt may be absent or behind what the artifacts show; where they
   disagree, the checked-in artifacts and the thread are the evidence, and
   `the-loop check <id>` re-derives the position from them.
3. Report what you found on the ticket before doing anything else — which
   artifacts exist, which gates the thread shows already approved, and where you
   believe the work item actually stands.
4. Never re-ask an approved gate, re-draft an artifact that exists, or claim to
   be resuming a conversation. You are not.
"""


def recovery_prompt_notice(advanced: bool, has_pointer: bool) -> str:
    """:data:`RECOVERY_NOTICE` when this spawn is a re-adoption, else ``""``.

    ``has_pointer`` is whether this machine holds graph state for the item; an
    ordinary spawn renders the empty string, so every other prompt is
    byte-identical to the one the-loop has always sent (R5.2).
    """
    return RECOVERY_NOTICE if advanced and not has_pointer else ""
