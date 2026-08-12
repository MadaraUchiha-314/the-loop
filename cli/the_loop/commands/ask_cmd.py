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

Deliberately **in-process**, not routed through the control-plane service (the
same exception class as ``sessions attach``/``reset``): this is the escalation
path, the one verb that must keep working when no service is running, when the
daemon is half-configured, or in a cloud session that has no daemon at all.
The core function stays in :mod:`the_loop.core.sessions`, so a route or MCP
tool later is a binding, not a port.

Spec: docs/specs/issue-208/design.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .base import Command, register
from .sessions_cmd import _cli_config, _render
from .. import eventlog
from ..core import sessions as core_sessions


@register
class AskCommand(Command):
    name = "ask"
    help = (
        "Ask a human a question on the work item (marker stamped centrally; "
        "the wait is recorded as session.awaiting_input)"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--work-item",
            required=True,
            help="Work-item ref the question goes to, e.g. github:OWNER/REPO#15 "
            "(the issues endpoint serves PR conversations too).",
        )
        text = parser.add_mutually_exclusive_group(required=True)
        text.add_argument(
            "--question",
            help="The question text (markdown).",
        )
        text.add_argument(
            "--question-file",
            help="Read the question from this file ('-' = stdin) — where "
            "multi-line markdown goes to survive shell quoting.",
        )

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("ask")
        if args.question_file:
            try:
                question = (
                    sys.stdin.read()
                    if args.question_file == "-"
                    else Path(args.question_file).read_text(encoding="utf-8")
                )
            except OSError as exc:
                print(f"error: cannot read the question: {exc}", file=sys.stderr)
                return 2
        else:
            question = args.question
        try:
            result = core_sessions.ask_session(
                args.work_item, question, config=_cli_config()
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return _render(result)
