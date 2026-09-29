"""``the-loop instances list|register|unregister`` — the fleet a manager serves.

A **manager** (issue-374, ``instance.role: manager``) keeps everything a worker does and
also serves the instances registered under ``instance.manager.instances`` through the
same ``/api/v1``. This command is the operator's terminal surface onto that registry —
and, like every routed command since issue-161, a **renderer**: the work happens in
:mod:`the_loop.core.instances`, reached through the control-plane service.

``register`` and ``unregister`` are config writes through the splice ``POST
/api/v1/config`` uses (decision-138 D4), so this command, the dashboard's Instances tab,
the API and a hand edit converge on one key in one file. ``list`` answers on every
role — a worker lists itself — so the same command reads a fleet or a lone instance.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

from .base import Command, register
from .. import cli_config, eventlog
from ..client.routing import routed, service_error
from ..core import instances as core_instances


def _cli_config() -> dict:
    return cli_config.load_cli_config(cli_config.default_cli_config_path())


def _report(exc: Exception) -> int:
    mapped = service_error(exc)
    if mapped is None:
        if isinstance(exc, ValueError):
            mapped = (f"error: {exc}", 2)
        elif isinstance(exc, LookupError):
            mapped = (f"error: {exc}", 1)
        else:
            raise exc
    message, code = mapped
    print(message, file=sys.stderr)
    return code


def instance_lines(doc: Dict[str, Any]) -> List[str]:
    """The rows as ``status`` and ``list`` print them, from the served document.

    One renderer for both commands, so the two cannot disagree about a state's
    spelling. The first row is this instance and says so; a row that is not live
    prints its ``detail`` where the counts would be.
    """
    rows = doc.get("instances") or []
    if not rows:
        return []
    table = [("name", "url", "state", "version", "mode", "managed", "sessions", "")]
    own = doc.get("name") or ""
    for index, row in enumerate(rows):
        live = row.get("state") == "live"
        note = "(this instance)" if index == 0 and row.get("name") == own else ""
        if not live:
            note = str(row.get("detail") or "")
        table.append(
            (
                str(row.get("name") or "(unnamed)"),
                str(row.get("url") or ""),
                str(row.get("state") or ""),
                str(row.get("version") or "") if live else "—",
                str(row.get("mode") or "") if live else "—",
                str(row.get("managedCount", "")) if live else "—",
                str(row.get("sessionCount", "")) if live else "—",
                note,
            )
        )
    widths = [max(len(r[i]) for r in table) for i in range(len(table[0]))]
    return [
        "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
        for row in table
    ]


@register
class InstancesCommand(Command):
    name = "instances"
    help = "List the fleet a manager serves, and register or unregister an instance"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="_command", metavar="<action>")
        listing = sub.add_parser("list", help="Every instance, this one first")
        listing.add_argument("--format", choices=["text", "json"], default="text")
        reg = sub.add_parser(
            "register", help="Add an instance to this manager's registry"
        )
        reg.add_argument("name", help="The member's own instance.name")
        reg.add_argument("url", help="Its service address, as this manager reaches it")
        unreg = sub.add_parser(
            "unregister", help="Remove an instance from this manager's registry"
        )
        unreg.add_argument("name")

    def run(self, args: argparse.Namespace) -> int:
        action = getattr(args, "_command", None)
        if not action:
            print(
                "error: `the-loop instances` needs an action (list|register|unregister)",
                file=sys.stderr,
            )
            return 2
        eventlog.configure_from_file("cli")
        try:
            if action == "list":
                return self._list(args)
            if action == "register":
                return self._register(args)
            return self._unregister(args)
        except Exception as exc:  # noqa: BLE001 — mapped, or re-raised by _report
            return _report(exc)

    def _list(self, args: argparse.Namespace) -> int:
        doc = routed(
            lambda connection: connection.get("/instances"),
            lambda: core_instances.list_instances(_cli_config()),
        )
        if args.format == "json":
            print(json.dumps(doc, indent=2))
            return 0
        for line in instance_lines(doc):
            print(line)
        return 0

    def _register(self, args: argparse.Namespace) -> int:
        config = _cli_config()
        result = routed(
            lambda connection: connection.post(
                "/instances/register", {"name": args.name, "url": args.url}
            ),
            lambda: core_instances.register_instance(
                config, args.name, args.url, config_path=cli_config.default_cli_config_path()
            ),
        )
        print(f"registered {result.get('instance') or args.name} in {result.get('path')}")
        return 0

    def _unregister(self, args: argparse.Namespace) -> int:
        config = _cli_config()
        result = routed(
            lambda connection: connection.post(
                "/instances/unregister", {"name": args.name}
            ),
            lambda: core_instances.unregister_instance(
                config, args.name, config_path=cli_config.default_cli_config_path()
            ),
        )
        print(f"unregistered {result.get('instance') or args.name} from {result.get('path')}")
        return 0
