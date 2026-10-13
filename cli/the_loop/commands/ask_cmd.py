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
from .. import eventlog
from ..client.routing import harness_routed, service_error
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
        parser.add_argument(
            "--summary",
            default="",
            help="A 2-3 sentence summary (what you decided, what you are least "
            "sure of) that leads the room's message instead of an excerpt "
            "(issue-393 R8). Optional; the question text is still recorded in full.",
        )
        parser.add_argument(
            "--default",
            default="",
            dest="default_answer",
            help="The affirmative answer to take if the human does not object "
            "(issue-393 R12.1) — e.g. 'Defaults are fine'. When set, the room's "
            "message offers a one-tap button that replies with this text.",
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
                ),
            )
        except Exception as exc:  # noqa: BLE001 — mapped, or re-raised below
            mapped = service_error(exc)
            if mapped is None:
                if not isinstance(exc, ValueError):
                    raise
                mapped = (f"error: {exc}", 2)
            print(mapped[0], file=sys.stderr)
            return mapped[1]
        return _render(result)
