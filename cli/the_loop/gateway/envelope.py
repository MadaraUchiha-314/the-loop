"""The stored event's shape, and the vocabulary the gateway and its clients share
(issue-496, R6.2, R10.1).

An :class:`Envelope` is what every adapter builds from a provider delivery and what
every fetch returns inside a :class:`Delivery`. It carries the provider's payload
**verbatim** plus exactly the routing fields R6.2 names — the gateway interprets a
payload only far enough to resolve the work item it concerns (:mod:`.adapters.common`),
and everything else (the control grammar, authorization, the self-marker check) runs on
the instance against the same bytes it would have read from the provider directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

__all__ = [
    "ALLOWED_HEADERS",
    "DEAD_LETTERED",
    "Delivery",
    "Envelope",
    "GATEWAY_EVENT_KEY",
    "OUTCOMES",
    "PROVIDERS",
    "ROLES",
    "SOURCES",
    "UNASSIGNED",
    "is_outcome",
    "subject_for_slug",
    "utcnow",
]

PROVIDERS: Tuple[str, ...] = ("github", "jira", "slack")
SOURCES: Tuple[str, ...] = ("webhook", "socket", "poll")
#: A claim's role (R5.3): the session that drives the work item on its ticket, or the
#: one reviewing its pull request (issue-279's binding to the PR).
ROLES: Tuple[str, ...] = ("driver", "reviewer")

#: The subject an event waits on while no claim, binding or actor registration covers
#: its work item (R2.2). Not a queue: a held event has ``routed = 0`` and no delivery
#: rows until a claim or binding routes it.
UNASSIGNED = "unassigned"

#: The provider headers an envelope keeps (§Security design — an allow-list, so a
#: provider's incidental headers never reach the store). Lower-cased on the way in.
ALLOWED_HEADERS: Tuple[str, ...] = (
    "x-github-event",
    "x-github-delivery",
    "x-github-hook-installation-target-id",
    "x-slack-request-timestamp",
    "x-atlassian-webhook-identifier",
)

#: Commit outcomes (design §gateway/consume.py). ``failed`` leaves the delivery pending
#: so a later fetch returns it; everything else commits it. ``dropped:<reason>`` carries
#: the dispatcher's reason after the colon.
OUTCOMES: Tuple[str, ...] = ("delivered", "spawned", "dropped", "failed")
DEAD_LETTERED = "dead-lettered"

#: The private payload key the client stamps before handing a delivery to today's
#: pipeline, so the dispatcher's ``dispatch.*`` records can carry ``gateway_event_id``
#: beside the delivery id (R10.2). Same convention as the router's ``PROVIDER_KEY``.
GATEWAY_EVENT_KEY = "x-the-loop-gateway-event"


def is_outcome(value: str) -> bool:
    head = value.split(":", 1)[0]
    return head in OUTCOMES or value == DEAD_LETTERED


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def subject_for_slug(slug: str) -> str:
    """``loop-<slug>``: the subject of a work item is named after the tmux slug the
    instance already uses for it (R2.1), so one name follows the work item from the
    provider to the pane."""
    return f"loop-{slug}"


@dataclass(frozen=True)
class Envelope:
    """One stored event — the ``event`` of every delivery and the ``events`` row."""

    subject: str
    provider: str
    source: str
    delivery_id: str
    kind: str
    payload: Any
    work_item: Optional[str] = None
    headers: Mapping[str, str] = field(default_factory=dict)
    received_at: str = field(default_factory=utcnow)
    attempt: int = 1
    id: Optional[int] = None  # assigned by the store on append
    #: Who caused the event, for actor routing (R5.5): ``(provider, login)`` or none.
    actor: Optional[str] = None

    def to_json(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "provider": self.provider,
            "source": self.source,
            "deliveryId": self.delivery_id,
            "receivedAt": self.received_at,
            "workItem": self.work_item,
            "kind": self.kind,
            "headers": dict(self.headers),
            "payload": self.payload,
            "attempt": self.attempt,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "Envelope":
        return cls(
            id=data.get("id"),
            subject=str(data["subject"]),
            provider=str(data["provider"]),
            source=str(data["source"]),
            delivery_id=str(data["deliveryId"]),
            received_at=str(data.get("receivedAt") or utcnow()),
            work_item=data.get("workItem"),
            kind=str(data["kind"]),
            headers=dict(data.get("headers") or {}),
            payload=data.get("payload"),
            attempt=int(data.get("attempt") or 1),
        )

    def payload_bytes(self) -> bytes:
        """The payload as stored: bytes, verbatim when the adapter had bytes."""
        if isinstance(self.payload, (bytes, bytearray)):
            return bytes(self.payload)
        return json.dumps(self.payload, separators=(",", ":"), default=str).encode()

    @staticmethod
    def filter_headers(headers: Mapping[str, str]) -> Dict[str, str]:
        """Keep only :data:`ALLOWED_HEADERS`, lower-cased."""
        kept: Dict[str, str] = {}
        for name, value in headers.items():
            lowered = name.lower()
            if lowered in ALLOWED_HEADERS:
                kept[lowered] = str(value)
        return kept


@dataclass(frozen=True)
class Delivery:
    """One row of an instance's queue, as a fetch returns it."""

    seq: int
    attempt: int
    event: Envelope
    subject: str = ""

    def to_json(self) -> Dict[str, Any]:
        env = self.event.to_json()
        env["attempt"] = self.attempt
        return {
            "seq": self.seq,
            "attempt": self.attempt,
            "subject": self.subject or self.event.subject,
            "event": env,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "Delivery":
        event = Envelope.from_json(data["event"])
        return cls(
            seq=int(data["seq"]),
            attempt=int(data.get("attempt") or event.attempt),
            event=event,
            subject=str(data.get("subject") or event.subject),
        )
