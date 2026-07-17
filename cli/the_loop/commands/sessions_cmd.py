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
import os
import shutil
import sys
from pathlib import Path
from typing import Callable, List

from .base import Command, register
from .gh_webhook import _load_config_defaults
from ..harness import ClaudeCodeAdapter, CursorAgentAdapter
from ..runner import TmuxRunner
from ..sessions import RegistryError, Session, SessionRegistry, WorkItemRef

logger = logging.getLogger("the-loop.sessions")

_HARNESS_BINARIES = {
    "claude": ClaudeCodeAdapter.default_binary,
    "cursor": CursorAgentAdapter.default_binary,
}


def _default_registry_dir() -> str:
    routing = _load_config_defaults().get("routing") or {}
    return str(routing.get("registryDir", ".the-loop/sessions"))


def _attach_argv(session: Session, read_only: bool) -> List[str]:
    argv = ["tmux", "attach-session"]
    if read_only:
        argv.append("-r")
    argv += ["-t", session.tmux_target]
    return argv


def attach_session(
    registry: SessionRegistry,
    work_item: str,
    read_only: bool = False,
    execvp: Callable = os.execvp,
) -> int:
    """Attach the caller's terminal to a tmux-mode session (R4.2/R4.3).

    ``execvp`` replaces this process with tmux on success (injectable for tests).
    """
    try:
        ref = WorkItemRef.parse(work_item)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    session = registry.find_by_work_item(ref)
    if session is None:
        print(f"error: no active session for {ref.ref}", file=sys.stderr)
        return 1
    if session.runner != "tmux":
        print(
            f"error: the session for {ref.ref} is a headless process session "
            "(runner=process) — there is no terminal to attach. Steer it via "
            "GitHub comments, or run it with routing.runner: tmux",
            file=sys.stderr,
        )
        return 1
    if not TmuxRunner().has_session(session.tmux_target):
        print(
            f"error: tmux session {session.tmux_target} not found (crashed or "
            "was killed) — check `the-loop sessions list` for live sessions",
            file=sys.stderr,
        )
        return 1
    argv = _attach_argv(session, read_only)
    execvp(argv[0], argv)
    return 0


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

        attach = actions.add_parser(
            "attach", help="Attach this terminal to a tmux-mode session"
        )
        attach.add_argument("--work-item", required=True)
        attach.add_argument(
            "--read-only",
            action="store_true",
            help="Observe without a keyboard (tmux attach -r).",
        )
        attach.add_argument("--registry-dir", default=registry_dir)
        attach.set_defaults(_action=self._attach)

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
        rows = [
            (
                "Work item",
                "Harness",
                "Session id",
                "Runner",
                "Tmux",
                "Status",
                "Last event",
            )
        ]
        for s in sessions:
            rows.append(
                (
                    s.work_item.ref,
                    s.harness,
                    s.harness_session_id,
                    s.runner,
                    s.tmux_target or "-",
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

    def _attach(self, args: argparse.Namespace) -> int:
        return attach_session(
            SessionRegistry(args.registry_dir),
            args.work_item,
            read_only=args.read_only,
        )

    def _close(self, args: argparse.Namespace) -> int:
        try:
            work_item = WorkItemRef.parse(args.work_item)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        registry = SessionRegistry(args.registry_dir)
        session = registry.find_by_work_item(work_item)
        if not registry.close(work_item):
            print(f"no active session for {work_item.ref}", file=sys.stderr)
            return 1
        if session is not None and session.runner == "tmux":
            result = TmuxRunner().kill(session)  # best-effort (R7.2/R7.3)
            if result.ok:
                print(f"killed tmux session {session.tmux_target}")
            else:
                print(f"note: tmux session {session.tmux_target} was already gone")
        print(f"closed session for {work_item.ref}")
        return 0
