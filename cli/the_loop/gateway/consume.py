"""The consumer API: fetch and commit, claims, actors, bindings, and the read-only views
(issue-496, R3, R4.2, R4.3, R5.3, R5.5, R5.7, R6.3, R9.2).

Pull, not push (design §Trade-offs). One call — ``POST /api/v1/gateway/fetch`` — does the
consumer loop's whole step, as a Kafka consumer's fetch-and-commit does: it refreshes the
instance's lease, commits the previous batch's outcomes, reads the next deliveries of
**that instance's queue**, and, when the queue is empty and ``wait`` is set, holds the
request open until something is appended to it or ``wait`` elapses. The other routes are
registrations and views. No streaming route is offered (R6.3).

Nothing here authenticates an instance (the author's decision; the network is the
boundary, §Security design). What it does refuse, with ``409`` and a ``gateway.refused``
record: a second peer under a live instance name (``duplicate-instance``), a commit for a
delivery this queue never fetched (``commit-undelivered``), an actor another live instance
registered (``duplicate-actor``), and — when ``instances`` is set in the gateway config —
a name outside the allow-list (``unknown-instance``).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import eventlog
from .config import GatewayConfig
from .envelope import ROLES
from .store import Refused, Store

__all__ = ["GatewayState", "build_consume_router", "API_PREFIX"]

logger = logging.getLogger("the-loop.gateway.consume")

API_PREFIX = "/api/v1/gateway"


class GatewayState:
    """What the routes share: the store, the config, and what the process reports as its
    health (the ingress states are filled in by :mod:`.ingresses`)."""

    def __init__(self, config: GatewayConfig, store: Store) -> None:
        self.config = config
        self.store = store
        self.started_at = time.time()
        #: Set by the shutdown path: no long-poll blocks from here on (R8.5).
        self.stopping = threading.Event()
        self.ingresses: Dict[str, str] = {}  # name -> running | off | failed:<reason>
        self.slack_socket: str = "off"  # up | down | off
        self.store_ok: bool = True
        self.restart_required: List[str] = []

    def health(self) -> Dict[str, Any]:
        queues = {q.instance: q.backlog for q in self.store.queues()}
        held = sum(row.held for row in self.store.subjects())
        return {
            "ok": self.store_ok,
            "uptimeSeconds": int(time.time() - self.started_at),
            "ingresses": dict(self.ingresses),
            "slack": {"socket": self.slack_socket},
            "store": {
                "ok": self.store_ok,
                "path": str(self.config.store.path),
                "events": sum(row.events for row in self.store.subjects()),
                "held": held,
                "queues": queues,
            },
            "restartRequired": list(self.restart_required),
            "listen": {
                "host": self.config.listen.host,
                "port": self.config.listen.port,
            },
        }


# -- bodies ---------------------------------------------------------------------------------------


class CommitEntry(BaseModel):
    seq: int = Field(
        ..., description="A delivery seq of this instance's queue, fetched earlier."
    )
    outcome: str = Field(
        ...,
        description="delivered | spawned | dropped:<reason> | failed — `failed` leaves the delivery pending.",
    )


class FetchBody(BaseModel):
    instance: str = Field(
        ...,
        description="The instance's name (`instance.name`, else `default`): its queue.",
    )
    peer: str = Field(
        "",
        description="A random id the client persists, so a restart is the same peer.",
    )
    cursor: int = Field(
        0, ge=0, description="The `committed` the server last returned; a hint."
    )
    max: int = Field(
        64,
        ge=1,
        description="At most this many deliveries; clamped to consume.maxBatch.",
    )
    wait: float = Field(
        0,
        ge=0,
        description="Hold an empty fetch open for up to this many seconds; clamped.",
    )
    lease: float = Field(
        0, ge=0, description="Seconds to hold the instance name for this peer; clamped."
    )
    commit: List[CommitEntry] = Field(
        default_factory=list, description="The previous batch's outcomes."
    )


class CommitBody(BaseModel):
    instance: str
    peer: str = ""
    commit: List[CommitEntry]


class ClaimBody(BaseModel):
    instance: str
    peer: str = ""
    subject: str
    role: str = Field(..., description="driver | reviewer")


class ActorsBody(BaseModel):
    instance: str
    peer: str = ""
    actors: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Per provider (github | slack | jira): the logins or ids.",
    )


class BindingBody(BaseModel):
    ref: str = Field(
        ..., description="The work item (`github:owner/repo#N`, `jira:site/KEY-N`)."
    )
    provider: str = Field(..., description="github | slack | jira")
    key: str = Field(
        ...,
        description="The object's key: `owner/repo#N` for a pull request, `<channel>:<thread_ts>` for a Slack thread.",
    )


# -- the router -----------------------------------------------------------------------------------


def _refused(
    state: GatewayState, refused: Refused, *, instance: str, peer: str = ""
) -> JSONResponse:
    eventlog.emit(
        "gateway.refused",
        level="warning",
        instance=instance,
        peer=peer or None,
        reason=refused.reason,
        holder=refused.holder or None,
        detail=refused.detail or None,
    )
    body: Dict[str, Any] = {"error": refused.reason, "instance": instance}
    if refused.holder:
        body["holder"] = refused.holder
    if refused.since:
        body["since"] = refused.since
    if refused.detail:
        body["detail"] = refused.detail
    return JSONResponse(status_code=409, content=body)


def _check_allowed(state: GatewayState, instance: str) -> Optional[JSONResponse]:
    allowed = state.config.instances
    if allowed is not None and instance not in allowed:
        return _refused(
            state,
            Refused(
                "unknown-instance",
                detail=f"{instance!r} is not in the gateway's instances list",
            ),
            instance=instance,
        )
    return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_consume_router(state: GatewayState, **router_kwargs: Any) -> APIRouter:
    """Every ``/api/v1/gateway`` operation, as a router the gateway app includes."""
    router = APIRouter(**router_kwargs)
    store = state.store
    consume = state.config.consume

    def _commit(instance: str, entries: Sequence[CommitEntry], peer: str = "") -> Any:
        outcomes: List[Tuple[int, str]] = [(e.seq, e.outcome) for e in entries]
        if not outcomes:
            return None
        conflict = store.peer_conflict(instance, peer)
        if conflict is not None:
            return conflict
        result = store.commit(instance, outcomes)
        if isinstance(result, Refused):
            return result
        for seq, outcome in result.applied:
            eventlog.emit(
                "subject.committed", instance=instance, seq=seq, outcome=outcome
            )
            if outcome != "delivered":
                # the poll ledger learns what became of a presence it offered (R3.4)
                from .adapters.poll import apply_commit_outcome

                apply_commit_outcome(store, store.event_of_seq(seq), outcome)
        return result

    @router.post(f"{API_PREFIX}/fetch", operation_id="gatewayFetch")
    def fetch(body: FetchBody) -> Any:
        """Refresh the lease, commit the previous batch, read the next deliveries of this
        instance's queue, long-polling when it is empty (R3.2–R3.4, R4.3)."""
        denied = _check_allowed(state, body.instance)
        if denied is not None:
            return denied
        lease_s = _clamp(
            body.lease or consume.lease_s[0], consume.lease_s[0], consume.lease_s[1]
        )
        lease = store.touch(body.instance, body.peer, lease_s)
        if isinstance(lease, Refused):
            return _refused(state, lease, instance=body.instance, peer=body.peer)
        committed = _commit(body.instance, body.commit, body.peer)
        if isinstance(committed, Refused):
            return _refused(state, committed, instance=body.instance, peer=body.peer)
        limit = int(_clamp(body.max, 1, consume.max_batch))
        wait = _clamp(body.wait, 0, consume.max_wait_s)
        result = store.fetch(body.instance, body.cursor, limit)
        if not result.deliveries and wait > 0:
            deadline = time.monotonic() + wait
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                store.wait(body.instance, remaining)
                result = store.fetch(body.instance, body.cursor, limit)
                if result.deliveries or state.stopping.is_set():
                    break
        for dead in result.dead_lettered:
            eventlog.emit(
                "subject.dead-lettered",
                level="warning",
                instance=dead.instance,
                seq=dead.seq,
                event_id=dead.event_id,
                attempts=dead.attempts,
            )
        for seq, event_id, attempt in result.redelivered:
            eventlog.emit(
                "subject.redelivered",
                instance=body.instance,
                seq=seq,
                event_id=event_id,
                attempt=attempt,
            )
        deliveries = [d.to_json() for d in result.deliveries]
        return {
            "instance": body.instance,
            "deliveries": deliveries,
            "cursor": deliveries[-1]["seq"] if deliveries else result.committed,
            "committed": result.committed,
            "lease": {"expiresIn": round(lease.expires_in, 1)},
        }

    @router.post(f"{API_PREFIX}/commit", operation_id="gatewayCommit")
    def commit(body: CommitBody) -> Any:
        """The commit step alone — for `the-loop stop`, and for a client with nothing to
        fetch for a while (R3.4)."""
        denied = _check_allowed(state, body.instance)
        if denied is not None:
            return denied
        result = _commit(body.instance, body.commit, body.peer)
        if isinstance(result, Refused):
            return _refused(state, result, instance=body.instance, peer=body.peer)
        committed = (
            result.committed if result is not None else store.committed(body.instance)
        )
        return {"instance": body.instance, "committed": committed}

    @router.put(f"{API_PREFIX}/claims", operation_id="gatewayClaim")
    def claim(body: ClaimBody) -> Any:
        """Publish a claim; the events held on that subject are routed onto the claimant's
        queue in the same transaction (R5.3, R2.2)."""
        denied = _check_allowed(state, body.instance)
        if denied is not None:
            return denied
        if body.role not in ROLES:
            raise HTTPException(
                status_code=400, detail=f"role must be one of {list(ROLES)}"
            )
        conflict = store.peer_conflict(body.instance, body.peer)
        if conflict is not None:
            return _refused(state, conflict, instance=body.instance, peer=body.peer)
        routed = store.claim(body.subject, body.instance, body.role)
        eventlog.emit(
            "gateway.claimed",
            subject=body.subject,
            instance=body.instance,
            role=body.role,
            routed=len(routed),
        )
        for event_id in routed:
            eventlog.emit(
                "subject.routed",
                event_id=event_id,
                subject=body.subject,
                to=[body.instance],
                by="claim",
            )
        return {
            "subject": body.subject,
            "instance": body.instance,
            "role": body.role,
            "routed": len(routed),
        }

    @router.delete(f"{API_PREFIX}/claims", operation_id="gatewayRelease")
    def release(body: ClaimBody) -> Any:
        denied = _check_allowed(state, body.instance)
        if denied is not None:
            return denied
        conflict = store.peer_conflict(body.instance, body.peer)
        if conflict is not None:
            return _refused(state, conflict, instance=body.instance, peer=body.peer)
        removed = store.release(body.subject, body.instance, body.role or None)
        eventlog.emit(
            "gateway.released",
            subject=body.subject,
            instance=body.instance,
            role=body.role,
        )
        return {"subject": body.subject, "instance": body.instance, "released": removed}

    @router.put(f"{API_PREFIX}/actors", operation_id="gatewayRegisterActors")
    def register(body: ActorsBody) -> Any:
        """Replace the instance's actor registration; an actor held by another live
        instance is refused (R5.5)."""
        denied = _check_allowed(state, body.instance)
        if denied is not None:
            return denied
        refused = store.register_actors(body.instance, body.actors, peer=body.peer)
        if refused is not None:
            return _refused(state, refused, instance=body.instance, peer=body.peer)
        routed = store.route_held_by_actors(body.instance)
        for event_id, subject in routed:
            eventlog.emit(
                "subject.routed",
                event_id=event_id,
                subject=subject,
                to=[body.instance],
                by="actor",
            )
        eventlog.emit(
            "gateway.registered",
            instance=body.instance,
            actors={k: len(v) for k, v in body.actors.items()},
            routed=len(routed),
        )
        return {
            "instance": body.instance,
            "actors": {k: sorted(v) for k, v in body.actors.items()},
            "routed": len(routed),
        }

    @router.post(f"{API_PREFIX}/bindings", operation_id="gatewayBind")
    def bind(body: BindingBody) -> Any:
        """Publish that an object belongs to a work item (R5.7); held events whose key
        now resolves are routed."""
        from .adapters.common import slug_of

        try:
            slug = slug_of(body.ref)
        except Exception as exc:  # noqa: BLE001 — a ref the schemes cannot parse
            raise HTTPException(status_code=400, detail=f"ref: {exc}") from exc
        routed = store.bind(body.provider, body.key, body.ref, slug)
        for event_id in routed:
            eventlog.emit(
                "subject.routed",
                event_id=event_id,
                subject=f"loop-{slug}",
                by="binding",
            )
        return {
            "ref": body.ref,
            "provider": body.provider,
            "key": body.key,
            "routed": len(routed),
        }

    @router.get(f"{API_PREFIX}/health", operation_id="gatewayHealth")
    def health() -> Dict[str, Any]:
        return state.health()

    @router.get(f"{API_PREFIX}/subjects", operation_id="gatewaySubjects")
    def subjects() -> Dict[str, Any]:
        rows = []
        for row in store.subjects():
            rows.append(
                {
                    "subject": row.subject,
                    "firstSeen": row.first_seen,
                    "claimants": [
                        {"instance": c.instance, "role": c.role, "since": c.since}
                        for c in row.claimants
                    ],
                    "events": row.events,
                    "held": row.held,
                    "pending": row.pending,
                    "oldestPendingAt": row.oldest_pending_at,
                    "dead": row.dead,
                }
            )
        return {"subjects": rows}

    @router.get(f"{API_PREFIX}/queues", operation_id="gatewayQueues")
    def queues() -> Dict[str, Any]:
        return {
            "queues": [
                {
                    "instance": q.instance,
                    "committed": q.committed,
                    "backlog": q.backlog,
                    "oldestPendingAt": q.oldest_pending_at,
                    "dead": q.dead,
                }
                for q in store.queues()
            ]
        }

    @router.get(f"{API_PREFIX}/instances", operation_id="gatewayInstances")
    def instances() -> Dict[str, Any]:
        now = time.time()
        return {
            "instances": [
                {
                    "instance": i.instance,
                    "peer": i.peer,
                    "committed": i.committed,
                    "firstSeen": i.first_seen,
                    "lastFetchAt": i.last_fetch_at,
                    "leaseLive": i.lease_live(now),
                    "leaseExpiresIn": round(max(0.0, i.lease_until - now), 1),
                    "actors": {k: list(v) for k, v in i.actors.items()},
                    "backlog": i.backlog,
                    "claims": [
                        {"subject": c.subject, "role": c.role}
                        for c in store.claims_of(i.instance)
                    ],
                }
                for i in store.instances()
            ]
        }

    return router


def mount(app: Any, state: GatewayState) -> None:
    app.include_router(build_consume_router(state))
    app.state.gateway = state
