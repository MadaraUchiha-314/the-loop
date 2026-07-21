"""``the-loop gh-poll start|stop`` — poll GitHub and spawn/route harness sessions.

A pull-based sibling of ``gh-webhook`` for machines a webhook cannot reach
(issue-34). ``start`` discovers issues/PRs carrying the auto-execute label via
``gh`` and drives them through the *same* router/dispatcher/registry the webhook
receiver uses, so sessions spawn and events route identically (including the
tmux runner). Poll-ingress defaults come from ``polling.ghPoll``; dispatch
behaviour is reused from ``webhooks.ghWebhook.routing``. Flags always win.

Spec: docs/specs/issue-34/design.md.
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
from .gh_webhook import _load_config_defaults
from ..poller import GhClient, PollConfig, Poller, PollState, check_gh_dependency

logger = logging.getLogger("the-loop.gh-poll")

_DEFAULTS = {
    "intervalSeconds": 60,
    "stateFile": ".the-loop/poll-state.json",
    "pidfile": ".the-loop/gh-poll.pid",
    "ghBinary": "gh",
}


def _load_full_config() -> dict:
    """Best-effort parse of the whole ``.the-loop/config.yaml`` (or ``{}``)."""
    cfg_path = Path(".the-loop/config.yaml")
    if not cfg_path.is_file():
        return {}
    try:
        import yaml  # optional dependency
    except ImportError:
        logger.debug("pyyaml not installed; skipping config-file defaults")
        return {}
    try:
        return yaml.safe_load(cfg_path.read_text()) or {}
    except Exception:  # noqa: BLE001
        logger.warning("could not parse %s; using built-in defaults", cfg_path)
        return {}


def _load_poll_defaults() -> dict:
    return ((_load_full_config().get("polling") or {}).get("ghPoll")) or {}


def _repos_from_ticketing() -> list:
    """Fall back to ``ticketing.github`` (owner/repo) when no repos configured."""
    gh = (_load_full_config().get("ticketing") or {}).get("github") or {}
    owner, repo = gh.get("owner"), gh.get("repo")
    return [f"{owner}/{repo}"] if owner and repo else []


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
class GhPollCommand(Command):
    name = "gh-poll"
    help = "Poll GitHub for labelled issues/PRs and spawn/route harness sessions"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        defaults = {**_DEFAULTS, **_load_poll_defaults()}
        monitor = defaults.get("monitor") or {}
        actions = parser.add_subparsers(dest="action", metavar="<action>")
        actions.required = True

        start = actions.add_parser("start", help="Start polling GitHub")
        start.add_argument(
            "--interval",
            type=int,
            default=int(defaults["intervalSeconds"]),
            help="Seconds between poll cycles (default: polling.ghPoll.intervalSeconds).",
        )
        start.add_argument(
            "--once",
            action="store_true",
            help="Run a single poll cycle and exit (useful under cron/systemd).",
        )
        start.add_argument(
            "--repo",
            action="append",
            default=None,
            metavar="OWNER/REPO",
            help="Repo to poll (repeatable). Default: polling.ghPoll.repos, "
            "else ticketing.github.",
        )
        start.add_argument(
            "--label",
            default=str(defaults.get("label", "")),
            help="Label gating what is polled (default: the routing autoExecuteLabel).",
        )
        start.add_argument(
            "--issues",
            action=argparse.BooleanOptionalAction,
            default=bool(monitor.get("issues", True)),
            help="Poll issues (default: polling.ghPoll.monitor.issues).",
        )
        start.add_argument(
            "--prs",
            action=argparse.BooleanOptionalAction,
            default=bool(monitor.get("pullRequests", True)),
            help="Poll pull requests (default: polling.ghPoll.monitor.pullRequests).",
        )
        start.add_argument(
            "--state-file",
            default=str(defaults["stateFile"]),
            help="Durable cross-poll comment-dedup state.",
        )
        start.add_argument(
            "--gh-binary",
            default=str(defaults["ghBinary"]),
            help="Path/name of the gh CLI.",
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
        poll_defaults = _load_poll_defaults()
        config = PollConfig.from_mapping(poll_defaults)
        config.interval_seconds = args.interval
        config.monitor_issues = args.issues
        config.monitor_prs = args.prs
        config.state_file = args.state_file
        config.gh_binary = args.gh_binary
        if args.label:
            config.label = args.label
        config.repos = args.repo or config.repos or _repos_from_ticketing()
        if not config.repos:
            logger.error(
                "no repositories to poll — pass --repo OWNER/REPO, set "
                "polling.ghPoll.repos, or configure ticketing.github"
            )
            return 1

        missing = check_gh_dependency(config.gh_binary)
        if missing:
            for line in missing:
                logger.error(line)
            return 1

        dispatcher, routing = _build_dispatcher(_load_config_defaults().get("routing"))
        poller = Poller(
            gh=GhClient(binary=config.gh_binary),
            registry=dispatcher.registry,
            dispatcher=dispatcher,
            config=config,
            auto_execute_label=routing.auto_execute_label,
            state=PollState(config.state_file),
        )

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
            "gh-poll polling %s every %ss (label=%r, runner=%s, spawnOnUnmatched=%s)",
            ", ".join(config.repos),
            config.interval_seconds,
            poller.label,
            routing.runner,
            routing.spawn_on_unmatched,
        )
        try:
            poller.run(once=args.once, stop_event=stop_event)
        finally:
            dispatcher.stop()
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
        print(f"sent SIGTERM to gh-poll poller (pid {pid})")
        return 0
