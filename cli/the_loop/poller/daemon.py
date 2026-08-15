"""The poller's run loop, out from under the removed ``poll`` command (issue-228).

``the-loop poll start`` used to be both the operator surface and the only
implementation of "run the poller". issue-228 removes the command — the operator
surface is now ``the-loop start|stop|status|restart``, composed per the CLI
config's ``enabled`` flags — so the run loop itself lives here, where
:mod:`the_loop.daemon_entry` (what the control plane and ``the-loop start``
spawn, and the cron/systemd foreground form) drives it directly.

What ran is unchanged (issue-34/63/159/191): the single-instance ``RunLock``
that doubles as the pidfile, the dependency checks, the heartbeat written
before the first cycle, config hot-reload per cycle, and the same
router/dispatcher/registry stack the webhook receiver uses. What is gone is the
detach machinery (``--daemon``'s double-fork + ready handshake): every remaining
detached start is a ``Popen(start_new_session=True)`` with the logfile on fds
1/2, and ``the-loop start`` proves liveness by waiting for this lock instead
(decision-084).

Spec: docs/specs/issue-228/design.md §D2.
"""

from __future__ import annotations

import logging
import signal
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .. import cli_config, eventlog
from ..authz import resolve_authorized_users
from ..runlock import RunLock
from ..state import StateLayout, layout_from_config, legacy_layout
from ..workitem import WorkItemStore

logger = logging.getLogger("the-loop.poll")

_DEFAULTS = {
    "intervalSeconds": 60,
    "maxRetries": 3,
}


@dataclass
class PollerOptions:
    """Everything :func:`run` needs, resolved from the CLI config."""

    interval: int
    max_retries: int
    state_dir: str
    pidfile: str
    status_file: str
    once: bool = False


def _config_path() -> Path:
    """Resolved per call, never cached at import: a ``--config`` override set by
    :mod:`the_loop.cli`'s pre-scan (or a test's env var) must always win."""
    return cli_config.default_cli_config_path()


def _load_polling_config() -> dict:
    """Best-effort read of ``polling`` from the CLI config (or ``{}``)."""
    return cli_config.load_cli_config(_config_path(), strict=False).get("polling") or {}


def _state_layout() -> StateLayout:
    """``state.root`` from the CLI config — the root of everything generated."""
    return layout_from_config(cli_config.load_cli_config(_config_path()))


def default_options(once: bool = False) -> PollerOptions:
    """The options the removed ``poll start`` parser would have defaulted to."""
    layout = _state_layout()
    polling = _load_polling_config()
    return PollerOptions(
        interval=int(polling.get("intervalSeconds") or _DEFAULTS["intervalSeconds"]),
        max_retries=int(polling.get("maxRetries") or _DEFAULTS["maxRetries"]),
        state_dir=str(layout.portable_dir),
        pidfile=str(layout.poll_pidfile),
        status_file=str(layout.poll_status),
        once=once,
    )


def _build_dispatcher(
    routing_map: Optional[dict], layout: Optional[StateLayout] = None
):
    """Compose the same registry + adapters + dispatcher the receiver uses."""
    from ..harness import build_adapters
    from ..sessions import SessionRegistry
    from ..webhook.dispatcher import Dispatcher, RoutingConfig

    routing = RoutingConfig.from_mapping(routing_map or {}, layout or _state_layout())
    dispatcher = Dispatcher(
        registry=SessionRegistry(routing.registry_dir),
        adapters=build_adapters(
            routing.harness_args, routing.harness_trust, routing.harness_plugins
        ),
        config=routing,
    )
    return dispatcher, routing


def age(timestamp: str) -> str:
    """``timestamp`` as "how long ago", or ``""`` when it cannot be read.

    Rendered beside the timestamp rather than instead of it: the absolute time is
    what an operator correlates with the log, and the relative one is what
    answers "is it stuck?" at a glance.
    """
    try:
        then = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except (TypeError, ValueError):
        return ""
    seconds = int((datetime.now(timezone.utc) - then).total_seconds())
    if seconds < 0:
        return "in the future"
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def describe_cycle(counters: dict) -> str:
    """The last cycle's counters as one line, mentioning only what happened."""
    parts = [
        f"{int(counters.get('itemsSeen') or 0)} item(s)",
        f"{int(counters.get('spawns') or 0)} spawn(s)",
        f"{int(counters.get('commentsForwarded') or 0)} comment(s) forwarded",
    ]
    for key, label in (
        ("closures", "closed"),
        ("failures", "gave up"),
        ("errors", "error(s)"),
    ):
        value = int(counters.get(key) or 0)
        if value:
            parts.append(f"{value} {label}")
    if counters.get("interrupted"):
        parts.append("interrupted")
    return ", ".join(parts)


