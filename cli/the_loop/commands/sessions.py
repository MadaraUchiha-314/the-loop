"""``the-loop sessions`` — see and manage everything the-loop is tracking.

Registration (issue-15) links a work item (``github:<owner>/<repo>#<number>``)
to a harness session so webhook/poll events route to it; harnesses register when
they start working a ticket (Claude Code: ``$CLAUDE_SESSION_ID``; Cursor: the
chat id) and close on finish.

Since issue-98 this is also the **operator's** surface over the daemon:

* ``list`` — one table of every tracked work item, joining the session registry,
  the poller's ledger and live tmux state, with links onward (ticket, terminal,
  PR);
* ``show`` — everything known about one work item;
* ``pause`` / ``resume`` — stop and restart the-loop acting on one work item,
  without ending its session; mirrored to the ``the-loop: paused`` GitHub label
  so the same control works from the browser;
* ``prune`` — drop session *records* the daemon has finished with.

Spec: docs/specs/issue-15/design.md §5 (requirement R2.2);
docs/specs/issue-98/design.md §6.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Callable, List, Optional

from .base import Command, register
from .gh_webhook import _load_config_defaults
from .. import cli_config, eventlog
from ..harness import ClaudeCodeAdapter, CursorAgentAdapter
from ..labels import GitHubLabeler
from ..runner import TmuxRunner
from ..sessions import (
    DEFAULT_PAUSE_FILE,
    DEFAULT_PAUSED_LABEL,
    PauseStore,
    RegistryError,
    Session,
    SessionRegistry,
    WorkItemRef,
)
from ..sessions.overview import (
    STATUSES,
    build_rows,
    render_detail,
    render_table,
)
from ..webhook.dispatcher import TmuxConfig

logger = logging.getLogger("the-loop.sessions")

_HARNESS_BINARIES = {
    "claude": ClaudeCodeAdapter.default_binary,
    "cursor": CursorAgentAdapter.default_binary,
}


def _routing() -> dict:
    return _load_config_defaults().get("routing") or {}


def _default_registry_dir() -> str:
    return str(_routing().get("registryDir", ".the-loop/sessions"))


def _default_pause_file() -> str:
    return str(_routing().get("pauseFile", DEFAULT_PAUSE_FILE))


def _default_paused_label() -> str:
    return str(_routing().get("pausedLabel", DEFAULT_PAUSED_LABEL))


def _default_poll_state_file() -> str:
    """``polling.stateFile`` — the poller's ledger, joined into ``list``."""
    polling = (
        cli_config.load_cli_config(
            cli_config.default_cli_config_path(), strict=False
        ).get("polling")
        or {}
    )
    return str(polling.get("stateFile", ".the-loop/poll-state.json"))


def _tmux_config() -> TmuxConfig:
    """``routing.tmux`` — retention/termination policy (issue-86, issue-94)."""
    return TmuxConfig.from_mapping(_routing().get("tmux") or {})


def _poll_state(path: str):
    """The poller's ledger, or ``None`` when there isn't one (never polled)."""
    from ..poller import PollState

    if not Path(path).is_file():
        return None
    return PollState(path)


