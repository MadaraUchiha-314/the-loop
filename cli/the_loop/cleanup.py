"""Reclaim the LOCAL resources a finished work item accumulated (issue-186).

Every started work item leaves three kinds of thing on the machine running
the-loop: one tmux session per endpoint (its own, plus one per pull request
delivering it — issue-172), one workspace checkout (a git worktree under the
shared clone, or a whole per-work-item folder — issue-76), and one machine-local
session record. When the work item ends, ``Dispatcher.close_session``
*transitions* the record and, by default, **keeps** the other two: retaining the
tmux session is the whole point of issue-86, and ``keepCheckoutOnClose`` is the
operator's own choice. Those defaults are right for the minutes after a merge
and wrong for the months after, and nothing ever came back to reclaim them.

This module is that return trip. Like :mod:`the_loop.reset` it removes nothing
itself — it owns **what is removed, in which order, and how a partial failure is
reported**, and takes the two acts that need a daemon (ending an endpoint,
removing a checkout) as injected callables. That split is what makes the
ordering testable with no tmux, no git and no dispatcher.

## What cleanup is *not*

It is not :mod:`the_loop.reset`. A reset is bootstrap-and-recovery: it forgets
everything, the **portable** record included, so a work item starts over on
newly-fixed code. Cleanup is the end of a life cycle, and the portable half —
``control`` (what an authorized user last asked for), ``poll`` (what the poller
has already seen) and ``graph`` (the phases this item was frozen to walk) — is
kept *on purpose*: it is the persistence and tracking that outlives the machine.
Nothing here imports :class:`the_loop.workitem.WorkItemStore`, and that absence
is asserted by a test rather than left to review.

It is also strictly **local**. No branch is deleted, no pull request or issue is
touched, no label removed — the only remote traffic on the cleanup path is the
paper trail the graph's own entry chain posts.

## The order, and why

1. every **endpoint**'s harness is ended and its tmux session killed — the
   harness process's cwd is inside the checkout, so it goes first;
2. the **checkout** is removed;
3. the **session record** is closed and then deleted — last, so a crash
   mid-cleanup leaves a record naming resources that have gone (run it again)
   rather than resources with no record naming them.

The graph move that records the transition happens *before* all of this, in the
caller (:meth:`the_loop.webhook.dispatcher.Dispatcher.cleanup_work_item`), for
the same reason step 1 precedes step 2: the node's entry chain writes into the
checkout.

Every step is wrapped: a failure lands in :attr:`CleanupOutcome.errors` and the
rest still runs, because a work item half torn down is worse than one reported
honestly as partly torn down.

Spec: docs/specs/issue-186/design.md § Architecture.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple, Union

from . import eventlog
from .sessions import Session, SessionRegistry, WorkItemRef

logger = logging.getLogger("the-loop.cleanup")

__all__ = [
    "PIECES",
    "SESSION",
    "TMUX",
    "WORKSPACE",
    "CleanupOutcome",
    "cleanup_work_item",
]

#: The pieces a cleanup can remove, in removal order. The same vocabulary the
#: report, the CLI and the event log speak — ``reset.PIECES``'s trick, so an
#: operator reading either verb's output is reading one set of words. The
#: harness is not a piece of its own: it lives *inside* a tmux session, and
#: ``TMUX`` means "that conversation is over, process included".
TMUX = "tmux"
WORKSPACE = "workspace"
SESSION = "session"
PIECES: Tuple[str, ...] = (TMUX, WORKSPACE, SESSION)

#: Ends ONE endpoint: terminate the harness inside it, then kill its tmux
#: session. Returns whether a tmux session was actually there to end.
#: ``Dispatcher._end_endpoint`` is the production implementation.
EndSession = Callable[[Session], bool]

#: Removes a work item's workspace checkout, returning whether one existed.
#: ``Dispatcher._remove_checkout`` is the production implementation.
RemoveCheckout = Callable[[WorkItemRef], bool]


@dataclass(frozen=True)
class CleanupOutcome:
    """What one work item's cleanup did (or, on a dry run, would do)."""

    ref: str
    removed: Tuple[str, ...] = ()
    #: Every endpoint whose conversation was ended — the work item's own ref and
    #: one per pull request. Reported because "which agents did you kill" is the
    #: question an operator asks next, and the record is gone by then.
    endpoints: Tuple[str, ...] = ()
    errors: Tuple[str, ...] = field(default=())
    dry_run: bool = False

    @property
    def found(self) -> bool:
        """Whether there was anything here at all.

        A work item whose only state was an unreadable record counts as found:
        "nothing to clean up" must never be how a failure is reported.
        """
        return bool(self.removed or self.endpoints or self.errors)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "ref": self.ref,
            "removed": list(self.removed),
            "endpoints": list(self.endpoints),
            "errors": list(self.errors),
            "dryRun": self.dry_run,
        }


