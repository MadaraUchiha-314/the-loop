"""``the-loop service`` — control-plane service lifecycle (issue-161).

``service start|stop|status`` manage the API service process with the same
discipline as the other daemons (issue-159): the pidfile is the flock, start is
idempotent, stop signals and waits. This is a **bootstrap command** — it manages
the service process itself, so it is an exception to the service-only execution
rule (decision-058). Since issue-228 the mechanics live in
:mod:`the_loop.core.lifecycle` (shared with ``the-loop start|stop|restart``);
this command is the explicit, single-service form, and deliberately ignores
`service.enabled` — an operator typing the granular verb *is* the enablement.
"""

from __future__ import annotations

import argparse
import sys

from .base import Command, register
from .. import eventlog
from ..api.config import base_url, service_pidfile
from ..core import lifecycle
from ..runlock import RunLock


def _healthy(config: dict) -> bool:
    from .. import client

    return client.healthy(config)


@register
class ServiceCommand(Command):
    name = "service"
    help = "Run the control-plane API service (start | stop | status)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        actions = parser.add_subparsers(dest="action", metavar="<action>")
        actions.required = True
        start = actions.add_parser("start", help="Start the API service")
        start.set_defaults(_action=self._start)
        stop = actions.add_parser("stop", help="Stop a running API service")
        stop.add_argument(
            "--timeout",
            type=float,
            default=lifecycle.SERVICE_STOP_TIMEOUT_SECONDS,
            help="Seconds to wait for the service to exit (default: 30).",
        )
        stop.set_defaults(_action=self._stop)
        status = actions.add_parser("status", help="Report the service's state")
        status.set_defaults(_action=self._status)

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("service")
        return args._action(args)

    # -- verbs -----------------------------------------------------------------

    def _start(self, args: argparse.Namespace) -> int:
        outcome = lifecycle.start_service(_load_config())
        if outcome["running"]:
            print(f"service {outcome['detail']}")
            return 0
        print(f"error: service {outcome['detail']}", file=sys.stderr)
        return 1

    def _stop(self, args: argparse.Namespace) -> int:
        outcome = lifecycle.stop_service(_load_config(), timeout=args.timeout)
        if outcome["running"]:
            print(f"error: service {outcome['detail']}", file=sys.stderr)
            return 1
        print(
            f"service {outcome['detail']}"
            if outcome["stopped"]
            else "service is not running"
        )
        return 0

    def _status(self, args: argparse.Namespace) -> int:
        config = _load_config()
        lock = RunLock(service_pidfile(config), name="service")
        if lock.is_held():
            health = "healthy" if _healthy(config) else "unresponsive"
            print(f"running (pid {lock.holder()}, {base_url(config)}, {health})")
            return 0
        print("not running")
        return 0


def _load_config() -> dict:
    from ..cli_config import default_cli_config_path, load_cli_config

    try:
        return load_cli_config(default_cli_config_path())
    except Exception:
        return {}