def _parse_ref(value: str) -> Optional[WorkItemRef]:
    try:
        return WorkItemRef.parse(value)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


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
    ref = _parse_ref(work_item)
    if ref is None:
        return 2
    session = registry.find_by_work_item(ref, include_closed=True)
    if session is None:
        print(f"error: no session recorded for {ref.ref}", file=sys.stderr)
        return 1
    if session.status != "active":
        # The work item finished but its tmux session was retained (issue-86):
        # attaching is exactly how a human reads back what happened. It is a
        # *record*, so it is always attached read-only — a closed work item's
        # terminal must not take input (issue-94).
        read_only = True
        print(
            f"note: the session for {ref.ref} is closed; attaching read-only to "
            "its retained tmux session",
            file=sys.stderr,
        )
    if session.runner != "tmux":
        print(
            f"error: the session for {ref.ref} is a headless process session "
            "(runner=process) — there is no terminal to attach. Steer it via "
            "GitHub comments, or run it with routing.runner: tmux",
            file=sys.stderr,
        )
        return 1
    runner = TmuxRunner()
    if not runner.is_available():
        from ..runner import check_dependencies

        for line in check_dependencies("tmux", web_enabled=False):
            print(f"error: {line}", file=sys.stderr)
        return 1
    if not runner.has_session(session.tmux_target):
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
    help = "See and manage the work items the-loop is tracking (and their sessions)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        registry_dir = _default_registry_dir()
        pause_file = _default_pause_file()
        poll_state_file = _default_poll_state_file()
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

        lst = actions.add_parser(
            "list", help="Table of every tracked work item and its session"
        )
        lst.add_argument(
            "--status",
            choices=sorted(STATUSES),
            help="Show only rows in this state.",
        )
        lst.add_argument("--work-item", default="", help="Show only this work item.")
        lst.add_argument("--format", choices=["table", "json"], default="table")
        lst.add_argument("--registry-dir", default=registry_dir)
        lst.add_argument("--pause-file", default=pause_file)
        lst.add_argument(
            "--poll-state-file",
            default=poll_state_file,
            help="The poller's ledger, joined in so tracked-but-unspawned items show.",
        )
        lst.set_defaults(_action=self._list)

        show = actions.add_parser("show", help="Everything known about one work item")
        show.add_argument("--work-item", required=True)
        show.add_argument("--format", choices=["text", "json"], default="text")
        show.add_argument("--registry-dir", default=registry_dir)
        show.add_argument("--pause-file", default=pause_file)
        show.add_argument("--poll-state-file", default=poll_state_file)
        show.set_defaults(_action=self._show)

        pause = actions.add_parser(
            "pause",
            help="Stop the-loop acting on a work item (session and tmux untouched)",
        )
        pause.add_argument("--work-item", required=True)
        pause.add_argument(
            "--reason", default="", help="Recorded with the pause, shown in `show`."
        )
        pause.add_argument("--pause-file", default=pause_file)
        self._add_label_flags(pause)
        pause.set_defaults(_action=self._pause)

        resume = actions.add_parser(
            "resume", help="Undo a pause — the-loop picks the work item back up"
        )
        resume.add_argument("--work-item", required=True)
        resume.add_argument("--pause-file", default=pause_file)
        self._add_label_flags(resume)
        resume.set_defaults(_action=self._resume)

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
        tmux_fate = close.add_mutually_exclusive_group()
        tmux_fate.add_argument(
            "--keep-tmux",
            dest="keep_tmux",
            action="store_true",
            default=None,
            help=(
                "Keep the tmux session so its transcript stays readable; the "
                "harness inside it is still ended unless "
                "routing.tmux.killHarnessOnClose is false "
                "(default: routing.tmux.keepSessionOnClose)."
            ),
        )
        tmux_fate.add_argument(
            "--kill-tmux",
            dest="keep_tmux",
            action="store_false",
            help="Kill the tmux session along with the registry entry.",
        )
        close.set_defaults(_action=self._close)

        prune = actions.add_parser(
            "prune", help="Remove finished session records (never kills anything)"
        )
        prune.add_argument(
            "--include-retained",
            action="store_true",
            help=(
                "Also remove closed records whose tmux session is still up "
                "(that session is the retained transcript — it is NOT killed)."
            ),
        )
        prune.add_argument("--dry-run", action="store_true")
        prune.add_argument("--registry-dir", default=registry_dir)
        prune.set_defaults(_action=self._prune)

    @staticmethod
    def _add_label_flags(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--no-label",
            dest="label",
            action="store_false",
            default=True,
            help=(
                "Keep the change local — do not add/remove the "
                f"{_default_paused_label()!r} label on GitHub."
            ),
        )
        parser.add_argument("--gh-binary", default="gh")

    def run(self, args: argparse.Namespace) -> int:
        # register/close write session-lifecycle events via the registry.
        eventlog.configure_from_file("sessions")
        return int(args._action(args) or 0)

    # -- actions -----------------------------------------------------------------

    def _register(self, args: argparse.Namespace) -> int:
        work_item = _parse_ref(args.work_item)
        if work_item is None:
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

    def _rows(self, args: argparse.Namespace, work_item: str = ""):
        # getattr defaults: the row builder is also called from embeddings/tests
        # that hand in only the fields they care about.
        pause_file = getattr(args, "pause_file", "") or _default_pause_file()
        poll_state_file = (
            getattr(args, "poll_state_file", "") or _default_poll_state_file()
        )
        return build_rows(
            SessionRegistry(args.registry_dir),
            PauseStore(pause_file, paused_label=_default_paused_label()),
            poll_state=_poll_state(poll_state_file),
            status=getattr(args, "status", None),
            work_item=work_item or getattr(args, "work_item", ""),
        )

    def _list(self, args: argparse.Namespace) -> int:
        rows = self._rows(args)
        if args.format == "json":
            print(json.dumps([row.to_dict() for row in rows]))
            return 0
        print(render_table(rows))
        if not rows:
            print(
                "(nothing tracked — no registered sessions and no polled work items)",
                file=sys.stderr,
            )
        return 0

    def _show(self, args: argparse.Namespace) -> int:
        ref = _parse_ref(args.work_item)
        if ref is None:
            return 2
        rows = self._rows(args, work_item=ref.ref)
        if not rows:
            print(
                f"error: nothing recorded for {ref.ref} — it has no session, is "
                "not in the poller's ledger, and is not paused",
                file=sys.stderr,
            )
            return 1
        row = rows[0]
        if args.format == "json":
            print(json.dumps(row.to_dict(), indent=2))
            return 0
        print(render_detail(row))
        if not row.pause_sources:
            print(
                f"\nnote: a {_default_paused_label()!r} label on the ticket also "
                "pauses it; this view reads the local ledger only.",
                file=sys.stderr,
            )
        return 0

    def _pause(self, args: argparse.Namespace) -> int:
        work_item = _parse_ref(args.work_item)
        if work_item is None:
            return 2
        store = PauseStore(args.pause_file, paused_label=_default_paused_label())
        if store.pause(work_item, reason=args.reason):
            print(
                f"paused {work_item.ref}"
                + (f" ({args.reason})" if args.reason else "")
                + " — its session, tmux transcript and checkout are untouched"
            )
            eventlog.emit(
                "session.paused", work_item=work_item.ref, reason=args.reason or None
            )
        else:
            print(f"{work_item.ref} was already paused")
        return self._sync_label(args, work_item, remove=False)

    def _resume(self, args: argparse.Namespace) -> int:
        work_item = _parse_ref(args.work_item)
        if work_item is None:
            return 2
        store = PauseStore(args.pause_file, paused_label=_default_paused_label())
        if store.resume(work_item):
            print(f"resumed {work_item.ref} — the-loop will act on it again")
            eventlog.emit("session.resumed", work_item=work_item.ref)
        else:
            print(f"{work_item.ref} was not paused")
        return self._sync_label(args, work_item, remove=True)

    def _sync_label(
        self, args: argparse.Namespace, work_item: WorkItemRef, remove: bool
    ) -> int:
        """Mirror the local pause onto the ticket. Never fails the command (R5.4)."""
        if not args.label:
            return 0
        labeler = GitHubLabeler(gh_binary=args.gh_binary)
        label = _default_paused_label()
        result = (
            labeler.remove(work_item, label)
            if remove
            else labeler.add(work_item, label)
        )
        verb = "removed" if remove else "added"
        if result.ok:
            if result.changed:
                print(f"{verb} the {label!r} label on {work_item.ref}")
        else:
            gh_cmd = "--remove-label" if remove else "--add-label"
            print(
                f"note: could not {('remove' if remove else 'add')} the {label!r} "
                f"label on {work_item.ref} ({result.error}). The local pause "
                f"stands; set it by hand with: gh issue edit {work_item.number} "
                f"--repo {work_item.owner}/{work_item.repo} {gh_cmd} '{label}'",
                file=sys.stderr,
            )
        return 0

    def _attach(self, args: argparse.Namespace) -> int:
        return attach_session(
            SessionRegistry(args.registry_dir),
            args.work_item,
            read_only=args.read_only,
        )

    def _prune(self, args: argparse.Namespace) -> int:
        """Remove closed session *records*; never signal a process (R7.4)."""
        registry = SessionRegistry(args.registry_dir)
        tmux = TmuxRunner()
        tmux_ready = tmux.is_available()
        removed = kept = 0
        for session in registry.list_sessions():
            if session.status == "active":
                continue
            retained = (
                session.runner == "tmux"
                and session.tmux_target
                and tmux_ready
                and tmux.has_session(session.tmux_target)
            )
            if retained and not args.include_retained:
                kept += 1
                print(
                    f"kept {session.work_item.ref} — its tmux session "
                    f"{session.tmux_target} is still up (retained transcript; "
                    "pass --include-retained to drop the record anyway)"
                )
                continue
            if args.dry_run:
                print(f"would remove {session.work_item.ref}")
                removed += 1
                continue
            if registry.remove(session.work_item):
                print(f"removed {session.work_item.ref}")
                removed += 1
        verb = "would remove" if args.dry_run else "removed"
        print(f"{verb} {removed} record(s); kept {kept} retained")
        return 0

    def _close(self, args: argparse.Namespace) -> int:
        work_item = _parse_ref(args.work_item)
        if work_item is None:
            return 2
        registry = SessionRegistry(args.registry_dir)
        session = registry.find_by_work_item(work_item)
        if not registry.close(work_item):
            print(f"no active session for {work_item.ref}", file=sys.stderr)
            return 1
        if session is not None and session.runner == "tmux":
            tmux = _tmux_config()
            keep = (
                tmux.keep_session_on_close if args.keep_tmux is None else args.keep_tmux
            )
            if keep:
                # Same rule as an auto-close: retain the transcript, end the
                # conversation, so nothing can be typed into it (issue-94).
                if tmux.kill_harness_on_close:
                    result = TmuxRunner().terminate_harness(
                        session, grace=tmux.harness_kill_grace_seconds
                    )
                    if result.ok and not result.session_missing:
                        print(
                            f"ended the harness in tmux session {session.tmux_target}"
                        )
                    elif not result.ok:
                        print(f"note: {result.error}", file=sys.stderr)
                print(
                    f"kept tmux session {session.tmux_target} — attach: "
                    f"tmux attach -r -t {session.tmux_target} (pass --kill-tmux to "
                    "end it)"
                )
            else:
                result = TmuxRunner().kill(session)  # best-effort (R7.2/R7.3)
                if result.ok:
                    print(f"killed tmux session {session.tmux_target}")
                else:
                    print(f"note: tmux session {session.tmux_target} was already gone")
        print(f"closed session for {work_item.ref}")
        return 0
