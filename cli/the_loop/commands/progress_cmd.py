"""``the-loop progress`` — a session's non-blocking status line (issue-340).

``ask`` is the only mid-flight signal a session has, and it blocks: the session
stops and waits for a human. ``progress`` is its opposite — the agent says where it
is and what is next, the verb returns at once, and the session keeps working. The
line becomes a ``session.progress`` event, heard by every channel that subscribes
to it (a Slack room edits one live line in place).

It is safe to call unconditionally. Only a work item carrying the progress label
(``progress.label``, default ``the-loop: progress``) emits anything; any other item
gets a one-line note and exit 0, and a report that arrives inside
``progress.minIntervalSeconds`` of the last is coalesced away with a note saying when
the next is welcome. See :mod:`the_loop.core.progress`.

**Routing** is ``ask``'s (issue-482): through the control-plane service when one
answers — its process holds the credentials the label read needs, and a session the
daemon spawned holds none — and in-process otherwise, with a note, never an
auto-started service.

Spec: docs/specs/issue-340/design.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .base import Command, register
from .sessions_cmd import _cli_config, _render
from .. import eventlog
from ..client.routing import harness_routed, service_error
from ..core import progress as core_progress
from ..core import sessions as core_sessions


@register
class ProgressCommand(Command):
    name = "progress"
    help = (
        "Tell the room where a long session is, without waiting for an answer "
        "(label-gated, rate-limited; recorded as session.progress)"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--work-item",
            required=True,
            help="Work-item ref the report is about, e.g. github:OWNER/REPO#15.",
        )
        text = parser.add_mutually_exclusive_group(required=True)
        text.add_argument(
            "--text",
            help="One or two lines: what is happening now, and what is next.",
        )
        text.add_argument(
            "--text-file",
            help="Read the report from this file ('-' = stdin).",
        )

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("progress")
        if args.text_file:
            try:
                text = (
                    sys.stdin.read()
                    if args.text_file == "-"
                    else Path(args.text_file).read_text(encoding="utf-8")
                )
            except OSError as exc:
                print(f"error: cannot read the report: {exc}", file=sys.stderr)
                return 2
        else:
            text = args.text
        actor = core_sessions._local_actor()
        try:
            result = harness_routed(
                lambda c: c.post(
                    "/sessions/progress",
                    {"ref": args.work_item, "text": text, "actor": actor},
                ),
                lambda: core_progress.progress_session(
                    args.work_item, text, config=_cli_config(), actor=actor
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
