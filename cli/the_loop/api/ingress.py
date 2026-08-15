"""Host the ingress daemons inside the control-plane service (issue-231).

With ``service.hostIngresses`` (default **true**), the one process ``the-loop
start`` boots when the service is enabled also runs the enabled ingresses —
the poller and the webhook receiver — as background threads under the app's
lifespan: one pid, one logfile, one thing for a supervisor. The run loops are
the same ones the standalone daemons execute (:mod:`the_loop.poller.daemon`,
:mod:`the_loop.webhook.daemon`); only where they run changes.

**The locks stay per ingress.** Each hosted ingress still acquires its own
pidfile ``RunLock`` — now held by the service's pid — so everything built on
the issue-159 discipline keeps answering truthfully: "at most one poller per
state root" holds against standalone daemons too, ``the-loop status`` and
``core.daemons`` read liveness from the same locks, and an ingress whose lock
is already held (a standalone daemon is running) is **skipped with a warning**
rather than fought over. ``the-loop stop`` recognises the hosted case by the
lock holder's pid equalling the service's and stops the one process.

Failure posture: a hosted ingress that cannot start — lock contention, an
enabled poller with no sources, an unbindable receiver port — degrades to a
logged warning and an eventlog record; the service itself keeps serving. The
API being up is what lets an operator see and fix the reason.
"""

from __future__ import annotations

import logging
import threading
from typing import List, Optional

from .. import eventlog
from ..runlock import RunLock

logger = logging.getLogger("the-loop.service")

#: How long shutdown waits for a hosted ingress thread to finish.
_JOIN_TIMEOUT_SECONDS = 30.0


class _HostedIngress:
    """One hosted run loop: its lock, its thread, and how to stop it."""

    def __init__(self, name: str, lock: RunLock, thread: threading.Thread, stop):
        self.name = name
        self.lock = lock
        self.thread = thread
        self._stop = stop

    def stop(self) -> None:
        try:
            self._stop()
        except Exception:  # noqa: BLE001 — shutdown must reach every ingress
            logger.exception("stopping hosted %s failed", self.name)
        self.thread.join(_JOIN_TIMEOUT_SECONDS)
        if self.thread.is_alive():
            logger.warning(
                "hosted %s did not finish within %.0fs; releasing its lock anyway",
                self.name,
                _JOIN_TIMEOUT_SECONDS,
            )
        self.lock.release()
        eventlog.emit("ingress.hosted_stopped", ingress=self.name)


def _acquire(name: str, pidfile: str) -> Optional[RunLock]:
    """The ingress's single-instance lock, or ``None`` with the reason logged."""
    lock = RunLock(pidfile, name=name)
    try:
        if lock.acquire():
            return lock
    except OSError as exc:
        logger.error("cannot use the %s lockfile %s: %s", name, pidfile, exc)
        return None
    logger.warning(
        "not hosting the %s: another one is already running (pid %s, pidfile "
        "%s) — likely a standalone daemon; stop it with `the-loop stop` to let "
        "the service host it",
        name,
        lock.holder() or "unknown",
        pidfile,
    )
    return None


def _start_poller(cli_config: dict) -> Optional[_HostedIngress]:
    from ..poller import daemon as poller_daemon

    polling = (cli_config.get("polling")) or {}
    if not polling.get("sources"):
        logger.error(
            "not hosting the poller: polling.enabled is true but polling.sources "
            "is empty — nothing to poll"
        )
        return None
    options = poller_daemon.default_options()
    lock = _acquire("poller", options.pidfile)
    if lock is None:
        return None
    stop_event = threading.Event()
    thread = threading.Thread(
        target=poller_daemon._run_locked,
        args=(options,),
        kwargs={"stop_event": stop_event, "install_signal_handlers": False},
        name="the-loop-poller",
        daemon=True,
    )
    thread.start()
    return _HostedIngress("poller", lock, thread, stop_event.set)


def _start_receiver(cli_config: dict) -> Optional[_HostedIngress]:
    from ..webhook import daemon as webhook_daemon

    options = webhook_daemon.default_options()
    lock = _acquire("gh-webhook", options.pidfile)
    if lock is None:
        return None
    built = webhook_daemon.build_receiver(options)
    if built is None:  # reasons already logged (dependency, bind, …)
        lock.release()
        return None
    httpd, cleanup = built

    def serve() -> None:
        try:
            httpd.serve_forever()
        finally:
            cleanup()

    thread = threading.Thread(target=serve, name="the-loop-gh-webhook", daemon=True)
    thread.start()
    return _HostedIngress("gh-webhook", lock, thread, httpd.shutdown)


def start_hosted_ingresses(cli_config: Optional[dict]) -> List[_HostedIngress]:
    """Start every ingress this process should host; never raises.

    Which ones is the same policy ``the-loop start`` composes on
    (`webhooks.ghWebhook.enabled`, `polling.enabled`); whether *this process*
    hosts them at all is ``service.hostIngresses``, resolved by the caller.
    """
    config = cli_config or {}
    hosted: List[_HostedIngress] = []
    starters = []
    if ((config.get("webhooks") or {}).get("ghWebhook") or {}).get("enabled", False):
        starters.append(("gh-webhook", _start_receiver))
    if (config.get("polling") or {}).get("enabled", False):
        starters.append(("poller", _start_poller))
    for name, start in starters:
        try:
            ingress = start(config)
        except Exception:  # noqa: BLE001 — one ingress must not take the API down
            logger.exception("hosting the %s failed during startup", name)
            ingress = None
        if ingress is not None:
            hosted.append(ingress)
            logger.info("hosting the %s in this service process", name)
            eventlog.emit("ingress.hosted", ingress=name)
    # The pidfiles double as the honest-start proof `the-loop start` waits on,
    # so nothing extra is written: a hosted ingress is up iff its lock is held.
    return hosted


def stop_hosted_ingresses(hosted: List[_HostedIngress]) -> None:
    """Stop in reverse start order; each stop is isolated."""
    for ingress in reversed(hosted):
        ingress.stop()
