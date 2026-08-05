"""``the-loop poll start|stop`` — poll ticketing/PR systems and spawn/route sessions.

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

Spec: docs/specs/issue-34/design.md; docs/specs/issue-63/design.md.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Optional

from .base import Command, register
from .. import cli_config, eventlog
from ..authz import resolve_authorized_users
from ..poller import (
    PollConfig,
    Poller,
    PollPlan,
    PollState,
    ProviderError,
    Reloader,
    build_provider,
)
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
            "pidfile": str(Path(layout.root) / "poll.pid"),
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
        start.set_defaults(_action=self._start)

        stop = actions.add_parser("stop", help="Stop a running poller")
        stop.add_argument("--pidfile", default=str(defaults["pidfile"]))
        stop.set_defaults(_action=self._stop)

    def run(self, args: argparse.Namespace) -> int:
        return int(args._action(args) or 0)

    # -- actions ---------------------------------------------------------------

    def _start(self, args: argparse.Namespace) -> int:
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        eventlog.configure_from_file("poll")
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
        )
        providers = plan.providers

        stop_event = threading.Event()
        pidfile = Path(args.pidfile)

        def _shutdown(signum, _frame):
            logger.info("received signal %s, stopping poller", signum)
            stop_event.set()

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        if not args.once:
            pidfile.parent.mkdir(parents=True, exist_ok=True)
            pidfile.write_text(str(os.getpid()))
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
        )
        try:
            poller.run(once=args.once, stop_event=stop_event)
        finally:
            dispatcher.stop()
            stop_web_terminal(web_proc)
            eventlog.emit("poller.stopped")
            if not args.once:
                try:
                    pidfile.unlink()
                except FileNotFoundError:
                    pass
        return 0

    def _stop(self, args: argparse.Namespace) -> int:
        pidfile = Path(args.pidfile)
        if not pidfile.is_file():
            print(f"no pidfile at {pidfile}; is the poller running?", file=sys.stderr)
            return 1
        try:
            pid = int(pidfile.read_text().strip())
        except ValueError:
            print(f"pidfile {pidfile} is corrupt", file=sys.stderr)
            return 1
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            print(f"process {pid} not running; removing stale pidfile", file=sys.stderr)
            pidfile.unlink(missing_ok=True)
            return 1
        print(f"sent SIGTERM to poll process (pid {pid})")
        return 0
