"""The single-instance lock the poller's pidfile carries (issue-159).

The bug this guards: nothing stopped two pollers from running against one
ledger. Both would read a work-item record on first touch and write it back
later, interleaving read-modify-write and re-forwarding each other's comments —
so ``poll stop && poll start``, a supervisor restarting early, or two
overlapping cron ``--once`` runs made a restart *observable*, which is the
opposite of what issue #159 asks for.

The lock is the pidfile, which is what makes ``stop`` honest too: being able to
take it proves nobody is running (so a pid left by a ``SIGKILL`` is never
signalled), and waiting for it to be released proves the poller has exited.

The interesting assertions are the ones a pid-liveness heuristic would fail:
the lock survives being probed, is released by the *kernel* when a holder dies
by any means, and reports a stale pidfile as free.

Pure stdlib: a real ``fork`` for the process-death case, no fixtures, no network.
"""

from __future__ import annotations

import os
import time

import pytest

from the_loop.runlock import HAVE_FLOCK, RunLock

pytestmark = pytest.mark.skipif(
    not HAVE_FLOCK, reason="flock is unavailable on this platform"
)


def test_acquire_writes_the_pid_and_release_removes_the_file(tmp_path):
    path = tmp_path / "poll.pid"
    lock = RunLock(path, name="poller")

    assert lock.acquire() is True
    assert lock.held is True
    assert path.read_text().strip() == str(os.getpid())
    assert lock.holder() == os.getpid()

    lock.release()
    assert lock.held is False
    assert not path.exists()


def test_acquire_creates_missing_parent_directories(tmp_path):
    lock = RunLock(tmp_path / "nested" / "deeper" / "poll.pid")
    assert lock.acquire() is True
    lock.release()


def test_a_second_lock_on_the_same_file_is_refused(tmp_path):
    """The property the whole change rests on, within one process."""
    path = tmp_path / "poll.pid"
    first, second = RunLock(path), RunLock(path)
    assert first.acquire() is True

    assert second.acquire() is False
    assert second.held is False
    # Refusing must not disturb the holder's own record.
    assert path.read_text().strip() == str(os.getpid())

    first.release()
    assert second.acquire() is True
    second.release()


def test_locks_on_different_files_are_independent(tmp_path):
    """Scoped to the state root (AC1.3): two roots, two pollers, both fine."""
    one = RunLock(tmp_path / "a" / "poll.pid")
    two = RunLock(tmp_path / "b" / "poll.pid")
    assert one.acquire() and two.acquire()
    one.release()
    two.release()


def test_is_held_is_true_only_while_somebody_holds_it(tmp_path):
    path = tmp_path / "poll.pid"
    probe = RunLock(path)
    assert probe.is_held() is False  # no file at all

    holder = RunLock(path)
    holder.acquire()
    assert probe.is_held() is True
    # Probing must be non-destructive: the holder still holds it afterwards.
    assert probe.is_held() is True
    assert RunLock(path).acquire() is False

    holder.release()
    assert probe.is_held() is False


def test_a_stale_pidfile_is_not_held_and_is_re_acquirable(tmp_path):
    """AC1.4 — a crash must not require manual cleanup before the next start."""
    path = tmp_path / "poll.pid"
    path.write_text("424242\n")  # a pid nobody is running, left by a SIGKILL

    probe = RunLock(path)
    assert probe.is_held() is False
    assert probe.holder() == 424242  # advisory only — see is_held

    fresh = RunLock(path)
    assert fresh.acquire() is True
    assert path.read_text().strip() == str(os.getpid())
    fresh.release()


def test_a_corrupt_pidfile_reports_no_holder_but_still_locks(tmp_path):
    path = tmp_path / "poll.pid"
    path.write_text("not-a-pid")
    lock = RunLock(path)
    assert lock.holder() == 0
    assert lock.acquire() is True
    assert lock.holder() == os.getpid()
    lock.release()


def test_the_kernel_releases_the_lock_when_the_holder_dies(tmp_path):
    """AC1.5 — nothing can strand the lock, including SIGKILL.

    A real child process takes the lock and is killed without a chance to clean
    up; the parent must then see the file as free. This is the property that
    makes a crashed poller recoverable with no operator action, and the one a
    ``try/finally`` cleanup could never provide.
    """
    path = tmp_path / "poll.pid"
    ready_r, ready_w = os.pipe()
    pid = os.fork()
    if pid == 0:  # pragma: no cover - child process
        try:
            os.close(ready_r)
            child_lock = RunLock(path)
            os.write(ready_w, b"1" if child_lock.acquire() else b"0")
            time.sleep(30)
        finally:
            os._exit(0)

    os.close(ready_w)
    try:
        assert os.read(ready_r, 1) == b"1"
        assert RunLock(path).is_held() is True
        assert RunLock(path).holder() == pid

        os.kill(pid, 9)
        os.waitpid(pid, 0)

        assert RunLock(path).is_held() is False
        recovered = RunLock(path)
        assert recovered.acquire() is True
        recovered.release()
    finally:
        os.close(ready_r)


