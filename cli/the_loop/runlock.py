"""An advisory single-instance lock, held on a daemon's own pidfile (issue-159).

The poller's per-work-item ledger was built to be idempotent across restarts
(``the_loop.poller.PollState``), but nothing stopped **two** pollers from running
against it. ``poll stop && poll start``, a supervisor restarting before the old
process has exited, two terminals, or two overlapping ``--once`` runs from cron
all produce a pair of pollers sharing one ledger — and since a record is read on
first touch and written back later, they interleave read-modify-write and
re-forward each other's comments. Exclusion is what makes a restart invisible.

**The lock is the pidfile.** Not a lock file *beside* one: "who is running" and
"how do I signal them" have to be one fact, or they disagree — and that
disagreement is the second half of the bug. A stale pidfile left by a ``SIGKILL``
currently makes ``poll stop`` send ``SIGTERM`` to whatever process now owns that
pid. Here the pid is only ever signalled when the lock proves a live daemon holds
it.

``flock`` is the mechanism, for three properties no liveness heuristic has:

* **the kernel releases it** when the fd closes — on exit, on ``SIGKILL``, on a
  host reboot. Nothing can strand it, so a leftover pidfile is simply *unlocked*
  and the next start takes it with no manual cleanup;
* **it is per inode**, so two daemons with different ``state.root`` values are
  independent with no naming scheme to invent;
* **"can I take it?" is a total, race-free answer** to "is one running?" — which
  ``os.kill(pid, 0)`` is not, because pid reuse makes it say yes about a stranger.

The pid is written **after** the lock is held, so a reader never sees the pid of
a process that lost the race.

Spec: docs/specs/issue-159/design.md §1.
"""

from __future__ import annotations

import errno
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("the-loop.runlock")

__all__ = ["HAVE_FLOCK", "RunLock"]

#: ``fcntl`` when this platform has it, else ``None`` (see :func:`RunLock._lock`).
#: Deliberately untyped so the two branches below read as one module-level fact.
fcntl: Any
try:  # POSIX only. the-loop's runner requires tmux, so this is effectively always on.
    import fcntl as _fcntl_module

    fcntl = _fcntl_module
    HAVE_FLOCK = True
except ImportError:  # pragma: no cover - not reachable on a supported platform
    fcntl = None
    HAVE_FLOCK = False


def _pid_alive(pid: int) -> bool:
    """Whether ``pid`` names a live process this user may signal.

    Only used by the non-POSIX fallback. Weaker than ``flock`` — pid reuse can
    make it say yes about an unrelated process — but never weaker than trusting
    the pidfile unconditionally, which is what it replaces.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # alive, owned by somebody else
        return True
    except OSError:
        return False
    return True


class RunLock:
    """Exclusive advisory lock on ``path``, which doubles as the pidfile.

    Held for the lifetime of the daemon and released by :meth:`release` (or by
    the OS, whichever comes first). Not reentrant and not thread-safe: one
    process, one lock, taken once at startup.
    """

    def __init__(self, path: os.PathLike | str, name: str = "daemon"):
        self.path = Path(path)
        self.name = name
        self._fd: Optional[int] = None

    # -- taking it -------------------------------------------------------------

    @property
    def held(self) -> bool:
        """Whether *this* object currently holds the lock."""
        return self._fd is not None

    def acquire(self) -> bool:
        """Take the lock and record this process's pid. False when someone else holds it.

        Raises ``OSError`` when the file cannot be created or locked for any
        reason other than contention — a daemon that cannot prove exclusivity
        must not run, so this is deliberately not swallowed.
        """
        if self._fd is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = self._open_locked()
        if fd is None:
            return False
        # Locked: only now is the pid ours to publish.
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        os.fsync(fd)
        self._fd = fd
        return True

    def _open_locked(self, create: bool = True) -> Optional[int]:
        """An fd on ``path`` holding the lock, or ``None`` when someone else does.

        Retries on a **stale inode**, which is the one race a naive
        open-then-flock has: a holder releasing unlinks the path and then closes
        its fd, so a process that opened the file in between would lock an
        orphaned inode — and believe it holds a lock a third process could take
        on the *new* file at the same path. Comparing the locked fd's inode with
        the one the path names now closes that window; the loop is bounded
        because each retry means somebody else completed a release.
        """
        flags = os.O_RDWR | (os.O_CREAT if create else 0)
        for _ in range(5):
            # A missing file propagates as OSError rather than becoming a
            # ``None``: ``None`` means "somebody else holds it", and a probe
            # (``create=False``) whose file has vanished means the opposite.
            fd = os.open(str(self.path), flags, 0o644)
            try:
                if not self._lock(fd):
                    os.close(fd)
                    return None
                if self._is_current(fd):
                    return fd
            except BaseException:
                os.close(fd)
                raise
            os.close(fd)  # stale inode — the path has been replaced; look again
        logger.warning(
            "%s lock %s kept being replaced while acquiring it; giving up this attempt",
            self.name,
            self.path,
        )
        return None

    def _is_current(self, fd: int) -> bool:
        """Whether the locked ``fd`` is still the file ``path`` names."""
        try:
            return os.fstat(fd).st_ino == os.stat(str(self.path)).st_ino
        except OSError:  # unlinked from under us — definitively not current
            return False

    def _lock(self, fd: int) -> bool:
        """Non-blocking exclusive lock on ``fd``; False when it is contended."""
        if not HAVE_FLOCK:
            logger.debug(
                "flock is unavailable on this platform; %s falls back to a "
                "pid-liveness check, which cannot detect pid reuse",
                self.name,
            )
            return not _pid_alive(self._read_pid())
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                return False
            raise
        return True

    def release(self) -> None:
        """Drop the lock and remove the pidfile. Safe to call when not held."""
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            self.path.unlink()
        except OSError:  # already gone, or not ours to remove — never fatal
            pass
        try:
            os.close(fd)  # releases the flock
        except OSError:  # pragma: no cover - closing a valid fd does not fail
            pass

    def __enter__(self) -> "RunLock":
        if not self.acquire():
            raise RuntimeError(
                f"{self.name} lock {self.path} is held by another process"
            )
        return self

    def __exit__(self, *_exc) -> None:
        self.release()

    # -- asking about it -------------------------------------------------------

    def _read_pid(self) -> int:
        try:
            return int(self.path.read_text().strip() or 0)
        except (OSError, ValueError):
            return 0

    def holder(self) -> int:
        """The pid recorded in the file, or ``0`` when there is none to read.

        Advisory: it says who *wrote* the file, and is only trustworthy about who
        is *running* when :meth:`is_held` agrees.
        """
        return self._read_pid()

    def is_held(self) -> bool:
        """Whether another process holds the lock right now.

        Implemented as "try to take it, and give it straight back if I could",
        which is the only honest formulation on POSIX — and, unlike probing the
        recorded pid, immune to pid reuse. Returns False when the file does not
        exist, or exists but is unlocked (a stale pidfile).
        """
        if self._fd is not None:
            return False  # we hold it, not "another process"
        if not self.path.exists():
            return False
        try:
            fd = self._open_locked(create=False)
        except OSError:
            return False
        if fd is None:
            return True
        if HAVE_FLOCK:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        return False

    def wait_until_free(self, timeout: float, interval: float = 0.1) -> bool:
        """Block until nobody holds the lock; False when ``timeout`` runs out.

        What makes ``stop`` truthful: it returns when the daemon has actually
        gone, not when the signal was sent — so a scripted ``stop && start``
        cannot overlap the shutdown it just asked for.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            if not self.is_held():
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(max(0.01, interval))
