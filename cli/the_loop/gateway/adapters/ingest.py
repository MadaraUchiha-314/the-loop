"""The one path from a provider delivery to the store (issue-496, R2.1–R2.4, R5.1, R5.2).

Every adapter — webhook, socket or poll — calls :meth:`Ingest.accept` with the provider's
bytes and headers. It resolves the subject (:func:`~.common.resolve_ref`), decides the
consumers (:func:`~the_loop.gateway.routing.consumers_for`), appends the envelope with its
fan-out in one transaction, records the events, and returns what the adapter should
answer the provider. The adapter answers **after** this returns (R2.4): a store failure
raises, and the adapter turns that into a non-2xx or a withheld ack so the provider
retries.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ... import eventlog
from ..consume import GatewayState
from ..envelope import Envelope
from ..routing import consumers_for
from .common import Unbound, actor_of, dedup_key, resolve_ref

__all__ = ["Ingest", "Outcome"]

logger = logging.getLogger("the-loop.gateway.ingest")

#: How much of a payload `gateway.received` may describe. The payload itself never
#: reaches the log (§Security design).
_SUMMARY_CAP = 120


@dataclass(frozen=True)
class Outcome:
    status: str  # stored | duplicate | dropped | invalid
    event_id: int = 0
    subject: str = ""
    consumers: tuple = ()
    reason: str = ""
    held: bool = False

    @property
    def accepted(self) -> bool:
        return self.status in ("stored", "duplicate")


#: The most a webhook body may weigh (security review SEC-9): GitHub caps its own
#: payloads at 25 MB, and the body is buffered before the signature can be checked.
MAX_BODY_BYTES = 25 * 1024 * 1024
#: The most of an unauthenticated header value that reaches a log line (SEC-8).
HEADER_MAX = 200


def clip(value: str, limit: int = HEADER_MAX) -> str:
    """``value`` cut to ``limit`` characters — for a header an unauthenticated peer
    chose, before it is recorded anywhere."""
    return value if len(value) <= limit else value[:limit] + "…"


def refuse_oversized(request: Any) -> Any:
    """A 413 when the declared ``Content-Length`` is above :data:`MAX_BODY_BYTES`, else
    ``None``; decided from the header, before any of the body is read."""
    from fastapi.responses import JSONResponse

    declared = request.headers.get("content-length")
    try:
        length = int(declared) if declared is not None else 0
    except ValueError:
        length = 0
    if length > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"status": "too large"})
    return None


class Ingest:
    def __init__(self, state: GatewayState) -> None:
        self.state = state

    def accept(
        self,
        provider: str,
        source: str,
        kind: str,
        delivery_id: str,
        headers: Mapping[str, str],
        body: bytes,
        payload: Optional[Any] = None,
        actor: Optional[str] = None,
    ) -> Outcome:
        """Store one delivery. ``payload`` is the parsed body when the adapter already
        has it (Socket Mode hands objects); otherwise ``body`` is parsed here. ``actor``
        overrides what the payload names — the poll adapter knows the item's author
        when the provider's synthesized payload carries no ``sender``."""
        if payload is None:
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                return self._dropped(
                    provider, kind, delivery_id, "invalid-payload", status="invalid"
                )
        if not isinstance(payload, Mapping):
            return self._dropped(
                provider, kind, delivery_id, "invalid-payload", status="invalid"
            )
        store = self.state.store
        try:
            resolved = resolve_ref(provider, kind, payload, store, self.state.config)
        except Unbound as exc:
            return self._dropped(
                provider, kind, delivery_id, exc.reason, detail=str(exc)
            )
        actor = actor or actor_of(provider, kind, payload)
        if provider == "slack" and "token" in payload:
            # Slack's deprecated verification token rides every envelope; the request
            # has been authenticated by now (signature or socket), and the store must
            # not keep a shared secret the-loop never reads (self-review S2)
            payload = {k: v for k, v in payload.items() if k != "token"}
            body = b""
        routing = consumers_for(
            resolved.subject,
            resolved.linked,
            (provider, actor) if actor else None,
            store,
        )
        env = Envelope(
            subject=resolved.subject,
            provider=provider,
            source=source,
            delivery_id=delivery_id,
            kind=kind,
            payload=body if body else payload,
            work_item=resolved.work_item,
            headers=Envelope.filter_headers(headers),
            actor=actor,
            dedup_key=dedup_key(provider, kind, payload, delivery_id),
        )
        result = store.append(env, list(routing.consumers), held_key=resolved.held_key)
        if not result.inserted:
            eventlog.emit(
                "gateway.dropped",
                level="debug",
                provider=provider,
                source=source,
                kind=kind,
                reason="duplicate",
                delivery_id=delivery_id,
                event_id=result.event_id or None,
            )
            return Outcome(
                status="duplicate", event_id=result.event_id, subject=resolved.subject
            )
        eventlog.emit(
            "gateway.received",
            provider=provider,
            source=source,
            kind=kind,
            delivery_id=delivery_id,
            subject=resolved.subject,
            event_id=result.event_id,
            summary=_summary(kind, payload),
        )
        eventlog.emit(
            "subject.appended",
            event_id=result.event_id,
            subject=resolved.subject,
            provider=provider,
            kind=kind,
            delivery_id=delivery_id,
        )
        # a binding or room published between the resolve and the append routed it
        # inside the append (issue-505, critic C2)
        late = bool(result.consumers) and not routing.consumers
        eventlog.emit(
            "subject.routed",
            event_id=result.event_id,
            subject=resolved.subject,
            to=list(result.consumers) if result.consumers else "unassigned",
            by="late" if late else routing.by,
        )
        return Outcome(
            status="stored",
            event_id=result.event_id,
            subject=resolved.subject,
            consumers=tuple(result.consumers),
            held=result.held,
        )

    def _dropped(
        self,
        provider: str,
        kind: str,
        delivery_id: str,
        reason: str,
        *,
        detail: str = "",
        status: str = "dropped",
    ) -> Outcome:
        eventlog.emit(
            "gateway.dropped",
            level="warning",
            provider=provider,
            kind=kind,
            reason=reason,
            delivery_id=delivery_id,
            detail=detail[:_SUMMARY_CAP] or None,
        )
        return Outcome(status=status, reason=reason)


def _summary(kind: str, payload: Mapping[str, Any]) -> str:
    action = payload.get("action")
    text = kind if not isinstance(action, str) else f"{kind}.{action}"
    return text[:_SUMMARY_CAP]