def test_wait_until_free_returns_immediately_when_nothing_holds_it(tmp_path):
    lock = RunLock(tmp_path / "poll.pid")
    started = time.monotonic()
    assert lock.wait_until_free(timeout=5.0) is True
    assert time.monotonic() - started < 1.0


def test_wait_until_free_times_out_while_a_holder_persists(tmp_path):
    """AC2.3 — `stop` must never report a success that has not happened."""
    path = tmp_path / "poll.pid"
    holder = RunLock(path)
    holder.acquire()
    try:
        assert RunLock(path).wait_until_free(timeout=0.2, interval=0.05) is False
    finally:
        holder.release()


def test_wait_until_free_notices_a_release(tmp_path):
    """AC2.2 — `stop` returns when the poller is gone, not when the signal is sent."""
    path = tmp_path / "poll.pid"
    holder = RunLock(path)
    holder.acquire()

    import threading

    threading.Timer(0.1, holder.release).start()
    assert RunLock(path).wait_until_free(timeout=5.0, interval=0.02) is True


def test_context_manager_acquires_and_releases(tmp_path):
    path = tmp_path / "poll.pid"
    with RunLock(path) as lock:
        assert lock.held and path.exists()
    assert not path.exists()


def test_context_manager_raises_when_the_lock_is_taken(tmp_path):
    path = tmp_path / "poll.pid"
    holder = RunLock(path)
    holder.acquire()
    try:
        with pytest.raises(RuntimeError, match="held by another process"):
            with RunLock(path):
                pass  # pragma: no cover - never entered
    finally:
        holder.release()


def test_release_is_idempotent(tmp_path):
    lock = RunLock(tmp_path / "poll.pid")
    lock.release()  # never acquired
    lock.acquire()
    lock.release()
    lock.release()


def test_acquire_is_idempotent_for_the_holder(tmp_path):
    lock = RunLock(tmp_path / "poll.pid")
    assert lock.acquire() is True
    assert lock.acquire() is True  # already ours; not a second lock
    assert lock.is_held() is False  # "another process holds it" — we are not another
    lock.release()


def test_acquire_raises_when_the_path_cannot_be_opened(tmp_path):
    """A poller that cannot prove exclusivity must not run (design §Error handling).

    The lockfile's "directory" is a regular file, so neither the mkdir nor the
    open can succeed — an OSError the caller turns into a refusal to start,
    never a silent unlocked run.
    """
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("")
    with pytest.raises(OSError):
        RunLock(blocker / "poll.pid").acquire()


def test_probing_a_file_that_vanishes_reports_not_held(tmp_path, monkeypatch):
    """A probe whose file disappears means "nobody holds it", not the reverse.

    `is_held` checks for the file and then opens it; between the two a holder
    can finish releasing. Reporting True there would make `poll stop` signal a
    pid that has already gone.
    """
    path = tmp_path / "poll.pid"
    path.write_text("424242\n")
    lock = RunLock(path)

    def vanished(self, create=True):
        raise FileNotFoundError(path)

    monkeypatch.setattr(RunLock, "_open_locked", vanished)
    assert lock.is_held() is False


def test_a_replaced_lockfile_is_re_probed_rather_than_trusted(tmp_path):
    """The stale-inode race: locking an orphaned inode must not count.

    A holder releasing unlinks the path and then closes its fd. A process that
    opened the file in between would lock the *orphaned* inode — and, without
    the inode check, believe it held a lock a third process could take on the
    new file at the same path.
    """
    path = tmp_path / "poll.pid"
    orphan = RunLock(path)
    assert orphan.acquire() is True
    # Simulate the release having unlinked the file while the fd stays open:
    # a different process has since created and locked a fresh one there.
    path.unlink()
    successor = RunLock(path)
    assert successor.acquire() is True
    try:
        # The orphan's fd still holds a lock — on an inode nobody can reach.
        # A probe must report the *current* file's holder, not that one.
        assert RunLock(path).is_held() is True
        assert RunLock(path).acquire() is False
    finally:
        orphan.release()
        successor.release()
