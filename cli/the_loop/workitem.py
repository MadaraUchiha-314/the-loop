"""One portable file per work item, with two sections (issue-128, decision-046).

``<state.root>/portable/<slug>.json`` is everything about a work item that is
true on any machine::

    {
      "ref": "github:octo/repo#15",
      "control": {"command": "start", "actor": "octocat", …},
      "poll":    {"seenComments": [...], "commentAttempts": {...}, …}
    }

Before this, the two halves were separate stores in separate directories,
because they have separate writers: the control record comes from a keyword an
authorized user typed, the poll section from what the poller has seen. Grouping
by writer is what produced three stores, a nested ``control/`` directory, and a
``.gitignore`` recipe that needed negations to say "carry these two, not that
one". Grouping by *portability* collapses it to one tracked directory — and, as
a bonus, splits the old single ``poll-state.json`` per work item, so two
machines conflict only if they worked the **same** item.

Two writers on one file means writes are **read-modify-write**: each caller
replaces only its own section, so a poll cycle can never clobber a control
command recorded a moment earlier by the other ingress. The write itself stays
atomic (``tempfile`` + ``os.replace``), so a crash never leaves half a record.

The legacy readers are the upgrade shim. When a section is absent from the new
record, the pre-issue-128 location is consulted — the control record at
``<root>/sessions/control/<slug>.json``, the poll entry inside
``<root>/sessions/poll-state.json`` (or its pre-issue-106 path). Silently
missing either would re-forward a whole thread or forget what was armed. Nothing
writes there any more, so each work item converges on the new layout the first
time it is touched, and the shim is deletable once no old roots remain.

The shim is skipped for a **section** this layout deliberately emptied — a
tombstone (`"control": null`) or a sealed record. Ending a work item clears its
control section, and re-reading the stale ``start`` from the old tree at that
point would re-arm an item that just finished. Per *section*, not per record: the
poll cycle usually writes first during an upgrade, and the old control record
must still be adopted afterwards or an armed item silently disarms.

Spec: docs/specs/issue-128/design.md §9.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union

from .sessions import WorkItemRef
from .state import LegacyLayout

logger = logging.getLogger("the-loop.workitem")

__all__ = ["CONTROL", "POLL", "SEALED", "WorkItemStore"]

#: The two sections of a work-item record.
CONTROL = "control"
POLL = "poll"

#: Marks a record whose sections were all deliberately removed while a
#: pre-issue-128 tree is still on disk. Without it, an ended work item would be
#: re-armed from the old tree the next time anything asked about it.
SEALED = "sealed"


def _as_ref(work_item: Union[str, WorkItemRef]) -> WorkItemRef:
    if isinstance(work_item, WorkItemRef):
        return work_item
    return WorkItemRef.parse(work_item)


def _read_json(path: Path) -> Optional[dict]:
    """Parse ``path``, or ``None`` when it is absent or unreadable.

    A corrupt file is a warning, never an exception: the daemon degrades to
    "nothing recorded" (fail closed for control, first-sight for poll) rather
    than failing an event on a file it could rewrite next cycle.
    """
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("ignoring unreadable state file %s: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None


class WorkItemStore:
    """File-per-work-item store of the portable sections under ``root``."""

    def __init__(self, root: Union[str, Path], legacy: Optional[LegacyLayout] = None):
        self.root = Path(root)
        self.legacy = legacy

    # -- paths -----------------------------------------------------------------

    def path_for(self, work_item: Union[str, WorkItemRef]) -> Path:
        return self.root / f"{_as_ref(work_item).slug}.json"

    def refs(self) -> Dict[str, Path]:
        """``{ref: path}`` for every record on disk (ref read from the file)."""
        found: Dict[str, Path] = {}
        if not self.root.is_dir():
            return found
        for path in sorted(self.root.glob("*.json")):
            record = _read_json(path)
            ref = str((record or {}).get("ref") or "")
            if ref:
                found[ref] = path
        return found

    # -- reads -----------------------------------------------------------------

    def read(self, work_item: Union[str, WorkItemRef]) -> dict:
        """The whole record, or ``{}`` when there is none."""
        return _read_json(self.path_for(work_item)) or {}

    def section(
        self, work_item: Union[str, WorkItemRef], name: str
    ) -> Optional[Dict[str, Any]]:
        """``name``'s contents, falling back to the pre-issue-128 location.

        ``None`` means "nothing recorded anywhere" — distinct from an empty
        section, which means the caller wrote one and it is genuinely empty.

        The fallback is skipped for a section this layout has **deliberately
        emptied** — a tombstone (the key present with a null value, or a sealed
        record). Ending a work item clears its control section, and reading the
        stale ``start`` back out of the old tree at that point would re-arm an
        item that has just finished, which is the opposite of what a durable
        `stop` is for. The check is per *section*, not per record: during an
        upgrade the poller usually writes first, and a control record in the old
        tree must still be adopted afterwards or an armed item silently disarms.
        """
        ref = _as_ref(work_item)
        record = self.read(ref)
        current = record.get(name)
        if isinstance(current, dict):
            return current
        if name in record or record.get(SEALED):
            return None
        return self._legacy_section(ref, name)

    def _legacy_section(self, ref: WorkItemRef, name: str) -> Optional[Dict[str, Any]]:
        if self.legacy is None:
            return None
        if name == CONTROL:
            record = _read_json(Path(self.legacy.control_dir) / f"{ref.slug}.json")
            if record is not None:
                logger.info(
                    "adopting the pre-issue-128 control record for %s; it will be "
                    "rewritten under %s",
                    ref.ref,
                    self.root,
                )
            return record
        if name == POLL:
            for candidate in (self.legacy.poll_state, self.legacy.pre_106_poll_state):
                items = (_read_json(Path(candidate)) or {}).get("items")
                entry = (items or {}).get(ref.ref) if isinstance(items, dict) else None
                if isinstance(entry, dict):
                    logger.info(
                        "adopting the pre-issue-128 poll state for %s from %s; it "
                        "will be rewritten under %s",
                        ref.ref,
                        candidate,
                        self.root,
                    )
                    return entry
        return None

    def has_section(self, work_item: Union[str, WorkItemRef], name: str) -> bool:
        return self.section(work_item, name) is not None

    # -- writes ----------------------------------------------------------------

    def write_section(
        self,
        work_item: Union[str, WorkItemRef],
        name: str,
        data: Optional[Dict[str, Any]],
    ) -> None:
        """Replace one section, leaving the other exactly as it is on disk.

        ``data=None`` removes the section; a record left with neither section is
        deleted rather than kept as an empty husk, so ``portable/`` lists the
        work items the-loop actually knows something about. The one exception is
        the upgrade window: when the old tree still holds something for this work
        item, a **sealed** record is left behind instead, because deleting the
        file would let the old tree resurrect state the-loop just ended.
        """
        ref = _as_ref(work_item)
        target = self.path_for(ref)
        record = self.read(ref)
        record["ref"] = ref.ref
        record[name] = data  # None is a tombstone: "deliberately not recorded"
        if not any(isinstance(record.get(s), dict) for s in (CONTROL, POLL)):
            if not self._legacy_holds(ref):
                self.drop(ref)
                return
            record = {"ref": ref.ref, SEALED: True}
        self.root.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(record, handle, indent=2)
                handle.write("\n")
            os.replace(tmp_name, target)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    def _legacy_holds(self, ref: WorkItemRef) -> bool:
        """Whether the pre-issue-128 tree still has anything for this work item."""
        return any(
            self._legacy_section(ref, name) is not None for name in (CONTROL, POLL)
        )

    def drop(self, work_item: Union[str, WorkItemRef]) -> bool:
        """Delete a work item's whole record. False when there was none."""
        try:
            self.path_for(work_item).unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:  # advisory cleanup — never break a close
            logger.warning("could not remove state for %s: %s", work_item, exc)
            return False
        return True
