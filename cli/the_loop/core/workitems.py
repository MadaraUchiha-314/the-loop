"""Core capability: work items — the portable records (issue-161).

Read surface over the per-work-item store (``portable/<slug>.json``,
issue-128/130). Writes stay with the two ingresses that own their sections;
the control plane reads.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..state import layout_from_config, legacy_layout
from ..workitem import WorkItemRef, WorkItemStore


def _store(config: Optional[dict] = None) -> WorkItemStore:
    layout = layout_from_config(config or {})
    return WorkItemStore(layout.portable_dir, legacy=legacy_layout(layout))


def list_work_items(config: Optional[dict] = None) -> List[Dict[str, Any]]:
    """Every portable record, ordered by ref — the shape the index derives from."""
    store = _store(config)
    records = []
    for ref in sorted(store.refs()):
        records.append(get_work_item(ref, config=config, _store_inst=store))
    return records


def get_work_item(
    ref: str,
    config: Optional[dict] = None,
    _store_inst: Optional[WorkItemStore] = None,
) -> Dict[str, Any]:
    """One work item's portable record; ``ValueError`` on a malformed ref,
    ``LookupError`` when no record exists."""
    parsed = WorkItemRef.parse(ref)  # raises ValueError on malformed input
    store = _store_inst or _store(config)
    record = store.read(parsed)
    if not record.get("ref"):
        raise LookupError(f"no record for work item {ref}")
    return record
