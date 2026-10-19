"""The instance's hosted ingress when a gateway is configured: a polling loop
(issue-496, R3.1, R3.3–R3.7, R4.2, R4.3, R5.3, R5.5, R5.7, R14.1, R14.4).

Replaces the receiver, the poller and the Slack listener on an instance whose
``cli-config.yaml`` has a ``gateway`` block (R3.8 is :mod:`the_loop.core.lifecycle`'s).
One loop over ``urllib.request`` — what ``manager/fleet.py`` already uses:

1. **Registers first.** On start and after every outage it sends ``PUT /actors`` with
   ``gateway.actors`` and re-asserts the claims of its live sessions (``PUT /claims`` for
   each the registry holds), so a gateway restart or a lost registration is repaired by
   the client, not the operator.
2. **Polls.** ``POST /fetch`` with ``instance = instance.name or "default"``, the
   persisted ``peer``, the ``committed`` the server last returned as the cursor,
   ``max = 64``, ``wait = gateway.longPollSeconds`` and the ``commit`` list accumulated
   since the previous fetch; then sleeps ``gateway.pollIntervalSeconds`` only when the
   response was empty **and** ``wait`` was zero (a long-poll already waited).
3. **Dispatches.** Each delivery goes to ``dispatch`` — today's pipeline, by provider
   (:mod:`.client_dispatch`) — under ``eventlog.context(gateway_event_id=…)`` so the
   instance's ``dispatch.*`` records name the gateway event (R10.2). The outcome
   (``delivered`` | ``spawned`` | ``dropped:<reason>`` | ``failed``) joins the pending
   commit list.
4. **Backs off.** Any transport error → exponential back-off 1 s → 60 s with jitter,
   ``gateway.unreachable`` once per outage and ``gateway.connected`` on recovery
   (R14.4); a ``409 duplicate-instance`` is logged with the holder and retried on the
   same schedule (R4.3). The instance never falls back to its own ingresses.

``stop`` flushes the pending commits with ``POST /commit``. A crash between a dispatch
and the next fetch leaves the batch uncommitted; the next fetch returns it with
``attempt + 1`` and the dispatcher's dedup drops a true duplicate (R3.6, R3.7).
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import cli_config as cli_config_mod
from .. import eventlog
from ..state import layout_from_config
from .envelope import Delivery

__all__ = ["GatewayClient", "PEER_FILE", "Transport", "urllib_transport"]

logger = logging.getLogger("the-loop.gateway.client")

PEER_FILE = "gateway-peer.json"
MAX_BATCH = 64
BACKOFF_MIN_S, BACKOFF_MAX_S = 1.0, 60.0

#: ``(method, path, body) -> (status, json body)``; the default is urllib.
Transport = Callable[[str, str, Optional[Mapping[str, Any]], float], Tuple[int, Any]]


def urllib_transport(base_url: str) -> Transport:
    def request(
        method: str, path: str, body: Optional[Mapping[str, Any]], timeout: float
    ):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            base_url.rstrip("/") + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310 — the configured gateway URL
                raw = response.read()
                return response.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                parsed = json.loads(raw) if raw else None
            except ValueError:
                parsed = {"error": raw.decode("utf-8", "replace")[:200]}
            return exc.code, parsed

    return request


class GatewayClient:
    """One instance's consumer loop against one gateway."""

    def __init__(
        self,
        cli_config: Mapping[str, Any],
        stop_event: Optional[threading.Event] = None,
        *,
        dispatch: Optional[Callable[[Delivery], str]] = None,
        claims: Optional[Callable[[], Sequence[Tuple[str, str]]]] = None,
        transport: Optional[Transport] = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
    ) -> None:
        block = cli_config_mod.gateway_block(cli_config)
        if block is None:
            raise ValueError("the config has no usable `gateway` block")
        self.block = block
        self.config = dict(cli_config)
        self.instance = cli_config_mod.instance_name(cli_config)
        self.stop_event = stop_event or threading.Event()
        self._dispatch = dispatch or (lambda delivery: "delivered")
        self._claims = claims or (lambda: [])
        self._transport = transport or urllib_transport(block.url)
        self._sleep = sleep
        self._rng = rng
        self.local_dir = Path(layout_from_config(self.config).local_dir)
        self.peer = self._load_peer()
        self.state = "off"  # off | connecting | connected | refused | unreachable
        self.since: Optional[str] = None
        self.committed = 0
        self.last_health: Optional[Dict[str, Any]] = None
        self.last_queue: Optional[Dict[str, Any]] = None
        self.refused_by: str = ""
        self.last_error: str = ""
        self.attempt = 0  # consecutive failures
        self.registered = False
        self._pending: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self.fetches = 0

    # -- the peer id survives restarts (R4.3) ----------------------------------------------

    def _load_peer(self) -> str:
        path = self.local_dir / PEER_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            peer = str(data.get("peer") or "")
            if peer:
                return peer
        except (OSError, ValueError):
            pass
        peer = uuid.uuid4().hex
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"peer": peer, "instance": self.instance}), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("gateway: cannot persist the peer id at %s (%s)", path, exc)
        return peer

    # -- transport -----------------------------------------------------------------------------

    def _call(
        self,
        method: str,
        path: str,
        body: Optional[Mapping[str, Any]] = None,
        *,
        timeout: float = 10.0,
    ) -> Tuple[int, Any]:
        return self._transport(method, path, body, timeout)

    def _mark_connected(self) -> None:
        if self.state != "connected":
            eventlog.emit(
                "gateway.connected",
                url=self.block.url,
                instance=self.instance,
                peer=self.peer,
            )
            self.since = _utcnow()
        self.state = "connected"
        self.attempt = 0
        self.last_error = ""
        self.refused_by = ""

    def _backoff(self) -> float:
        self.attempt += 1
        base = min(BACKOFF_MAX_S, BACKOFF_MIN_S * (2 ** (self.attempt - 1)))
        return min(BACKOFF_MAX_S, base * (0.5 + self._rng()))

    def _unreachable(self, error: str) -> None:
        if self.state != "unreachable":
            eventlog.emit(
                "gateway.unreachable",
                level="warning",
                url=self.block.url,
                instance=self.instance,
                error=error[:200],
            )
        self.state = "unreachable"
        self.registered = False
        self.last_error = error

    def _refused(self, body: Any) -> None:
        body = body if isinstance(body, Mapping) else {}
        reason = str(body.get("error") or "refused")
        holder = str(body.get("holder") or "")
        eventlog.emit(
            "gateway.refused",
            level="warning",
            instance=self.instance,
            peer=self.peer,
            reason=reason,
            holder=holder or None,
            detail=str(body.get("detail") or "") or None,
        )
        self.state = "refused"
        self.refused_by = holder
        self.last_error = reason
        if reason == "duplicate-actor":
            self.registered = False

    # -- registrations (R5.3, R5.5) -----------------------------------------------------------------

    def register(self) -> bool:
        """``PUT /actors`` then re-assert every live claim; ``False`` on any refusal or error."""
        actors = {
            provider: list(names)
            for provider, names in self.block.actors.items()
            if names
        }
        status, body = self._call(
            "PUT",
            "/api/v1/gateway/actors",
            {"instance": self.instance, "peer": self.peer, "actors": actors},
        )
        if status == 409:
            self._refused(body)
            return False
        if status != 200:
            raise urllib.error.URLError(f"PUT /actors answered {status}")
        for subject, role in self._claims():
            self.publish_claim(subject, role, _raise=True)
        self.registered = True
        return True

    def publish_claim(self, subject: str, role: str, *, _raise: bool = False) -> bool:
        try:
            status, _ = self._call(
                "PUT",
                "/api/v1/gateway/claims",
                {"instance": self.instance, "subject": subject, "role": role},
            )
        except Exception as exc:  # noqa: BLE001 — a claim is re-asserted on the next reconnect
            if _raise:
                raise
            logger.warning(
                "gateway: claim %s as %s not published (%s)", subject, role, exc
            )
            return False
        return status == 200

    def release_claim(self, subject: str, role: str = "") -> bool:
        try:
            status, _ = self._call(
                "DELETE",
                "/api/v1/gateway/claims",
                {
                    "instance": self.instance,
                    "subject": subject,
                    "role": role or "driver",
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("gateway: release of %s not published (%s)", subject, exc)
            return False
        return status == 200

    def publish_binding(self, ref: str, provider: str, key: str) -> bool:
        try:
            status, _ = self._call(
                "POST",
                "/api/v1/gateway/bindings",
                {"ref": ref, "provider": provider, "key": key},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("gateway: binding %s → %s not published (%s)", key, ref, exc)
            return False
        return status == 200

    # -- the loop (R3.1, R3.3, R3.4) -------------------------------------------------------------------

    def fetch_once(self) -> Optional[List[Delivery]]:
        """One fetch, with the pending commits; ``None`` when nothing was fetched (an
        error or a refusal, already recorded)."""
        with self._lock:
            commits = list(self._pending)
        body = {
            "instance": self.instance,
            "peer": self.peer,
            "cursor": self.committed,
            "max": MAX_BATCH,
            "wait": self.block.long_poll_s,
            "lease": self.block.lease_s,
            "commit": commits,
        }
        status, answer = self._call(
            "POST",
            "/api/v1/gateway/fetch",
            body,
            timeout=float(self.block.long_poll_s) + 15.0,
        )
        if status == 409:
            self._refused(answer)
            return None
        if status != 200 or not isinstance(answer, Mapping):
            raise urllib.error.URLError(f"POST /fetch answered {status}")
        with self._lock:
            # the server applied these; anything appended meanwhile stays pending
            self._pending = self._pending[len(commits) :]
        self.committed = int(answer.get("committed") or 0)
        self.fetches += 1
        self._mark_connected()
        return [Delivery.from_json(d) for d in answer.get("deliveries") or []]

    def handle(self, delivery: Delivery) -> str:
        """Dispatch one delivery and queue its outcome for the next fetch (R3.4, R10.2)."""
        with eventlog.context(
            gateway_event_id=delivery.event.id, delivery_id=delivery.event.delivery_id
        ):
            try:
                outcome = self._dispatch(delivery) or "delivered"
            except Exception as exc:  # noqa: BLE001 — a failed dispatch is redelivered
                logger.exception("gateway: dispatching seq %s failed", delivery.seq)
                outcome = "failed"
                eventlog.emit(
                    "dispatch.error",
                    level="error",
                    error=str(exc)[:200],
                    seq=delivery.seq,
                )
        with self._lock:
            self._pending.append({"seq": delivery.seq, "outcome": outcome})
        return outcome

    def step(self) -> bool:
        """One iteration: register if needed, fetch, dispatch. Returns whether to sleep
        the poll interval (an empty plain poll)."""
        try:
            if not self.registered and not self.register():
                return False
            deliveries = self.fetch_once()
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self._unreachable(str(exc))
            return False
        if deliveries is None:
            return False
        for delivery in deliveries:
            if self.stop_event.is_set():
                break
            self.handle(delivery)
        return not deliveries and self.block.long_poll_s == 0

    def run(self) -> int:
        self.state = "connecting"
        while not self.stop_event.is_set():
            idle = self.step()
            if self.state in ("unreachable", "refused"):
                self.stop_event.wait(self._backoff())
            elif idle:
                self.stop_event.wait(self.block.poll_interval_s)
        self.flush()
        self.state = "off"
        return 0

    def flush(self) -> bool:
        """``POST /commit`` whatever is pending — a stop's last word (R3.4)."""
        with self._lock:
            commits = list(self._pending)
        if not commits:
            return True
        try:
            status, _ = self._call(
                "POST",
                "/api/v1/gateway/commit",
                {"instance": self.instance, "peer": self.peer, "commit": commits},
            )
        except Exception as exc:  # noqa: BLE001 — the next fetch after a restart recommits
            logger.warning(
                "gateway: final commit not delivered (%s); the next start recommits",
                exc,
            )
            return False
        if status == 200:
            with self._lock:
                self._pending = self._pending[len(commits) :]
            return True
        return False

    # -- the instance's view of itself (R10.3) ------------------------------------------------------------

    def document(self, *, probe: bool = True) -> Dict[str, Any]:
        """The ``GET /api/v1/gateway`` body the dashboard card renders."""
        health: Optional[Dict[str, Any]] = None
        queue: Optional[Dict[str, Any]] = None
        if probe and self.state == "connected":
            try:
                status, body = self._call("GET", "/api/v1/gateway/health", timeout=3.0)
                health = body if status == 200 and isinstance(body, dict) else None
                status, body = self._call("GET", "/api/v1/gateway/queues", timeout=3.0)
                if status == 200 and isinstance(body, dict):
                    queue = next(
                        (
                            q
                            for q in body.get("queues", [])
                            if q.get("instance") == self.instance
                        ),
                        None,
                    )
            except Exception:  # noqa: BLE001 — the card shows what it can
                pass
        return {
            "configured": True,
            "url": self.block.url,
            "state": self.state,
            "instance": self.instance,
            "peer": self.peer,
            "since": self.since,
            "committed": self.committed,
            "attempt": self.attempt,
            "refusedBy": self.refused_by or None,
            "error": self.last_error or None,
            "mode": {
                "pollIntervalSeconds": self.block.poll_interval_s,
                "longPollSeconds": self.block.long_poll_s,
            },
            "claims": [{"subject": s, "role": r} for s, r in self._claims()],
            "health": health,
            "queue": queue,
        }


def _utcnow() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
