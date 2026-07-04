"""``the-loop sessions register|list|close`` — manage the session registry.

Links a work item (``github:<owner>/<repo>#<number>``) to a harness session so
the webhook receiver can route events to it. Harnesses register themselves
when they start working a ticket (Claude Code: ``$CLAUDE_SESSION_ID``; Cursor:
the chat id the agent was launched with) and close on finish.

Spec: docs/specs/issue-15/design.md §5 (requirement R2.2).
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

from .base import Command, register
from .gh_webhook import _load_config_defaults
from ..harness import ClaudeCodeAdapter, CursorAgentAdapter
from ..sessions import RegistryError, Session, SessionRegistry, WorkItemRef

logger = logging.getLogger("the-loop.sessions")

_HARNESS_BINARIES = {
    "claude": ClaudeCodeAdapter.default_binary,
    "cursor": CursorAgentAdapter.default_binary,
}


def _default_registry_dir() -> str:
    routing = _load_config_defaults().get("routing") or {}
    return str(routing.get("registryDir", ".the-loop/sessions"))


@register
class SessionsCommand(Command):
    name = "sessions"
    help = "Manage work-item ↔ harness-session registrations (webhook routing)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        registry_dir = _default_registry_dir()
        actions = parser.add_subparsers(dest="action", metavar="<action>")
        actions.required = True

        reg = actions.add_parser(
            "register", help="Register the session working a work item"
        )
        reg.add_argument(
            "--work-item",
            required=True,
            help="Work-item ref, e.g. github:OWNER/REPO#15",
        )
        reg.add_argument("--harness", required=True, choices=sorted(_HARNESS_BINARIES))
        reg.add_argument(
            "--harness-session-id",
            required=True,
            help="Claude session id ($CLAUDE_SESSION_ID) or Cursor chat id.",
        )
        reg.add_argument(
            "--cwd",
            default=".",
            help="Directory the session runs in (resume is scoped to it).",
        )
        reg.add_argument(
            "--force",
            action="store_true",
            help="Replace an existing active registration for this work item.",
        )
        reg.add_argument("--registry-dir", default=registry_dir)
        reg.set_defaults(_action=self._register)

        lst = actions.add_parser("list", help="List registered sessions")
        lst.add_argument("--status", choices=["active", "closed"])
        lst.add_argument("--format", choices=["table", "json"], default="table")
        lst.add_argument("--registry-dir", default=registry_dir)
        lst.set_defaults(_action=self._list)

        close = actions.add_parser("close", help="Close a work item's session")
        close.add_argument("--work-item", required=True)
        close.add_argument("--registry-dir", default=registry_dir)
        close.set_defaults(_action=self._close)

    def run(self, args: argparse.Namespace) -> int:
        return int(args._action(args) or 0)

    # -- actions -----------------------------------------------------------------

    def _register(self, args: argparse.Namespace) -> int:
        try:
            work_item = WorkItemRef.parse(args.work_item)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        binary = _HARNESS_BINARIES[args.harness]
        if shutil.which(binary) is None:
            # Registration still succeeds — dispatch will hard-error if the
            # binary is still missing when an event arrives.
            print(
                f"warning: harness CLI {binary!r} not found on PATH; events for "
                f"{work_item.ref} cannot be dispatched until it is installed",
                file=sys.stderr,
            )
        session = Session(
            work_item=work_item,
            harness=args.harness,
            harness_session_id=args.harness_session_id,
            cwd=str(Path(args.cwd).resolve()),
        )
        try:
            SessionRegistry(args.registry_dir).register(session, force=args.force)
        except RegistryError as exc:
            print(f"error: {exc} (pass --force to replace)", file=sys.stderr)
            return 1
        print(f"registered {work_item.ref} -> {args.harness}:{args.harness_session_id}")
        return 0

    def _list(self, args: argparse.Namespace) -> int:
        sessions = SessionRegistry(args.registry_dir).list_sessions(status=args.status)
        if args.format == "json":
            print(json.dumps([s.to_dict() for s in sessions]))
            return 0
        rows = [("Work item", "Harness", "Session id", "Status", "Last event")]
        for s in sessions:
            rows.append(
                (
                    s.work_item.ref,
                    s.harness,
                    s.harness_session_id,
                    s.status,
                    s.last_event_at or "-",
                )
            )
        widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
        for row in rows:
            print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
        if not sessions:
            print("(no registered sessions)", file=sys.stderr)
        return 0

    def _close(self, args: argparse.Namespace) -> int:
        try:
            work_item = WorkItemRef.parse(args.work_item)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if not SessionRegistry(args.registry_dir).close(work_item):
            print(f"no active session for {work_item.ref}", file=sys.stderr)
            return 1
        print(f"closed session for {work_item.ref}")
        return 0
