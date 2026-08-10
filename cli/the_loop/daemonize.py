"""Detach a long-lived process from the shell that started it (issue-191).

``the-loop poll start`` was a daemon in every respect except the ones that make a
daemon survive. It ran in the foreground and left detaching, redirecting and
reporting to whoever typed the command, so operators backgrounded it with ``&``
from whatever session was handy — which ties the poller's lifetime to that
session's process group. We lost one that way: it ran for ~4.5 hours and then
died silently when the parent's process group was torn down. Because that start
had not redirected stdout either, it stopped writing to its log at the same
moment, and left a pidfile pointing at a dead pid.

The incantation that works — ``setsid nohup … >> log 2>&1 &`` — is five things
the tool should do itself. This module is four of them (the fifth, the pidfile,
is :mod:`the_loop.runlock`, taken *after* the final fork so it records the pid
that actually survives).

**The contract is shaped like** ``os.fork()``: :func:`daemonize` returns ``None``
in the daemon, where execution continues, and the daemon's pid in the original
process, which must then exit. The two halves are told apart by the return value
and nothing else.

**Why a handshake at all.** A detached start that returns instantly reports
nothing: a dependency check that fails, a lock already held, a provider that
cannot be built — all of it lands in a logfile the operator has not thought to
read yet, and ``poll start --daemon && poll status`` races its own daemon. So the
original process holds a pipe and blocks until the daemon calls
:func:`notify_ready`. The pipe is deliberately raw, because **EOF is free**: if
the daemon dies at any point before reporting itself up, the kernel closes its
write end, the read returns empty, and the failure is known immediately with no
timer involved. The timeout only ever covers a daemon that is alive but wedged.

Spec: docs/specs/issue-191/design.md.
"""

from __future__ import annotations

import os
import select
import sys
import time
from pathlib import Path
from typing import Optional

__all__ = ["HAVE_FORK", "daemonize", "notify_ready", "open_logfile"]

#: Whether this platform can fork. POSIX only — the-loop's runner requires tmux,
#: so this is effectively always true where a daemon is wanted at all.
HAVE_FORK = hasattr(os, "fork")

#: How long the original process waits for the daemon to report itself up before
#: giving up on it. Generous: a cold start builds providers, checks dependencies
#: and may bind the ttyd web terminal. Only a *live but wedged* daemon ever waits
#: this long — a daemon that dies is reported the moment its pipe closes.
DEFAULT_READY_TIMEOUT = 60.0

#: The daemon's end of the handshake, installed by :func:`daemonize` in the child.
_ready_fd: Optional[int] = None


def open_logfile(path: os.PathLike | str) -> int:
    """An append-mode fd on ``path``, creating its parent directory.

    Called **before** any fork on purpose: a daemon whose output has nowhere to
    go is the defect this module exists to prevent, so the failure has to reach
    the operator's terminal rather than the logfile that could not be opened.
    Raises ``OSError``.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)


def daemonize(
    logfile: os.PathLike | str,
    timeout: float = DEFAULT_READY_TIMEOUT,
) -> Optional[int]:
    """Detach into a daemon whose stdout/stderr append to ``logfile``.

    Returns ``None`` **in the daemon**: execution continues there, and the caller
    MUST call :func:`notify_ready` once it is genuinely up (lock held, checks
    passed) so the original process can report a truthful exit code.

    Returns **in the original process** the daemon's pid, or ``0`` when the
    daemon exited — or stayed silent past ``timeout`` — without ever reporting
    itself up. The caller must then exit; the original process never falls
    through into the daemon's work.

    Raises ``OSError`` if the logfile cannot be opened (before any fork) and
    ``RuntimeError`` on a platform without ``fork``.
    """
    if not HAVE_FORK:  # pragma: no cover - not reachable on a supported platform
        raise RuntimeError(
            "this platform cannot fork; run the poller in the foreground"
        )

    log_fd = open_logfile(logfile)
    read_fd, write_fd = os.pipe()

    try:
        first = os.fork()
    except OSError:
        os.close(log_fd)
        os.close(read_fd)
        os.close(write_fd)
        raise

    if first > 0:
        # The original process. Closing *our* copy of the write end is what makes
        # the daemon's death observable: the read below then sees EOF the moment
        # the last write end in the world goes away.
        os.close(write_fd)
        os.close(log_fd)
        try:
            return _await_ready(read_fd, timeout)
        finally:
            os.close(read_fd)
            # The intermediate child exits immediately; reaping it here is what
            # keeps a foreground `poll start --daemon` from leaving a zombie.
            _reap(first)

    # -- intermediate child ----------------------------------------------------
    # setsid makes it a session leader with no controlling terminal; forking
    # again means the surviving process is *not* a session leader, so it can
    # never re-acquire one by opening a tty.
    os.close(read_fd)
    os.setsid()
    if os.fork() > 0:
        # _exit, not sys.exit: no atexit hooks, no second flush of buffers this
        # process shares with the daemon it just forked.
        os._exit(0)

    # -- the daemon ------------------------------------------------------------
    # Deliberately no chdir("/"): every path the-loop resolves — the CLI config,
    # state.root, the workspace root — is relative to the working directory the
    # operator ran the command in.
    global _ready_fd
    _ready_fd = write_fd
    _redirect(log_fd)
    return None


def notify_ready() -> None:
    """Report this daemon as up to the process that started it.

    A no-op when the process was not daemonized (the foreground path, and every
    test that imports this module without forking), and safe to call twice — the
    fd is dropped after the first write.
    """
    global _ready_fd
    fd, _ready_fd = _ready_fd, None
    if fd is None:
        return
    try:
        os.write(fd, f"{os.getpid()}\n".encode())
    except OSError:  # pragma: no cover - the reader has gone; nothing to report to
        pass
    finally:
        try:
            os.close(fd)
        except OSError:  # pragma: no cover - closing a valid fd does not fail
            pass


# -- internals ------------------------------------------------------------------


def _await_ready(read_fd: int, timeout: float) -> int:
    """The daemon's pid, or ``0`` when it died or stayed silent.

    ``select`` rather than a blocking read, because the two failure modes are
    different and only one of them is a timeout: a daemon that *dies* closes the
    pipe and is reported at once, while a daemon that is alive but wedged is the
    only case the clock is for.
    """
    deadline = time.monotonic() + max(0.0, timeout)
    chunks = b""
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return 0  # alive but silent past the timeout
        ready, _, _ = select.select([read_fd], [], [], remaining)
        if not ready:
            return 0  # alive but silent past the timeout
        data = os.read(read_fd, 32)
        if not data:  # EOF: every write end is closed, so the daemon has gone
            break
        chunks += data
        if b"\n" in chunks:
            break
    try:
        return int(chunks.decode().strip() or 0)
    except ValueError:  # pragma: no cover - we are the only writer, and we write a pid
        return 0


def _redirect(log_fd: int) -> None:
    """Point stdin at /dev/null and stdout/stderr at ``log_fd``.

    Done after the last fork, so nothing the original process printed is
    redirected, and at the fd level rather than by rebinding ``sys.stdout``, so
    output from C extensions and from anything the daemon spawns lands in the
    same file.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    devnull = os.open(os.devnull, os.O_RDONLY)
    try:
        os.dup2(devnull, 0)
    finally:
        os.close(devnull)
    os.dup2(log_fd, 1)
    os.dup2(log_fd, 2)
    if log_fd > 2:
        os.close(log_fd)


def _reap(pid: int) -> None:
    """Wait for the intermediate child, which exits as soon as it has forked."""
    try:
        os.waitpid(pid, 0)
    except OSError:  # pragma: no cover - already reaped, or no such child
        pass