def _as_ref(work_item: Union[str, WorkItemRef]) -> WorkItemRef:
    if isinstance(work_item, WorkItemRef):
        return work_item
    return WorkItemRef.parse(work_item)


def _endpoints(record: Session) -> List[Session]:
    """Every conversation on ``record``, pull requests first.

    The work item's own session is ended **last**: it is the one an operator is
    most likely to be watching, and ending it first would kill the conversation
    that would otherwise report what happened to the others.
    """
    return [pr for pr in record.pull_requests if pr.tmux_target] + (
        [record] if record.tmux_target else []
    )


def cleanup_work_item(
    work_item: Union[str, WorkItemRef],
    *,
    registry: SessionRegistry,
    end_session: Optional[EndSession] = None,
    remove_checkout: Optional[RemoveCheckout] = None,
    dry_run: bool = False,
    actor: str = "",
    source: str = "",
) -> CleanupOutcome:
    """Remove this machine's runtime resources for ``work_item``.

    ``end_session`` and ``remove_checkout`` are the two acts that need a daemon;
    ``None`` means "do not do that part" — what a dry run passes, and what a unit
    test passes when only the ordering is under test.

    Deliberately tolerant of a **missing session record** (issue-186 R4.1/R4.2):
    a work item whose record was already deleted, or which this machine never
    registered, may still have a checkout on disk — so the checkout is removed
    from the ref alone, and the whole call reports honestly rather than refusing.
    """
    ref = _as_ref(work_item)
    removed: List[str] = []
    errors: List[str] = []
    endpoints: List[str] = []

    record = registry.find_by_work_item(ref, include_closed=True)
    if record is not None:
        for endpoint in _endpoints(record):
            endpoints.append(endpoint.work_item.ref)
            if dry_run or end_session is None:
                continue
            try:
                if end_session(endpoint):
                    _note(removed, TMUX)
            except Exception as exc:  # noqa: BLE001 — one stuck pane must not
                # strand the checkout and the record behind it.
                errors.append(
                    f"could not end the session for {endpoint.work_item.ref}: {exc}"
                )
        if dry_run and endpoints:
            _note(removed, TMUX)

    # The checkout is keyed by the work item alone, so it is reclaimed whether or
    # not a record survives to describe it.
    if remove_checkout is not None and not dry_run:
        try:
            if remove_checkout(ref):
                _note(removed, WORKSPACE)
        except Exception as exc:  # noqa: BLE001 — advisory, as every workspace
            # teardown in the-loop is: report it and keep going.
            errors.append(f"could not remove the workspace checkout: {exc}")

    if record is not None:
        if dry_run:
            _note(removed, SESSION)
        else:
            try:
                registry.close(ref)  # a live record must not be deleted while active
                if registry.forget(ref):
                    _note(removed, SESSION)
            except OSError as exc:
                errors.append(f"could not remove the session record: {exc}")

    outcome = CleanupOutcome(
        ref=ref.ref,
        removed=tuple(removed),
        endpoints=tuple(endpoints),
        errors=tuple(errors),
        dry_run=dry_run,
    )
    if not dry_run:
        # Emitted even when nothing was found: "there was nothing left of that
        # work item on this machine" is a fact worth being able to look up, and
        # a silent no-op is exactly the gap the log exists to close.
        eventlog.emit(
            "session.cleaned",
            level="warning" if errors else "info",
            work_item=outcome.ref,
            actor=actor or None,
            source=source or None,
            removed=list(outcome.removed),
            endpoints=list(outcome.endpoints) or None,
            found=outcome.found,
            error="; ".join(errors) or None,
        )
        logger.info(
            "cleaned up %s (removed: %s)", outcome.ref, ", ".join(removed) or "nothing"
        )
    return outcome


def _note(removed: List[str], piece: str) -> None:
    """Record ``piece`` once, keeping :data:`PIECES` order in the report."""
    if piece not in removed:
        removed.append(piece)
        removed.sort(key=PIECES.index)
