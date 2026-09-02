"""The ledger envelope — how a recorded event says where it came from (issue-309).

When the bus records an event that originated off the ledger, the comment (or issue)
it writes carries one invisible HTML comment beside the visible attribution::

    <!-- the-loop:event {"type":"gate.feedback","source":"slack",
                         "actor":{"slack":"U0456","github":"octocat"},
                         "ts":"2026-09-02T10:00:00Z"} -->

Both halves live here — :func:`stamp` and :func:`parse` — for the reason
:mod:`the_loop.authz` gives for the self-authored marker: what the-loop writes and what
it recognises must be the same lines of code.

The envelope is **provenance, never authority**. Ingress reads it for exactly two
things: to skip re-publishing a record as a ``comment.*`` event (the channel that raised
it already has it — loop prevention across channels), and, in the graph's human gates,
to attribute the record to the person it names — and that only when the comment's real
poster is an authorized login and the named login is too (decision-103 D4). An envelope
on a comment by anyone else is text.

The parser accepts one JSON object with string leaves under the four fixed keys and
returns ``None`` for anything else; it never raises.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Mapping, Optional

__all__ = ["ENVELOPE_PREFIX", "Envelope", "has_envelope", "parse", "stamp"]

ENVELOPE_PREFIX = "<!-- the-loop:event "
_ENVELOPE_RE = re.compile(r"<!--\s*the-loop:event\s+(\{.*?\})\s*-->", re.DOTALL)
_KEYS = ("type", "source", "actor", "ts")


@dataclass(frozen=True)
class Envelope:
    """What a recorded event says about itself."""

    type: str
    source: str
    actor: Mapping[str, str] = field(default_factory=dict)
    ts: str = ""

    def to_json(self) -> str:
        payload: Dict[str, object] = {
            "type": self.type,
            "source": self.source,
            "actor": {str(k): str(v) for k, v in self.actor.items() if v},
            "ts": self.ts or _utcnow(),
        }
        # `-->` inside a value would close the HTML comment early; a JSON string
        # cannot carry it unescaped once `>` is encoded.
        return json.dumps(payload, separators=(",", ":"), sort_keys=True).replace(
            ">", "\\u003e"
        )


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp(body: str, envelope: Envelope) -> str:
    """``body`` with the envelope appended. Idempotent per envelope type/source."""
    existing = parse(body)
    if existing and (existing.type, existing.source) == (
        envelope.type,
        envelope.source,
    ):
        return body
    return f"{body.rstrip()}\n\n{ENVELOPE_PREFIX}{envelope.to_json()} -->\n"


def has_envelope(body: Optional[str]) -> bool:
    return parse(body) is not None


def parse(body: Optional[str]) -> Optional[Envelope]:
    """The envelope in ``body`` — ``None`` when there is none, or it is malformed."""
    if not body:
        return None
    match = _ENVELOPE_RE.search(body)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    event_type = payload.get("type")
    source = payload.get("source")
    if not isinstance(event_type, str) or not isinstance(source, str):
        return None
    if not event_type.strip() or not source.strip():
        return None
    actor_raw = payload.get("actor")
    actor: Dict[str, str] = {}
    if isinstance(actor_raw, dict):
        for key, value in actor_raw.items():
            if isinstance(key, str) and isinstance(value, str) and value:
                actor[key] = value
    elif actor_raw is not None:
        return None
    ts = payload.get("ts")
    if ts is not None and not isinstance(ts, str):
        return None
    if any(key not in _KEYS for key in payload):
        return None
    return Envelope(type=event_type, source=source, actor=actor, ts=ts or "")
