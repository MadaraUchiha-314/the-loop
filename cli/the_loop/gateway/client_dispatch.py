"""Today's pipeline, fed from the queue (issue-496, R3.4–R3.7, R5.6, R10.2).

The gateway delivers raw provider events; **this** is where the instance judges them,
exactly as it would have had they arrived at its own receiver, poller or listener:

- ``github`` → ``Router.route`` (the linkage, the dedup, the authorized-actor guard and
  the control grammar) then ``Dispatcher.handle``; the outcome is read back with
  ``delivery_status`` — ``done`` → ``delivered`` (``spawned`` when the dispatch created
  the work item's record), ``settled`` → ``dropped:<why>``, ``unhandled`` → ``failed``
  (the delivery comes back with ``attempt + 1``), ``inflight`` → *deferred*: the client
  asks again before its next fetch, so a commit never claims more than the dispatcher
  has done (R3.4);
- ``jira`` → ``JiraDoorbell.ring`` as the receiver does today;
- ``slack`` → ``slack.dispatch_envelope`` — the classification half of the listener.

Before the hand-off the delivery id is correlated with the gateway event id
(:func:`the_loop.eventlog.correlate`), so every ``dispatch.*`` record the dispatcher's
worker threads emit for it carries ``gateway_event_id`` (R10.2).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Union

from .. import eventlog
from .envelope import Delivery

__all__ = ["Deferred", "Pipeline", "build_pipeline"]

logger = logging.getLogger("the-loop.gateway.pipeline")

#: How long a dispatch may stay in flight before the client commits it as delivered
#: anyway: the dispatcher owns it by then, and holding the queue open longer would
#: block every later delivery on one slow resume.
INFLIGHT_GRACE_S = 120.0


@dataclass
class Deferred:
    """An outcome the dispatcher has not settled yet; ``resolve`` is asked again before
    each fetch and answers ``None`` while the dispatch is still in flight."""

    delivery_id: str
    resolve: Callable[[], Optional[str]]
    since: float


Outcome = Union[str, Deferred]


class Pipeline:
    def __init__(
        self,
        *,
        router: Any,
        dispatcher: Any,
        cli_config: Mapping[str, Any],
        doorbell: Optional[Any] = None,
        slack_dispatch: Optional[
            Callable[[str, Mapping[str, Any], Mapping[str, Any]], str]
        ] = None,
    ) -> None:
        self.router = router
        self.dispatcher = dispatcher
        self.cli_config = dict(cli_config)
        self.doorbell = doorbell
        self._slack_dispatch = slack_dispatch

    def reload(self, cli_config: Mapping[str, Any]) -> None:
        self.cli_config = dict(cli_config)

    # -- the entry point the client calls ------------------------------------------------------

    def dispatch(self, delivery: Delivery) -> Outcome:
        env = delivery.event
        eventlog.correlate(env.delivery_id, gateway_event_id=env.id)
        if env.provider == "github":
            return self._github(delivery)
        if env.provider == "jira":
            return self._jira(delivery)
        if env.provider == "slack":
            return self._slack(delivery)
        return "dropped:unknown-provider"

    # -- GitHub --------------------------------------------------------------------------------------

    def _github(self, delivery: Delivery) -> Outcome:
        env = delivery.event
        payload = dict(env.payload) if isinstance(env.payload, Mapping) else {}
        routed = self.router.route(env.kind, payload, env.delivery_id)
        if routed is None:
            # the router recorded why (routing.dropped: duplicate-delivery |
            # unauthorized-actor | no-work-item | …); the queue only needs to move on
            return "dropped:not-routed"
        refs = list(routed.work_items)
        had_record = {
            ref.ref for ref in refs if self.dispatcher.registry.record_owning(ref)
        }
        self.dispatcher.handle(routed)
        started = time.monotonic()

        def resolve() -> Optional[str]:
            status = self.dispatcher.delivery_status(env.delivery_id, refs)
            if status == "done":
                spawned = any(
                    ref.ref not in had_record
                    and self.dispatcher.registry.record_owning(ref)
                    for ref in refs
                )
                return "spawned" if spawned else "delivered"
            if status == "settled":
                why = self.dispatcher.delivery_outcome(env.delivery_id) or "settled"
                return f"dropped:{why}"
            if status == "unhandled":
                return "failed"
            if time.monotonic() - started > INFLIGHT_GRACE_S:
                return "delivered"
            return None

        first = resolve()
        if first is not None:
            return first
        return Deferred(env.delivery_id, resolve, started)

    # -- Jira ------------------------------------------------------------------------------------------

    def _jira(self, delivery: Delivery) -> Outcome:
        if self.doorbell is None:
            return "dropped:no-jira"
        from ..webhook.jira import read_doorbell

        payload = (
            delivery.event.payload
            if isinstance(delivery.event.payload, Mapping)
            else {}
        )
        result = str(self.doorbell.ring(read_doorbell(payload)) or "")
        if result.startswith("ignored"):
            return "dropped:" + result.split(":", 1)[-1]
        if result == "error":
            return "failed"
        return "delivered"

    # -- Slack ------------------------------------------------------------------------------------------

    def _slack(self, delivery: Delivery) -> Outcome:
        payload = (
            delivery.event.payload
            if isinstance(delivery.event.payload, Mapping)
            else {}
        )
        dispatch = self._slack_dispatch
        if dispatch is None:
            from ..channels.slack import dispatch_envelope

            dispatch = dispatch_envelope
        result = str(dispatch(delivery.event.kind, payload, self.cli_config) or "")
        if result.startswith("ignored"):
            return "dropped:" + result.split(":", 1)[-1]
        return "delivered"


def build_pipeline(cli_config: Mapping[str, Any], config_path: Any = None) -> Pipeline:
    """Today's router and dispatcher, composed as ``webhook/daemon._build_ingress`` does
    — minus the HTTP server — for an instance that consumes from a gateway (C4 wires it
    into the hosted-ingress set). ``config_path`` is accepted for symmetry; the builder
    resolves the CLI config the way every daemon does."""
    from ..webhook import daemon as webhook_daemon

    routing = dict(cli_config.get("routing") or {})
    gh_webhook = dict(((cli_config.get("webhooks") or {}).get("ghWebhook")) or {})
    on_event, dispatcher, _config, _on_jira = webhook_daemon._build_ingress(  # noqa: SLF001 — the one composition
        routing, gh_webhook
    )
    doorbells: Dict[str, Any] = getattr(on_event, "doorbells", {}) or {}
    pipeline = Pipeline(
        router=getattr(on_event, "router"),
        dispatcher=dispatcher,
        cli_config=cli_config,
        doorbell=_DoorbellProxy(doorbells) if doorbells else None,
    )
    pipeline.reload_if_changed = getattr(on_event, "reload_if_changed", lambda: None)  # type: ignore[attr-defined]
    return pipeline


class _DoorbellProxy:
    """Rings whichever doorbell the hot reload currently holds (the daemon's own
    ``doorbells`` dict is rebuilt on a config change)."""

    def __init__(self, doorbells: Dict[str, Any]) -> None:
        self._doorbells = doorbells

    def ring(self, bell: Any) -> str:
        doorbell = self._doorbells.get("bell")
        if doorbell is None:
            return "ignored:unconfigured"
        return str(doorbell.ring(bell))
