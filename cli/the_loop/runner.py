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
import re
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, List, Optional, Sequence

from .harness.base import UnsupportedRunnerError
from .sessions import Session, WorkItemRef, tmux_session_name

if TYPE_CHECKING:  # pragma: no cover — type-only
    from .harness.base import HarnessAdapter
    from .webhook.dispatcher import WebTerminalConfig

__all__ = [
    "HUB_SESSION",
    "SESSION_ABSENT",
    "SESSION_DEAD",
    "SESSION_LIVE",
    "SESSION_UNKNOWN",
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
# How often `terminate_harness` re-reads pane liveness while waiting out its
# SIGTERM grace period. Stepped (not wall-clock) so an injected sleeper in tests
# cannot spin.
_TERMINATE_POLL_SECONDS = 0.2
# Shape a tmux target must have before the-loop will signal the processes inside
# it: the `loop-<slug>` names `target_for` mints. The registry is a plain file,
# and terminating reaches OS processes — so a corrupted/hand-edited `tmuxTarget`
# must not be able to aim a SIGTERM at some other tmux session's panes.
#
# `.` and `:` are excluded (issue-154): they are tmux's own target grammar
# (`session:window.pane`), so a name carrying them does not merely fail to
# resolve — tmux re-parses it into a *different kind* of target. `target_for`
# and `Session.__post_init__` both rewrite them, so nothing that came through
# the normal path is rejected here; this keeps the shape unreachable for
# anything that did not.
_LOOP_TARGET_RE = re.compile(r"^loop-[A-Za-z0-9_-]+$")

# What a tmux session named `loop-<slug>` can be, as far as the-loop is
# concerned (issue-146). The fourth value is the one this vocabulary exists for:
# before it, "tmux answered: no such session" and "tmux never answered" were the
# same `False`, so a busy server turned a live session into a respawn — which
# then collided with the very session it was replacing.
SESSION_LIVE = "live"  # exists, and at least one pane is still running
SESSION_DEAD = "dead"  # exists, every pane has exited (retained, issue-86)
SESSION_ABSENT = "absent"  # tmux answered: there is no such session
SESSION_UNKNOWN = "unknown"  # tmux did not answer (timeout, OSError, no binary)
# How long a read-only probe waits for tmux. Deliberately far shorter than
# `routing.dispatchTimeoutSeconds`, which governs the spawn — so a probe CAN time
# out while the spawn behind it gets a real answer. That asymmetry is fine now
# that an unanswered probe is `SESSION_UNKNOWN` rather than "absent".
_PROBE_TIMEOUT_SECONDS = 10
# tmux's refusal when `new-session -s <name>` names a session that already
# exists. Matched only to decide whether to *re-probe* — never to authorise the
# kill that may follow, which `session_state` decides.
_DUPLICATE_SESSION_RE = re.compile(r"duplicate session", re.IGNORECASE)

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
    # tmux's own exit status, or None when tmux never answered (probe timeout,
    # OSError, binary missing). The distinction :meth:`TmuxRunner.session_state`
    # is built on — see SESSION_UNKNOWN (issue-146).
    exit_code: Optional[int] = None
    # Set when an operation could not proceed because a session already holds the
    # target name — the collision tmux calls `duplicate session`. ``session_live``
    # then says whether that occupant still has a running harness, i.e. whether
    # the pending event can simply be delivered into it instead (issue-146).
    session_exists: bool = False
    session_live: bool = False


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
        """tmux session name for a work item, spelled the way tmux will keep it.

        `-` separated, because `:` and `.` are tmux target syntax — but the slug
        is also the registry *file name* and deliberately keeps its dots
        (issue-130), so a repo like `octo/foo.js`, or any work item on a
        non-default host, still arrives here with one. Passing that through was
        issue-154: tmux created `loop-…foo_js-15`, the-loop recorded and posted
        `loop-…foo.js-15`, and every later probe addressed a target tmux read as
        `session.window`. :func:`tmux_session_name` applies tmux's own rule, so
        the name minted here is the name tmux ends up with — byte for byte, and
        unchanged for every slug without a `.`/`:`.

        Stored in the registry and never re-derived after.
        """
        return tmux_session_name(f"loop-{work_item.slug}")

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
                exit_code=proc.returncode,
                error=(
                    f"tmux {argv[0]} exited {proc.returncode}: "
                    f"{proc.stderr.strip() or proc.stdout.strip()}"
                ),
            )
        return TmuxResult(ok=True, exit_code=0, output=proc.stdout or "")

    def spawn(
        self,
        work_item: WorkItemRef,
        adapter: "HarnessAdapter",
        prompt: str,
        cwd: str,
        session_id: str,
        timeout: Optional[float] = None,
        resume: bool = False,
    ) -> TmuxResult:
        """Start the harness TUI detached in ``loop-<slug>`` with a pre-assigned id.

        With ``resume`` the TUI is asked to **continue** the conversation
        ``session_id`` names instead of starting a new one (issue-89) — the
        respawn path's way of not losing everything the agent knew about the
        work item.
        """
        try:
            harness_argv = (
                adapter.interactive_resume_argv(prompt, session_id)
                if resume
                else adapter.interactive_argv(prompt, session_id)
            )
        except UnsupportedRunnerError as exc:
            return TmuxResult(ok=False, error=str(exc))
        target = self.target_for(work_item)
        argv = [
            "new-session",
            "-d",
            "-s",
            target,
            "-c",
            cwd,
            "--",
            adapter.binary,
        ] + harness_argv
        blocked = self._clear_target(target, timeout)
        if blocked is not None:
            return blocked
        result = self._run(argv, timeout)
        if not result.ok and _DUPLICATE_SESSION_RE.search(result.error):
            # tmux is the authority on the collision, and it disagrees with the
            # pre-flight probe — which can time out on a busy server and read as
            # "nothing there". Re-decide knowing the name IS taken, and if the
            # occupant was clearable spawn exactly once more: a straight line, so
            # a persistent collision costs one extra attempt and then reports
            # itself instead of recurring every cycle forever (issue-146).
            logger.info(
                "tmux refused to create %s (%s); re-checking what holds the name",
                target,
                result.error,
            )
            blocked = self._clear_target(target, timeout, present=True)
            if blocked is not None:
                return blocked
            result = self._run(argv, timeout)
        if result.ok and self.remain_on_exit:
            self._set_remain_on_exit(target, timeout)
        return result

    def _clear_target(
        self, target: str, timeout: Optional[float], present: bool = False
    ) -> Optional[TmuxResult]:
        """Make ``target`` free for ``new-session``; a result when it cannot be.

        ``None`` means "go ahead". Anything else is the result :meth:`spawn` must
        return, carrying ``session_exists``/``session_live`` so the caller can
        route the pending event into the occupant rather than retrying a spawn
        that can only fail the same way (issue-146).

        ``present=True`` says tmux has already *proved* the name is taken (it
        answered ``duplicate session``), which changes only what an **unreadable**
        probe means: not "try anyway" but "something is there that will not
        identify itself".

        The rule the whole method turns on: ``loop-<slug>`` is derived from the
        work item, so an occupant is almost always **this work item's own agent**.
        A live one is therefore never killed — an idle detached agent is
        indistinguishable from a busy one, and spawning over it would destroy work
        in progress. Only a definite "every pane is dead" ever licenses
        ``kill-session``.

        The one exception, recorded rather than hidden (issue-154): the name is
        tmux-normalised, so two work items whose slugs differ only in a ``.``/``_``
        position (``octo/foo.bar#15`` vs ``octo/foo_bar#15``) share it. The
        aliasing is tmux's — it cannot host both names at once either — and this
        method's refusal to spawn over a live occupant is exactly what keeps it
        harmless: the worst case is the *other* work item's event routed into an
        agent, never an agent destroyed.
        """
        state = self.session_state(target)
        if state == SESSION_ABSENT:
            return None
        if state == SESSION_UNKNOWN and not present:
            # The probe did not answer, so there is nothing to decide on. Let
            # `new-session` be the authority: it either succeeds (the name was
            # free) or reports the collision, which comes back here.
            logger.debug(
                "tmux did not answer for %s; letting new-session decide", target
            )
            return None
        if state in (SESSION_LIVE, SESSION_UNKNOWN):
            # Live, or held by an occupant tmux will not describe. Both are
            # reported as live: never destroy what you cannot see, and let the
            # caller *try delivering* into it — harmless if the occupant turns out
            # to be a dead pane (the paste simply fails and is retried), and
            # exactly right if there is an agent in there.
            return TmuxResult(
                ok=False,
                session_exists=True,
                session_live=True,
                error=(
                    f"tmux session {target} already exists and its harness is "
                    "still running; not spawning over a live session"
                    if state == SESSION_LIVE
                    else (
                        f"tmux session {target} already exists and tmux would not "
                        "say what holds it; not spawning over it"
                    )
                ),
            )
        # Dead: a pane retained by remain-on-exit (issue-86) — a leftover holding
        # the name, and nothing is lost by clearing it.
        logger.info("clearing stale tmux session %s before spawn", target)
        killed = self._run(["kill-session", "-t", target], timeout)
        if killed.ok or self.session_state(target) == SESSION_ABSENT:
            # A kill that reported failure against a session that is now gone is
            # a success in the only sense that matters: the name is free.
            return None
        return TmuxResult(
            ok=False,
            session_exists=True,
            session_live=False,
            error=(
                f"tmux session {target} already exists and could not be cleared "
                f"({killed.error}); not spawning over it"
            ),
        )

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

    def session_state(self, target: str) -> str:
        """What holds ``target``: live / dead / absent, or *unknown* (issue-146).

        ``absent`` is returned **only** when tmux itself answered — any non-zero
        exit means "no such session" or "no server running", both of which mean
        the name is free. When tmux never answered (the probe timed out, the
        binary is missing, the call raised) the answer is ``unknown``, and no
        caller may read that as absence: doing so is what let a busy tmux server
        turn a live session into a respawn, which then collided with it.

        Classified from the exit *status*, never from tmux's wording, so nothing
        depends on a message tmux is free to change.
        """
        probe = self._run(["has-session", "-t", target], timeout=_PROBE_TIMEOUT_SECONDS)
        if not probe.ok:
            return SESSION_ABSENT if probe.exit_code is not None else SESSION_UNKNOWN
        panes = self._run(
            ["list-panes", "-t", target, "-F", "#{pane_dead}"],
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
        if not panes.ok:
            return SESSION_LIVE
        flags = [line.strip() for line in panes.output.splitlines() if line.strip()]
        if not flags:
            return SESSION_LIVE
        return SESSION_LIVE if any(flag != "1" for flag in flags) else SESSION_DEAD

    def has_session(self, target: str) -> bool:
        """Whether a session holds ``target`` — dead or alive.

        Existence only — no pane read, so it stays a single tmux call. An
        unanswered probe reads False, which is what this method's callers
        (``terminate_harness``, ``sessions attach``) want: both are best-effort
        readers where "assume it is gone" is the safe answer. Callers that must
        not confuse silence with absence use :meth:`session_state` directly.
        """
        return self._run(
            ["has-session", "-t", target], timeout=_PROBE_TIMEOUT_SECONDS
        ).ok

    def has_live_session(self, target: str) -> bool:
        """True when the session exists AND at least one pane is still running.

        With ``remain-on-exit`` a session outlives its harness process, so
        ``has-session`` alone no longer means "there is something to talk to".
        Anything unreadable — a tmux too old to know ``#{pane_dead}``, empty
        output, or (issue-146) a probe tmux never answered at all — is treated as
        **live**, degrading to the pre-issue-86 behaviour rather than declaring
        healthy sessions dead. A delivery therefore *attempts the paste* on a
        doubtful probe and fails transiently if the session really is gone,
        instead of respawning over a session that is still running.
        """
        return self.session_state(target) in (SESSION_LIVE, SESSION_UNKNOWN)

    def survived(
        self,
        target: str,
        delay: float,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> bool:
        """True when ``target``'s pane is still running ``delay`` seconds on.

        ``tmux new-session -d`` returns as soon as tmux forks the pane, so a
        harness that refuses to start (``claude --resume <unknown-id>`` exits 1
        in well under a second) still looks like a successful spawn. This
        short grace period turns that into an answerable question — used by the
        resume-on-respawn path to fall back to a fresh session instead of
        registering a corpse (issue-89). ``delay <= 0`` reads the pane state
        immediately; ``sleeper`` is injectable so tests never wait.
        """
        if delay > 0:
            sleeper(delay)
        return self.has_live_session(target)

    def live_pane_pids(self, target: str) -> List[int]:
        """Pids of ``target``'s still-running panes (empty when none/unreadable).

        The only source of a pid the-loop ever signals: tmux's own view of the
        panes of a session the-loop itself spawned. A dead pane's pid is skipped
        — it names a process that has already exited (issue-94, R3.6).
        """
        result = self._run(
            ["list-panes", "-t", target, "-F", "#{pane_pid} #{pane_dead}"], timeout=10
        )
        if not result.ok:
            return []
        pids: List[int] = []
        for line in result.output.splitlines():
            parts = line.split()
            if not parts:
                continue
            dead = parts[1] if len(parts) > 1 else "0"
            if dead == "1":
                continue
            try:
                pid = int(parts[0])
            except ValueError:  # a tmux too old for the format: nothing to signal
                continue
            # Hard guard: os.kill treats 0/negative as "my whole process group"
            # / "that group". Only a real, positive pid is ever signalled.
            if pid > 0:
                pids.append(pid)
        return pids

    def _signal(
        self,
        pids: Sequence[int],
        sig: int,
        killer: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """Best-effort signal delivery — an unsignalable pid never raises."""
        send = killer or os.kill  # resolved per call, so it stays injectable
        for pid in pids:
            try:
                send(pid, sig)
            except ProcessLookupError:
                logger.debug("process %s already gone", pid)
            except (PermissionError, OSError) as exc:
                logger.warning("could not signal process %s: %s", pid, exc)

    def terminate_harness(
        self,
        session: Session,
        grace: float = 5.0,
        timeout: Optional[float] = None,
        sleeper: Callable[[float], None] = time.sleep,
        killer: Optional[Callable[[int, int], None]] = None,
    ) -> TmuxResult:
        """End the harness running in a *retained* session's pane (issue-94).

        Retention (issue-86) keeps the tmux session so its scrollback stays
        readable — but until now it also kept the harness **running**, so a
        finished work item left a writable `claude` TUI anyone could paste into.
        This ends the conversation while keeping the transcript: `remain-on-exit`
        is (re-)set first so the pane survives its process, then the pane's own
        pids get SIGTERM, escalating to SIGKILL if they outlive ``grace``.

        Best-effort throughout: a missing session, an unreadable pane list, an
        already-exited process or a refused signal are reported, never raised —
        closing the work item must not depend on it.
        """
        target = session.tmux_target
        if not target:
            return TmuxResult(ok=True)
        if not _LOOP_TARGET_RE.match(target):
            logger.warning(
                "refusing to terminate processes in tmux target %r for %s: not a "
                "the-loop `loop-<slug>` session",
                target,
                session.work_item.ref,
            )
            return TmuxResult(
                ok=False, error=f"{target!r} is not a the-loop tmux session name"
            )
        if not self.has_session(target):
            return TmuxResult(
                ok=True,
                session_missing=True,
                error=f"tmux session {target} is already gone",
            )
        # Without this the pane closes with its process — taking the window, the
        # session and the transcript the retention exists for.
        self._set_remain_on_exit(target, timeout)
        pids = self.live_pane_pids(target)
        if not pids:
            return TmuxResult(ok=True)  # nothing running in there any more
        logger.info("terminating harness in %s (pid(s) %s)", target, pids)
        self._signal(pids, signal.SIGTERM, killer)
        for _ in range(int(max(0.0, grace) / _TERMINATE_POLL_SECONDS)):
            if not self.has_live_session(target):
                return TmuxResult(ok=True)
            sleeper(_TERMINATE_POLL_SECONDS)
        if not self.has_live_session(target):
            return TmuxResult(ok=True)
        logger.warning(
            "harness in %s survived SIGTERM after %ss; sending SIGKILL",
            target,
            grace,
        )
        self._signal(self.live_pane_pids(target), signal.SIGKILL, killer)
        if self.has_live_session(target):
            return TmuxResult(
                ok=False,
                error=f"harness in {target} is still running after SIGKILL",
            )
        return TmuxResult(ok=True)

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
