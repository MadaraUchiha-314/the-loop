"""Core capability: the fleet — which instances exist, and registering one (issue-374).

Served by **every** role (decision-138 D9): a worker answers with one row, itself, so
the dashboard's Instances tab has one renderer and one code path; a manager answers
with its own row first and then one per registered member, each from a probe no
older than ``manager.probeIntervalSeconds``.

Registration is a **config write** (decision-138 D4): ``register_instance`` and
``unregister_instance`` patch ``instance.manager.instances`` through
:func:`the_loop.core.config.update_config` — the splice that keeps the operator's
comments, the schema check, the migration gate, the atomic write and the
``config.updated`` event — so a hand edit, the dashboard, the CLI and the API are one
path and the file is the only store. Neither is an MCP tool (R4.5).
"""

from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

from .. import eventlog
from ..api.config import base_url
from ..instance import NAME_RE, parse_member_url
from . import config as core_config
from .instance import describe_instance, instance_config

__all__ = [
    "LIVE",
    "MISMATCHED",
    "UNREACHABLE",
    "list_instances",
    "register_instance",
    "self_row",
    "unregister_instance",
]

#: The three states a row can be in. A worker's own row, and a manager's own, are
#: always ``live``: it is this process.
LIVE, UNREACHABLE, MISMATCHED = "live", "unreachable", "mismatched"


def _version() -> str:
    try:
        return version("the-loopy-one")
    except PackageNotFoundError:  # pragma: no cover — source checkout
        return "unknown"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def self_row(config: Optional[dict] = None) -> Dict[str, Any]:
    """This instance as one fleet row — the shape a manager reports for a member.

    ``url`` is the service address this config binds, ``state`` is ``live`` (it is
    this process), and the counts come from :func:`describe_instance` so the tab
    and ``GET /api/v1/instance`` cannot disagree.
    """
    doc = describe_instance(config)
    return {
        "name": doc["name"],
        "url": base_url(config),
        "state": LIVE,
        "version": _version(),
        "mode": doc["scope"]["mode"],
        "managedCount": len(doc["managed"]),
        "sessionCount": int(doc.get("sessionCount") or 0),
        "probedAt": _now(),
    }


def list_instances(config: Optional[dict] = None, *, fleet: Any = None) -> Dict[str, Any]:
    """``{role, name, instances: [...]}`` (R3.1).

    ``fleet`` is a manager's :class:`~the_loop.manager.fleet.Fleet`; passed by the
    manager facade so the rows come from its probe cache rather than a second set of
    connections. Without one — a worker, or a manager read outside the service — the
    document holds the self row alone.
    """
    identity = instance_config(config)
    rows: List[Dict[str, Any]] = [self_row(config)]
    if fleet is not None:
        rows.extend(fleet.rows())
    return {"role": identity.role, "name": identity.name, "instances": rows}


def _require_manager(config: Optional[dict]) -> None:
    identity = instance_config(config)
    if not identity.is_manager:
        raise ValueError(
            "this instance manages no others (instance.role is "
            f"{identity.role!r}); set instance.role: manager in its CLI config to "
            "register instances with it"
        )


def _raw_registry(config: Optional[dict]) -> List[Any]:
    block = (config or {}).get("instance")
    manager = block.get("manager") if isinstance(block, dict) else None
    entries = manager.get("instances") if isinstance(manager, dict) else None
    return list(entries) if isinstance(entries, list) else []


def _write_registry(
    entries: List[Any], config_path: Optional[Union[str, Path]]
) -> Dict[str, Any]:
    # Sparse: only the registry changes. `update_config` proves the merged document
    # against the schema before anything is written, so an entry that would not
    # validate — one this module never builds — leaves the file byte-identical.
    return core_config.update_config(
        {"instance": {"manager": {"instances": entries}}}, config_path
    )


def register_instance(
    config: Optional[dict],
    name: str,
    url: str,
    *,
    config_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Add ``{name, url}`` to the manager's registry (R4.2, R4.3).

    Validates as the reader validates — the grammar, an ``http(s)`` URL without
    userinfo, not this manager's own address, not a name already registered — and
    answers :class:`ValueError` (400) on a violation with nothing written. Does
    **not** require the member to be reachable: an operator registers a box before
    it is up, and the row shows ``unreachable`` until it is. Raises the same on a
    worker, naming ``instance.role`` (R4.4).
    """
    _require_manager(config)
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ValueError(
            "name must fit ^[a-z0-9][a-z0-9-]{0,39}$ — the member's own instance.name"
        )
    normalised = parse_member_url(url)
    if normalised is None:
        raise ValueError(
            "url must be an http:// or https:// address without userinfo, query or "
            "fragment — the member's service address as this manager reaches it"
        )
    if normalised == base_url(config).rstrip("/"):
        raise ValueError(
            "url is this manager's own service address; a manager is its own first "
            "member and is never registered"
        )
    entries = _raw_registry(config)
    for entry in entries:
        if isinstance(entry, dict) and entry.get("name") == name:
            raise ValueError(f"an instance named {name!r} is already registered")
    entries.append({"name": name, "url": normalised})
    result = _write_registry(entries, config_path)
    eventlog.emit("instance.registered", instance=name)
    result["instance"] = name
    return result


def unregister_instance(
    config: Optional[dict],
    name: str,
    *,
    config_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Remove the entry named ``name`` (R4.3); :class:`LookupError` (404) when absent."""
    _require_manager(config)
    entries = _raw_registry(config)
    kept = [
        entry
        for entry in entries
        if not (isinstance(entry, dict) and entry.get("name") == name)
    ]
    if len(kept) == len(entries):
        raise LookupError(f"no instance named {name!r} is registered")
    result = _write_registry(kept, config_path)
    eventlog.emit("instance.unregistered", instance=name)
    result["instance"] = name
    return result
