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
from pathlib import Path
from typing import Any, Dict, List

from .base import Command, register
from .. import cli_config, eventlog, strings
from ..client.routing import routed, service_error
from ..core import standing as core_standing


def _cli_config() -> dict:
    return cli_config.load_cli_config(cli_config.default_cli_config_path())


def _report(exc: Exception) -> int:
    mapped = service_error(exc)
    if mapped is None:
        if isinstance(exc, ValueError):
            mapped = (strings.t("cli.standing.report.error", exc=exc), 2)
        elif isinstance(exc, LookupError):
            mapped = (strings.t("cli.standing.report.error", exc=exc), 1)
        else:
            raise exc
    message, code = mapped
    print(message, file=sys.stderr)
    return code


def _print_control(result: Dict[str, Any]) -> int:
    rows: List[Dict[str, Any]] = result.get("sessions") or []
    if not rows:
        print(
            strings.t("cli.standing.print-control.no-standing-sessions-declared"),
            file=sys.stderr,
        )
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
    help = strings.t("cli.standing.help")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="_command", metavar="<action>")

        listing = sub.add_parser("list", help=strings.t("cli.standing.list.help"))
        listing.add_argument("--format", choices=["text", "json"], default="text")

        create = sub.add_parser("create", help=strings.t("cli.standing.create.help"))
        create.add_argument("name")
        create.add_argument(
            "--harness", default="", help=strings.t("cli.standing.create.harness.help")
        )
        create.add_argument(
            "--cwd", default="", help=strings.t("cli.standing.create.cwd.help")
        )
        create.add_argument(
            "--prompt", default="", help=strings.t("cli.standing.create.prompt.help")
        )
        create.add_argument(
            "--prompt-file",
            default="",
            help=strings.t("cli.standing.create.prompt-file.help"),
        )
        create.add_argument("--description", default="")
        create.add_argument(
            "--harness-arg",
            action="append",
            default=None,
            dest="harness_args",
            help=strings.t("cli.standing.create.harness-arg.help"),
        )
        create.add_argument(
            "--slack",
            action="store_true",
            help=strings.t("cli.standing.create.slack.help"),
        )
        create.add_argument("--slack-channel", default="")
        create.add_argument(
            "--no-auto-start",
            action="store_true",
            help=strings.t("cli.standing.create.no-auto-start.help"),
        )
        create.add_argument(
            "--no-start",
            action="store_true",
            help=strings.t("cli.standing.create.no-start.help"),
        )

        delete = sub.add_parser(
            "delete",
            help=strings.t("cli.standing.delete.help"),
        )
        delete.add_argument("name")

        start = sub.add_parser("start", help=strings.t("cli.standing.start.help"))
        start.add_argument("name", nargs="?", default="")

        stop = sub.add_parser("stop", help=strings.t("cli.standing.stop.help"))
        stop.add_argument("name", nargs="?", default="")

        restart = sub.add_parser("restart", help=strings.t("cli.standing.restart.help"))
        restart.add_argument("name")

        say = sub.add_parser("say", help=strings.t("cli.standing.say.help"))
        say.add_argument("name")
        say.add_argument(
            "--text", required=True, help=strings.t("cli.standing.say.text.help")
        )
        say.add_argument(
            "--actor",
            default="",
            help=strings.t("cli.standing.say.actor.help"),
        )

    def run(self, args: argparse.Namespace) -> int:
        action = getattr(args, "_command", None)
        if not action:
            print(
                strings.t("cli.standing.run.the-loop-standing-needs-an"),
                file=sys.stderr,
            )
            return 2
        eventlog.configure_from_file("cli")
        try:
            if action == "list":
                return self._list(args)
            if action == "say":
                return self._say(args)
            if action == "create":
                return self._create(args)
            if action == "delete":
                return self._delete(args)
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
            print(
                strings.t("cli.standing.list.no-standing-sessions-declared"),
                file=sys.stderr,
            )
            return 0
        table = [
            (
                strings.t("cli.standing.list.table.header.name"),
                strings.t("cli.standing.list.table.header.harness"),
                strings.t("cli.standing.list.table.header.tmux"),
                strings.t("cli.standing.list.table.header.declared"),
                strings.t("cli.standing.list.table.header.status"),
                strings.t("cli.standing.list.table.header.live"),
                strings.t("cli.standing.list.table.header.slack"),
            )
        ]
        for row in rows:
            table.append(
                (
                    row["name"],
                    row["harness"] or "-",
                    row["tmuxTarget"],
                    strings.t("cli.standing.list.yes")
                    if row["declared"]
                    else strings.t("cli.standing.list.no"),
                    row["status"],
                    strings.t("cli.standing.list.yes")
                    if row["running"]
                    else strings.t("cli.standing.list.no"),
                    row["slackThread"] or "-",
                )
            )
        widths = [max(len(r[i]) for r in table) for i in range(len(table[0]))]
        for row in table:
            print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
        return 0

    def _create(self, args: argparse.Namespace) -> int:
        prompt = args.prompt
        if args.prompt_file:
            if prompt:
                print(
                    strings.t("cli.standing.create.pass-prompt-or-prompt-file"),
                    file=sys.stderr,
                )
                return 2
            try:
                prompt = Path(args.prompt_file).expanduser().read_text(encoding="utf-8")
            except OSError as exc:
                print(
                    strings.t(
                        "cli.standing.create.cannot-read",
                        prompt_file=args.prompt_file,
                        exc=exc,
                    ),
                    file=sys.stderr,
                )
                return 2
        body = {
            "name": args.name,
            "harness": args.harness,
            "cwd": args.cwd,
            "prompt": prompt,
            "description": args.description,
            "harnessArgs": args.harness_args,
            "slackEnabled": bool(args.slack),
            "slackChannel": args.slack_channel,
            "autoStart": not args.no_auto_start,
            "start": not args.no_start,
        }
        result = routed(
            lambda connection: connection.post("/standing-sessions/create", body),
            lambda: core_standing.create_standing(
                args.name,
                harness=args.harness,
                cwd=args.cwd,
                prompt=prompt,
                description=args.description,
                harness_args=args.harness_args,
                slack_enabled=bool(args.slack),
                slack_channel=args.slack_channel,
                auto_start=not args.no_auto_start,
                start=not args.no_start,
                config=_cli_config(),
            ),
        )
        return _print_control(result)

    def _delete(self, args: argparse.Namespace) -> int:
        result = routed(
            lambda connection: connection.post(
                "/standing-sessions/delete", {"name": args.name}
            ),
            lambda: core_standing.delete_standing(args.name, config=_cli_config()),
        )
        return _print_control(result)

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
