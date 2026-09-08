"""Core capability: this instance's identity and managed set (issue-322).

The read surface a future **manager** aggregates across instances (decision-110
D8): every instance serves the same API, and this document says which instance
answered and what it manages. Derived, never kept — the managed set is the union
of the declared list and the records the instance already writes (D2).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..cli_config import apply_instance
from ..control import ControlStore
from ..instance import InstanceConfig
from ..sessions import SessionRegistry, WorkItemRef
from ..state import layout_from_config, legacy_layout

#: The sources a managed entry can come from, in the order they are reported.
DECLARED, SESSION, CONTROL = "declared", "session", "control"


def instance_config(config: Optional[dict] = None) -> InstanceConfig:
    """The ``instance`` block of ``config`` as the dispatcher reads it.

    Through :func:`~the_loop.cli_config.apply_instance` so the reading — every
    warning, every narrowing — is the one construction (decision-109 D1); a
    config handed in directly (the SDK, a test) is read the same way a loaded
    file is.
    """
    doc = dict(config or {})
    doc["routing"] = dict(doc.get("routing") or {})
    apply_instance(doc)
    return InstanceConfig.from_mapping(doc["routing"].get("_instance") or {})


def describe_instance(config: Optional[dict] = None) -> Dict[str, Any]:
    """``{name, scope: {mode, workItems}, managed: [{ref, url, sources}]}``.

    ``managed`` is one row per work item, sorted by ref, each naming every source
    that puts it in the set: ``declared`` (the config), ``session`` (a live
    session record in the registry — the same reading as the dispatcher's
    ``record_owning``), ``control`` (a control record in the portable state).
    """
    instance = instance_config(config)
    layout = layout_from_config(config or {})
    routing = (config or {}).get("routing") or {}
    registry_dir = str(routing.get("registryDir") or layout.local_dir)
    sources: Dict[str, List[str]] = {}

    def add(ref: str, source: str) -> None:
        sources.setdefault(ref, [])
        if source not in sources[ref]:
            sources[ref].append(source)

    for ref in instance.declared:
        add(ref, DECLARED)
    for session in SessionRegistry(registry_dir).list_sessions():
        if session.status != "closed":
            add(session.work_item.ref, SESSION)
    store = ControlStore(layout.portable_dir, legacy=legacy_layout(layout))
    for ref in store.store.refs():
        if store.get(ref) is not None:
            add(ref, CONTROL)

    managed = []
    for ref in sorted(sources):
        row: Dict[str, Any] = {"ref": ref, "sources": sources[ref]}
        try:
            url = WorkItemRef.parse(ref).url
        except ValueError:
            url = ""
        if url:
            row["url"] = url
        managed.append(row)
    doc = instance.to_dict()
    doc["managed"] = managed
    return doc