def heartbeat_lines(beat, running: bool) -> list:
    """The poller's progress as lines of text, for ``the-loop status``.

    Enrichment only (issue-191): an absent heartbeat loses these lines and
    nothing more — liveness is the lock, reported by the caller.
    """
    if beat is None:
        return ["last cycle: unknown — no heartbeat recorded"]
    lines = []
    if beat.started_at:
        lines.append(f"started:    {beat.started_at} ({age(beat.started_at)})")
    if not beat.last_cycle_at:
        lines.append("last cycle: none recorded yet")
        return lines
    suffix = "" if running else ", before it stopped"
    lines.append(
        f"last cycle: {beat.last_cycle_at} ({age(beat.last_cycle_at)}{suffix}) — "
        f"{describe_cycle(beat.last_cycle)}"
    )
    return lines


def _clear_stale_pidfile(pidfile: Path) -> None:
    """Remove a pidfile no live poller holds, and say so (issue-191, R3.2).

    ``flock`` already makes a stale pidfile harmless — it is simply
    *unlocked*, so the next start takes it — but leaving it there means every
    `ps`/`cat` cross-check an operator does answers with a dead pid. Removing
    it is safe against the one race it has: a poller taking the lock between
    the probe and the unlink gets its file removed from under it, and
    :meth:`RunLock._open_locked` detects exactly that (a stale inode) and
    retries.
    """
    if not pidfile.is_file():
        return
    lock = RunLock(pidfile, name="poller")
    if lock.is_held():
        return
    holder = lock.holder()
    try:
        pidfile.unlink()
    except OSError:  # someone else got there first — nothing to clean up
        return
    logger.info(
        "removed a stale pidfile %s (pid %s is not running)",
        pidfile,
        holder or "unknown",
    )


def run(
    options: Optional[PollerOptions] = None,
    stop_event: Optional[threading.Event] = None,
    install_signal_handlers: bool = True,
) -> int:
    """Run the poller in this process until stopped (or once, under cron).

    The one startup sequence every path converges on (NFR1): lock acquisition,
    dependency checks, heartbeat, hot reload, the run loop.

    ``stop_event``/``install_signal_handlers`` exist for the **hosted** form
    (issue-231): the control-plane service runs this loop on a background
    thread, where installing signal handlers is impossible (POSIX allows them
    on the main thread only) and shutdown arrives as an event set by the
    service's lifespan instead of a signal.
    """
    options = options or default_options()
    # A no-op when the hosting process (uvicorn, issue-231) configured logging.
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    eventlog.configure_from_file("poll")

    # Config validation happens BEFORE the lock. `the-loop start` proves a
    # daemon started by seeing its lock held, so a poller doomed by its own
    # config (an unknown provider) must exit without ever holding it —
    # transiently taking the lock and dying during validation reads as a
    # successful start to a caller that samples at the wrong moment. This
    # pre-flight is pure (parse + construct, nothing touched), so it does not
    # loosen the lock-first rule below, which exists to fence *side effects*.
    from . import PollConfig, ProviderError, build_provider

    try:
        for source in PollConfig.from_mapping(_load_polling_config()).sources:
            build_provider(source, default_label="")
    except ProviderError as exc:
        logger.error("%s", exc)
        return 1

    _clear_stale_pidfile(Path(options.pidfile))

    # At most one poller per state root (issue-159). Taken BEFORE anything
    # else is built: a second poller must not get as far as checking
    # dependencies or binding the ttyd web terminal, and above all must not
    # touch the ledger — two pollers reading a work-item record on first
    # touch and writing it back later interleave read-modify-write and
    # re-forward each other's comments, which is exactly what makes a
    # restart observable. `--once` takes it too, so two overlapping cron
    # invocations cannot interleave either. The lock IS the pidfile, so
    # "who is running" and "how do I signal them" cannot disagree.
    lock = RunLock(options.pidfile, name="poller")
    try:
        acquired = lock.acquire()
    except OSError as exc:
        logger.error("cannot use the poller lockfile %s: %s", options.pidfile, exc)
        return 1
    if not acquired:
        holder = lock.holder()
        logger.error(
            "another poller is already running (pid %s, pidfile %s); not "
            "starting a second one against the same state — stop it first "
            "with `the-loop stop`",
            holder or "unknown",
            options.pidfile,
        )
        eventlog.emit(
            "poller.blocked",
            level="error",
            pidfile=str(options.pidfile),
            holder=holder or None,
        )
        return 1
    try:
        return _run_locked(
            options,
            stop_event=stop_event,
            install_signal_handlers=install_signal_handlers,
        )
    finally:
        lock.release()


