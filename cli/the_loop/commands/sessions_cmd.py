"""``the-loop sessions register|list|start|pause|resume|stop|cleanup|attach|close|reset``.

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

Since issue-186 there is a second remover, and the two are not the same verb.
`reset` is bootstrap-and-recovery: it forgets the **portable** record too, so
the item starts over. `cleanup` is the end of a life cycle: it releases the
local resources — tmux sessions, workspace checkout, the machine-local record —
and *keeps* the portable half, because persistence and tracking are what outlive
the machine. It is a control verb like the other four, so it does post its
keyword back to the ticket.

Since issue-161 this module is a **renderer**: register, list, close and the
four control verbs all execute in :mod:`the_loop.core.sessions`, reached
through the control-plane service (R2.2). What is left here is argument
parsing, table/JSON formatting, and the two actions that cannot leave this
process — ``attach`` replaces the caller's terminal with tmux, and ``reset``
is a bootstrap-and-recovery action that must work when nothing is running.

Spec: docs/specs/issue-15/design.md §5 (requirement R2.2);
docs/specs/issue-106/design.md §6; docs/specs/issue-137/design.md;
docs/specs/issue-161/design.md §2.
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .base import Command, register
from .gh_webhook import _CONFIG_PATH, _state_layout
from ..poller.daemon import _build_dispatcher
from .. import cli_config, eventlog
from ..client.routing import routed, service_error
from ..control import CLEANUP, PAUSE, RESUME, START, STOP, ControlStore
from ..core import sessions as core_sessions
from ..reset import WORKSPACE, reset_work_item, work_items_with_state
from ..runner import TmuxRunner
from ..sessions import Session, SessionRegistry, WorkItemRef
from ..state import legacy_layout
from ..webhook.dispatcher import RoutingConfig

logger = logging.getLogger("the-loop.sessions")


def _routing_config() -> RoutingConfig:
    """The same ``routing`` config the daemon runs on (path defaults included)."""
    return RoutingConfig.from_mapping(cli_config.load_routing_config(), _state_layout())


def _default_registry_dir() -> str:
    routing = cli_config.load_routing_config()
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


def _cli_config() -> dict:
    """The operator's CLI config, as core's surfaces expect to receive it."""
    return cli_config.load_cli_config(_CONFIG_PATH)


def _render(result: Dict[str, Any]) -> int:
    """Print core's ``messages`` on the streams they name; its exit code back.

    Core never prints (the same call serves HTTP and MCP), so the words an
    operator reads travel as data and this is the only place they reach a
    terminal — which is what keeps the CLI's output identical whether the work
    ran in-process or over the service.
    """
    for message in result.get("messages") or []:
        stream = sys.stderr if message.get("stream") == "err" else sys.stdout
        print(message.get("text", ""), file=stream)
    return int(result.get("exitCode") or 0)


def _dispatcher_for(args: argparse.Namespace):
    """The daemon's dispatcher, pointed at the registry this invocation names.

    ``--registry-dir`` defaults to the configured one, so this is normally a
    no-op — but when an operator points the CLI at another registry, the close
    and the spawn must land in *that* one, not in the config's.
    """
    routing = dict(cli_config.load_routing_config())
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
    if not session.tmux_target:
        print(
            f"error: no tmux session recorded yet for {ref.ref} — one is "
            "spawned when its next event is dispatched (a self-registered or "
            "pre-tmux-only record starts without one)",
            file=sys.stderr,
        )
        return 1
    runner = TmuxRunner()
    if not runner.is_available():
        from ..runner import check_dependencies

        for line in check_dependencies(web_enabled=False):
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
        reg.add_argument(
            "--harness", required=True, choices=sorted(core_sessions.HARNESS_BINARIES)
        )
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
            CLEANUP: (
                "Release a finished work item's LOCAL resources: kill its tmux "
                "sessions, remove its workspace checkout (uncommitted work in it "
                "is gone) and delete its machine-local session record. Ignores "
                "the keepSessionOnClose/keepCheckoutOnClose retention settings, "
                "keeps the portable record (control, poll, graph), and touches "
                "nothing remote."
            ),
        }
        for command in (START, PAUSE, RESUME, STOP, CLEANUP):
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
            result = routed(
                lambda connection: connection.post(
                    "/sessions/register",
                    {
                        "ref": args.work_item,
                        "harness": args.harness,
                        "harnessSessionId": args.harness_session_id,
                        "cwd": args.cwd,
                        "force": bool(args.force),
                    },
                ),
                lambda: core_sessions.register_session(
                    args.work_item,
                    args.harness,
                    args.harness_session_id,
                    cwd=args.cwd,
                    force=args.force,
                    config=_cli_config(),
                    registry_dir=args.registry_dir,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — mapped, or re-raised below
            return self._report(exc)
        return _render(result)

    def _list(self, args: argparse.Namespace) -> int:
        try:
            sessions = routed(
                lambda connection: connection.get(
                    "/sessions", params={"status": args.status}
                ),
                lambda: core_sessions.list_sessions(
                    status=args.status,
                    config=_cli_config(),
                    registry_dir=args.registry_dir,
                    portable_dir=args.portable_dir,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — mapped, or re-raised below
            return self._report(exc)

        if args.format == "json":
            print(json.dumps(sessions))
            return 0
        rows = [
            (
                "Work item",
                "Harness",
                "Session id",
                "Tmux",
                "Status",
                "Control",
                "Last event",
            )
        ]
        for s in sessions:
            record = s.get("control")
            rows.append(
                (
                    s["workItem"]["ref"],
                    s["harness"],
                    s["harnessSessionId"],
                    s["tmuxTarget"] or "-",
                    s["status"],
                    f"{record['command']} ({record['source']})" if record else "-",
                    s["lastEventAt"] or "-",
                )
            )
        widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
        for row in rows:
            print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
        if not sessions:
            print("(no registered sessions)", file=sys.stderr)
        return 0

    @staticmethod
    def _report(exc: Exception) -> int:
        """A client-side failure as the CLI's ``(message, exit code)``.

        ``ValueError`` is core's "caller mistake" on the local path and arrives
        as a 400 on the routed one, so both land on the same exit code.
        """
        mapped = service_error(exc)
        if mapped is None:
            if isinstance(exc, ValueError):
                mapped = (f"error: {exc}", 2)
            else:
                raise exc
        print(mapped[0], file=sys.stderr)
        return mapped[1]

    def _attach(self, args: argparse.Namespace) -> int:
        return attach_session(
            SessionRegistry(args.registry_dir),
            args.work_item,
            read_only=args.read_only,
        )

    # -- execution control (issue-106) ------------------------------------------

    def _control(self, args: argparse.Namespace) -> int:
        """Render one control verb, applied by :mod:`the_loop.core.sessions`.

        The whole sequence — local effect, control record, ticket comment, in
        that order — lives in core, so an operator's ``sessions pause`` and an
        agent's MCP ``control_session`` are the same code path and cannot drift.
        """
        try:
            result = routed(
                lambda connection: connection.post(
                    "/sessions/control",
                    {
                        "ref": args.work_item,
                        "verb": args._command,
                        "comment": bool(args.comment),
                    },
                ),
                lambda: core_sessions.control_session(
                    args.work_item,
                    args._command,
                    comment=args.comment,
                    config=_cli_config(),
                    registry_dir=args.registry_dir,
                    portable_dir=args.portable_dir,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — mapped, or re-raised below
            return self._report(exc)
        return _render(result)

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
            result = routed(
                lambda connection: connection.post(
                    "/sessions/close",
                    {"ref": args.work_item, "keepTmux": args.keep_tmux},
                ),
                lambda: core_sessions.close_session(
                    args.work_item,
                    keep_tmux=args.keep_tmux,
                    config=_cli_config(),
                    registry_dir=args.registry_dir,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — mapped, or re-raised below
            return self._report(exc)
        return _render(result)
