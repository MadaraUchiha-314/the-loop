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
import re
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Set

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, field_validator

from .. import eventlog
from .config import GatewayConfig
from .envelope import subject_for_slug, ROLES, PROVIDERS
from .slack_proxy import SlackProxy
from .store import Refused, Store, peer_fingerprint

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
        #: Open long-polls, by instance name (security review SEC-5): a fetch is a sync
        #: route, so each open long-poll holds one of the server's worker threads for up
        #: to consume.maxWaitSeconds. One per name — a second under a live name is a 409
        #: anyway — and at most ``max_long_polls`` in all; beyond either, the fetch is a
        #: plain poll that answers at once, so anonymous names cannot starve the rest.
        self.max_long_polls = MAX_OPEN_LONG_POLLS
        self._long_polls: Set[str] = set()
        self._long_polls_lock = threading.Lock()
        #: Outbound Slack for the instances (issue-519): a pass-through over the live
        #: config, so a reload of `slack.post.enabled` is seen at the next call. A test
        #: replaces it with one built over a fake web client.
        self.slack_proxy = SlackProxy(self)

    def long_poll_slot(self, instance: str) -> bool:
        with self._long_polls_lock:
            if (
                instance in self._long_polls
                or len(self._long_polls) >= self.max_long_polls
            ):
                return False
            self._long_polls.add(instance)
            return True

    def release_long_poll(self, instance: str) -> None:
        with self._long_polls_lock:
            self._long_polls.discard(instance)

    def health(self) -> Dict[str, Any]:
        queues = {q.instance: q.backlog for q in self.store.queues()}
        events, held = self.store.totals()
        posting_ok, posting_reason = self.slack_proxy.available()
        return {
            "ok": self.store_ok,
            "uptimeSeconds": int(time.time() - self.started_at),
            "ingresses": dict(self.ingresses),
            # `posting` (issue-519, R4.6): whether this gateway makes Slack calls for its
            # instances — `on`, or why not (`disabled` | `no-token` |
            # `socket-unconfigured`); the instance's status wording reads it
            "slack": {
                "socket": self.slack_socket,
                "posting": "on" if posting_ok else posting_reason,
            },
            # no store path and no bind address here (security review SEC-10c): the
            # answer goes to any peer on the network; `gateway status` reads both from
            # the config on the gateway's own host
            "store": {
                "ok": self.store_ok,
                "events": events,
                "held": held,
                "queues": queues,
            },
            "restartRequired": list(self.restart_required),
        }


# -- bodies ---------------------------------------------------------------------------------------


#: Bounds on what an unauthenticated peer may write (security review SEC-4, SEC-6): a
#: name, a subject, a key, an actor, an outcome — and a 64-bit sequence, so an oversized
#: body is a 422 at the door rather than a row, an OverflowError or a log line.
NAME_MAX = 128
SUBJECT_MAX = 256
KEY_MAX = 512
ACTORS_MAX = 256
#: The most rooms one instance may publish (issue-505, abuse case 5).
ROOMS_MAX = 256
#: A Slack conversation id — the id half of ``workchannels._SLACK_TARGET_RE``. No
#: ``:``, so a room can never collide with a thread key ``<channel>:<ts>``.
SLACK_CHANNEL_RE = re.compile(r"^[CGD][A-Z0-9_-]{1,20}$")
COMMITS_MAX = 1024
SEQ_MAX = 2**63 - 1
#: A Slack Web API method name (`chat.postMessage`); the allow-list is the proxy's.
SLACK_METHOD_MAX = 64
#: The most a call's `params` may weigh serialised (issue-519, R5.4): Slack refuses a
#: message over 40 000 characters and 50 blocks, so this is above anything the instance
#: renders and far below the server's body limit. A 422 at the door writes nothing.
SLACK_PARAMS_MAX = 256 * 1024
#: A file URL (`url_private_download`); the host rule is the proxy's.
SLACK_URL_MAX = 2048
#: The most long-polls held open at once (SEC-5); the rest answer as plain polls.
MAX_OPEN_LONG_POLLS = 32


