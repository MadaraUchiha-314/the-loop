"""When this machine's poller last looked at a work item (issue-382).

Two timestamps per ref — ``lastPolledAt`` (the last cycle that listed it) and
``closureCheckedAt`` (the last cycle that asked the provider whether an unlisted
item had ended and was not told *closed*) — kept in one machine-local file,
``<state.root>/local/poll-clocks.json``.

They used to be keys of the ``poll`` section, inside
``<state.root>/portable/<slug>.json`` — the half of the-loop's state that is
**tracked in git**. The poller stamps them every cycle, so an operator whose
``state.root`` sits in a repository (this one does) had a permanently dirty
working tree and a diff nobody wrote before every commit.

The fix is the classification the layout already publishes, applied one level
down. ``docs/cli/state.md`` splits generated state by *does it mean anything on
another machine?*, and the poller's other clock file, ``poll-status.json``, is
already local — "clock readings from one machine's poller. Carried elsewhere
they describe a process that is not there." A per-item poll clock is that same
sentence per item, and it is the only part of the ledger whose loss costs a
**question** rather than a redelivery: without ``seenComments`` a whole thread
is forwarded again; without a clock the item is merely due for its next closure
check, which is one provider call, capped per cycle (decision-115).

Everything here is best-effort in one direction. A missing, unreadable or
mangled file is an **empty** map — every ref reads as "no clock", which the
closure schedule already means *ask now* — and a write that fails is logged and
swallowed. A clock must never be what fails a delivery.

Spec: docs/specs/issue-382/design.md § Components & interfaces.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple, Union

logger = logging.getLogger("the-loop.pollclocks")

__all__ = ["CLOCK_KEYS", "CLOCKS_FILE", "PollClockStore"]

#: The clocks, and the only keys this file carries. The poll ledger keeps them
#: as ordinary keys in memory; these are what :class:`PollClockStore` peels off
#: on the way to disk, so the pair is declared once and read by both sides.
CLOCK_KEYS: Tuple[str, ...] = ("lastPolledAt", "closureCheckedAt")

#: The file's name under ``<state.root>/local/``.
CLOCKS_FILE = "poll-clocks.json"


class PollClockStore:
    """Every ref's poll clocks, in one machine-local JSON file.

    Machine-wide rather than one file per work item — like
    ``local/model-verdicts.json`` and unlike the session record — because there
    is one writer (the poller, holding the single-instance lock) and the whole
    map is two short strings per ref. Keyed by the ref itself, a work item's and
    a pull request's alike: refs are globally unique, so this map needs none of
    the owner relation the portable ledger has to carry.
    """

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self._clocks: Optional[Dict[str, Dict[str, str]]] = None

    @classmethod
    def beside(cls, portable_dir: Union[str, Path]) -> "PollClockStore":
        """The clock file for the state root that holds ``portable_dir``.

        How a caller that already has a :class:`~the_loop.workitem.WorkItemStore`
        finds the file without threading a second path through every signature.
        It is the same location :attr:`the_loop.state.StateLayout.poll_clocks`
        derives from the root, and ``test_pollclocks.py`` pins the two to each
        other so the convenience cannot drift from the declaration.
        """
        return cls(Path(portable_dir).parent / "local" / CLOCKS_FILE)

    # -- reads -----------------------------------------------------------------

    def _load(self) -> Dict[str, Dict[str, str]]:
        if self._clocks is not None:
            return self._clocks
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            data = {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("could not read the poll clocks %s: %s", self.path, exc)
            data = {}
        clocks: Dict[str, Dict[str, str]] = {}
        for ref, entry in ((data or {}).get("clocks") or {}).items():
            if not isinstance(entry, dict):
                logger.debug(
                    "skipping a poll-clock entry that is not a mapping: %s", ref
                )
                continue
            kept = {
                key: value
                for key, value in entry.items()
                if key in CLOCK_KEYS and isinstance(value, str) and value
            }
            if kept:
                clocks[str(ref)] = kept
        self._clocks = clocks
        return clocks

    def get(self, ref: str) -> Dict[str, str]:
        """``ref``'s clocks, or ``{}`` — which reads as *never polled here*."""
        return dict(self._load().get(ref) or {})

    def all(self) -> Dict[str, Dict[str, str]]:
        """Every ref's clocks. Read by nothing on the hot path; used by the
        control plane's listing, which joins them back onto the records."""
        return {ref: dict(entry) for ref, entry in self._load().items()}

    # -- writes ----------------------------------------------------------------

    def put(self, ref: str, clocks: Mapping[str, str]) -> None:
        """Replace ``ref``'s clocks. An empty mapping drops the entry.

        Wholesale rather than merged: the caller is the poll ledger, which holds
        both clocks in memory and writes what it has. A merge here would make
        "this item has no closure check" unsayable.
        """
        kept = {
            key: value
            for key, value in clocks.items()
            if key in CLOCK_KEYS and isinstance(value, str) and value
        }
        entries = self._load()
        if kept:
            entries[ref] = kept
        elif entries.pop(ref, None) is None:
            return  # nothing recorded, nothing to drop: no write
        self._write(entries)

    def forget(self, ref: str) -> None:
        """Drop ``ref``'s clocks — its ledger ended, or was reset."""
        self.put(ref, {})

    def _write(self, entries: Dict[str, Dict[str, str]]) -> None:
        payload = {"clocks": entries}
        directory = self.path.parent
        try:
            directory.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                "w", dir=str(directory), delete=False, encoding="utf-8"
            )
            with handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(handle.name, self.path)
        except OSError as exc:  # never fail a poll cycle over a clock
            logger.warning("could not write the poll clocks %s: %s", self.path, exc)
