"""``the-loop start|stop|status|restart`` — the whole system's lifecycle (issue-228).

One vocabulary for "bring the-loop up/down": ``start`` reads the CLI config and
starts, detached, every service it enables — the control-plane service
(`service.enabled`, with the MCP layer mounted per `service.mcp.enabled`), the
webhook receiver (`webhooks.ghWebhook.enabled`) and the poller
(`polling.enabled`). ``stop`` stops whatever is running, regardless of flags.
``status`` reports both, exiting 0 only when every enabled service is up.
``restart`` composes stop → (optional CLI upgrade, the issue-152 planner) →
start, and is also reachable as ``POST /api/v1/restart``.

These are **bootstrap commands** — the decision-058 exception `service` already
holds: the process manager cannot route through the processes it manages, so
they execute :mod:`the_loop.core.lifecycle` in-process.

Spec: docs/specs/issue-228/design.md · Decision: 084
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .base import Command, register
from .. import cli_config, eventlog
from ..core import lifecycle
from ..poller.heartbeat import PollHeartbeat
from ..state import layout_from_config


def _load_config() -> dict:
    """The CLI config — refusing a present-but-broken one (design §Errors).

    A *missing* file is a legitimate fresh install and composes the defaults
    (service + MCP on, ingresses off). A file that exists but cannot be parsed,
    or predates a migration, raises: composing services against defaults the
    operator did not write is how a disabled webhook gets started.
    """
    path = cli_config.default_cli_config_path()
    if not path.is_file():
        return {}
    return cli_config.load_cli_config(path, strict=True)


def _config_or_error() -> Optional[dict]:
    try:
        return _load_config()
    except Exception as exc:  # noqa: BLE001 — every load failure renders the same way
        print(f"error: cannot load the CLI config: {exc}", file=sys.stderr)
        return None


def _print_rows(rows) -> None:
    if not rows:
        return
    width = max(len(row["service"]) for row in rows)
    for row in rows:
        flag = "enabled" if row["enabled"] else "disabled"
        print(
            f"{row['service'].ljust(width)}  {row['outcome']:<15} [{flag}]"
            + (f"  {row['detail']}" if row.get("detail") else "")
        )


def _print_standing(rows) -> None:
    """The standing sessions (issue-277), in their own section under the services.

    Their own section rather than more `services` rows, because they are not
    services: the `services` list keeps the exact shape every reader of it
    already expects, and a deployment that declares no standing session prints
    nothing extra.
    """
    if not rows:
        return
    print("standing sessions:")
    width = max(len(row["name"]) for row in rows)
    for row in rows:
        print(
            f"{row['name'].ljust(width)}  {row.get('outcome', ''):<15}"
            + (f"  {row['detail']}" if row.get("detail") else "")
        )


@register
class StartCommand(Command):
    name = "start"
    help = "Start every service the CLI config enables (service, webhook, poller)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass

    def run(self, args: argparse.Namespace) -> int:
        config = _config_or_error()
        if config is None:
            return 2
        eventlog.configure_from_file("cli")
        report = lifecycle.start_all(config)
        _print_rows(report["services"])
        _print_standing(report.get("standingSessions") or [])
        return 0 if report["ok"] else 1


@register
class StopCommand(Command):
    name = "stop"
    help = "Stop every running the-loop service (poller, webhook, service)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass

    def run(self, args: argparse.Namespace) -> int:
        config = _config_or_error()
        if config is None:
            return 2
        eventlog.configure_from_file("cli")
        report = lifecycle.stop_all(config)
        _print_rows(report["services"])
        _print_standing(report.get("standingSessions") or [])
        return 0 if report["ok"] else 1


@register
class StatusCommand(Command):
    name = "status"
    help = "Report each service's state; exit 0 iff every enabled one is running"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--format", choices=["text", "json"], default="text")

    def run(self, args: argparse.Namespace) -> int:
        config = _config_or_error()
        if config is None:
            return 2
        report = lifecycle.status_all(config)
        if args.format == "json":
            print(json.dumps(report, indent=2))
            return 0 if report["ok"] else 1
        for row in report["services"]:
            flag = "enabled" if row["enabled"] else "disabled"
            liveness = (
                f"running (pid {row['pid']})" if row["running"] else "not running"
            )
            if row.get("hosted"):
                liveness = f"running (hosted in the service, pid {row['pid']})"
            extra = ""
            if row["service"] == "service" and row["running"]:
                extra = f" — {row['url']}, {'healthy' if row['healthy'] else 'unresponsive'}"
                if not row["mcp"]["enabled"]:
                    extra += ", MCP disabled"
            print(f"{row['service']:<11} {liveness} [{flag}]{extra}")
            if row["service"] == "poller":
                # Progress beside liveness, the issue-191 enrichment: absent
                # heartbeat loses these lines, never the liveness answer.
                from ..poller import daemon as poller_daemon

                beat = PollHeartbeat.read(layout_from_config(config).poll_status)
                for line in poller_daemon.heartbeat_lines(beat, row["running"]):
                    print(f"            {line}")
        standing = report.get("standingSessions") or []
        if standing:
            print("standing sessions:")
            for row in standing:
                liveness = "running" if row.get("running") else "not running"
                where = (
                    "declared"
                    if row.get("declared")
                    else "recorded, no longer declared"
                )
                if row.get("declared") and not row.get("autoStart"):
                    where += ", not auto-started"
                print(f"{row['name']:<11} {liveness} [{where}]")
        return 0 if report["ok"] else 1


@register
class RestartCommand(Command):
    name = "restart"
    help = "Stop every running service, then start every enabled one"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--with-upgrade",
            action="store_true",
            help=(
                "Upgrade the-loop's CLI between stop and start (the issue-152 "
                "installer plan for the cli component). A failed upgrade is "
                "reported but never leaves the system down: the start half "
                "still runs on the current version."
            ),
        )

    def run(self, args: argparse.Namespace) -> int:
        config = _config_or_error()
        if config is None:
            return 2
        eventlog.configure_from_file("cli")
        print("stopping:")
        stop_report = lifecycle.stop_all(config)
        _print_rows(stop_report["services"])
        _print_standing(stop_report.get("standingSessions") or [])

        upgrade_ok = True
        if args.with_upgrade:
            upgrade_ok = self._upgrade()

        print("starting:")
        start_report = lifecycle.start_all(config)
        _print_rows(start_report["services"])
        _print_standing(start_report.get("standingSessions") or [])
        ok = stop_report["ok"] and start_report["ok"] and upgrade_ok
        eventlog.emit("restart.completed", ok=ok, withUpgrade=args.with_upgrade or None)
        return 0 if ok else 1

    @staticmethod
    def _upgrade() -> bool:
        """Upgrade the CLI distribution in place (R4.2/R4.3).

        CLI component only, deliberately (design D4): the plugin component
        edits harness settings files no service restart needs, and the narrow
        plan keeps the API-triggered path from touching Claude's config.
        """
        from .. import install as install_mod
        from .install_cmd import render_table

        print("upgrading the CLI:")
        try:
            steps = install_mod.plan(["cli"], upgrade=True)
            results = install_mod.execute(steps, dry_run=False)
        except Exception as exc:  # noqa: BLE001 — a failed upgrade must not stop the start half
            print(f"upgrade failed: {exc}", file=sys.stderr)
            return False
        print(render_table(results))
        return install_mod.exit_code(results) == 0
