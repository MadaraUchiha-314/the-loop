"""Core capability: the ingress daemons' lifecycle and status (issue-161).

Status is read straight off each daemon's pidfile lock (the flock discipline of
issue-159 — ``is_held`` answers race-free, ``holder`` is advisory). Start/stop
run through the CLI's own verbs as the same transitional adapter
:mod:`the_loop.core.sessions` uses, for the same reason: those verbs already
carry the whole lifecycle contract (lock acquisition, graceful stop-and-wait,
`already` outcomes) and must not be re-implemented.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from ..runlock import RunLock
from ..state import layout_from_config
from .sessions import SERVICE_LOCAL_ENV

DAEMONS = ("poller", "gh-webhook")

_VERBS: Dict[str, Dict[str, list]] = {
    "poller": {
        "start": ["poll", "start"],
        "stop": ["poll", "stop"],
    },
    "gh-webhook": {
        "start": ["gh-webhook", "start"],
        "stop": ["gh-webhook", "stop"],
    },
}


def _pidfile(daemon: str, config: Optional[dict] = None) -> str:
    layout = layout_from_config(config or {})
    if daemon == "poller":
        return str(Path(layout.root) / "poll.pid")
    if daemon == "gh-webhook":
        return layout.pidfile
    raise ValueError(f"unknown daemon {daemon!r} (one of {DAEMONS})")


def daemon_status(daemon: str, config: Optional[dict] = None) -> Dict[str, Any]:
    """``{daemon, running, pid, pidfile}`` — pid is advisory (issue-159)."""
    pidfile = _pidfile(daemon, config)
    lock = RunLock(pidfile, name=daemon)
    running = lock.is_held()
    return {
        "daemon": daemon,
        "running": running,
        "pid": lock.holder() if running else 0,
        "pidfile": pidfile,
    }


def control_daemon(
    daemon: str, verb: str, config: Optional[dict] = None, timeout: float = 120.0
) -> Dict[str, Any]:
    """Start or stop a daemon through its own CLI verb (argv, no shell).

    Both daemons run in the foreground by design (operators background them), so
    ``start`` spawns **detached** — its own session, output to the daemon's own
    logging — and reports the spawn; the daemon's pidfile lock remains the truth
    about whether it stayed up (poll it via :func:`daemon_status`). ``stop`` is
    the daemon's own graceful stop-and-wait verb and is waited on.
    """
    if verb not in ("start", "stop"):
        raise ValueError(f"unknown daemon verb {verb!r} (start|stop)")
    pidfile = _pidfile(daemon, config)  # validates the daemon name
    argv = [sys.executable, "-m", "the_loop", *_VERBS[daemon][verb]]
    env = {**os.environ, SERVICE_LOCAL_ENV: "1"}
    if verb == "start":
        if RunLock(pidfile, name=daemon).is_held():
            return {
                "daemon": daemon,
                "verb": verb,
                "exitCode": 0,
                "output": "already running",
            }
        proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
        return {
            "daemon": daemon,
            "verb": verb,
            "exitCode": 0,
            "output": f"spawned pid {proc.pid}",
        }
    proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
        argv, capture_output=True, text=True, timeout=timeout, env=env
    )
    return {
        "daemon": daemon,
        "verb": verb,
        "exitCode": proc.returncode,
        "output": (proc.stdout + proc.stderr).strip(),
    }
