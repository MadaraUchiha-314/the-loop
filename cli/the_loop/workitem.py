"""One portable file per work item, with two sections (issue-128, decision-046).

``<state.root>/portable/<slug>.json`` is everything about a work item that is
true on any machine::

    {
      "ref": "github:octo/repo#15",
      "url": "https://github.com/octo/repo/issues/15",
      "control": {"command": "start", "actor": "octocat", …},
      "poll":    {"seenComments": [...], "commentAttempts": {...}, …}
    }

The ``url`` is a navigation aid derived from the ref (issue-130), because these
files are tracked and therefore read by people. Beside the records sits
``index.json``, one derived list of everything in the directory — see
:meth:`WorkItemStore._write_index`. Neither is read by the-loop.

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
from typing import Any, Dict, List, Optional, Tuple, Union

from .sessions import WorkItemRef
from .state import LegacyLayout

logger = logging.getLogger("the-loop.workitem")

__all__ = ["CONTROL", "GRAPH", "INDEX_FILE", "POLL", "SEALED", "WorkItemStore"]

#: The two sections of a work-item record.
CONTROL = "control"
POLL = "poll"
#: The graph a work item was frozen to walk (issue-177): every node with whether
#: it is walked or skipped, written when an authorized user answers the
#: `phase-selection` gate. **Portable** on purpose — the shape of a work item's
#: process is part of tracking the work item, not of the machine running it, so
#: it travels with `control` and survives a hand-off to another host.
GRAPH = "graph"

#: Every section a record may carry. A record with none of them is deleted
#: rather than kept as an empty husk.
SECTIONS = (CONTROL, POLL, GRAPH)

#: The directory's index (issue-130) — one file listing every record beside it,
#: so ``portable/`` answers "what is being tracked?" without opening each record.
#: Derived on every write and read by nothing: see :meth:`WorkItemStore._write_index`.
INDEX_FILE = "index.json"

#: Marks a record whose sections were all deliberately removed while a
#: pre-issue-128 tree is still on disk. Without it, an ended work item would be
#: re-armed from the old tree the next time anything asked about it.
SEALED = "sealed"


def _as_ref(work_item: Union[str, WorkItemRef]) -> WorkItemRef:
    if isinstance(work_item, WorkItemRef):
        return work_item
    return WorkItemRef.parse(work_item)


def _url_for(ref: str) -> str:
    """``ref``'s browser URL, or ``""`` when it has none (or will not parse)."""
    try:
        return WorkItemRef.parse(ref).url
    except ValueError:
        return ""


def _identified(ref: WorkItemRef, record: Dict[str, Any]) -> Dict[str, Any]:
    """``record`` with its identity first: the ref, then the URL when derivable.

    Key order is normalised on write, so a record does not carry the order its
    sections happened to be written in — these files are read by people, in a
    pull-request diff (issue-130). ``url`` is a navigation aid *derived* from the
    ref, and absent rather than guessed when none can be derived; the ref itself
    is untouched, because it is what parses, what the filename comes from, and
    what the pre-issue-128 shim keys on.
    """
    head: Dict[str, Any] = {"ref": ref.ref}
    if ref.url:
        head["url"] = ref.url
    return {**head, **{k: v for k, v in record.items() if k not in ("ref", "url")}}


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
        return {str(record["ref"]): path for path, record in self._records()}

    def _records(self) -> List[Tuple[Path, Dict[str, Any]]]:
        """``(path, record)`` for every readable record, sorted by file name.

        Three things in the directory are deliberately *not* records: the index
        (:data:`INDEX_FILE`, which describes them), the atomic writer's ``.tmp``
        leftovers (not ``*.json``), and any stray a person left behind. A file
        that will not parse, or that names no work item, is skipped rather than
        described from its filename.
        """
        if not self.root.is_dir():
            return []
        found = []
        for path in sorted(self.root.glob("*.json")):
            if path.name == INDEX_FILE:
                continue
            record = _read_json(path)
            if isinstance(record, dict) and str(record.get("ref") or ""):
                found.append((path, record))
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
        record = self.read(ref)
        record[name] = data  # None is a tombstone: "deliberately not recorded"
        if not any(isinstance(record.get(s), dict) for s in SECTIONS):
            if not self._legacy_holds(ref):
                self.drop(ref)
                return
            record = {SEALED: True}
        self._write_json(self.path_for(ref), _identified(ref, record))
        self._write_index()

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        """Write ``payload`` to ``path`` atomically (``tempfile`` + ``os.replace``).

        Every file this store produces goes through here, so a crash never leaves
        half of one — a record or the index alike.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    # -- the index -------------------------------------------------------------

    def _index_entries(self) -> List[Dict[str, Any]]:
        """One entry per record: what it is, where it is, what it holds."""
        entries: List[Dict[str, Any]] = []
        for path, record in self._records():
            ref = str(record["ref"])
            entry: Dict[str, Any] = {"ref": ref}
            url = _url_for(ref)
            if url:
                entry["url"] = url
            entry["file"] = path.name
            entry["sections"] = [
                section for section in SECTIONS if isinstance(record.get(section), dict)
            ]
            if record.get(SEALED):
                entry["sealed"] = True  # explains a record with no sections
            entries.append(entry)
        return sorted(entries, key=lambda entry: entry["ref"])

    def _write_index(self) -> None:
        """Rewrite — or remove — the directory's index (issue-130).

        `portable/` is the tracked half of the-loop's state, so it is read by a
        *person*: in a pull-request diff, or with ``jq``. The index is what lets
        the directory answer "which work items is the-loop tracking, and where do
        they live?" without opening every record.

        **Derived, on every write.** The entries are rebuilt by scanning the
        directory rather than maintained incrementally, so a record added or
        removed by hand — or written by a version that kept no index — is picked
        up by the next write, and a forged index (this file is tracked, so it is
        proposable by anyone who can open a pull request) cannot survive one.
        Nothing in the-loop reads it, which is what keeps a stale index a
        cosmetic problem rather than a behavioural one, and what makes two
        machines conflicting on it safe to resolve by taking either side.

        **Best-effort.** The record beside it is a fact about a work item; this is
        a convenience. Failing an arming ``start`` because a convenience could not
        be written would be a silent disarm, so an ``OSError`` here is logged and
        swallowed. The directory keeps no empty index: when the last record goes,
        so does this file.
        """
        target = self.root / INDEX_FILE
        entries = self._index_entries()
        try:
            if entries:
                self._write_json(target, {"workItems": entries})
            else:
                target.unlink(missing_ok=True)
        except OSError as exc:  # advisory: never break the write it accompanies
            logger.warning("could not update the portable index %s: %s", target, exc)

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
        self._write_index()
        return True
