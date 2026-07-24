"""tmux runner: host webhook-spawned harness sessions in attachable tmux sessions.

With ``routing.runner: tmux`` the dispatcher starts the harness's *interactive*
TUI inside a detached, named tmux session (``loop-<work-item-slug>``) instead of
a one-shot headless subprocess; webhook events are bracketed-pasted into the
TUI; humans attach locally, over SSH, or via the optional ttyd web terminal.
tmux/ttyd are native host binaries (a wheel can't carry them), verified by
``check_dependencies`` at receiver start.

Spec: docs/specs/issue-32/design.md (decision-021).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from .harness.base import UnsupportedRunnerError
from .sessions import Session, WorkItemRef

if TYPE_CHECKING:  # pragma: no cover — type-only
    from .harness.base import HarnessAdapter
    from .webhook.dispatcher import WebTerminalConfig

__all__ = [
    "HUB_SESSION",
    "TmuxResult",
    "TmuxRunner",
    "UnsupportedRunnerError",
    "check_dependencies",
    "web_terminal_argv",
    "start_web_terminal",
    "stop_web_terminal",
]

logger = logging.getLogger("the-loop.runner")

# tmux paste buffer used for event delivery; -d deletes it after each paste.
_EVENT_BUFFER = "the-loop-evt"
# Shared hub session the web terminal (ttyd) drops browser clients into; the
# loop-* sessions are one `switch-client`/`choose-tree` away from it.
HUB_SESSION = "the-loop-hub"

_INSTALL_HINTS = {
    "tmux": (
        "macOS: `brew install tmux` · Debian/Ubuntu: `apt install tmux` · "
        "Fedora: `dnf install tmux`"
    ),
    "ttyd": (
        "macOS: `brew install ttyd` · Debian/Ubuntu: `apt install ttyd` · "
        "static builds: https://github.com/tsl0922/ttyd/releases"
    ),
}


@dataclass
class TmuxResult:
    """Outcome of one tmux operation (mirrors DispatchResult's ok/error shape)."""

    ok: bool
    error: str = ""
    # Set only when a delivery failed because the target tmux session is gone
    # (crashed/killed) or its pane is dead — the *terminal* fault the dispatcher
    # recovers from by respawning, as opposed to a transient tmux error
    # (issue-80).
    session_missing: bool = False
    # stdout of the invocation, for the queries that read tmux back
    # (``has_live_session``); empty for the fire-and-forget commands.
    output: str = ""


def check_dependencies(runner: str, web_enabled: bool) -> List[str]:
    """Missing native dependencies for the configured runner, with install hints.

    Empty when everything needed is present (R6.2: silent on the happy path).
    """
    needed: List[str] = []
    if runner == "tmux":
        needed.append("tmux")
    if web_enabled:
        if "tmux" not in needed:
            needed.append("tmux")
        needed.append("ttyd")
    return [
        f"missing dependency: {binary} — install it ({_INSTALL_HINTS[binary]})"
        for binary in needed
        if shutil.which(binary) is None
    ]


def web_terminal_argv(host: str, port: int) -> List[str]:
    """ttyd command serving a shared tmux hub session as a browser terminal.

    Binds ``host`` (default 127.0.0.1 — access control is environmental,
    decision-021); each browser client attaches to ``the-loop-hub`` and reaches
    any loop-* session via tmux's own session switching.
    """
    return [
        "ttyd",
        "--writable",
        "-p",
        str(port),
        "-i",
        host,
        "tmux",
        "new-session",
        "-A",
        "-s",
        HUB_SESSION,
    ]


def start_web_terminal(web_terminal: "WebTerminalConfig") -> subprocess.Popen:
    """Launch ttyd serving the shared tmux hub session and log its URL.

    Shared by ``gh-webhook start`` and ``poll start`` (issue-65) so both
    ingress paths spawn/log/terminate ttyd identically.
    """
    proc = subprocess.Popen(web_terminal_argv(web_terminal.host, web_terminal.port))
    logger.info(
        "web terminal (ttyd) serving tmux sessions on http://%s:%s "
        "— access control is environmental (decision-021)",
        web_terminal.host,
        web_terminal.port,
    )
    return proc


def stop_web_terminal(proc: Optional[subprocess.Popen]) -> None:
    """Stop a ttyd child process, escalating to kill if it ignores SIGTERM."""
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


class TmuxRunner:
    """Spawn / deliver-to / kill harness TUIs hosted in named tmux sessions.

    ``remain_on_exit`` keeps a spawned session's pane — and with it the whole
    scrollback — after the harness process exits, so a finished session stays
    readable instead of tmux tearing the window down (issue-86).
    """

    def __init__(self, binary: str = "tmux", remain_on_exit: bool = True):
        self.binary = binary
        self.remain_on_exit = remain_on_exit

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def target_for(self, work_item: WorkItemRef) -> str:
        """tmux session name for a work item — `-` separated (`:`/`.` are tmux
        target syntax), stored in the registry and never re-derived after."""
        return f"loop-{work_item.slug}"

    def _run(self, argv: List[str], timeout: Optional[float] = None) -> TmuxResult:
        if not self.is_available():
            return TmuxResult(
                ok=False,
                error=(
                    f"tmux binary {self.binary!r} not found on PATH — install it "
                    f"({_INSTALL_HINTS['tmux']})"
                ),
            )
        cmd = [self.binary] + argv
        logger.debug("running %s", " ".join(cmd[:6]) + " …")
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return TmuxResult(
                ok=False, error=f"tmux {argv[0]} timed out after {timeout}s"
            )
        except OSError as exc:
            return TmuxResult(ok=False, error=f"could not run tmux: {exc}")
        if proc.returncode != 0:
            return TmuxResult(
                ok=False,
                error=(
                    f"tmux {argv[0]} exited {proc.returncode}: "
                    f"{proc.stderr.strip() or proc.stdout.strip()}"
                ),
            )
        return TmuxResult(ok=True, output=proc.stdout or "")

    def spawn(
        self,
        work_item: WorkItemRef,
        adapter: "HarnessAdapter",
        prompt: str,
        cwd: str,
        session_id: str,
        timeout: Optional[float] = None,
    ) -> TmuxResult:
        """Start the harness TUI detached in ``loop-<slug>`` with a pre-assigned id."""
        try:
            harness_argv = adapter.interactive_argv(prompt, session_id)
        except UnsupportedRunnerError as exc:
            return TmuxResult(ok=False, error=str(exc))
        target = self.target_for(work_item)
        if self.has_session(target):
            # A stale session with this deterministic name (crash/restart
            # leftover) would make new-session fail with "duplicate session";
            # the registry says the work item has no active session, so the
            # leftover is dead weight — clear it.
            logger.info("clearing stale tmux session %s before spawn", target)
            self._run(["kill-session", "-t", target], timeout)
        result = self._run(
            ["new-session", "-d", "-s", target, "-c", cwd, "--", adapter.binary]
            + harness_argv,
            timeout,
        )
        if result.ok and self.remain_on_exit:
            self._set_remain_on_exit(target, timeout)
        return result

    def _set_remain_on_exit(self, target: str, timeout: Optional[float]) -> None:
        """Keep the pane (and its scrollback) after the harness exits (issue-86).

        Best-effort: ``remain-on-exit`` is a *window* option (hence ``-w``) and
        older tmux builds may reject the invocation — the session is perfectly
        usable without it, so a failure is a warning, never a failed spawn.
        """
        result = self._run(
            ["set-option", "-t", target, "-w", "remain-on-exit", "on"], timeout
        )
        if not result.ok:
            logger.warning(
                "could not set remain-on-exit on %s (%s) — the pane will close "
                "when the harness exits, losing its scrollback",
                target,
                result.error,
            )

    def has_session(self, target: str) -> bool:
        return self._run(["has-session", "-t", target], timeout=10).ok

    def has_live_session(self, target: str) -> bool:
        """True when the session exists AND at least one pane is still running.

        With ``remain-on-exit`` a session outlives its harness process, so
        ``has-session`` alone no longer means "there is something to talk to".
        Anything unreadable (a tmux too old to know ``#{pane_dead}``, empty
        output) is treated as **live** — degrading to the pre-issue-86
        behaviour rather than declaring healthy sessions dead.
        """
        if not self.has_session(target):
            return False
        result = self._run(
            ["list-panes", "-t", target, "-F", "#{pane_dead}"], timeout=10
        )
        if not result.ok:
            return True
        flags = [line.strip() for line in result.output.splitlines() if line.strip()]
        if not flags:
            return True
        return any(flag != "1" for flag in flags)

    def deliver(
        self, session: Session, prompt: str, timeout: Optional[float] = None
    ) -> TmuxResult:
        """Paste ``prompt`` into the session's TUI (bracketed paste) and submit.

        The prompt travels via tempfile → load-buffer so size/quoting are
        non-issues; -p pastes bracketed so the TUI treats it as one message.
        """
        target = session.tmux_target
        if not self.has_live_session(target):
            return TmuxResult(
                ok=False,
                session_missing=True,
                error=(
                    f"tmux session {target} not found or its harness has exited "
                    "(crashed, killed, or a retained dead pane); respawning a "
                    "fresh session and delivering this event into it"
                ),
            )
        fd, path = tempfile.mkstemp(prefix="the-loop-evt-")
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(prompt)
            for argv in (
                ["load-buffer", "-b", _EVENT_BUFFER, path],
                ["paste-buffer", "-p", "-d", "-b", _EVENT_BUFFER, "-t", target],
                ["send-keys", "-t", target, "Enter"],
            ):
                result = self._run(argv, timeout)
                if not result.ok:
                    return result
        finally:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        return TmuxResult(ok=True)

    def kill(self, session: Session, timeout: Optional[float] = None) -> TmuxResult:
        return self._run(["kill-session", "-t", session.tmux_target], timeout)
