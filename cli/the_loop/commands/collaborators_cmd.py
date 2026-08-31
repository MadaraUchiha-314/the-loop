"""``the-loop add-collaborator`` / ``the-loop remove-collaborator`` (issue-307).

The terminal form of the two control keywords. Grants a GitHub login **work-item
collaborator** status on one work item: from then on that login's comments on it —
and on the pull requests routed to its session — reach the session as agent input.
That is the whole grant. A collaborator cannot issue a control command, cannot arm
or spawn a session, and cannot satisfy a human gate; all three keep reading
``routing.authorizedUsers`` alone.

Two top-level commands rather than one with a verb argument, because the issue asks
for exactly the words an authorized user types on the ticket — the CLI and the
keyword are deliberately the same phrase, so the thread and the terminal read alike.

Deliberately **in-process**, not routed through the control-plane service — the same
exception class as ``the-loop ask`` and ``sessions attach``/``reset``: a roster is a
small write on a tracked record plus a comment, and requiring a running service for
it would make the roster unfixable in exactly the situation an operator most wants
to fix it (decision-102). The logic stays in :mod:`the_loop.core.collaborators`, so
a route or MCP tool later is a binding, not a port.

Spec: docs/specs/issue-307/design.md §5.
"""

from __future__ import annotations

import argparse
import sys

from .base import Command, register
from .sessions_cmd import _cli_config, _default_portable_dir, _render
from .. import eventlog
from ..control import ADD_COLLABORATOR, REMOVE_COLLABORATOR
from ..core import collaborators as core_collaborators


class _CollaboratorCommand(Command):
    """Shared argument parsing and rendering for the two verbs."""

    verb: str = ""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "logins",
            nargs="+",
            metavar="@LOGIN",
            help="GitHub login(s) to act on, with or without the leading @.",
        )
        parser.add_argument(
            "--work-item",
            required=True,
            help="The work item the grant is scoped to, e.g. github:OWNER/REPO#15. "
            "A grant covers this work item only — the same person on another item "
            "needs another grant.",
        )
        parser.add_argument("--portable-dir", default=_default_portable_dir())
        parser.add_argument(
            "--comment",
            action=argparse.BooleanOptionalAction,
            default=True,
            help=(
                "Post the equivalent keyword comment on the work item so the thread "
                "records who granted what (default: on; best-effort)."
            ),
        )

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("collaborators")
        try:
            result = core_collaborators.manage_collaborators(
                args.work_item,
                self.verb,
                list(args.logins),
                comment=args.comment,
                config=_cli_config(),
                portable_dir=args.portable_dir,
            )
        except ValueError as exc:
            # A malformed login or work-item ref: the caller's mistake, so exit 2
            # (argparse's own code) and change nothing at all.
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return _render(result)


@register
class AddCollaboratorCommand(_CollaboratorCommand):
    name = "add-collaborator"
    verb = ADD_COLLABORATOR
    help = (
        "Grant a GitHub login work-item collaborator status on one work item "
        "(their comments become input for its session — nothing more)"
    )


@register
class RemoveCollaboratorCommand(_CollaboratorCommand):
    name = "remove-collaborator"
    verb = REMOVE_COLLABORATOR
    help = "Revoke a work-item collaborator's grant"
