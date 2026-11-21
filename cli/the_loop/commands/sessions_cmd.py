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
import contextlib
import getpass
import io
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .base import Command, register
from ..poller.daemon import _build_dispatcher
from ..webhook.daemon import _state_layout
from .. import cli_config, eventlog, strings
from ..client.routing import harness_routed, routed, service_error
from ..control import CLEANUP, PAUSE, RESUME, START, STOP, ControlStore
from ..core import sessions as core_sessions
from ..reset import WORKSPACE, reset_work_item, work_items_with_state
from ..runner import INSTANCE_ENV_VAR, WORK_ITEM_ENV_VAR, TmuxRunner
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
    return cli_config.load_cli_config(cli_config.default_cli_config_path())


def _foreign_work_item(ref: str) -> str:
    """Why ``ref`` is refused here, or ``""`` when it is this session's own.

    The daemon names a session's work item in its environment
    (``THE_LOOP_WORK_ITEM``). The hook verbs and `the-loop wait` act on that one
    only, so another ref is refused before anything is sent. A process that
    carries the daemon's instance variable (``THE_LOOP_INSTANCE``) and not that
    name is refused too: the name was lost, and without it this check would
    pass every ref. Only that variable counts here. ``THE_LOOP_CLI_CONFIG`` is
    also how an operator points the CLI at a config in their own shell, so it
    marks nothing; and a daemon whose instance has no name sets no instance
    variable, so its sessions are not caught by this second refusal. Any other
    shell is let through, so an operator can run the verbs by hand.

    This is a check on the caller's own environment and nothing more. The
    service authenticates no caller; what it checks is that the ref has a live
    session in the registry.
    """
    own = os.environ.get(WORK_ITEM_ENV_VAR, "").strip()
    if not own:
        if os.environ.get(INSTANCE_ENV_VAR):
            return strings.t(
                "cli.sessions.unnamed-work-item",
                marker=INSTANCE_ENV_VAR,
                name=WORK_ITEM_ENV_VAR,
            )
        return ""
    try:
        if WorkItemRef.parse(own).ref == WorkItemRef.parse(ref).ref:
            return ""
    except ValueError:
        if own == ref.strip():
            return ""
    return strings.t("cli.sessions.foreign-work-item", ref=ref, own=own)


#: A background task in one of these states is over. Anything else a harness
#: lists is still running.
_FINISHED_TASK_STATES = frozenset(
    {"completed", "failed", "killed", "cancelled", "canceled", "stopped", "done"}
)


#: How long the Stop payload is waited for: this long for its first byte, and
#: this long again for the rest once some of it has come.
_PAYLOAD_WAIT_SECONDS = 1.0


def _read_what_is_there(stream: Any) -> str:
    """What ``stream`` gives within the wait, without needing its end.

    The read runs on a thread, and the thread is left behind when the wait is
    over: nothing asks the platform whether a read would block, so the bound
    holds for a pipe on Windows too. A stream with a descriptor is read from
    it a piece at a time, so what has come is kept when the rest never does.
    Any other stream is read whole, or not at all.
    """
    pieces: List[Any] = []
    #: Set by the first piece, and when the reader ends.
    first = threading.Event()

    def read() -> None:
        try:
            try:
                descriptor = stream.fileno()
            except (AttributeError, OSError, ValueError):
                pieces.append(stream.read())
                return
            while True:
                chunk = os.read(descriptor, 65536)
                if not chunk:
                    return
                pieces.append(chunk)
                first.set()
        except (OSError, ValueError):
            return
        finally:
            first.set()

    reader = threading.Thread(target=read, name="the-loop-stdin", daemon=True)
    reader.start()
    # This long for the first of it, and this long again for the rest.
    first.wait(_PAYLOAD_WAIT_SECONDS)
    reader.join(_PAYLOAD_WAIT_SECONDS if pieces else 0)
    return "".join(
        piece.decode("utf-8", errors="replace") if isinstance(piece, bytes) else piece
        for piece in list(pieces)
        if isinstance(piece, (bytes, str))
    )


