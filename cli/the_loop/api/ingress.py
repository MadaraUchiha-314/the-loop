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
logged warning and an ``ingress.hosted_failed`` event at level ``error``
(issue-339); the service itself keeps serving. The API being up is what lets an
operator see and fix the reason, and the event is what puts it where the trail
is read: before it, a poller that never came up was visible only as the
*absence* of a ``poller.started``, which nothing was computing.
"""

from __future__ import annotations

import logging
import threading
from typing import List, Optional, Tuple

from .. import eventlog
from ..runlock import RunLock

logger = logging.getLogger("the-loop.service")

#: What a starter answers: the hosted ingress, or ``None`` and WHY. The reason is a
#: return value rather than only a log line because it is what the
#: ``ingress.hosted_failed`` event carries (issue-339, R3.1) — an enabled ingress that
#: never came up used to be visible only as a missing ``poller.started``. ``None`` with
#: an EMPTY reason is the third answer: not a failure, just not asked for — a Slack
#: channel enabled with ``read.mode: poll`` wants no hosted listener, and must not be
#: reported as one that could not start.
_Start = Tuple[Optional["_HostedIngress"], str]

#: What :func:`_acquire` answers: the held lock, or ``None`` and the same reason.
_Acquired = Tuple[Optional[RunLock], str]

#: How long shutdown waits for a hosted ingress thread to finish.
_JOIN_TIMEOUT_SECONDS = 30.0


class _HostedIngress:
    """One hosted run loop: its lock, its thread, and how to stop it."""

    def __init__(
        self,
        name: str,
        lock: RunLock,
        thread: threading.Thread,
        stop,
        stopping: Optional[threading.Event] = None,
    ):
        self.name = name
        self.lock = lock
        self.thread = thread
        self._stop = stop
        #: Set by :meth:`stop` BEFORE the loop is asked to end, so the thread's own
        #: `finally` can tell "we shut it down" from "it ended by itself" (issue-339).
        self.stopping = stopping or threading.Event()

    def stop(self) -> None:
        self.stopping.set()
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


def _host(name: str, lock: RunLock, run, stop) -> _HostedIngress:
    """Run a hosted loop on a thread, and keep its lock honest (issue-339).

    A run loop that ends **on its own** — a dependency it needs is missing, an
    unhandled exception, a config it cannot act on — must not leave the lock held: the
    lock IS what ``the-loop status`` and ``GET /api/v1/health`` read for liveness, so a
    dead ingress would otherwise be reported as running under the service's pid, which
    is the shape of the outage issue-339 reports. Dropping the lock makes both surfaces
    say "not running", and the ``ingress.hosted_failed`` event says why it is not.

    ``stop`` is only ever called by :meth:`_HostedIngress.stop`, which sets ``stopping``
    first — so an orderly shutdown releases the lock once, in the caller, and records
    ``ingress.hosted_stopped`` as it always has. This is the discipline the Slack
    listener has had since issue-334, applied to every hosted ingress.
    """
    stopping = threading.Event()

    def serve() -> None:
        try:
            run()
        except Exception:  # noqa: BLE001 — the service keeps serving
            logger.exception("the hosted %s stopped on an error", name)
        finally:
            if not stopping.is_set():
                lock.release()
                eventlog.emit(
                    "ingress.hosted_failed",
                    level="error",
                    ingress=name,
                    reason=(
                        "the run loop ended on its own, without a shutdown; its lock "
                        "is released so `status` does not report it as running — the "
                        "reason is in the service log"
                    ),
                )

    thread = threading.Thread(target=serve, name=f"the-loop-{name}", daemon=True)
    thread.start()
    return _HostedIngress(name, lock, thread, stop, stopping=stopping)


def _acquire(name: str, pidfile: str) -> _Acquired:
    """The ingress's single-instance lock, or ``None`` with the reason (issue-339).

    The reason travels back to the caller as well as to the log, because it is what the
    ``ingress.hosted_failed`` event says — a lock holder's pid and a pidfile path, the
    same words the logfile gets.
    """
    lock = RunLock(pidfile, name=name)
    try:
        if lock.acquire():
            return lock, ""
    except OSError as exc:
        logger.error("cannot use the %s lockfile %s: %s", name, pidfile, exc)
        return None, f"cannot use the lockfile {pidfile}: {exc}"
    holder = lock.holder() or "unknown"
    logger.warning(
        "not hosting the %s: another one is already running (pid %s, pidfile "
        "%s) — likely a standalone daemon; stop it with `the-loop stop` to let "
        "the service host it",
        name,
        holder,
        pidfile,
    )
    return None, (
        f"another {name} is already running (pid {holder}, pidfile {pidfile}) — "
        "likely a standalone daemon"
    )


def _start_poller(cli_config: dict) -> _Start:
    from ..poller import daemon as poller_daemon

    polling = (cli_config.get("polling")) or {}
    if not polling.get("sources"):
        reason = (
            "polling.enabled is true but polling.sources is empty — nothing to poll"
        )
        logger.error("not hosting the poller: %s", reason)
        return None, reason
    options = poller_daemon.default_options()
    lock, reason = _acquire("poller", options.pidfile)
    if lock is None:
        return None, reason
    stop_event = threading.Event()
    return (
        _host(
            "poller",
            lock,
            lambda: poller_daemon._run_locked(
                options, stop_event=stop_event, install_signal_handlers=False
            ),
            stop_event.set,
        ),
        "",
    )


def _start_receiver(cli_config: dict) -> _Start:
    from ..webhook import daemon as webhook_daemon

    options = webhook_daemon.default_options()
    lock, reason = _acquire("gh-webhook", options.pidfile)
    if lock is None:
        return None, reason
    built = webhook_daemon.build_receiver(options)
    if built is None:  # reasons already logged (dependency, bind, …)
        lock.release()
        return None, (
            "the receiver could not be built — a missing dependency, or a port it "
            "cannot bind; the reason is in the service log"
        )
    httpd, cleanup = built

    def serve() -> None:
        try:
            httpd.serve_forever()
        finally:
            cleanup()

    return _host("gh-webhook", lock, serve, httpd.shutdown), ""


def _start_slack_listener(cli_config: dict) -> _Start:
    """The Slack Socket Mode listener as a hosted thread (issue-334).

    Only when the channel is enabled with ``read.mode: socket`` — the same rule
    ``channels listen`` applies — and only with both tokens present, refused
    loudly otherwise so ``the-loop start`` reports it rather than hosting a
    loop that would exit at once. A listener that stops on its own (a token
    Slack rejects, an exception past the SDK's reconnect) releases its lock,
    so ``status`` never reports a dead listener as running — :func:`_host`'s job
    since issue-339, and every hosted ingress's property now.
    """
    import os

    from ..channels import slack as slack_channel
    from ..core import daemons as core_daemons

    config = slack_channel.SlackChannelConfig.from_mapping(cli_config)
    if not config.enabled or config.read_mode != "socket":
        # Not asked for: `channels listen` in the foreground, or read.mode: poll.
        return None, ""
    missing = [
        env
        for env in (config.app_token_env, config.bot_token_env)
        if not os.environ.get(env)
    ]
    if missing:
        # The variable NAMES, never their values (issue-339, abuse case AC5).
        reason = (
            f"{' and '.join(missing)} not set — Socket Mode needs the app-level "
            "token (xapp-, connections:write) and the bot token (xoxb-)"
        )
        logger.error("not hosting the slack listener: %s", reason)
        return None, reason
    lock, reason = _acquire(
        core_daemons.SLACK_LISTENER,
        core_daemons._pidfile(core_daemons.SLACK_LISTENER, cli_config),
    )
    if lock is None:
        return None, reason
    stop_event = threading.Event()
    # Since issue-339 the "ended on its own -> drop the lock" discipline this listener
    # introduced is `_host`'s, and every hosted ingress has it.
    return (
        _host(
            core_daemons.SLACK_LISTENER,
            lock,
            lambda: slack_channel.run_socket_listener(cli_config, stop_event),
            stop_event.set,
        ),
        "",
    )


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
            ingress, reason = start(config)
        except Exception as exc:  # noqa: BLE001 — one ingress must not take the API down
            logger.exception("hosting the %s failed during startup", name)
            ingress, reason = None, str(exc) or exc.__class__.__name__
        if ingress is not None:
            hosted.append(ingress)
            logger.info("hosting the %s in this service process", name)
            eventlog.emit("ingress.hosted", ingress=name)
        elif reason:
            # The event that was missing (issue-339, R3.1). An enabled ingress that
            # never came up used to leave a logfile line and NOTHING in the event log —
            # so `the-loop events`, the stream and self-diagnosis saw only the absence
            # of a `poller.started`, which is a signal something has to derive. A
            # starter that declined because it was not asked for answers with an empty
            # reason and is passed over (R3.3): `channels.slack.enabled` puts the
            # listener in `starters`, but `read.mode: poll` is a configuration, not a
            # failure. The service keeps serving either way — the API being up is what
            # makes the reason reachable (R3.2).
            eventlog.emit(
                "ingress.hosted_failed", level="error", ingress=name, reason=reason
            )
    # The pidfiles double as the honest-start proof `the-loop start` waits on,
    # so nothing extra is written: a hosted ingress is up iff its lock is held.
    return hosted


def stop_hosted_ingresses(hosted: List[_HostedIngress]) -> None:
    """Stop in reverse start order; each stop is isolated."""
    for ingress in reversed(hosted):
        ingress.stop()
