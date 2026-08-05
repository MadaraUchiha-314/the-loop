"""Core capability: the structured event log's query surface (issue-161).

Same filters as ``the-loop events`` (issue-50); the command, the HTTP API and
the MCP tool all funnel here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .. import eventlog


def query_events(
    path: Optional[str] = None,
    *,
    types: Optional[Sequence[str]] = None,
    work_item: Optional[str] = None,
    delivery_id: Optional[str] = None,
    source: Optional[str] = None,
    min_level: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """The last ``limit`` matching events (0 = no limit), oldest first."""
    if limit < 0:
        raise ValueError("limit must be >= 0")
    log_path = path or str(eventlog.load_config().get("path", eventlog.DEFAULT_PATH))
    records = list(
        eventlog.read_events(
            log_path,
            types=list(types or []),
            work_item=work_item,
            delivery_id=delivery_id,
            source=source,
            min_level=min_level,
            since=since,
        )
    )
    return records[-limit:] if limit else records


def event_types() -> Dict[str, str]:
    """The documented event-type catalog (name → description)."""
    return dict(eventlog.EVENT_TYPES)
