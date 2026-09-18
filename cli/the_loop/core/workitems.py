"""Core capability: work items — the portable records (issue-161).

Read surface over the per-work-item store (``portable/<slug>.json``,
issue-128/130). Writes stay with the two ingresses that own their sections;
the control plane reads.

What it serves is the record **plus this machine's poll clocks** (issue-382).
``lastPolledAt`` and ``closureCheckedAt`` moved out of the tracked record — they
are readings of cycles this machine ran, and rewriting them every minute left
every operator whose ``state.root`` is a repository with a dirty working tree —
so the two halves are joined again here, at the only place that reads both. The
served shape is unchanged, which is why the dashboard's *last activity*
(``ui/src/api/model.ts``) and the attention surface's clean-poll rule
(``core/attention.py``) needed no edit at all.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..pollclocks import PollClockStore
from ..state import layout_from_config, legacy_layout
from ..workitem import POLL, PULL_REQUESTS, WorkItemRef, WorkItemStore


def _store(config: Optional[dict] = None) -> WorkItemStore:
    layout = layout_from_config(config or {})
    return WorkItemStore(layout.portable_dir, legacy=legacy_layout(layout))


def _clocks(config: Optional[dict] = None) -> PollClockStore:
    return PollClockStore(layout_from_config(config or {}).poll_clocks)


def _with_clocks(record: Dict[str, Any], clocks: PollClockStore) -> Dict[str, Any]:
    """``record`` with each ledger it carries dated by this machine's clocks.

    Into **existing** sections only: a record with no ``poll`` does not grow one
    because a clock outlived it, so "the record, plus what this machine knows
    about when it looked" stays a true description of what is served.
    """
    ledger = record.get(POLL)
    if isinstance(ledger, dict):
        ledger.update(clocks.get(str(record.get("ref") or "")))
    ledgers = record.get(PULL_REQUESTS)
    if isinstance(ledgers, dict):
        for ref, entry in ledgers.items():
            if isinstance(entry, dict):
                entry.update(clocks.get(str(ref)))
    return record


def list_work_items(config: Optional[dict] = None) -> List[Dict[str, Any]]:
    """Every portable record, ordered by ref — the shape the index derives from."""
    store = _store(config)
    clocks = _clocks(config)
    records = []
    for ref in sorted(store.refs()):
        records.append(
            get_work_item(ref, config=config, _store_inst=store, _clocks_inst=clocks)
        )
    return records


def get_work_item(
    ref: str,
    config: Optional[dict] = None,
    _store_inst: Optional[WorkItemStore] = None,
    _clocks_inst: Optional[PollClockStore] = None,
) -> Dict[str, Any]:
    """One work item's portable record; ``ValueError`` on a malformed ref,
    ``LookupError`` when no record exists."""
    parsed = WorkItemRef.parse(ref)  # raises ValueError on malformed input
    store = _store_inst or _store(config)
    record = store.read(parsed)
    if not record.get("ref"):
        raise LookupError(f"no record for work item {ref}")
    return _with_clocks(record, _clocks_inst or _clocks(config))