def _background_work(stream: Any) -> bool:
    """Whether the harness's Stop payload on ``stream`` lists running background
    work.

    Claude Code's payload carries ``background_tasks``, a list of objects with a
    ``status``. Everything else means "no": a terminal, an empty or unreadable
    stream, a payload of another shape, a task with no status. Never waits on a
    stream that has nothing to read.
    """
    try:
        if stream is None or stream.isatty():
            return False
        payload = json.loads(_read_what_is_there(stream) or "null")
    except (OSError, ValueError):
        return False
    tasks = payload.get("background_tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list):
        return False
    return any(
        isinstance(task, dict)
        and isinstance(task.get("status"), str)
        and task["status"].strip().lower() not in _FINISHED_TASK_STATES
        and bool(task["status"].strip())
        for task in tasks
    )


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
        print(strings.t("cli.sessions.error", error=exc), file=sys.stderr)
        return 2
    session = registry.find_by_work_item(ref, include_closed=True)
    if session is None:
        print(strings.t("cli.sessions.attach.no-session", ref=ref.ref), file=sys.stderr)
        return 1
    if session.status != "active":
        # The work item finished but its tmux session was retained (issue-86):
        # attaching is exactly how a human reads back what happened. It is a
        # *record*, so it is always attached read-only — a closed work item's
        # terminal must not take input (issue-94).
        read_only = True
        print(strings.t("cli.sessions.attach.closed", ref=ref.ref), file=sys.stderr)
    if not session.tmux_target:
        print(strings.t("cli.sessions.attach.no-tmux", ref=ref.ref), file=sys.stderr)
        return 1
    runner = TmuxRunner()
    if not runner.is_available():
        from ..runner import check_dependencies

        for line in check_dependencies(web_enabled=False):
            print(strings.t("cli.sessions.error", error=line), file=sys.stderr)
        return 1
    if not runner.has_session(session.tmux_target):
        print(
            strings.t("cli.sessions.attach.tmux-gone", target=session.tmux_target),
            file=sys.stderr,
        )
        return 1
    argv = _attach_argv(session, read_only)
    execvp(argv[0], argv)
    return 0


@register
class SessionsCommand(Command):
    name = "sessions"
    help = strings.t("cli.sessions.help")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        registry_dir = _default_registry_dir()
        portable_dir = _default_portable_dir()
        actions = parser.add_subparsers(dest="action", metavar="<action>")
        actions.required = True

        reg = actions.add_parser(
            "register", help=strings.t("cli.sessions.register.help")
        )
        reg.add_argument(
            "--work-item",
            required=True,
            help=strings.t("cli.sessions.work-item.help"),
        )
        reg.add_argument(
            "--harness", required=True, choices=sorted(core_sessions.HARNESS_BINARIES)
        )
        reg.add_argument(
            "--harness-session-id",
            required=True,
            help=strings.t("cli.sessions.register.harness-session-id.help"),
        )
        reg.add_argument(
            "--cwd",
            default=".",
            help=strings.t("cli.sessions.register.cwd.help"),
        )
        reg.add_argument(
            "--force",
            action="store_true",
            help=strings.t("cli.sessions.register.force.help"),
        )
        reg.add_argument("--registry-dir", default=registry_dir)
        reg.add_argument("--portable-dir", default=portable_dir)
        reg.set_defaults(_action=self._register)

        link = actions.add_parser(
            "link-pr",
            help=strings.t("cli.sessions.link-pr.help"),
        )
        link.add_argument(
            "--work-item",
            required=True,
            help=strings.t("cli.sessions.work-item.help"),
        )
        which = link.add_mutually_exclusive_group(required=True)
        which.add_argument(
            "--pull-request",
            metavar="REF|N",
            help=strings.t("cli.sessions.link-pr.pull-request.help"),
        )
        which.add_argument(
            "--discover",
            action="store_true",
            help=strings.t("cli.sessions.link-pr.discover.help"),
        )
        link.add_argument(
            "--branch",
            default="",
            help=strings.t("cli.sessions.link-pr.branch.help"),
        )
        link.add_argument(
            "--head-owner",
            default="",
            help=strings.t("cli.sessions.link-pr.head-owner.help"),
        )
        link.add_argument(
            "--repository",
            default="",
            metavar="[HOST/]OWNER/REPO",
            help=strings.t("cli.sessions.link-pr.repository.help"),
        )
        link.add_argument("--registry-dir", default=registry_dir)
        link.add_argument("--portable-dir", default=portable_dir)
        link.set_defaults(_action=self._link_pr)

        stop_check = actions.add_parser(
            "stop-check", help=strings.t("cli.sessions.stop-check.help")
        )
        stop_check.add_argument(
            "--work-item",
            required=True,
            help=strings.t("cli.sessions.work-item.help"),
        )
        stop_check.add_argument(
            "--gave-up",
            action="store_true",
            help=strings.t("cli.sessions.stop-check.gave-up.help"),
        )
        stop_check.set_defaults(_action=self._stop_check)

        turn_start = actions.add_parser(
            "turn-start", help=strings.t("cli.sessions.turn-start.help")
        )
        turn_start.add_argument(
            "--work-item",
            required=True,
            help=strings.t("cli.sessions.work-item.help"),
        )
        turn_start.set_defaults(_action=self._turn_start)

        lst = actions.add_parser("list", help=strings.t("cli.sessions.list.help"))
        lst.add_argument("--status", choices=["active", "paused", "closed"])
        lst.add_argument("--format", choices=["table", "json"], default="table")
        lst.add_argument("--registry-dir", default=registry_dir)
        lst.add_argument("--portable-dir", default=portable_dir)
        lst.set_defaults(_action=self._list)

        attach = actions.add_parser(
            "attach", help=strings.t("cli.sessions.attach.help")
        )
        attach.add_argument("--work-item", required=True)
        attach.add_argument(
            "--read-only",
            action="store_true",
            help=strings.t("cli.sessions.attach.read-only.help"),
        )
        attach.add_argument("--registry-dir", default=registry_dir)
        attach.add_argument("--portable-dir", default=portable_dir)
        attach.set_defaults(_action=self._attach)

        # -- execution control (issue-106) --------------------------------------
        # The same four commands an authorized user issues by keyword, from the
        # machine running the-loop. Each posts its keyword back to the ticket.
        control_help = {
            START: strings.t("cli.sessions.control.start.help"),
            PAUSE: strings.t("cli.sessions.control.pause.help"),
            RESUME: strings.t("cli.sessions.control.resume.help"),
            STOP: strings.t("cli.sessions.control.stop.help"),
            CLEANUP: strings.t("cli.sessions.control.cleanup.help"),
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
                help=strings.t("cli.sessions.control.comment.help"),
            )
            sub.set_defaults(_action=self._control, _command=command)

        # -- reset (issue-137) --------------------------------------------------
        # The one action that removes rather than transitions: everything this
        # machine remembers about a work item goes, so it starts over on the
        # code the operator has just fixed.
        reset = actions.add_parser(
            "reset",
            help=strings.t("cli.sessions.reset.help"),
        )
        reset.add_argument(
            "--work-item",
            action="append",
            metavar="REF",
            help=strings.t("cli.sessions.reset.work-item.help"),
        )
        reset.add_argument(
            "--all",
            dest="all_items",
            action="store_true",
            help=strings.t("cli.sessions.reset.all.help"),
        )
        reset.add_argument(
            "--dry-run",
            action="store_true",
            help=strings.t("cli.sessions.reset.dry-run.help"),
        )
        reset.add_argument("--registry-dir", default=registry_dir)
        reset.add_argument("--portable-dir", default=portable_dir)
        reset.set_defaults(_action=self._reset)

        close = actions.add_parser("close", help=strings.t("cli.sessions.close.help"))
        close.add_argument("--work-item", required=True)
        close.add_argument("--registry-dir", default=registry_dir)
        close.add_argument("--portable-dir", default=portable_dir)
        tmux_fate = close.add_mutually_exclusive_group()
        tmux_fate.add_argument(
            "--keep-tmux",
            dest="keep_tmux",
            action="store_true",
            default=None,
            help=strings.t("cli.sessions.close.keep-tmux.help"),
        )
        tmux_fate.add_argument(
            "--kill-tmux",
            dest="keep_tmux",
            action="store_false",
            help=strings.t("cli.sessions.close.kill-tmux.help"),
        )
        close.set_defaults(_action=self._close)

        restart = actions.add_parser(
            "restart",
            help=strings.t("cli.sessions.restart.help"),
        )
        restart.add_argument(
            "--work-item",
            action="append",
            default=[],
            help=strings.t("cli.sessions.restart.work-item.help"),
        )
        restart.add_argument(
            "--all",
            dest="all_sessions",
            action="store_true",
            help=strings.t("cli.sessions.restart.all.help"),
        )
        restart.add_argument(
            "--dry-run",
            action="store_true",
            help=strings.t("cli.sessions.restart.dry-run.help"),
        )
        restart.add_argument("--format", choices=["text", "json"], default="text")
        restart.add_argument("--registry-dir", default=registry_dir)
        restart.add_argument("--portable-dir", default=portable_dir)
        restart.set_defaults(_action=self._restart)

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

    def _link_pr(self, args: argparse.Namespace) -> int:
        """Record "this pull request delivers this work item" (issue-274).

        The step a session runs in the same breath as opening the pull request.
        The router prefers this binding over every inference, and a pull request
        the-loop authored carries none of the inferences — so without this the
        review comments its own phase gate asks for never reach it.
        """
        if args.discover:
            return self._discover_prs(args)
        from ..core import github_ops

        try:
            result = routed(
                lambda connection: connection.post(
                    "/sessions/link-pr",
                    {"ref": args.work_item, "pullRequest": args.pull_request},
                ),
                lambda: github_ops.link_pull_request(
                    args.work_item,
                    args.pull_request,
                    _cli_config(),
                    registry_dir=args.registry_dir,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — mapped, or re-raised below
            return self._report(exc)
        return _render(result)

    def _discover_prs(self, args: argparse.Namespace) -> int:
        """``link-pr --discover`` (issue-447): the pull requests are asked of
        GitHub, not parsed out of a tool's output. The branch and the repository
        are the checkout's, read here — the service does not run in it."""
        from ..core import github_ops
        from ..ghhost import current_branch, origin_github_repo

        cwd = Path.cwd()
        branch = args.branch or current_branch(cwd)
        if not branch:
            print(strings.t("cli.sessions.link-pr.no-branch"), file=sys.stderr)
            return 2
        # The origin only when it is on a GitHub host this instance trusts;
        # otherwise the work item's own repository (core's default for "").
        repository = args.repository or origin_github_repo(
            cwd, github_ops.trusted_hosts(_cli_config())
        )
        try:
            result = routed(
                lambda connection: connection.post(
                    "/sessions/link-pr",
                    {
                        "ref": args.work_item,
                        "discover": True,
                        "branch": branch,
                        "repository": repository,
                        "headOwner": args.head_owner,
                    },
                ),
                lambda: github_ops.discover_pull_requests(
                    args.work_item,
                    branch,
                    repository,
                    _cli_config(),
                    head_owner=args.head_owner,
                    registry_dir=args.registry_dir,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — mapped, or re-raised below
            return self._report(exc)
        return _render(result)

    def _stop_check(self, args: argparse.Namespace) -> int:
        """Ask whether this session's turn may end.

        For the harness's Stop hook, which pipes its own payload in. One fact is
        read from it and forwarded: whether the harness lists background work
        still running. The answer is printed as JSON; `allow` and `refuse` both
        exit 0, and only a check that could not be made exits non-zero.
        """
        from ..core import stopcheck

        foreign = _foreign_work_item(args.work_item)
        if foreign:
            print(foreign, file=sys.stderr)
            return 2
        background = _background_work(sys.stdin)
        try:
            result = harness_routed(
                lambda connection: connection.post(
                    "/sessions/stop-check",
                    {
                        "ref": args.work_item,
                        "backgroundWork": background,
                        "gaveUp": bool(args.gave_up),
                    },
                ),
                lambda: stopcheck.stop_check(
                    args.work_item,
                    config=_cli_config(),
                    background_work=background,
                    gave_up=args.gave_up,
                ),
            )
        except LookupError as exc:
            print(strings.t("cli.sessions.error", error=exc), file=sys.stderr)
            return 1
        except Exception as exc:  # noqa: BLE001 — mapped, or re-raised below
            return self._report(exc)
        print(json.dumps(result))
        return 0

    def _turn_start(self, args: argparse.Namespace) -> int:
        """Record that this session's turn started.

        For the harness's turn-start hook, so it runs before every turn of every
        session. It must never break or delay one: every failure is swallowed,
        nothing is printed, and the exit code is always 0.
        """
        from ..core import stopcheck

        if _foreign_work_item(args.work_item):
            return 0
        try:
            # Its only output would be the routing notes on stderr.
            with contextlib.redirect_stderr(io.StringIO()):
                harness_routed(
                    lambda connection: connection.post(
                        "/sessions/turn-start", {"ref": args.work_item}
                    ),
                    lambda: stopcheck.turn_start(args.work_item, config=_cli_config()),
                )
        except Exception:  # noqa: BLE001 — a hook's bookkeeping never fails a turn
            logger.debug("turn start not recorded", exc_info=True)
        return 0

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
                strings.t("cli.sessions.list.column.work-item"),
                strings.t("cli.sessions.list.column.harness"),
                strings.t("cli.sessions.list.column.model"),
                strings.t("cli.sessions.list.column.session-id"),
                strings.t("cli.sessions.list.column.tmux"),
                strings.t("cli.sessions.list.column.status"),
                strings.t("cli.sessions.list.column.state"),
                strings.t("cli.sessions.list.column.control"),
                strings.t("cli.sessions.list.column.last-event"),
            )
        ]
        # What each session is doing: the state the service
        # derived from the event log. `-` for a row that carries none.
        states = strings.section("cli.sessions.list.state")
        for s in sessions:
            record = s.get("control")
            state = (s.get("session") or {}).get("state") or ""
            # What this session is actually running on (issue-358). `-` means
            # "the harness's own" — either the work item chose nothing, or the
            # record predates the-loop recording it. An effort level rides in the
            # same cell, because the pair is how an operator thinks about it.
            model = s.get("model") or ""
            effort = s.get("effort") or ""
            shown = (
                f"{model} ({effort})" if model and effort else (model or effort or "-")
            )
            rows.append(
                (
                    s["workItem"]["ref"],
                    s["harness"],
                    shown,
                    s["harnessSessionId"],
                    s["tmuxTarget"] or "-",
                    s["status"],
                    states.get(state, state or "-"),
                    f"{record['command']} ({record['source']})" if record else "-",
                    s["lastEventAt"] or "-",
                )
            )
        # issue-533, R7.1: a column only when some session holds an opted-in
        # credential, so a deployment that configures none sees today's table.
        held = [
            ", ".join(
                f"{name}@{fp}"
                for name, fp in sorted((s.get("credentials") or {}).items())
            )
            for s in sessions
        ]
        if any(held):
            rows = [rows[0] + (strings.t("cli.sessions.list.column.credentials"),)] + [
                row + (cell or "-",) for row, cell in zip(rows[1:], held)
            ]
        widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
        for row in rows:
            print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
        if not sessions:
            print(strings.t("cli.sessions.list.empty"), file=sys.stderr)
        return 0

    def _restart(self, args: argparse.Namespace) -> int:
        """``sessions restart`` — in-process, like ``reset`` and for its reason.

        This is bootstrap-and-recovery for a deployment whose credentials have
        just changed (issue-410); routing it through the control-plane service
        would make the recovery depend on the thing an operator runs it to
        repair, and it replaces processes on this host either way.
        """
        try:
            result = core_sessions.restart_sessions(
                refs=args.work_item,
                all_sessions=args.all_sessions,
                dry_run=args.dry_run,
                config=_cli_config(),
                registry_dir=args.registry_dir,
                portable_dir=args.portable_dir,
            )
        except Exception as exc:  # noqa: BLE001 — mapped, or re-raised below
            return self._report(exc)
        if args.format == "json":
            # `messages` is carried too, unlike `list`'s JSON: this verb can refuse
            # (no env file, neither --all nor a ref) and a caller that got only an
            # exit code would have no way to learn why.
            print(json.dumps(result))
            return int(result.get("exitCode") or 0)
        return _render(result)

    @staticmethod
    def _report(exc: Exception) -> int:
        """A client-side failure as the CLI's ``(message, exit code)``.

        ``ValueError`` is core's "caller mistake" on the local path and arrives
        as a 400 on the routed one, so both land on the same exit code.
        """
        mapped = service_error(exc)
        if mapped is None:
            if isinstance(exc, ValueError):
                mapped = (strings.t("cli.sessions.error", error=exc), 2)
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
            print(strings.t("cli.sessions.reset.exclusive"), file=sys.stderr)
            return 2
        if not args.work_item and not args.all_items:
            print(strings.t("cli.sessions.reset.no-selector"), file=sys.stderr)
            return 2

        registry = SessionRegistry(args.registry_dir)
        store = _control_store(args).store  # the portable half, legacy shim wired

        if args.all_items:
            items = work_items_with_state(registry, store)
            if not items:
                print(strings.t("cli.sessions.reset.nothing-held"), file=sys.stderr)
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
                    print(strings.t("cli.sessions.error", error=line), file=sys.stderr)
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
        noun = (
            strings.t("cli.sessions.reset.noun-one")
            if len(done) == 1
            else strings.t("cli.sessions.reset.noun-many")
        )
        if args.dry_run:
            print(
                strings.t("cli.sessions.reset.would-reset", count=len(done), noun=noun)
            )
        elif done:
            print(strings.t("cli.sessions.reset.done", count=len(done), noun=noun))
        return 0 if len(done) == len(outcomes) else 1

    def _report_reset(self, outcome, dry_run: bool) -> None:
        """One work item's result. The irreversible facts get their own lines."""
        if outcome.was_live:
            print(
                strings.t("cli.sessions.reset.would-end-live", ref=outcome.ref)
                if dry_run
                else strings.t("cli.sessions.reset.ended-live", ref=outcome.ref)
            )
        if WORKSPACE in outcome.removed:
            print(strings.t("cli.sessions.reset.removed-workspace", ref=outcome.ref))
        pieces = [piece for piece in outcome.removed if piece != WORKSPACE]
        if pieces:
            joined = ", ".join(pieces)
            print(
                strings.t(
                    "cli.sessions.reset.would-remove", ref=outcome.ref, pieces=joined
                )
                if dry_run
                else strings.t(
                    "cli.sessions.reset.removed", ref=outcome.ref, pieces=joined
                )
            )
        for error in outcome.errors:
            print(
                strings.t(
                    "cli.sessions.reset.item-error", ref=outcome.ref, error=error
                ),
                file=sys.stderr,
            )
        if not outcome.found:
            print(
                strings.t("cli.sessions.reset.nothing-for-item", ref=outcome.ref),
                file=sys.stderr,
            )

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
            strings.t(
                "cli.sessions.reset.would-remove-workspace",
                ref=outcome.ref,
                root=workspace.root,
            )
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
            warnings.append(strings.t("cli.sessions.reset.receiver-running", pid=pid))
        routing = _routing_config()
        if not routing.control.require_start_command and (
            routing.spawn_on_unmatched != "never"
        ):
            warnings.append(
                strings.t(
                    "cli.sessions.reset.may-respawn", spawn=routing.spawn_on_unmatched
                )
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
