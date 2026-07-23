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
provider-specific knobs. Dispatch behaviour is reused from
``webhooks.ghWebhook.routing``. Flags cover only the run loop.

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
from typing import List, Optional

from .base import Command, register
from .gh_webhook import _load_config_defaults
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

logger = logging.getLogger("the-loop.poll")

# The CLI config (webhooks/polling/eventLog) — not the PLUGIN config below.
_CONFIG_PATH = cli_config.default_cli_config_path()

# The repo-local PLUGIN config (.the-loop/config.yaml), read only as a
# convenience fallback (ticketing.github) when the daemon happens to be
# started from within the one repo it watches.
_PLUGIN_CONFIG_PATH = Path(".the-loop/config.yaml")

_DEFAULTS = {
    "intervalSeconds": 60,
    "stateFile": ".the-loop/poll-state.json",
    "pidfile": ".the-loop/poll.pid",
}


def _load_polling_config() -> dict:
    """Best-effort read of ``polling`` from the CLI config (or ``{}``)."""
    return cli_config.load_cli_config(_CONFIG_PATH, strict=False).get("polling") or {}


def _load_plugin_config() -> dict:
    """Best-effort parse of the repo-local PLUGIN config (or ``{}``)."""
    return cli_config.load_cli_config(_PLUGIN_CONFIG_PATH, strict=False)


def _repos_from_ticketing() -> List[str]:
    """Fall back to ``ticketing.github`` (owner/repo) for a github source."""
    gh = (_load_plugin_config().get("ticketing") or {}).get("github") or {}
    owner, repo = gh.get("owner"), gh.get("repo")
    return [f"{owner}/{repo}"] if owner and repo else []


def _ticketing_owner() -> Optional[str]:
    gh = (_load_plugin_config().get("ticketing") or {}).get("github") or {}
    owner = gh.get("owner")
    return str(owner) if owner else None


def _build_dispatcher(routing_map: Optional[dict]):
    """Compose the same registry + adapters + dispatcher the receiver uses."""
    from ..harness import build_adapters
    from ..sessions import SessionRegistry
    from ..webhook.dispatcher import Dispatcher, RoutingConfig

    routing = RoutingConfig.from_mapping(routing_map or {})
    dispatcher = Dispatcher(
        registry=SessionRegistry(routing.registry_dir),
        adapters=build_adapters(routing.harness_args),
        config=routing,
    )
    return dispatcher, routing


@register
class PollCommand(Command):
    name = "poll"
    help = "Poll configured ticketing/PR sources and spawn/route harness sessions"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        defaults = {**_DEFAULTS, **_load_polling_config()}
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
            "--state-file",
            default=str(defaults["stateFile"]),
            help="Durable cross-poll comment-dedup state.",
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
        dispatcher, routing = _build_dispatcher(_load_config_defaults().get("routing"))

        # Rebuilds the mutable plan (providers + interval) from the config file.
        # Used once for the initial plan and again by the Reloader on each edit,
        # so a hot reload and a cold start go through exactly the same code.
        def build_plan() -> PollPlan:
            cfg = PollConfig.from_mapping(_load_polling_config())
            providers = [
                build_provider(
                    source,
                    default_label=routing.auto_execute_label,
                    fallback_repos=_repos_from_ticketing(),
                )
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
        missing += check_dependencies(routing.runner, routing.web_terminal.enabled)
        if missing:
            for line in missing:
                logger.error(line)
            return 1

        web_proc = None
        if routing.web_terminal.enabled:
            web_proc = start_web_terminal(routing.web_terminal)

        config = PollConfig.from_mapping(_load_polling_config())
        config.interval_seconds = args.interval  # flag overrides until a config edit
        config.state_file = args.state_file
        authorized = resolve_authorized_users(
            routing.authorized_users, _ticketing_owner()
        )
        if not authorized:
            logger.warning(
                "no authorizedUsers configured (and no ticketing.github.owner) — "
                "the poller will act on NO items or comments until you set "
                "webhooks.ghWebhook.routing.authorizedUsers (prompt-injection guard)"
            )
        poller = Poller(
            providers=plan.providers,
            registry=dispatcher.registry,
            dispatcher=dispatcher,
            config=config,
            state=PollState(config.state_file),
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
            "poll: %s every %ss (runner=%s, spawnOnUnmatched=%s)",
            "; ".join(p.describe() for p in providers),
            config.interval_seconds,
            routing.runner,
            routing.spawn_on_unmatched,
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
