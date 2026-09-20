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

**The set follows the config** (issue-395). Every long-lived process re-reads the
CLI config from its content hash and applies what it can — sources, intervals,
routing — but *which* ingresses this process hosts used to be composed once, in
the lifespan's first line, and never revisited: turning the Slack listener off
(``read.mode: off``) fired ``config.reloaded`` from the poller and left the
listener's connection open until a restart. :class:`HostedIngresses` is the
composition as a thing that can be re-run: it starts the set, watches the file
on a supervisor thread, and on every change stops what is no longer enabled and
starts what newly is, through the same starters, locks and refusals as at boot.
Membership only — an ingress whose own config changed keeps reloading what it
reloads today, and a listener that froze its config keeps it until it is stopped.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union

from .. import eventlog
from ..runlock import RunLock

logger = logging.getLogger("the-loop.service")

#: How often the supervisor re-hashes the config file to reconcile the hosted set
#: (issue-395). The operator-visible latency of a `read.mode: off` taking effect; one
#: sha256 of a ~10 KB file per tick.
RECONCILE_INTERVAL_SECONDS = 5.0

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

    def stop(self, reason: str = "shutdown") -> None:
        """End the loop, release the lock, record it.

        ``reason`` is ``shutdown`` (the service is going down) or ``config`` (the
        config no longer enables this ingress, issue-395) — carried on the event so
        the trail says why a listener went away while the service stayed up.
        """
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
        eventlog.emit("ingress.hosted_stopped", ingress=self.name, reason=reason)


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
    from ..repos import repository_bounds

    polling = (cli_config.get("polling")) or {}
    if not polling.get("sources"):
        reason = (
            "polling.enabled is true but polling.sources is empty — nothing to poll"
        )
        logger.error("not hosting the poller: %s", reason)
        return None, reason
    if not repository_bounds(cli_config):
        # issue-348: what is polled moved to the top level, so a fully configured
        # source can still have nothing to poll. Refused here, as an empty
        # `sources` is, rather than looping on a per-cycle provider error.
        reason = (
            "polling.enabled is true but the top-level `repositories` is empty "
            "— nothing to poll"
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


#: Boot order, and the starter for each ingress. ``stop`` walks it reversed.
_STARTERS: Tuple[Tuple[str, Callable[[dict], _Start]], ...] = (
    ("gh-webhook", _start_receiver),
    ("poller", _start_poller),
    ("slack-listener", _start_slack_listener),
)


def _wanted(config: dict) -> List[Tuple[str, Callable[[dict], _Start]]]:
    """The ingresses ``config`` enables, in boot order, each with its starter.

    The predicate is :func:`the_loop.core.lifecycle.enabled_services` — the one
    ``the-loop start`` and ``the-loop status`` already share (`polling.enabled`,
    `webhooks.ghWebhook.enabled`, `channels.slack.enabled` with `read.mode: socket`) —
    so the boot composition and the reconcile (issue-395) can never disagree with
    either command about what is enabled. Imported lazily: ``core.lifecycle`` is the
    composition layer above this module, and pulling it in at import time would make
    the hosting depend on the thing that depends on it.
    """
    from ..core.lifecycle import enabled_services

    enabled = enabled_services(config)
    return [(name, start) for name, start in _STARTERS if enabled.get(name)]


def _start_one(name: str, start: Callable[[dict], _Start], config: dict, *, why: str):
    """Run one starter and record the outcome; never raises. Returns the ingress or None."""
    try:
        ingress, reason = start(config)
    except Exception as exc:  # noqa: BLE001 — one ingress must not take the API down
        logger.exception("hosting the %s failed (%s)", name, why)
        ingress, reason = None, str(exc) or exc.__class__.__name__
    if ingress is not None:
        logger.info("hosting the %s in this service process (%s)", name, why)
        eventlog.emit("ingress.hosted", ingress=name, reason=why)
        return ingress
    if reason:
        # The event that was missing (issue-339, R3.1). An enabled ingress that
        # never came up used to leave a logfile line and NOTHING in the event log —
        # so `the-loop events`, the stream and self-diagnosis saw only the absence
        # of a `poller.started`, which is a signal something has to derive. A
        # starter that declined because it was not asked for answers with an empty
        # reason and is passed over (R3.3): a listener in `read.mode: poll` is a
        # configuration, not a failure. The service keeps serving either way — the
        # API being up is what makes the reason reachable (R3.2).
        eventlog.emit(
            "ingress.hosted_failed", level="error", ingress=name, reason=reason
        )
    return None


def start_hosted_ingresses(cli_config: Optional[dict]) -> List[_HostedIngress]:
    """Start every ingress this process should host; never raises.

    Which ones is the same policy ``the-loop start`` composes on
    (`webhooks.ghWebhook.enabled`, `polling.enabled`, `channels.slack.enabled` with
    `read.mode: socket`); whether *this process* hosts them at all is
    ``service.hostIngresses``, resolved by the caller.
    """
    config = cli_config or {}
    hosted: List[_HostedIngress] = []
    for name, start in _wanted(config):
        ingress = _start_one(name, start, config, why="startup")
        if ingress is not None:
            hosted.append(ingress)
    # The pidfiles double as the honest-start proof `the-loop start` waits on,
    # so nothing extra is written: a hosted ingress is up iff its lock is held.
    return hosted


def stop_hosted_ingresses(hosted: List[_HostedIngress]) -> None:
    """Stop in reverse start order; each stop is isolated."""
    for ingress in reversed(hosted):
        ingress.stop()


class HostedIngresses:
    """The hosted set as a thing that follows the config (issue-395).

    ``start()`` composes the set exactly as :func:`start_hosted_ingresses` does, then
    runs a supervisor thread that re-hashes ``config_path`` every ``interval`` seconds
    through the same strict loader the service's :class:`~the_loop.cli_config.ConfigHolder`
    uses, and on a change calls :meth:`reconcile`. ``stop()`` ends the supervisor
    *first*, then the ingresses in reverse start order — under the one lock
    :meth:`reconcile` takes, so a shutdown and a reconcile never interleave.

    A thread rather than the per-request refresh because a service nobody is calling
    (the second instance of the e2e run, whose listener was to be turned off) must
    still notice; a :class:`~the_loop.reload.Reloader` rather than a watcher because it
    is what every other process uses — stdlib, content hash, and an unloadable file
    keeps the previous value, so a half-typed edit stops nothing.
    """

    def __init__(
        self,
        cli_config: Optional[dict],
        config_path: Union[str, Path],
        *,
        interval: float = RECONCILE_INTERVAL_SECONDS,
    ) -> None:
        from ..cli_config import load_cli_config
        from ..reload import Reloader

        self.config: dict = dict(cli_config or {})
        self.path = Path(config_path)
        self.interval = float(interval)
        self._hosted: List[_HostedIngress] = []
        self._lock = threading.RLock()
        self._stopping = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self._reloader: "Reloader[dict]" = Reloader(
            self.path, lambda: load_cli_config(self.path, strict=True)
        )

    @property
    def hosted(self) -> List[_HostedIngress]:
        """The ingresses hosted right now (a copy; boot order)."""
        with self._lock:
            return list(self._hosted)

    def start(self) -> None:
        with self._lock:
            self._hosted = start_hosted_ingresses(self.config)
        self._stopping.clear()
        self.thread = threading.Thread(
            target=self._supervise, name="the-loop-ingress-supervisor", daemon=True
        )
        self.thread.start()

    def stop(self) -> None:
        """End the supervisor, then every hosted ingress (reverse start order)."""
        self._stopping.set()
        thread = self.thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(_JOIN_TIMEOUT_SECONDS)
        with self._lock:
            stop_hosted_ingresses(self._hosted)
            self._hosted = []

    def _supervise(self) -> None:
        while not self._stopping.wait(self.interval):
            try:
                fresh = self._reloader.poll_for_change()
                if fresh is not None and not self._stopping.is_set():
                    self.reconcile(fresh)
            except Exception:  # noqa: BLE001 — one bad tick must not lose the supervisor
                logger.exception("reconciling the hosted ingresses failed; will retry")

    def reconcile(self, config: dict) -> None:
        """Make the hosted set match what ``config`` enables.

        Membership only: *hosted − wanted* is stopped (``reason: config``), *wanted −
        hosted* is started with ``config`` through the same starter as at boot, and an
        ingress in both is left exactly as it is. A hosted entry whose thread has
        already ended on its own (its lock released by :func:`_host`) is dropped, so a
        config edit can bring back a listener that died on, say, a rejected token.
        """
        with self._lock:
            if self._stopping.is_set():
                return
            self.config = dict(config or {})
            wanted = _wanted(self.config)
            wanted_names = [name for name, _ in wanted]
            alive = [h for h in self._hosted if h.thread.is_alive()]
            dead = [h.name for h in self._hosted if not h.thread.is_alive()]
            for name in dead:
                logger.info(
                    "the hosted %s had already ended on its own; the config can "
                    "start it again",
                    name,
                )
            keep = [h for h in alive if h.name in wanted_names]
            stopped: List[str] = []
            for ingress in reversed([h for h in alive if h.name not in wanted_names]):
                logger.info(
                    "the config no longer enables the %s; stopping it", ingress.name
                )
                ingress.stop(reason="config")
                stopped.append(ingress.name)
            started: List[str] = []
            hosted_names = {h.name for h in keep}
            for name, start in wanted:
                if name in hosted_names:
                    continue
                ingress = _start_one(name, start, self.config, why="config")
                if ingress is not None:
                    keep.append(ingress)
                    started.append(name)
            # Boot order, whatever order the starts happened in.
            order = {name: i for i, (name, _) in enumerate(_STARTERS)}
            self._hosted = sorted(keep, key=lambda h: order.get(h.name, len(order)))
            if stopped or started:
                detail = "hosted ingresses: " + "; ".join(
                    part
                    for part in (
                        f"stopped {', '.join(stopped)}" if stopped else "",
                        f"started {', '.join(started)}" if started else "",
                    )
                    if part
                )
                logger.info("hot-reloaded %s", detail)
                eventlog.emit("config.reloaded", detail=detail)