def _run_locked(
    options: PollerOptions,
    stop_event: Optional[threading.Event] = None,
    install_signal_handlers: bool = True,
) -> int:
    """The poll run itself, with the single-instance lock already held."""
    from . import (
        PollConfig,
        Poller,
        PollHeartbeat,
        PollPlan,
        PollState,
        ProviderError,
        Reloader,
        build_provider,
    )

    dispatcher, routing = _build_dispatcher(
        cli_config.load_routing_config(_config_path())
    )

    # Rebuilds the mutable plan (providers + interval) from the config file.
    # Used once for the initial plan and again by the Reloader on each edit,
    # so a hot reload and a cold start go through exactly the same code.
    def build_plan() -> PollPlan:
        cfg = PollConfig.from_mapping(_load_polling_config())
        providers = [
            build_provider(source, default_label=routing.auto_execute_label)
            for source in cfg.sources
        ]
        return PollPlan(providers=providers, interval_seconds=cfg.interval_seconds)

    try:
        plan = build_plan()
    except ProviderError as exc:
        logger.error("%s", exc)
        return 1
    if not plan.providers:
        logger.error(
            "no polling sources configured — add entries under "
            f"polling.sources in the CLI config ({_config_path()}, e.g. "
            "provider: github)"
        )
        return 1

    from ..runner import check_dependencies, start_web_terminal, stop_web_terminal

    missing = [line for p in plan.providers for line in p.check_dependencies()]
    missing += check_dependencies(routing.web_terminal.enabled)
    if missing:
        for line in missing:
            logger.error(line)
        return 1

    web_proc = None
    if routing.web_terminal.enabled:
        web_proc = start_web_terminal(routing.web_terminal)

    config = PollConfig.from_mapping(_load_polling_config())
    config.interval_seconds = options.interval  # option overrides until a config edit
    config.max_retries = max(1, int(options.max_retries))
    authorized = resolve_authorized_users(routing.authorized_users)
    if not authorized:
        logger.warning(
            "no authorizedUsers configured — the poller will act on NO items "
            "or comments until you set routing.authorizedUsers in the CLI "
            "config (prompt-injection guard)"
        )
    # The heartbeat is written before the first cycle too, so `the-loop status`
    # can answer "started, no cycle yet" rather than "never ran" during the
    # first interval.
    heartbeat = PollHeartbeat(
        options.status_file or _state_layout().poll_status,
        interval_seconds=config.interval_seconds,
    )
    heartbeat.record(None)
    poller = Poller(
        providers=plan.providers,
        registry=dispatcher.registry,
        dispatcher=dispatcher,
        config=config,
        state=PollState(
            WorkItemStore(options.state_dir, legacy=legacy_layout(_state_layout()))
        ),
        reloader=Reloader(_config_path(), build_plan),
        authorized_users=authorized,
        heartbeat=lambda summary: heartbeat.record(
            summary, interval_seconds=config.interval_seconds
        ),
    )
    providers = plan.providers

    stop_event = stop_event if stop_event is not None else threading.Event()

    if install_signal_handlers:

        def _shutdown(signum, _frame):
            logger.info("received signal %s, stopping poller", signum)
            stop_event.set()

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

    logger.info(
        "poll: %s every %ss (spawnOnUnmatched=%s, state=%s)",
        "; ".join(p.describe() for p in providers),
        config.interval_seconds,
        routing.spawn_on_unmatched,
        options.state_dir,
    )
    if routing.control.enabled and routing.control.require_start_command:
        logger.info(
            "a labelled work item is armed, not started: an authorized user "
            "starts it by commenting %r (or running `the-loop sessions "
            "start`) — set routing.control.requireStartCommand: false for "
            "the pre-issue-106 label-alone behaviour",
            routing.control.keyword("start"),
        )
    eventlog.emit(
        "poller.started",
        interval_seconds=config.interval_seconds,
        sources=[p.describe() for p in providers],
        once=options.once,
    )
    try:
        poller.run(once=options.once, stop_event=stop_event)
    finally:
        # Whatever the dispatcher could not deliver before it shut down had
        # an attempt spent on it that never reached a session; hand that
        # budget back so restarting does not accumulate toward
        # `polling.maxRetries` (issue-159). The pidfile goes with the lock,
        # released by the caller.
        poller.release_abandoned(dispatcher.stop())
        stop_web_terminal(web_proc)
        eventlog.emit("poller.stopped")
    return 0
