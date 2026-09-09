"""Host the ingress daemons inside the control-plane service (issue-231).

With ``service.hostIngresses`` (default **true**), the one process ``the-loop
start`` boots when the service is enabled also runs the enabled ingresses —
the poller and the webhook receiver — as background threads under the app's
lifespan: one pid, one logfile, one thing for a supervisor. The run loops are
the same ones the standalone daemons execute (:mod:`the_loop.poller.daemon`,
:mod:`the_loop.webhook.daemon`); only where they run changes.

Since issue-334 the same lifespan hosts a third run loop when the Slack channel
reads over Socket Mode: the listener (``the-loop channels listen``'s loop), so
``the-loop start`` brings up the long-lived connection the config asks for and
nothing has to be run in a foreground shell beside it.

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


def _start_slack_listener(cli_config: dict) -> Optional[_HostedIngress]:
    """The Slack Socket Mode listener as a hosted thread (issue-334).

    Only when the channel is enabled with ``read.mode: socket`` — the same rule
    ``channels listen`` applies — and only with both tokens present, refused
    loudly otherwise so ``the-loop start`` reports it rather than hosting a
    loop that would exit at once. A listener that stops on its own (a token
    Slack rejects, an exception past the SDK's reconnect) releases its lock,
    so ``status`` never reports a dead listener as running.
    """
    import os

    from ..channels import slack as slack_channel
    from ..core import daemons as core_daemons

    config = slack_channel.SlackChannelConfig.from_mapping(cli_config)
    if not config.enabled or config.read_mode != "socket":
        return None
    missing = [
        env
        for env in (config.app_token_env, config.bot_token_env)
        if not os.environ.get(env)
    ]
    if missing:
        logger.error(
            "not hosting the slack listener: %s not set — Socket Mode needs the "
            "app-level token (xapp-, connections:write) and the bot token (xoxb-)",
            " and ".join(missing),
        )
        return None
    lock = _acquire(
        core_daemons.SLACK_LISTENER,
        core_daemons._pidfile(core_daemons.SLACK_LISTENER, cli_config),
    )
    if lock is None:
        return None
    stop_event = threading.Event()

    def serve() -> None:
        try:
            slack_channel.run_socket_listener(cli_config, stop_event)
        except Exception:  # noqa: BLE001 — the service keeps serving
            logger.exception("the hosted slack listener stopped on an error")
        finally:
            if not stop_event.is_set():
                # Ended on its own, not by shutdown: drop the lock so `status`
                # tells the truth and a restart can host it again.
                lock.release()
                eventlog.emit(
                    "ingress.hosted_stopped",
                    ingress=core_daemons.SLACK_LISTENER,
                    reason="exited",
                )

    thread = threading.Thread(target=serve, name="the-loop-slack-listener", daemon=True)
    thread.start()
    return _HostedIngress(core_daemons.SLACK_LISTENER, lock, thread, stop_event.set)


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
    slack = (config.get("channels") or {}).get("slack") or {}
    if isinstance(slack, dict) and slack.get("enabled", False):
        starters.append(("slack-listener", _start_slack_listener))
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
