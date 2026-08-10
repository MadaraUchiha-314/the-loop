"""Core capability: the ingress daemons' lifecycle and status (issue-161).

Status reads the daemon's pidfile lock directly (the flock discipline of
issue-159 — ``is_held`` answers race-free under pid reuse). **Stop** signals
and waits here, in core, with no subprocess at all. **Start** spawns
:mod:`the_loop.daemon_entry`, a core-owned entry point, rather than shelling
out to the-loop's own CLI verb — the transitional adapter the owner asked us to
remove (PR #162). A daemon is a long-lived process by nature, so a detached
spawn is inherent; what changed is that it no longer round-trips through the
command surface.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from ..daemonize import open_logfile
from ..poller.heartbeat import PollHeartbeat
from ..runlock import RunLock
from ..state import layout_from_config

DAEMONS = ("poller", "gh-webhook")

#: How long ``stop`` waits for the daemon to actually exit.
STOP_TIMEOUT_SECONDS = 30.0


def _pidfile(daemon: str, config: Optional[dict] = None) -> str:
    layout = layout_from_config(config or {})
    if daemon == "poller":
        return layout.poll_pidfile
    if daemon == "gh-webhook":
        return layout.pidfile
    raise ValueError(f"unknown daemon {daemon!r} (one of {DAEMONS})")


def _logfile(daemon: str, config: Optional[dict] = None) -> str:
    """Where a daemon started from here sends its stdout/stderr (issue-191).

    It used to be ``/dev/null``, which is the same defect the poller had when it
    was backgrounded by hand: a daemon that runs fine and logs nowhere. The
    receiver has no logfile of its own yet, so it lands beside the poller's under
    ``logs/``.
    """
    layout = layout_from_config(config or {})
    if daemon == "poller":
        return layout.poller_log
    if daemon == "gh-webhook":
        return str(Path(layout.root) / "logs" / "gh-webhook.out")
    raise ValueError(f"unknown daemon {daemon!r} (one of {DAEMONS})")


def daemon_status(daemon: str, config: Optional[dict] = None) -> Dict[str, Any]:
    """``{daemon, running, pid, pidfile, logfile, startedAt, lastCycleAt}``.

    ``pid`` is advisory (issue-159): it is what the pidfile records, and only
    trustworthy about who is *running* when ``running`` agrees. ``startedAt`` and
    ``lastCycleAt`` come from the poller's heartbeat (issue-191) and are empty for
    ``gh-webhook``, which keeps none — saying so is more useful to a client than
    omitting the keys for one daemon and not the other.
    """
    pidfile = _pidfile(daemon, config)
    lock = RunLock(pidfile, name=daemon)
    running = lock.is_held()
    beat = (
        PollHeartbeat.read(layout_from_config(config or {}).poll_status)
        if daemon == "poller"
        else None
    )
    return {
        "daemon": daemon,
        "running": running,
        "pid": lock.holder() if running else 0,
        "pidfile": pidfile,
        "logfile": _logfile(daemon, config),
        "startedAt": beat.started_at if beat else "",
        "lastCycleAt": beat.last_cycle_at if beat else "",
    }


def control_daemon(
    daemon: str,
    verb: str,
    config: Optional[dict] = None,
    timeout: float = STOP_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Start or stop a daemon. Idempotent in both directions (issue-159)."""
    if verb not in ("start", "stop"):
        raise ValueError(f"unknown daemon verb {verb!r} (start|stop)")
    pidfile = _pidfile(daemon, config)  # validates the daemon name
    lock = RunLock(pidfile, name=daemon)

    if verb == "start":
        if lock.is_held():
            return {
                "daemon": daemon,
                "verb": verb,
                "running": True,
                "pid": lock.holder(),
                "exitCode": 0,
                "output": "already running",
            }
        logfile = _logfile(daemon, config)
        try:
            log_fd = open_logfile(logfile)
        except OSError as exc:
            raise ValueError(
                f"cannot open the {daemon} logfile {logfile}: {exc}"
            ) from exc
        try:
            proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
                [sys.executable, "-m", "the_loop.daemon_entry", daemon],
                stdout=log_fd,
                stderr=log_fd,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        finally:
            os.close(log_fd)
        return {
            "daemon": daemon,
            "verb": verb,
            "running": True,
            "pid": proc.pid,
            "exitCode": 0,
            "output": f"spawned pid {proc.pid}; logging to {logfile}",
        }

    # stop — signal the holder and wait for the lock to clear. No subprocess.
    if not lock.is_held():
        return {
            "daemon": daemon,
            "verb": verb,
            "running": False,
            "pid": 0,
            "exitCode": 0,
            "output": f"{daemon} is not running",
        }
    pid = lock.holder()
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError as exc:
        raise ValueError(f"cannot signal {daemon} (pid {pid}): {exc}") from exc
    if lock.wait_until_free(timeout):
        return {
            "daemon": daemon,
            "verb": verb,
            "running": False,
            "pid": pid,
            "exitCode": 0,
            "output": f"stopped {daemon} (pid {pid})",
        }
    return {
        "daemon": daemon,
        "verb": verb,
        "running": True,
        "pid": pid,
        "exitCode": 1,
        "output": f"{daemon} (pid {pid}) did not exit within {timeout:.0f}s",
    }
