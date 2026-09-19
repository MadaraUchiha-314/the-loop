"""``the-loop add-channel`` / ``the-loop remove-channel`` (issue-375).

The terminal form of the two control keywords. Declares a **collaboration channel**
on one work item: from then on that work item's updates are posted in that channel,
and messages there from authorized users reach the work item instead of the central
channel's kickoff.

Two top-level commands rather than one with a verb argument, for
``add-collaborator``'s reason: the CLI and the keyword are deliberately the same
phrase, so the thread and the terminal read alike.

Deliberately **in-process**, not routed through the control-plane service — the same
exception class as ``the-loop ask`` and ``add-collaborator`` (decision-102): naming
a room is a small write on a tracked record plus a comment, and requiring a running
service for it would make it unfixable in exactly the situation an operator most
wants to fix it. The logic stays in :mod:`the_loop.core.workchannels`.

Spec: docs/specs/issue-375/design.md §4.
"""

from __future__ import annotations

import argparse
import sys

from .base import Command, register
from .sessions_cmd import _cli_config, _default_portable_dir, _render
from .. import eventlog
from ..control import ADD_CHANNEL, REMOVE_CHANNEL
from ..core import workchannels as core_workchannels
from ..workchannels import DEFAULT_LISTEN, LISTEN_MODES


class _ChannelCommand(Command):
    """Shared argument parsing and rendering for the two verbs."""

    verb: str = ""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "channels",
            nargs="+",
            metavar="TYPE@TARGET",
            help=(
                "Channel(s) to act on, e.g. slack@C0123ABCD (slack://C0123ABCD is "
                "the same thing). Slack takes a conversation id, not a #name."
            ),
        )
        parser.add_argument(
            "--work-item",
            required=True,
            help="The work item the channel is declared on, e.g. "
            "github:OWNER/REPO#375. A channel backs one work item at a time.",
        )
        parser.add_argument("--portable-dir", default=_default_portable_dir())
        parser.add_argument(
            "--comment",
            action=argparse.BooleanOptionalAction,
            default=True,
            help=(
                "Post the equivalent keyword comment on the work item so the thread "
                "records who declared what (default: on; best-effort)."
            ),
        )

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("workchannels")
        try:
            result = core_workchannels.manage_channels(
                args.work_item,
                self.verb,
                list(args.channels),
                comment=args.comment,
                config=_cli_config(),
                portable_dir=args.portable_dir,
                listen=getattr(args, "listen", DEFAULT_LISTEN),
            )
        except ValueError as exc:
            # A malformed channel ref, an unknown type, a work-item ref that will
            # not parse, or a channel another work item holds: the caller's to fix,
            # so exit 2 (argparse's own code) and change nothing at all.
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return _render(result)


@register
class AddChannelCommand(_ChannelCommand):
    name = "add-channel"
    verb = ADD_CHANNEL
    help = (
        "Declare a collaboration channel on one work item (its updates go there, "
        "and messages there reach it — when the-loop is mentioned, or all of them "
        "with --listen all)"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--listen",
            choices=LISTEN_MODES,
            default=DEFAULT_LISTEN,
            help=(
                "How the room listens (issue-389): 'mentions' — the-loop hears a "
                "message there only when it is addressed (default) — or 'all' — "
                "every message there is input. Re-declaring the room replaces the "
                "mode."
            ),
        )


@register
class RemoveChannelCommand(_ChannelCommand):
    name = "remove-channel"
    verb = REMOVE_CHANNEL
    help = "Undeclare a work item's collaboration channel"
