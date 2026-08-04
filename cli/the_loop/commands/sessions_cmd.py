"""``the-loop sessions register|list|start|pause|resume|stop|attach|close|reset``.

Links a work item (``github:<owner>/<repo>#<number>``) to a harness session so
the webhook receiver can route events to it. Harnesses register themselves
when they start working a ticket (Claude Code: ``$CLAUDE_SESSION_ID``; Cursor:
the chat id the agent was launched with) and close on finish.

Since issue-106 it is also the **operator's** control surface: someone with
shell access to the machine running the-loop can `start`, `pause`, `resume` or
`stop` a work item's execution — the same four commands an authorized user
issues by keyword in a comment — and each one posts that same keyword back to
the work item, so the ticket stays the full record of who asked for what. Those
comments carry the loop-prevention marker: the action has already been applied
locally, and the daemon must not read it back and re-apply it.

Since issue-137 it also carries the one action that **removes** rather than
transitions: `reset` forgets everything this machine holds about a work item —
its session record, its control and poll sections, its checkout — so an item
mid-flight when the CLI was fixed starts over on the new code. It posts nothing
to the ticket: there is no `reset` keyword, deliberately (decision-050).

Spec: docs/specs/issue-15/design.md §5 (requirement R2.2);
docs/specs/issue-106/design.md §6; docs/specs/issue-137/design.md.
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .base import Command, register
from .gh_webhook import _load_config_defaults, _state_layout
from .poll import _build_dispatcher
from .. import eventlog
from ..comments import post_issue_comment
from ..control import (
    PAUSE,
    RESUME,
    START,
    STOP,
    ControlConfig,
    ControlStore,
    command_comment,
)
from ..harness import ClaudeCodeAdapter, CursorAgentAdapter
from ..reset import WORKSPACE, reset_work_item, work_items_with_state
from ..runner import TmuxRunner
from ..sessions import RegistryError, Session, SessionRegistry, WorkItemRef
from ..state import legacy_layout
from ..webhook.dispatcher import RoutingConfig, TmuxConfig
from ..webhook.router import RoutedEvent

logger = logging.getLogger("the-loop.sessions")

_HARNESS_BINARIES = {
    "claude": ClaudeCodeAdapter.default_binary,
    "cursor": CursorAgentAdapter.default_binary,
}


def _routing_config() -> RoutingConfig:
    """The same ``routing`` config the daemon runs on (path defaults included)."""
    return RoutingConfig.from_mapping(
        _load_config_defaults().get("routing") or {}, _state_layout()
    )


def _default_registry_dir() -> str:
    routing = _load_config_defaults().get("routing") or {}
    return str(routing.get("registryDir") or _state_layout().local_dir)


def _default_portable_dir() -> str:
    return _state_layout().portable_dir


def _control_store(args: argparse.Namespace) -> ControlStore:
    """The portable half of the state, wherever `state.root` points (issue-128).

    Deliberately not derived from ``--registry-dir``: that flag moves the
    machine-local session handles, and a control record is not one of those —
    it is a fact about the work item. ``--portable-dir`` moves this half.
    """
    layout = _state_layout()
    root = getattr(args, "portable_dir", "") or layout.portable_dir
    return ControlStore(root, legacy=legacy_layout(layout))


def _control_config() -> ControlConfig:
    """``routing.control`` — the keyword vocabulary (issue-106)."""
    routing = _load_config_defaults().get("routing") or {}
    return ControlConfig.from_mapping(routing.get("control") or {})


def _dispatcher_for(args: argparse.Namespace):
    """The daemon's dispatcher, pointed at the registry this invocation names.

    ``--registry-dir`` defaults to the configured one, so this is normally a
    no-op — but when an operator points the CLI at another registry, the close
    and the spawn must land in *that* one, not in the config's.
    """
    routing = dict(_load_config_defaults().get("routing") or {})
    routing["registryDir"] = args.registry_dir
    dispatcher, config = _build_dispatcher(routing, _state_layout())
    # Same reasoning for the portable half: a spawn started from the CLI must
    # record its control state where this invocation is looking (issue-128).
    dispatcher.control_store = _control_store(args)
    return dispatcher, config


def _running_receiver_pid() -> Optional[int]:
    """The receiver's pid when its pidfile names a process that is alive.

    A liveness probe, not a signal: ``os.kill(pid, 0)`` delivers nothing. A
    ``PermissionError`` means the process exists under another user, which
    counts as running — the warning is about a daemon holding state, and whose
    daemon it is does not change that (issue-137, R5.1).
    """
    try:
        pid = int(Path(_state_layout().pidfile).read_text().strip())
    except (OSError, ValueError):
        return None
    if pid <= 0:
        # A corrupt pidfile, not a process: 0 and negatives address process
        # *groups*, and this probe must never widen beyond one pid.
        return None
    try:
        os.kill(pid, 0)
    except PermissionError:
        return pid
    except OSError:  # ProcessLookupError (stale pidfile) and anything else
        return None
    return pid


class _LazyCloser:
    """Ends live sessions through the daemon's dispatcher, built on first use.

    A reset that finds no live session must not pay for a dispatcher — building
    one resolves the workspace, the harness trust config and the runner — and,
    more to the point, must not *fail* because one could not be built. So it is
    constructed at the first live session and stopped once at the end.
    """

    def __init__(self, args: argparse.Namespace):
        self._args = args
        self._dispatcher = None

    def __call__(self, session: Session) -> bool:
        if self._dispatcher is None:
            self._dispatcher, _ = _dispatcher_for(self._args)
        return bool(
            self._dispatcher.close_session(session, reason="reset from the CLI")
        )

    def stop(self) -> None:
        if self._dispatcher is not None:
            self._dispatcher.stop(timeout=5)


def _local_actor() -> str:
    """Who ran the CLI — recorded and shown on the ticket, never trusted as auth.

    Local shell access *is* the authorization here (there is no allowlist to
    check against on this side); the name is for the audit trail.
    """
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 — no controlling user (container/cron)
        return ""


def _tmux_config() -> TmuxConfig:
    """``routing.tmux`` — retention/termination policy (issue-86, issue-94)."""
    routing = _load_config_defaults().get("routing") or {}
    return TmuxConfig.from_mapping(routing.get("tmux") or {})


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
    help = "Manage work-item ↔ harness-session registrations (webhook routing)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        registry_dir = _default_registry_dir()
        portable_dir = _default_portable_dir()
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
        reg.add_argument("--portable-dir", default=portable_dir)
        reg.set_defaults(_action=self._register)

        lst = actions.add_parser("list", help="List registered sessions")
        lst.add_argument("--status", choices=["active", "paused", "closed"])
        lst.add_argument("--format", choices=["table", "json"], default="table")
        lst.add_argument("--registry-dir", default=registry_dir)
        lst.add_argument("--portable-dir", default=portable_dir)
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
        attach.add_argument("--portable-dir", default=portable_dir)
        attach.set_defaults(_action=self._attach)

        # -- execution control (issue-106) --------------------------------------
        # The same four commands an authorized user issues by keyword, from the
        # machine running the-loop. Each posts its keyword back to the ticket.
        control_help = {
            START: (
                "Start execution for a work item (spawns a session, or resumes "
                "a paused one)"
            ),
            PAUSE: "Pause delivery to a work item's session (it keeps its state)",
            RESUME: "Resume delivery to a paused session",
            STOP: "Stop execution: close the session and end its harness",
        }
        for command in (START, PAUSE, RESUME, STOP):
            sub = actions.add_parser(command, help=control_help[command])
            sub.add_argument("--work-item", required=True)
            sub.add_argument("--registry-dir", default=registry_dir)
            sub.add_argument("--portable-dir", default=portable_dir)
            sub.add_argument(
                "--comment",
                action=argparse.BooleanOptionalAction,
                default=True,
                help=(
                    "Post the equivalent keyword comment on the work item so the "
                    "thread records this action (default: on; best-effort)."
                ),
            )
            sub.set_defaults(_action=self._control, _command=command)

        # -- reset (issue-137) --------------------------------------------------
        # The one action that removes rather than transitions: everything this
        # machine remembers about a work item goes, so it starts over on the
        # code the operator has just fixed.
        reset = actions.add_parser(
            "reset",
            help=(
                "Forget this machine's state for a work item (session record, "
                "control + poll sections) so it starts from scratch"
            ),
        )
        reset.add_argument(
            "--work-item",
            action="append",
            metavar="REF",
            help="Which work item to reset. Repeatable.",
        )
        reset.add_argument(
            "--all",
            dest="all_items",
            action="store_true",
            help=(
                "Reset every work item this machine holds state for. Must be "
                "asked for explicitly — a bare `reset` never means this."
            ),
        )
        reset.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be removed, and change nothing.",
        )
        reset.add_argument("--registry-dir", default=registry_dir)
        reset.add_argument("--portable-dir", default=portable_dir)
        reset.set_defaults(_action=self._reset)

        close = actions.add_parser("close", help="Close a work item's session")
        close.add_argument("--work-item", required=True)
        close.add_argument("--registry-dir", default=registry_dir)
        close.add_argument("--portable-dir", default=portable_dir)
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

    def run(self, args: argparse.Namespace) -> int:
        # register/close write session-lifecycle events via the registry.
        eventlog.configure_from_file("sessions")
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
        store = _control_store(args)

        def control_of(session: Session) -> str:
            record = store.get(session.work_item)
            return f"{record.command} ({record.source})" if record else "-"

        if args.format == "json":
            print(
                json.dumps(
                    [
                        {
                            **s.to_dict(),
                            "control": (
                                record.to_dict()
                                if (record := store.get(s.work_item))
                                else None
                            ),
                        }
                        for s in sessions
                    ]
                )
            )
            return 0
        rows = [
            (
                "Work item",
                "Harness",
                "Session id",
                "Runner",
                "Tmux",
                "Status",
                "Control",
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
                    control_of(s),
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

    # -- execution control (issue-106) ------------------------------------------

    def _control(self, args: argparse.Namespace) -> int:
        """Apply one control command locally, then record it on the ticket.

        Order matters: the local effect first, the control record with it, and
        the comment last — the comment is a *report* of what happened, so a
        failing `gh` never leaves the ticket claiming something the-loop did not
        do (and never undoes what it did).
        """
        command = args._command
        try:
            work_item = WorkItemRef.parse(args.work_item)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        store = _control_store(args)
        actor = _local_actor()
        # A **disarming** command (pause/stop) is recorded whether or not there
        # was anything to act on — a stopped work item must not re-spawn on the
        # next event. An **arming** one (start/resume) is recorded only when it
        # actually acted, so a start that could not run leaves nothing standing
        # (owner decision on PR #107): the same rule the comment path follows.
        if command in (PAUSE, STOP):
            store.record(work_item, command, source="cli", actor=actor)

        effect, code = self._apply_control(command, work_item, args)
        if command in (START, RESUME) and effect in ("resumed", "running"):
            store.record(work_item, command, source="cli", actor=actor)
        eventlog.emit(
            "control.command",
            work_item=work_item.ref,
            command=command,
            source="cli",
            actor=actor,
            effect=effect,
        )
        if args.comment:
            self._post_control_comment(work_item, command, actor)
        return code

    def _apply_control(
        self, command: str, work_item: WorkItemRef, args: argparse.Namespace
    ) -> Tuple[str, int]:
        """``(effect, exit code)`` of applying ``command`` to ``work_item``."""
        registry = SessionRegistry(args.registry_dir)
        session = registry.find_by_work_item(work_item)

        if command in (START, RESUME):
            if session is not None and session.is_paused:
                registry.resume(work_item)
                print(f"resumed session for {work_item.ref}")
                return "resumed", 0
            if command == RESUME:
                where = "is not paused" if session is not None else "has no session"
                print(f"nothing to resume: {work_item.ref} {where}", file=sys.stderr)
                return "noop", 1
            if session is not None:
                print(f"{work_item.ref} is already running ({session.harness})")
                return "running", 0
            return self._spawn_for_start(work_item, args)

        if command == PAUSE:
            if registry.pause(work_item) is None:
                print(
                    f"no running session for {work_item.ref} to pause; recorded "
                    "the pause, so it will not spawn on its own",
                    file=sys.stderr,
                )
                return "noop", 1
            print(
                f"paused session for {work_item.ref} — events are held until "
                "you resume it"
            )
            return "paused", 0

        # STOP
        if session is None:
            print(
                f"no live session for {work_item.ref}; recorded the stop, so it "
                "will not spawn on its own",
                file=sys.stderr,
            )
            return "noop", 1
        dispatcher, _ = _dispatcher_for(args)
        try:
            dispatcher.close_session(session, reason="stopped from the CLI")
        finally:
            dispatcher.stop(timeout=5)
        print(f"stopped execution for {work_item.ref} (session closed)")
        return "stopped", 0

    def _spawn_for_start(self, work_item: WorkItemRef, args: argparse.Namespace):
        """Spawn a session for a start issued from the CLI.

        Runs through the *daemon's* dispatcher rather than a second spawn
        implementation, so the workspace checkout, the harness trust pre-flight,
        the configured runner and the session announcement all behave exactly as
        they do for a start issued by comment.

        The synthesised event is marked ``labeled=True``: shell access to the
        machine running the-loop is a strictly higher privilege than commenting
        on an issue, so the CLI does not additionally require the auto-execute
        label (which it cannot see without an API call anyway).

        The start requirement is satisfied by recording the request first — that
        is what the dispatcher's gate reads — and the record is **cleared again
        if no session came up**, so a start that could not run leaves nothing
        standing to be picked up by a later event (owner decision on PR #107).
        """
        store = _control_store(args)
        dispatcher, routing = _dispatcher_for(args)
        if routing.spawn_on_unmatched == "never":
            print(
                "error: routing.spawnOnUnmatched is 'never', so the-loop will "
                "not spawn sessions; set it to 'labeled' (or 'always') first",
                file=sys.stderr,
            )
            dispatcher.stop(timeout=5)
            return "rejected", 1
        store.record(work_item, START, source="cli", actor=_local_actor())
        payload = {
            "action": "control-start",
            "repository": {"full_name": f"{work_item.owner}/{work_item.repo}"},
            "issue": {"number": work_item.number},
        }
        routed = RoutedEvent(
            event="issues",
            action="control-start",
            delivery_id=f"cli-start-{uuid.uuid4()}",
            work_items=[work_item],
            payload=payload,
            labeled=True,
        )
        print(f"starting a session for {work_item.ref}…")
        try:
            dispatcher.handle(routed)
        finally:
            # Drains the work item's queue: the spawn runs to completion (a
            # process-runner spawn is the whole task, hence the dispatch timeout).
            dispatcher.stop(timeout=routing.dispatch_timeout_seconds)
        session = SessionRegistry(args.registry_dir).find_by_work_item(work_item)
        if session is None:
            # Nothing came up, so leave nothing armed: the operator re-runs the
            # command rather than the work item starting itself on a later event.
            store.clear(work_item)
            print(
                f"error: could not start a session for {work_item.ref} — see the "
                "log above (and `the-loop events --work-item …`) for why",
                file=sys.stderr,
            )
            return "failed", 1
        print(
            f"started {session.harness} session for {work_item.ref} "
            f"(runner={session.runner})"
        )
        return "spawned", 0

    def _post_control_comment(
        self, work_item: WorkItemRef, command: str, actor: str
    ) -> None:
        """Record the action on the ticket (best-effort — never fails the action)."""
        config = _control_config()
        ok, error = post_issue_comment(
            work_item,
            command_comment(command, config, actor=actor),
            gh_binary=config.gh_binary,
        )
        if ok:
            print(f"commented {config.keyword(command)!r} on {work_item.ref}")
            eventlog.emit("control.announced", work_item=work_item.ref, command=command)
            return
        print(
            f"note: could not comment on {work_item.ref} ({error}); the command "
            "was still applied locally",
            file=sys.stderr,
        )
        eventlog.emit(
            "control.announce_failed",
            level="warning",
            work_item=work_item.ref,
            command=command,
            error=error,
        )

    # -- reset (issue-137) -------------------------------------------------------

    def _reset(self, args: argparse.Namespace) -> int:
        """Forget this machine's state for one, several, or all work items.

        The surface owns the selector rules, the all-or-nothing ref validation
        and the reporting; :mod:`the_loop.reset` owns what is removed and in
        which order.
        """
        if args.work_item and args.all_items:
            print(
                "error: --work-item and --all are mutually exclusive; name the "
                "work items, or ask for all of them",
                file=sys.stderr,
            )
            return 2
        if not args.work_item and not args.all_items:
            print(
                "error: pass --work-item <ref> (repeatable) or --all; a bare "
                "reset never means 'reset everything'",
                file=sys.stderr,
            )
            return 2

        registry = SessionRegistry(args.registry_dir)
        store = _control_store(args).store  # the portable half, legacy shim wired

        if args.all_items:
            items = work_items_with_state(registry, store)
            if not items:
                print(
                    "nothing to reset: this machine holds no work-item state",
                    file=sys.stderr,
                )
                return 1
        else:
            # Validated all-or-nothing: a typo in the third of four refs must
            # not leave the first two reset.
            items, invalid, seen = [], [], set()
            for raw in args.work_item:
                try:
                    item = WorkItemRef.parse(raw)
                except ValueError as exc:
                    invalid.append(str(exc))
                    continue
                # The same item named twice is one reset, not a reset followed
                # by a puzzling "nothing to reset" for something just cleared.
                if item.ref not in seen:
                    seen.add(item.ref)
                    items.append(item)
            if invalid:
                for line in invalid:
                    print(f"error: {line}", file=sys.stderr)
                return 2

        for warning in self._reset_warnings():
            print(warning, file=sys.stderr)

        closer = None if args.dry_run else _LazyCloser(args)
        actor = _local_actor()
        outcomes = []
        try:
            for item in items:
                outcomes.append(
                    reset_work_item(
                        item,
                        registry=registry,
                        store=store,
                        close=closer,
                        dry_run=args.dry_run,
                        actor=actor,
                    )
                )
                self._report_reset(outcomes[-1], dry_run=args.dry_run)
                if args.dry_run and outcomes[-1].was_live:
                    self._warn_about_the_checkout(outcomes[-1])
        finally:
            if closer is not None:
                closer.stop()

        done = [outcome for outcome in outcomes if outcome.ok]
        noun = "work item" if len(done) == 1 else "work items"
        if args.dry_run:
            print(f"would reset {len(done)} {noun} (dry run — nothing was changed)")
        elif done:
            print(f"reset {len(done)} {noun}")
        return 0 if len(done) == len(outcomes) else 1

    def _report_reset(self, outcome, dry_run: bool) -> None:
        """One work item's result. The irreversible facts get their own lines."""
        if outcome.was_live:
            print(
                f"{outcome.ref}: "
                + ("would end a live session" if dry_run else "ended a live session")
            )
        if WORKSPACE in outcome.removed:
            print(
                f"{outcome.ref}: removed the workspace checkout — uncommitted "
                "work in it is gone"
            )
        pieces = [piece for piece in outcome.removed if piece != WORKSPACE]
        if pieces:
            verb = "would remove" if dry_run else "reset — removed"
            print(f"{outcome.ref}: {verb} {', '.join(pieces)}")
        for error in outcome.errors:
            print(f"{outcome.ref}: error: {error}", file=sys.stderr)
        if not outcome.found:
            print(f"{outcome.ref}: nothing to reset", file=sys.stderr)

    def _warn_about_the_checkout(self, outcome) -> None:
        """Say in the *rehearsal* that a real run would remove the checkout.

        A dry run cannot know whether a checkout is on disk without building the
        dispatcher it deliberately does not build — but the config alone says
        whether the close path would remove one, and the piece that is not
        recoverable is exactly the piece an operator must not discover
        afterwards.
        """
        workspace = _routing_config().workspace
        if not workspace.root or workspace.keep_checkout_on_close:
            return
        print(
            f"{outcome.ref}: would also remove its workspace checkout under "
            f"{workspace.root} — uncommitted work in it would be gone"
        )

    def _reset_warnings(self) -> List[str]:
        """What the operator should know *before* reading the report.

        Both are warnings rather than refusals: an operator may legitimately
        reset one work item while the daemon serves others, and a refusal would
        only be routed around with a `--force` that means less.
        """
        warnings = []
        pid = _running_receiver_pid()
        if pid is not None:
            warnings.append(
                f"warning: the gh-webhook receiver looks like it is running (pid "
                f"{pid}); it holds poll state in memory and can write it back "
                "after this reset — stop it first for a clean slate"
            )
        routing = _routing_config()
        if not routing.control.require_start_command and (
            routing.spawn_on_unmatched != "never"
        ):
            warnings.append(
                "warning: routing.control.requireStartCommand is false and "
                f"spawnOnUnmatched is {routing.spawn_on_unmatched!r}, so a reset "
                "work item is first-sight again and may re-spawn on the next "
                "poll cycle rather than waiting for a start"
            )
        return warnings

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
