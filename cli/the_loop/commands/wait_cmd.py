"""``the-loop wait`` — a session says what it waits for, and until when (issue-551).

A session that waits on something that is not a person — CI, another session,
a build it started — used to end its turn in silence, and nothing told the-loop
that the silence was meant. This verb records the wait as
``session.wait_declared``: the Stop gate then allows the one stop that ends the
turn, the status surfaces show the condition, and when the time is up the
watcher treats the session as idle again.

It is not a way to wait on a person. On a human-owned node it is refused; a
question goes through ``the-loop ask``.

**Routing** is ``the-loop ask``'s: through the control-plane service when one
answers (:func:`~the_loop.client.routing.harness_routed`), and a session the
daemon spawned never runs it in-process. The core function is
:func:`the_loop.core.stopcheck.declare_wait`; ``POST /api/v1/sessions/wait`` is
its binding.

Spec: docs/specs/issue-551/design.md § Interfaces.
"""

from __future__ import annotations

import argparse
import sys

from . import sessions_cmd
from .base import Command, register
from .. import eventlog, strings
from ..client.routing import harness_routed, service_error
from ..core import stopcheck
from ..durations import parse_duration


@register
class WaitCommand(Command):
    name = "wait"
    help = strings.t("cli.wait.help")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--work-item",
            required=True,
            help=strings.t("cli.wait.work-item.help"),
        )
        parser.add_argument(
            "--for",
            required=True,
            dest="condition",
            metavar="CONDITION",
            help=strings.t("cli.wait.for.help"),
        )
        parser.add_argument(
            "--until",
            required=True,
            metavar="DURATION",
            help=strings.t("cli.wait.until.help"),
        )

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("wait")
        foreign = sessions_cmd._foreign_work_item(args.work_item)
        if foreign:
            print(foreign, file=sys.stderr)
            return 2
        try:
            # Checked here too, so a mistake is named before anything is sent.
            condition = stopcheck.check_condition(args.condition)
            seconds = parse_duration(args.until)
            result = harness_routed(
                lambda c: c.post(
                    "/sessions/wait",
                    {
                        "ref": args.work_item,
                        "condition": condition,
                        "seconds": seconds,
                    },
                ),
                lambda: stopcheck.declare_wait(
                    args.work_item,
                    condition,
                    seconds,
                    config=sessions_cmd._cli_config(),
                ),
            )
        except Exception as exc:  # noqa: BLE001 — mapped, or re-raised below
            mapped = service_error(exc)
            if mapped is None:
                if not isinstance(exc, (ValueError, LookupError)):
                    raise
                code = 2 if isinstance(exc, ValueError) else 1
                mapped = (strings.t("cli.wait.run.error", exc=exc), code)
            print(mapped[0], file=sys.stderr)
            return mapped[1]
        return sessions_cmd._render(result)
