"""``the-loop standing list|start|stop|restart|say`` — sessions with no work item.

A standing session (issue-277) is declared in the CLI config under
``standingSessions``, brought up by ``the-loop start``, and addressed **by
name**: it owns no ticket, so `the-loop sessions`' work-item vocabulary does not
reach it and neither does a GitHub event. This command is the operator's
terminal surface onto them — and, like every other routed command since
issue-161, a **renderer**: the work happens in :mod:`the_loop.core.standing`,
reached through the control-plane service.

``say`` is the one that matters day to day: it pastes a message straight into a
running session's TUI, which is how an operator talks to a session that has no
comment thread to answer on.

Spec: docs/specs/issue-277/design.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

from .base import Command, register
from .. import cli_config, eventlog
from ..client.routing import routed, service_error
from ..core import standing as core_standing


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


def _print_control(result: Dict[str, Any]) -> int:
    rows: List[Dict[str, Any]] = result.get("sessions") or []
    if not rows:
        print("(no standing sessions declared)", file=sys.stderr)
        return 0
    width = max(len(row["name"]) for row in rows)
    for row in rows:
        line = f"{row['name'].ljust(width)}  {row.get('outcome', ''):<15}"
        detail = row.get("detail")
        stream = sys.stderr if row.get("outcome") == "failed" else sys.stdout
        print(line + (f"  {detail}" if detail else ""), file=stream)
    return 0 if result.get("ok") else 1


@register
class StandingCommand(Command):
    name = "standing"
    help = "List and steer the standing sessions (sessions with no work item)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="_command", metavar="<action>")

        listing = sub.add_parser("list", help="Every declared or recorded session")
        listing.add_argument("--format", choices=["text", "json"], default="text")

        start = sub.add_parser("start", help="Start one session, or every declared one")
        start.add_argument("name", nargs="?", default="")

        stop = sub.add_parser("stop", help="Stop one session, or every recorded one")
        stop.add_argument("name", nargs="?", default="")

        restart = sub.add_parser("restart", help="Stop then start one session")
        restart.add_argument("name")

        say = sub.add_parser("say", help="Paste a message into a running session")
        say.add_argument("name")
        say.add_argument("--text", required=True, help="The message to deliver")
        say.add_argument(
            "--actor",
            default="",
            help=(
                "Who is speaking, recorded on the event for the audit trail. "
                "Never trusted as authentication."
            ),
        )

    def run(self, args: argparse.Namespace) -> int:
        action = getattr(args, "_command", None)
        if not action:
            print(
                "error: `the-loop standing` needs an action "
                "(list|start|stop|restart|say)",
                file=sys.stderr,
            )
            return 2
        eventlog.configure_from_file("cli")
        try:
            if action == "list":
                return self._list(args)
            if action == "say":
                return self._say(args)
            return self._control(args, action)
        except Exception as exc:  # noqa: BLE001 — mapped, or re-raised by _report
            return _report(exc)

    # -- actions ---------------------------------------------------------------

    def _list(self, args: argparse.Namespace) -> int:
        rows = routed(
            lambda connection: connection.get("/standing-sessions"),
            lambda: core_standing.list_standing(config=_cli_config()),
        )
        if args.format == "json":
            print(json.dumps(rows, indent=2))
            return 0
        if not rows:
            print("(no standing sessions declared)", file=sys.stderr)
            return 0
        table = [("Name", "Harness", "Tmux", "Declared", "Status", "Live", "Slack")]
        for row in rows:
            table.append(
                (
                    row["name"],
                    row["harness"] or "-",
                    row["tmuxTarget"],
                    "yes" if row["declared"] else "no",
                    row["status"],
                    "yes" if row["running"] else "no",
                    row["slackThread"] or "-",
                )
            )
        widths = [max(len(r[i]) for r in table) for i in range(len(table[0]))]
        for row in table:
            print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
        return 0

    def _control(self, args: argparse.Namespace, verb: str) -> int:
        name = getattr(args, "name", "")
        result = routed(
            lambda connection: connection.post(
                "/standing-sessions/control", {"name": name, "verb": verb}
            ),
            lambda: core_standing.control_standing(name, verb, config=_cli_config()),
        )
        return _print_control(result)

    def _say(self, args: argparse.Namespace) -> int:
        result = routed(
            lambda connection: connection.post(
                "/standing-sessions/say",
                {"name": args.name, "text": args.text, "actor": args.actor},
            ),
            lambda: core_standing.say_standing(
                args.name, args.text, actor=args.actor, config=_cli_config()
            ),
        )
        for message in result.get("messages") or []:
            stream = sys.stderr if message.get("stream") == "err" else sys.stdout
            print(message.get("text", ""), file=stream)
        return int(result.get("exitCode") or 0)
