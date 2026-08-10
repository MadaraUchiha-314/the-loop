"""``the-loop poll start|stop|status`` — poll ticketing/PR systems and spawn/route sessions.

A pull-based, **provider-agnostic** sibling of ``gh-webhook`` for machines a
webhook cannot reach (issue-34). ``start`` reads ``polling.sources`` from the
CLI config (``the_loop.cli_config`` for the ``cli-config.yaml`` resolution order —
``--config``, then ``$THE_LOOP_CLI_CONFIG``, then ``./.the-loop/cli-config.yaml``,
then ``~/.the-loop/cli-config.yaml``, decision-032),
builds a :class:`PollProvider` for each (GitHub ships), discovers the
label-gated work items in each source, and drives them through the *same*
router/dispatcher/registry the webhook receiver uses — so sessions spawn and
events route identically (including the tmux runner). The system interfaces
with a provider (e.g. GitHub) *only* through config; the CLI and core carry no
provider-specific knobs. Dispatch behaviour is the top-level ``routing`` block,
read through :func:`the_loop.cli_config.load_routing_config` — the same policy
the receiver runs on, which is why issue-142 promoted it out from under
``webhooks``. Flags cover only the run loop.

``start`` runs in the **foreground** by default — which is what cron (`--once`)
and a systemd ``Type=simple`` unit expect — and detaches properly with
``--daemon``: double-fork, ``setsid``, stdout/stderr redirected to a logfile, and
the pidfile written by the process that actually survives (issue-191). ``status``
answers "is the poller running, and is it making progress" from the lock and the
heartbeat, so that question costs one command instead of a ps/pidfile/log
cross-check.

Spec: docs/specs/issue-34/design.md; docs/specs/issue-63/design.md;
docs/specs/issue-191/design.md.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .base import Command, register
from .. import cli_config, eventlog
from ..authz import resolve_authorized_users
from ..daemonize import daemonize, notify_ready, open_logfile
from ..poller import (
    Heartbeat,
    PollConfig,
    Poller,
    PollHeartbeat,
    PollPlan,
    PollState,
    ProviderError,
    Reloader,
    build_provider,
)
from ..runlock import RunLock
from ..state import StateLayout, layout_from_config, legacy_layout
from ..workitem import WorkItemStore

logger = logging.getLogger("the-loop.poll")

# The CLI config (webhooks/polling/eventLog). Deliberately the ONLY config
# source the poller reads (issue-63 review): which repos to watch and who may
# trigger it are CLI-config concerns, not the repo-local plugin config's.
_CONFIG_PATH = cli_config.default_cli_config_path()

_DEFAULTS = {
    "intervalSeconds": 60,
    "maxRetries": 3,
}

# How long `stop` waits for the poller to actually exit before reporting that it
# did not (issue-159). Generous enough for the dispatcher to drain its queues,
# short enough that a scripted `stop && start` fails loudly rather than hanging.
_STOP_TIMEOUT_SECONDS = 30.0


def _load_polling_config() -> dict:
    """Best-effort read of ``polling`` from the CLI config (or ``{}``)."""
    return cli_config.load_cli_config(_CONFIG_PATH, strict=False).get("polling") or {}


def _state_layout() -> StateLayout:
    """``state.root`` from the CLI config — the root of everything generated."""
    return layout_from_config(cli_config.load_cli_config(_CONFIG_PATH))


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


def _age(timestamp: str) -> str:
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


def _describe_cycle(counters: dict) -> str:
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


def _render_status(report: dict, beat: Optional[Heartbeat]) -> list:
    """``poll status`` as lines of text."""
    running = bool(report["running"])
    pidfile = report["pidfile"]
    if report["stalePidfile"]:
        pidfile += f" (stale — pid {report['recordedPid'] or 'unknown'} is not running)"
    liveness = f"running (pid {report['pid']})" if running else "not running"
    lines = [
        f"poller:     {liveness}",
        f"pidfile:    {pidfile}",
        f"logfile:    {report['logfile']}",
    ]
    if beat is None:
        lines.append(
            "last cycle: unknown — no heartbeat at "
            f"{report['statusFile']} (a poller from before it existed, or one "
            "whose heartbeat was removed)"
        )
        return lines
    if beat.started_at:
        lines.append(f"started:    {beat.started_at} ({_age(beat.started_at)})")
    if not beat.last_cycle_at:
        lines.append("last cycle: none recorded yet")
        return lines
    suffix = "" if running else ", before it stopped"
    lines.append(
        f"last cycle: {beat.last_cycle_at} ({_age(beat.last_cycle_at)}{suffix}) — "
        f"{_describe_cycle(beat.last_cycle)}"
    )
    return lines


@register
class PollCommand(Command):
    name = "poll"
    help = "Poll configured ticketing/PR sources and spawn/route harness sessions"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        # Path defaults come from `state.root` (issue-106) and are computed here,
        # not at import: `--config` is resolved just before this runs. The ledger
        # lives with the rest of the portable state (issue-128); a pre-issue-128
        # location is still READ per work item, so an upgrade never re-forwards a
        # thread it has already seen.
        layout = _state_layout()
        defaults = {
            **_DEFAULTS,
            "stateDir": layout.portable_dir,
            "pidfile": layout.poll_pidfile,
            "logfile": layout.poller_log,
            "statusFile": layout.poll_status,
            **_load_polling_config(),
        }
        actions = parser.add_subparsers(dest="action", metavar="<action>")
        actions.required = True

        start = actions.add_parser("start", help="Start polling configured sources")
        start.add_argument(
            "--interval",
            type=int,
            default=int(defaults["intervalSeconds"]),
            help="Seconds between poll cycles (default: polling.intervalSeconds).",
        )
        start.add_argument(
            "--once",
            action="store_true",
            help="Run a single poll cycle and exit (useful under cron/systemd).",
        )
        start.add_argument(
            "--state-dir",
            default=str(defaults["stateDir"]),
            help="Portable work-item records (cross-poll comment-dedup state).",
        )
        start.add_argument(
            "--max-retries",
            type=int,
            default=int(defaults["maxRetries"]),
            help=(
                "Per-event delivery attempts before giving up "
                "(default: polling.maxRetries)."
            ),
        )
        start.add_argument(
            "--pidfile",
            default=str(defaults["pidfile"]),
            help="Where to record the poller PID (for `stop`).",
        )
        # One setting, two spellings, so the last flag on the line wins. The
        # DEFAULT stays foreground: `--once` under cron and a systemd
        # `Type=simple` unit both require it, and a default that detaches would
        # break them silently to save one discoverable flag (decision-072).
        start.add_argument(
            "--daemon",
            dest="daemon",
            action="store_true",
            default=False,
            help=(
                "Detach: double-fork + setsid, redirect stdout/stderr to "
                "--logfile, and leave a poller that outlives this shell."
            ),
        )
        start.add_argument(
            "--foreground",
            dest="daemon",
            action="store_false",
            help="Run in the foreground (the default) — for systemd/supervisors.",
        )
        start.add_argument(
            "--logfile",
            default=str(defaults["logfile"]),
            help=(
                "Where a daemonized poller's stdout/stderr go "
                "(default: <state.root>/logs/poller.out)."
            ),
        )
        start.add_argument(
            "--status-file",
            default=str(defaults["statusFile"]),
            help="Where the poller records its heartbeat (for `status`).",
        )
        start.set_defaults(_action=self._start)

        stop = actions.add_parser("stop", help="Stop a running poller")
        stop.add_argument("--pidfile", default=str(defaults["pidfile"]))
        stop.add_argument(
            "--timeout",
            type=float,
            default=_STOP_TIMEOUT_SECONDS,
            help=(
                "Seconds to wait for the poller to actually exit before "
                "reporting that it did not (default: 30)."
            ),
        )
        stop.set_defaults(_action=self._stop)

        status = actions.add_parser(
            "status", help="Report whether a poller is running, and its last cycle"
        )
        status.add_argument("--pidfile", default=str(defaults["pidfile"]))
        status.add_argument("--logfile", default=str(defaults["logfile"]))
        status.add_argument("--status-file", default=str(defaults["statusFile"]))
        status.add_argument("--format", choices=["text", "json"], default="text")
        status.set_defaults(_action=self._status)

    def run(self, args: argparse.Namespace) -> int:
        return int(args._action(args) or 0)

    # -- actions ---------------------------------------------------------------

    def _start(self, args: argparse.Namespace) -> int:
        if getattr(args, "daemon", False):
            outcome = self._detach(args)
            if outcome is not None:  # the original process — never the daemon
                return outcome
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        eventlog.configure_from_file("poll")
        self._clear_stale_pidfile(Path(args.pidfile))

        # At most one poller per state root (issue-159). Taken BEFORE anything
        # else is built: a second poller must not get as far as checking
        # dependencies or binding the ttyd web terminal, and above all must not
        # touch the ledger — two pollers reading a work-item record on first
        # touch and writing it back later interleave read-modify-write and
        # re-forward each other's comments, which is exactly what makes a
        # restart observable. `--once` takes it too, so two overlapping cron
        # invocations cannot interleave either. The lock IS the pidfile, so
        # "who is running" and "how do I signal them" cannot disagree.
        lock = RunLock(args.pidfile, name="poller")
        try:
            acquired = lock.acquire()
        except OSError as exc:
            logger.error("cannot use the poller lockfile %s: %s", args.pidfile, exc)
            return 1
        if not acquired:
            holder = lock.holder()
            logger.error(
                "another poller is already running (pid %s, pidfile %s); not "
                "starting a second one against the same state — stop it first "
                "with `the-loop poll stop`",
                holder or "unknown",
                args.pidfile,
            )
            eventlog.emit(
                "poller.blocked",
                level="error",
                pidfile=str(args.pidfile),
                holder=holder or None,
            )
            return 1
        try:
            return self._run_poller(args, lock)
        finally:
            lock.release()

    # -- detaching -------------------------------------------------------------

    def _detach(self, args: argparse.Namespace) -> Optional[int]:
        """Fork the poller into a daemon. ``None`` means "you are the daemon".

        Everything that can be checked before forking **is**, so a refusal
        reaches the operator's terminal rather than a logfile nobody has opened
        yet: the conflicting flag, the unopenable logfile, and a lock another
        poller already holds. What cannot be checked here — dependencies,
        providers, the race for the lock — is reported back over the handshake
        by :func:`the_loop.daemonize.notify_ready`, which the daemon calls only
        once it is genuinely up.
        """
        if args.once:
            print(
                "--daemon and --once are contradictory: a single cycle has "
                "nothing to detach for, and detaching would hide its exit code "
                "from the cron job that asked for it. Use one or the other.",
                file=sys.stderr,
            )
            return 2
        try:
            os.close(open_logfile(args.logfile))  # R2.4: prove it, then let go
        except OSError as exc:
            print(
                f"cannot open the poller logfile {args.logfile}: {exc}",
                file=sys.stderr,
            )
            return 1
        lock = RunLock(args.pidfile, name="poller")
        if lock.is_held():
            print(
                f"another poller is already running (pid {lock.holder() or 'unknown'}, "
                f"pidfile {args.pidfile}); stop it first with `the-loop poll stop`",
                file=sys.stderr,
            )
            return 1

        try:
            pid = daemonize(args.logfile)
        except OSError as exc:  # fork exhausted, or the logfile vanished
            print(f"cannot detach the poller: {exc}", file=sys.stderr)
            return 1
        if pid is None:
            return None  # we are the daemon; carry on with the ordinary start
        if pid == 0:
            print(
                "the poller did not come up — it exited during startup, or did "
                f"not report itself ready in time. See {args.logfile}",
                file=sys.stderr,
            )
            return 1
        print(f"poller started (pid {pid}); logging to {args.logfile}")
        return 0

    @staticmethod
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

    def _run_poller(self, args: argparse.Namespace, lock: RunLock) -> int:
        """The poll run itself, with the single-instance lock already held."""
        dispatcher, routing = _build_dispatcher(
            cli_config.load_routing_config(_CONFIG_PATH)
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
                f"polling.sources in the CLI config ({_CONFIG_PATH}, e.g. "
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
        config.interval_seconds = args.interval  # flag overrides until a config edit
        config.max_retries = max(1, int(args.max_retries))
        authorized = resolve_authorized_users(routing.authorized_users)
        if not authorized:
            logger.warning(
                "no authorizedUsers configured — the poller will act on NO items "
                "or comments until you set routing.authorizedUsers in the CLI "
                "config (prompt-injection guard)"
            )
        # The heartbeat is written before the first cycle too, so `poll status`
        # can answer "started, no cycle yet" rather than "never ran" during the
        # first interval.
        heartbeat = PollHeartbeat(
            getattr(args, "status_file", None) or _state_layout().poll_status,
            interval_seconds=config.interval_seconds,
        )
        heartbeat.record(None)
        poller = Poller(
            providers=plan.providers,
            registry=dispatcher.registry,
            dispatcher=dispatcher,
            config=config,
            state=PollState(
                WorkItemStore(args.state_dir, legacy=legacy_layout(_state_layout()))
            ),
            reloader=Reloader(_CONFIG_PATH, build_plan),
            authorized_users=authorized,
            heartbeat=lambda summary: heartbeat.record(
                summary, interval_seconds=config.interval_seconds
            ),
        )
        providers = plan.providers

        stop_event = threading.Event()

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
            args.state_dir,
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
            once=args.once,
            daemon=bool(getattr(args, "daemon", False)) or None,
            logfile=str(args.logfile) if getattr(args, "daemon", False) else None,
        )
        # Everything that can fail at startup has now either failed or passed, so
        # this is the first honest moment to tell the process that started us we
        # are up (issue-191, R3.5). A no-op unless we were daemonized.
        notify_ready()
        try:
            poller.run(once=args.once, stop_event=stop_event)
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

    def _stop(self, args: argparse.Namespace) -> int:
        """Stop the running poller, and return only once it has actually gone.

        The pidfile is also the poller's lock (issue-159), which is what makes
        both halves of this honest. Being able to *take* the lock proves nobody
        is running, so a pid left behind by a `SIGKILL` is never signalled — it
        used to be, and on a busy host pid reuse meant `the-loop` sending
        `SIGTERM` to an unrelated process. And waiting for the lock to be
        released proves the poller has exited, so the `stop && start` an
        operator actually types cannot overlap the shutdown it just asked for.
        """
        pidfile = Path(args.pidfile)
        if not pidfile.is_file():
            print(f"no pidfile at {pidfile}; is the poller running?", file=sys.stderr)
            return 1
        lock = RunLock(pidfile, name="poller")
        if not lock.is_held():
            print(
                f"no poller is running; removing the stale pidfile {pidfile}",
                file=sys.stderr,
            )
            pidfile.unlink(missing_ok=True)
            return 1
        pid = lock.holder()
        if pid <= 0:
            print(f"pidfile {pidfile} is corrupt", file=sys.stderr)
            return 1
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:  # died between the lock probe and the signal
            print(f"process {pid} not running; removing stale pidfile", file=sys.stderr)
            pidfile.unlink(missing_ok=True)
            return 1
        print(f"sent SIGTERM to poll process (pid {pid}); waiting for it to exit")
        if not lock.wait_until_free(args.timeout):
            print(
                f"poll process (pid {pid}) had not exited after {args.timeout:g}s; "
                "it may be draining a long dispatch — check again before starting "
                "another poller",
                file=sys.stderr,
            )
            return 1
        print(f"poll process (pid {pid}) stopped")
        return 0

    def _status(self, args: argparse.Namespace) -> int:
        """Report liveness, pid and last cycle. Exit 0 running, 1 not (issue-191).

        Liveness comes from the **lock** and nothing else: it is the only
        formulation immune to pid reuse, and the only one a file cannot forge.
        The heartbeat beside it adds progress — when this poller started, when it
        last finished a cycle, what that cycle did — and is treated as
        enrichment throughout: an absent or unreadable one loses those lines and
        nothing more.

        The exit code is what makes this scriptable: `poll status || …` is a
        health check, which is the ps/pidfile/log cross-check this action exists
        to replace.
        """
        pidfile = Path(args.pidfile)
        lock = RunLock(pidfile, name="poller")
        running = lock.is_held()
        recorded = lock.holder() if pidfile.is_file() else 0
        stale = pidfile.is_file() and not running
        beat = PollHeartbeat.read(args.status_file)

        report = {
            "daemon": "poller",
            "running": running,
            "pid": recorded if running else 0,
            "pidfile": str(pidfile),
            "stalePidfile": stale,
            "recordedPid": recorded,
            "logfile": str(args.logfile),
            "statusFile": str(args.status_file),
            "startedAt": beat.started_at if beat else "",
            "lastCycleAt": beat.last_cycle_at if beat else "",
            "lastCycle": dict(beat.last_cycle) if beat else {},
            "intervalSeconds": beat.interval_seconds if beat else 0,
        }
        if args.format == "json":
            print(json.dumps(report, indent=2))
        else:
            for line in _render_status(report, beat):
                print(line)
        return 0 if running else 1
