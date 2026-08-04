"""Forget everything the-loop's CLI knows about a work item (issue-137).

The CLI remembers a work item in four places, and every one of them survives an
upgrade: the session record (the harness conversation and where it runs), the
``control`` section (what an authorized user last armed), the ``poll`` section
(which comments have already been seen) and the workspace checkout. That memory
is the point — it is what makes a ``stop`` durable and what stops a redelivery
re-forwarding a whole thread — right up until the operator fixes a bug **in
the-loop itself** and needs the item to start over on the new code.

There was no verb for that. ``sessions stop`` ends the session but leaves a
closed record and the whole poll ledger, so the item is still "known"; deleting
the files by hand is worse than it looks, because dropping
``portable/<slug>.json`` outright lets the pre-issue-128 readers hand the old
``start`` straight back (:mod:`the_loop.workitem` § the legacy readers).

So this module removes nothing itself. It **composes** the erasure paths that
already exist — the dispatcher's close path, and
``WorkItemStore.write_section(..., None)``, whose seal-vs-delete rule is exactly
what stops the legacy resurrection — around the one primitive the registry never
had: deleting a session record. Order matters and is not incidental:

1. close the live session, so no harness is left running against records that
   have gone;
2. delete the session record, so a crash mid-reset leaves an item with no
   session rather than an *armed* item whose session the registry forgot;
3. clear ``control`` (which disarms it), then ``poll`` (which makes the thread
   first-sight again).

Every step is wrapped: an unwritable record lands in :attr:`ResetOutcome.errors`
rather than raising, so one broken work item cannot strand the rest of a
``--all`` run.

Spec: docs/specs/issue-137/design.md § Components & interfaces.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple, Union

from . import eventlog
from .sessions import Session, SessionRegistry, WorkItemRef
from .workitem import CONTROL, POLL, WorkItemStore

logger = logging.getLogger("the-loop.reset")

__all__ = [
    "CONTROL",
    "PIECES",
    "POLL",
    "SESSION",
    "WORKSPACE",
    "ResetOutcome",
    "reset_work_item",
    "work_items_with_state",
]

#: The two pieces that are not portable sections, named so the report and the
#: event log speak the same vocabulary as ``docs/cli/state.md``.
WORKSPACE = "workspace"
SESSION = "session"

#: Everything a reset can remove, in removal order.
PIECES: Tuple[str, ...] = (WORKSPACE, SESSION, CONTROL, POLL)

#: Ends a live session and reports whether a workspace checkout went with it.
#: ``Dispatcher.close_session`` is the production implementation.
Closer = Callable[[Session], bool]


@dataclass(frozen=True)
class ResetOutcome:
    """What one work item's reset did (or, on a dry run, would do)."""

    ref: str
    removed: Tuple[str, ...] = ()
    was_live: bool = False
    errors: Tuple[str, ...] = field(default=())
    dry_run: bool = False

    @property
    def found(self) -> bool:
        """Whether there was anything here at all.

        An item whose only state was an unwritable record counts as found: "there
        was nothing to reset" must never be how a failure is reported.
        """
        return bool(self.removed or self.was_live or self.errors)

    @property
    def ok(self) -> bool:
        return self.found and not self.errors

    def to_dict(self) -> dict:
        return {
            "ref": self.ref,
            "removed": list(self.removed),
            "wasLive": self.was_live,
            "errors": list(self.errors),
            "dryRun": self.dry_run,
        }


def _as_ref(work_item: Union[str, WorkItemRef]) -> WorkItemRef:
    if isinstance(work_item, WorkItemRef):
        return work_item
    return WorkItemRef.parse(work_item)


def reset_work_item(
    work_item: Union[str, WorkItemRef],
    *,
    registry: SessionRegistry,
    store: WorkItemStore,
    close: Optional[Closer] = None,
    dry_run: bool = False,
    actor: str = "",
) -> ResetOutcome:
    """Remove this machine's state for ``work_item``.

    ``close`` ends a live session; ``None`` means "do not close" — what a dry run
    passes, and what a unit test passes when the session is beside the point. A
    live session is reported as :attr:`ResetOutcome.was_live` either way, because
    ending a running agent is the least reversible thing a reset does and must be
    visible in the rehearsal too.
    """
    ref = _as_ref(work_item)
    removed: List[str] = []
    errors: List[str] = []

    session = registry.find_by_work_item(ref, include_closed=True)
    was_live = session is not None and session.is_live
    if session is not None:
        if was_live and close is not None and not dry_run:
            try:
                if close(session):
                    removed.append(WORKSPACE)
            except Exception as exc:  # noqa: BLE001 — a teardown failure must not
                # leave the item both running AND remembered: report it, keep going.
                errors.append(f"could not end the session: {exc}")
        if dry_run:
            removed.append(SESSION)
        else:
            try:
                if registry.forget(ref):
                    removed.append(SESSION)
            except OSError as exc:
                errors.append(f"could not remove the session record: {exc}")

    for section in (CONTROL, POLL):
        try:
            if store.section(ref, section) is None:
                continue
            if not dry_run:
                store.write_section(ref, section, None)
            removed.append(section)
        except OSError as exc:
            errors.append(f"could not remove the {section} record: {exc}")

    outcome = ResetOutcome(
        ref=ref.ref,
        removed=tuple(removed),
        was_live=was_live,
        errors=tuple(errors),
        dry_run=dry_run,
    )
    if not dry_run:
        # Emitted even when nothing was found: a reset that hit an empty work
        # item is a fact about the machine, and a silent no-op is exactly the
        # gap the log exists to close. The log itself is append-only — nothing
        # here (or anywhere in this module) can rewrite it.
        eventlog.emit(
            "session.reset",
            level="warning" if errors else "info",
            work_item=outcome.ref,
            actor=actor or None,
            removed=list(outcome.removed),
            was_live=was_live or None,
            found=outcome.found,
            error="; ".join(errors) or None,
        )
        logger.info(
            "reset %s (removed: %s)", outcome.ref, ", ".join(removed) or "nothing"
        )
    return outcome


def work_items_with_state(
    registry: SessionRegistry, store: WorkItemStore
) -> List[WorkItemRef]:
    """Every work item this machine holds any state for, sorted by ref.

    The union of what the two stores themselves recognise as records — the
    registry matches only the files it wrote, and the work-item store skips the
    index, the atomic writer's leftovers and anything naming no work item. A
    stranger's file in a shared state directory is therefore not enumerated, and
    so is never removed by ``--all``.

    A record holding **no** section is not state: a ``sealed`` tombstone marks a
    work item the-loop has already ended (it exists only so a pre-issue-128 tree
    cannot resurrect it). Enumerating one would make ``--all`` report "nothing to
    reset" — and exit non-zero — for a machine that is in fact perfectly clean.
    """
    found: Dict[str, WorkItemRef] = {}
    for session in registry.list_sessions():
        found.setdefault(session.work_item.ref, session.work_item)
    for ref in store.refs():
        if ref in found:
            continue
        try:
            item = WorkItemRef.parse(ref)
        except ValueError:
            logger.warning(
                "ignoring state file naming an unparseable work item: %s", ref
            )
            continue
        if any(store.section(item, section) is not None for section in (CONTROL, POLL)):
            found[ref] = item
    return [found[ref] for ref in sorted(found)]