class CommitEntry(BaseModel):
    seq: int = Field(
        ...,
        ge=0,
        le=SEQ_MAX,
        description="A delivery seq of this instance's queue, fetched earlier.",
    )
    outcome: str = Field(
        ...,
        max_length=NAME_MAX,
        description="delivered | spawned | dropped:<reason> | failed — `failed` leaves the delivery pending.",
    )


class FetchBody(BaseModel):
    instance: str = Field(
        ...,
        min_length=1,
        max_length=NAME_MAX,
        description="The instance's name (`instance.name`, else `default`): its queue.",
    )
    peer: str = Field(
        "",
        max_length=NAME_MAX,
        description="A random id the client persists, so a restart is the same peer.",
    )
    cursor: int = Field(
        0,
        ge=0,
        le=SEQ_MAX,
        description="The `committed` the server last returned; a hint.",
    )
    max: int = Field(
        64,
        ge=1,
        le=SEQ_MAX,
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
        default_factory=list,
        max_length=COMMITS_MAX,
        description="The previous batch's outcomes.",
    )


class CommitBody(BaseModel):
    instance: str = Field(..., min_length=1, max_length=NAME_MAX)
    peer: str = Field("", max_length=NAME_MAX)
    commit: List[CommitEntry] = Field(..., max_length=COMMITS_MAX)


class ClaimBody(BaseModel):
    instance: str = Field(..., min_length=1, max_length=NAME_MAX)
    peer: str = Field("", max_length=NAME_MAX)
    subject: str = Field(..., min_length=1, max_length=SUBJECT_MAX)
    role: str = Field(..., max_length=NAME_MAX, description="driver | reviewer")


class ActorsBody(BaseModel):
    instance: str = Field(..., min_length=1, max_length=NAME_MAX)
    peer: str = Field("", max_length=NAME_MAX)
    actors: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Per provider (github | slack | jira): the logins or ids.",
    )

    @field_validator("actors")
    @classmethod
    def _bounded(cls, value: Dict[str, List[str]]) -> Dict[str, List[str]]:
        for provider, names in value.items():
            if provider not in PROVIDERS:
                raise ValueError(f"unknown provider {provider!r}")
            if len(names) > ACTORS_MAX:
                raise ValueError(f"{provider}: more than {ACTORS_MAX} actors")
            if any(not name or len(name) > SUBJECT_MAX for name in names):
                raise ValueError(f"{provider}: an actor name is empty or too long")
        return value


class BindingBody(BaseModel):
    instance: str = Field(
        ...,
        min_length=1,
        max_length=NAME_MAX,
        description="The publishing instance's name: allow-listed like a claim.",
    )
    peer: str = Field(
        "",
        max_length=NAME_MAX,
        description="Its persisted peer id; a different peer under a live name is 409.",
    )
    ref: str = Field(
        ...,
        min_length=1,
        max_length=KEY_MAX,
        description="The work item (`github:owner/repo#N`, `jira:site/KEY-N`).",
    )
    provider: str = Field(..., description="github | slack | jira")
    key: str = Field(
        ...,
        min_length=1,
        max_length=KEY_MAX,
        description="The object's key: `owner/repo#N` for a pull request, `<channel>:<thread_ts>` for a Slack thread.",
    )

    @field_validator("provider")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in PROVIDERS:
            raise ValueError(f"unknown provider {value!r}")
        return value


class RoomsBody(BaseModel):
    instance: str = Field(
        ...,
        min_length=1,
        max_length=NAME_MAX,
        description="The publishing instance's name: allow-listed like a claim.",
    )
    peer: str = Field(
        "",
        max_length=NAME_MAX,
        description="Its persisted peer id; a different peer under a live name is 409.",
    )
    rooms: Dict[str, str] = Field(
        default_factory=dict,
        description="Every room the instance holds, `{Slack channel id: work item ref}`. "
        "Replaces the instance's previous set; a room left out is retracted.",
    )

    @field_validator("rooms")
    @classmethod
    def _bounded(cls, value: Dict[str, str]) -> Dict[str, str]:
        from .adapters.common import slug_of

        if len(value) > ROOMS_MAX:
            raise ValueError(f"more than {ROOMS_MAX} rooms")
        for channel, ref in value.items():
            if not SLACK_CHANNEL_RE.match(channel):
                raise ValueError(f"{channel[:40]!r} is not a Slack conversation id")
            if not ref or len(ref) > KEY_MAX:
                raise ValueError(f"{channel}: the work item ref is empty or too long")
            try:
                slug_of(ref)
            except Exception as exc:  # noqa: BLE001 — a ref the schemes cannot parse
                raise ValueError(f"{channel}: {exc}") from exc
        return value


