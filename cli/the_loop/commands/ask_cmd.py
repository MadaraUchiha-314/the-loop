"""``the-loop ask`` — an agent's question, posted right and recorded (issue-208).

The interaction directive (issue-134) tells a spawned session to ask its
questions as comments on the work item — and, until this verb, to *post them
itself* with ``gh``, remembering the loop-prevention marker every single time.
A forgotten marker turns the agent's own question into an event that resumes
its own session (issue-104's bug, one lapse away); and because the post was
just a ``gh`` call, nothing in the-loop knew the session was now waiting.

``ask`` closes both holes: the marker is stamped centrally by
:func:`~the_loop.core.sessions.ask_session` (no agent memory involved), and the
wait becomes a first-class ``session.awaiting_input`` event — which is what
lights the dashboard's question card and the ``attention`` surface, and what
``POST /api/v1/sessions/reply`` answers.

**Routing** (issue-482): through the control-plane service when one answers —
its process holds the credentials, and a session the daemon spawned holds none —
via :func:`~the_loop.client.routing.harness_routed`. A daemon-spawned session with
no service fails with a message saying so; anywhere else (a cloud checkout with
no daemon, a person at a terminal) the verb still runs in-process, with a note,
because this is the escalation path and must keep working when nothing else is
running. Never an auto-started service. The core function stays in
:mod:`the_loop.core.sessions`; ``POST /api/v1/sessions/ask`` is its binding.

Spec: docs/specs/issue-208/design.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .base import Command, register
from .sessions_cmd import _cli_config, _render
from .. import eventlog, strings
from ..client.routing import harness_routed, service_error
from ..core import sessions as core_sessions
from ..durations import parse_duration


@register
class AskCommand(Command):
    name = "ask"
    help = strings.t("cli.ask.help")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--work-item",
            required=True,
            help=strings.t("cli.ask.work-item.help"),
        )
        text = parser.add_mutually_exclusive_group(required=True)
        text.add_argument(
            "--question",
            help=strings.t("cli.ask.question.help"),
        )
        text.add_argument(
            "--question-file",
            help=strings.t("cli.ask.question-file.help"),
        )
        parser.add_argument(
            "--summary",
            default="",
            help=strings.t("cli.ask.summary.help"),
        )
        parser.add_argument(
            "--default",
            default="",
            dest="default_answer",
            help=strings.t("cli.ask.default.help"),
        )
        parser.add_argument(
            "--after",
            default="",
            help=strings.t("cli.ask.after.help"),
        )

    def run(self, args: argparse.Namespace) -> int:
        after = None
        if args.after:
            # Refused here, before anything is read or sent (issue-551 R6.6). The
            # operator's minimum is the service's to apply: it holds the config.
            try:
                after = parse_duration(args.after)
                if not args.default_answer.strip():
                    raise ValueError(strings.t("core.sessions.ask.after-needs-default"))
            except ValueError as exc:
                print(strings.t("cli.ask.run.error", exc=exc), file=sys.stderr)
                return 2
        eventlog.configure_from_file("ask")
        if args.question_file:
            try:
                question = (
                    sys.stdin.read()
                    if args.question_file == "-"
                    else Path(args.question_file).read_text(encoding="utf-8")
                )
            except OSError as exc:
                print(
                    strings.t("cli.ask.run.cannot-read-the-question", exc=exc),
                    file=sys.stderr,
                )
                return 2
        else:
            question = args.question
        actor = core_sessions._local_actor()
        try:
            result = harness_routed(
                lambda c: c.post(
                    "/sessions/ask",
                    {
                        "ref": args.work_item,
                        "question": question,
                        "summary": args.summary,
                        "default": args.default_answer,
                        "defaultAfterSeconds": after,
                        "actor": actor,
                    },
                ),
                lambda: core_sessions.ask_session(
                    args.work_item,
                    question,
                    config=_cli_config(),
                    summary=args.summary,
                    default_answer=args.default_answer,
                    actor=actor,
                    default_after_seconds=after,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — mapped, or re-raised below
            mapped = service_error(exc)
            if mapped is None:
                if not isinstance(exc, ValueError):
                    raise
                mapped = (strings.t("cli.ask.run.error", exc=exc), 2)
            print(mapped[0], file=sys.stderr)
            return mapped[1]
        return _render(result)