class SlackCallBody(BaseModel):
    """One Slack Web API call the gateway makes for an instance (issue-519, R2.1)."""

    instance: str = Field(
        ...,
        min_length=1,
        max_length=NAME_MAX,
        description="The calling instance's name: allow-listed like a claim.",
    )
    peer: str = Field(
        "",
        max_length=NAME_MAX,
        description="Its persisted peer id; a different peer under a live name is 409.",
    )
    method: str = Field(
        ...,
        min_length=1,
        max_length=SLACK_METHOD_MAX,
        description="The Slack Web API method (`chat.postMessage`); one of the fourteen "
        "the instance calls, else 422 method-not-allowed and nothing is sent.",
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="The method's parameters, passed to Slack as a JSON body; at most "
        "256 KiB serialised.",
    )

    @field_validator("params")
    @classmethod
    def _bounded(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        import json

        if len(json.dumps(value, separators=(",", ":"))) > SLACK_PARAMS_MAX:
            raise ValueError(f"params over {SLACK_PARAMS_MAX} bytes")
        return value


class SlackDownloadBody(BaseModel):
    """A message's file, fetched with the gateway's bot token (issue-519, R3.1)."""

    instance: str = Field(..., min_length=1, max_length=NAME_MAX)
    peer: str = Field("", max_length=NAME_MAX)
    url: str = Field(
        ...,
        min_length=1,
        max_length=SLACK_URL_MAX,
        description="The file's `url_private_download`: https, on one of Slack's hosts, "
        "every redirect re-checked, at most 25 MiB — else 422 off-host / 413 over-cap.",
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
        if not result.deliveries and wait > 0 and state.long_poll_slot(body.instance):
            try:
                deadline = time.monotonic() + wait
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    store.wait(body.instance, remaining)
                    # the name may have changed hands while this fetch slept (critic
                    # C1): a peer whose lease lapsed mid-wait reads nothing of the new
                    # holder's
                    conflict = store.peer_conflict(body.instance, body.peer)
                    if conflict is not None:
                        return _refused(
                            state, conflict, instance=body.instance, peer=body.peer
                        )
                    result = store.fetch(body.instance, body.cursor, limit)
                    if result.deliveries or state.stopping.is_set():
                        break
            finally:
                state.release_long_poll(body.instance)
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
        now resolves are routed. The publisher is checked like a claimant (security
        review SEC-2): allow-listed by name, refused as a stale peer under a live name,
        and recorded as `gateway.bound`, so a binding that redirects a subject is
        visible and never anonymous."""
        from .adapters.common import slug_of

        denied = _check_allowed(state, body.instance)
        if denied is not None:
            return denied
        conflict = store.peer_conflict(body.instance, body.peer)
        if conflict is not None:
            return _refused(state, conflict, instance=body.instance, peer=body.peer)
        try:
            slug = slug_of(body.ref)
        except Exception as exc:  # noqa: BLE001 — a ref the schemes cannot parse
            raise HTTPException(status_code=400, detail=f"ref: {exc}") from exc
        own_subject = ""
        if body.provider == "github":
            # a pull request has a subject of its own; what was held there before the
            # binding is routed now (critic C3, R5.7). A sha key has none.
            try:
                own_subject = subject_for_slug(slug_of(f"github:{body.key}"))
            except Exception:  # noqa: BLE001
                own_subject = ""
        routed = store.bind(
            body.provider, body.key, body.ref, slug, own_subject=own_subject
        )
        eventlog.emit(
            "gateway.bound",
            instance=body.instance,
            provider=body.provider,
            key=body.key,
            ref=body.ref,
            routed=len(routed),
        )
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

    @router.put(f"{API_PREFIX}/rooms", operation_id="gatewayPublishRooms")
    def rooms(body: RoomsBody) -> Any:
        """Replace the instance's rooms — the Slack collaboration channels its work
        items declared (issue-505). A Slack event in a room with no thread binding
        resolves to the room's work item; the events held under the channel are routed
        when the room is published. A room another live instance holds is kept and
        reported in `refused`. Checked like a claim: allow-listed, and a stale peer
        under a live name is 409."""
        from .adapters.common import slug_of

        denied = _check_allowed(state, body.instance)
        if denied is not None:
            return denied
        wanted = {channel: (ref, slug_of(ref)) for channel, ref in body.rooms.items()}
        result = store.publish_rooms(body.instance, wanted, peer=body.peer)
        if isinstance(result, Refused):
            return _refused(state, result, instance=body.instance, peer=body.peer)
        for channel, holder in result.refused:
            eventlog.emit(
                "gateway.refused",
                level="warning",
                instance=body.instance,
                reason="duplicate-room",
                holder=holder,
                channel=channel,
            )
        eventlog.emit(
            "gateway.rooms",
            instance=body.instance,
            rooms=len(result.rooms),
            routed=len(result.routed),
            refused=[channel for channel, _ in result.refused] or None,
        )
        for event_id, subject in result.routed:
            eventlog.emit(
                "subject.routed", event_id=event_id, subject=subject, by="room"
            )
        return {
            "instance": body.instance,
            "rooms": {channel: body.rooms[channel] for channel in result.rooms},
            "refused": [
                {"channel": channel, "holder": holder}
                for channel, holder in result.refused
            ],
            "routed": len(result.routed),
        }

    def _guarded(instance: str, peer: str) -> Optional[JSONResponse]:
        denied = _check_allowed(state, instance)
        if denied is not None:
            return denied
        conflict = store.peer_conflict(instance, peer)
        if conflict is not None:
            return _refused(state, conflict, instance=instance, peer=peer)
        return None

    @router.post(f"{API_PREFIX}/slack/call", operation_id="gatewaySlackCall")
    def slack_call(body: SlackCallBody) -> Any:
        """One Slack Web API call for the instance, made with the bot token this gateway
        holds for Socket Mode (issue-519). A pass-through: Slack's status, body and
        Retry-After come back verbatim, `ok: false` included. Refused with 422
        method-not-allowed for a method outside the fourteen the instance calls (nothing
        sent), 503 posting-unavailable {reason: disabled | no-token | socket-unconfigured},
        502 slack-unreachable on a transport failure, and the consumer guards every route
        has: 409 unknown-instance / duplicate-instance. Nothing is stored or retried."""
        denied = _guarded(body.instance, body.peer)
        if denied is not None:
            return denied
        result = state.slack_proxy.call(body.instance, body.method, body.params)
        return JSONResponse(
            status_code=result.status, content=result.body, headers=result.headers
        )

    @router.post(f"{API_PREFIX}/slack/download", operation_id="gatewaySlackDownload")
    def slack_download(body: SlackDownloadBody) -> Any:
        """A message's file for the instance, fetched with the gateway's bot token under
        the instance's own rules (issue-519): Slack's hosts only, every redirect
        re-checked, 25 MiB at most. 200 with the bytes and their Content-Type; 422
        off-host, 413 over-cap, 502 transfer-failed, 503 posting-unavailable, and the
        consumer guards (409)."""
        denied = _guarded(body.instance, body.peer)
        if denied is not None:
            return denied
        result = state.slack_proxy.download(body.instance, body.url)
        if isinstance(result.body, (bytes, bytearray)):
            return Response(
                content=bytes(result.body),
                status_code=result.status,
                media_type=result.media_type,
            )
        return JSONResponse(status_code=result.status, content=result.body)

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
                    "peerFingerprint": peer_fingerprint(i.peer),
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
                    "rooms": [
                        {"channel": channel, "workItem": ref}
                        for channel, ref in store.rooms_of(i.instance)
                    ],
                }
                for i in store.instances()
            ]
        }

    return router


def mount(app: Any, state: GatewayState) -> None:
    app.include_router(build_consume_router(state))
    app.state.gateway = state
