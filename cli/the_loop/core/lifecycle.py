"""Core capability: the whole system's lifecycle (issue-228, decision-084).

One composition point for "bring the-loop up/down": which services the CLI
config enables (`service.enabled`, `webhooks.ghWebhook.enabled`,
`polling.enabled`, with the MCP layer a flag *on* the service), starting each
enabled one detached, stopping every running one, and reporting both — the
functions behind ``the-loop start|stop|status|restart`` and
``POST /api/v1/restart``.

Nothing here runs a service; it composes the runtimes that exist. The two
ingress daemons go through :mod:`the_loop.core.daemons` (which spawns
``the_loop.daemon_entry``); the control-plane service is spawned the way
it always has been (``python -m the_loop.api.serve``) and
probed over ``/health``. A daemon's successful start is proven by **waiting for
its pidfile lock to be held** — the honest-start property the removed
``poll start --daemon`` handshake provided, without the double-fork.

``stop`` deliberately ignores the ``enabled`` flags (R3.1): a service disabled
*after* it was started must still be stoppable. ``status``'s ``ok`` means
"every enabled service is running", which is what makes ``the-loop status``
scriptable as a health check.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import eventlog
from ..api.config import base_url, service_config, service_pidfile
from ..daemonize import open_logfile
from ..runlock import RunLock
from ..state import layout_from_config
from . import daemons as core_daemons

#: Start order. The service first, so anything the daemons spawn can reach it;
#: :func:`stop_all` walks it reversed.
SERVICES = ("service", "gh-webhook", "poller")

#: How long ``start`` waits for the service's /health.
SERVICE_START_TIMEOUT_SECONDS = 15.0
#: How long ``start`` waits for a spawned daemon to hold its pidfile lock.
DAEMON_START_TIMEOUT_SECONDS = 10.0
#: How long ``stop`` waits for the service to release its lock.
SERVICE_STOP_TIMEOUT_SECONDS = 30.0
#: How long ``stop`` waits for a hosted ingress's lock after the service exits.
#: Short: the service's own stop already waited for the whole process, so this
#: only covers the release racing the process's last breath (issue-231).
STOP_TIMEOUT_HOSTED_SECONDS = 5.0


def _webhook_enabled(config: Optional[dict]) -> bool:
    return bool(
        (((config or {}).get("webhooks") or {}).get("ghWebhook") or {}).get(
            "enabled", False
        )
    )


def _polling(config: Optional[dict]) -> dict:
    return ((config or {}).get("polling")) or {}


def enabled_services(config: Optional[dict] = None) -> Dict[str, bool]:
    """Which services the config asks ``start`` to compose (decision-084 D1)."""
    conf = service_config(config)
    return {
        "service": conf["enabled"],
        "gh-webhook": _webhook_enabled(config),
        "poller": bool(_polling(config).get("enabled", False)),
    }


def _row(service: str, enabled: bool, outcome: str, detail: str = "") -> Dict[str, Any]:
    return {
        "service": service,
        "enabled": enabled,
        "outcome": outcome,
        "detail": detail,
    }


def _service_lock(config: Optional[dict]) -> RunLock:
    return RunLock(service_pidfile(config), name="service")


def _healthy(config: Optional[dict]) -> bool:
    from .. import client

    return client.healthy(config)


def spawn_service() -> "subprocess.Popen[bytes]":
    """Spawn the control-plane service, detached — the one service spawn."""
    return subprocess.Popen(  # noqa: S603 — fixed argv, no shell
        [sys.executable, "-m", "the_loop.api.serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def start_service(config: Optional[dict] = None) -> Dict[str, Any]:
    """Start the control-plane service and wait for /health (idempotent)."""
    lock = _service_lock(config)
    if lock.is_held():
        return {
            "running": True,
            "pid": lock.holder(),
            "detail": f"already running (pid {lock.holder()}) at {base_url(config)}",
            "started": False,
        }
    spawn_service()
    deadline = time.monotonic() + SERVICE_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _healthy(config):
            return {
                "running": True,
                "pid": lock.holder(),
                "detail": f"started at {base_url(config)}",
                "started": True,
            }
        time.sleep(0.25)
    return {
        "running": False,
        "pid": 0,
        "detail": (
            "did not become healthy; check the event log "
            "(`the-loop events --source service`)"
        ),
        "started": False,
    }


def stop_service(
    config: Optional[dict] = None, timeout: float = SERVICE_STOP_TIMEOUT_SECONDS
) -> Dict[str, Any]:
    """Stop the control-plane service and wait for it to exit (idempotent)."""
    lock = _service_lock(config)
    if not lock.is_held():
        return {"running": False, "pid": 0, "detail": "not running", "stopped": False}
    pid = lock.holder()
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    if lock.wait_until_free(timeout):
        return {
            "running": False,
            "pid": pid,
            "detail": f"stopped (pid {pid})",
            "stopped": True,
        }
    return {
        "running": True,
        "pid": pid,
        "detail": f"did not exit within {timeout:.0f}s",
        "stopped": False,
    }


def _start_daemon(daemon: str, config: Optional[dict]) -> Dict[str, Any]:
    """Start an ingress daemon and wait for its lock — the honest start."""
    lock = RunLock(core_daemons._pidfile(daemon, config), name=daemon)
    if lock.is_held():
        return _row(daemon, True, "already-running", f"pid {lock.holder()}")
    result = core_daemons.control_daemon(daemon, "start", config)
    deadline = time.monotonic() + DAEMON_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if lock.is_held():
            return _row(daemon, True, "started", result["output"])
        time.sleep(0.1)
    # A daemon that never took its lock exited during startup (bad config,
    # missing dependency, contended bind) — its reasons are in the logfile.
    return _row(
        daemon,
        True,
        "failed",
        f"did not come up; see {core_daemons._logfile(daemon, config)}",
    )


def _await_hosted(
    daemon: str, config: Optional[dict], service_pid: int
) -> Dict[str, Any]:
    """The honest start for an ingress the *service* hosts (issue-231).

    Nothing is spawned here: the service's lifespan starts the ingress on a
    thread and takes its per-ingress pidfile lock under the service's own pid.
    Waiting for that lock is the same proof `_start_daemon` uses; the holder's
    pid tells hosted (== the service's) apart from a standalone daemon that
    was already running (anything else).
    """
    lock = RunLock(core_daemons._pidfile(daemon, config), name=daemon)
    deadline = time.monotonic() + DAEMON_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if lock.is_held():
            holder = lock.holder()
            if service_pid and holder == service_pid:
                return _row(
                    daemon, True, "hosted", f"in the service process (pid {holder})"
                )
            return _row(daemon, True, "already-running", f"standalone, pid {holder}")
        time.sleep(0.1)
    return _row(
        daemon,
        True,
        "failed",
        "the service did not host it; check `the-loop events --source service`",
    )


def start_all(config: Optional[dict] = None) -> Dict[str, Any]:
    """Start every enabled service, reporting per service (R1).

    One service's failure never hides the others' outcomes (R1.4); ``ok`` is
    "every enabled service ended up running".
    """
    enabled = enabled_services(config)
    conf = service_config(config)
    rows: List[Dict[str, Any]] = []
    # issue-231: with the service enabled and `service.hostIngresses` (the
    # default), the enabled ingresses run *inside* the service process — one
    # pid — so nothing is spawned for them here; their honest start is waiting
    # for the per-ingress lock the service takes while hosting them. With the
    # service disabled (or the mode off), they spawn standalone as before.
    hosting = enabled["service"] and conf["hostIngresses"]
    service_up = False
    service_pid = 0

    if not enabled["service"]:
        rows.append(_row("service", False, "disabled", "service.enabled is false"))
    else:
        try:
            outcome = start_service(config)
            service_up = bool(outcome["running"])
            service_pid = int(outcome["pid"] or 0)
            mcp = (
                "/mcp exposed"
                if conf["mcpEnabled"]
                else "MCP disabled (service.mcp.enabled)"
            )
            rows.append(
                _row(
                    "service",
                    True,
                    (
                        "started"
                        if outcome["started"]
                        else ("already-running" if outcome["running"] else "failed")
                    ),
                    f"{outcome['detail']}; {mcp}",
                )
            )
        except Exception as exc:  # noqa: BLE001 — isolate per-service failures (R1.4)
            rows.append(_row("service", True, "failed", str(exc)))

    def _ingress_row(daemon: str) -> Dict[str, Any]:
        if hosting:
            if not service_up:
                return _row(
                    daemon,
                    True,
                    "failed",
                    "the service hosts the ingresses (service.hostIngresses) "
                    "and did not come up",
                )
            return _await_hosted(daemon, config, service_pid)
        return _start_daemon(daemon, config)

    if not enabled["gh-webhook"]:
        rows.append(
            _row("gh-webhook", False, "disabled", "webhooks.ghWebhook.enabled is false")
        )
    else:
        try:
            rows.append(_ingress_row("gh-webhook"))
        except Exception as exc:  # noqa: BLE001
            rows.append(_row("gh-webhook", True, "failed", str(exc)))

    if not enabled["poller"]:
        rows.append(_row("poller", False, "disabled", "polling.enabled is false"))
    elif not (_polling(config).get("sources") or []):
        # Caught at plan time rather than as a spawn whose failure lands only
        # in a logfile: an enabled poller with nothing to poll is a config
        # contradiction the operator should hear about on their terminal.
        rows.append(
            _row(
                "poller",
                True,
                "misconfigured",
                "polling.enabled is true but polling.sources is empty",
            )
        )
    else:
        try:
            rows.append(_ingress_row("poller"))
        except Exception as exc:  # noqa: BLE001
            rows.append(_row("poller", True, "failed", str(exc)))

    ok = all(
        row["outcome"] in ("started", "already-running", "hosted", "disabled")
        for row in rows
    )
    return {"services": rows, "ok": ok}


def stop_all(config: Optional[dict] = None) -> Dict[str, Any]:
    """Stop every running service, reverse start order, ignoring ``enabled``.

    An ingress whose lock is held by the **service's own pid** is hosted
    (issue-231): it is not signalled directly — SIGTERM to that pid is the
    service's shutdown — but stopped *by* stopping the service, and its row is
    reported only once its lock has actually been released.
    """
    by_name: Dict[str, Dict[str, Any]] = {}
    enabled = enabled_services(config)
    service_lock = _service_lock(config)
    service_pid = service_lock.holder() if service_lock.is_held() else 0
    hosted: List[str] = []
    for daemon in ("poller", "gh-webhook"):
        try:
            lock = RunLock(core_daemons._pidfile(daemon, config), name=daemon)
            if service_pid and lock.is_held() and lock.holder() == service_pid:
                hosted.append(daemon)
                continue
            result = core_daemons.control_daemon(daemon, "stop", config)
            outcome = (
                "stopped"
                if result["exitCode"] == 0 and result["pid"]
                else ("not-running" if result["exitCode"] == 0 else "failed")
            )
            by_name[daemon] = _row(daemon, enabled[daemon], outcome, result["output"])
        except Exception as exc:  # noqa: BLE001
            by_name[daemon] = _row(daemon, enabled[daemon], "failed", str(exc))
    try:
        outcome = stop_service(config)
        by_name["service"] = _row(
            "service",
            enabled["service"],
            (
                "stopped"
                if outcome["stopped"]
                else ("not-running" if not outcome["running"] else "failed")
            ),
            outcome["detail"],
        )
    except Exception as exc:  # noqa: BLE001
        by_name["service"] = _row("service", enabled["service"], "failed", str(exc))
    for daemon in hosted:
        lock = RunLock(core_daemons._pidfile(daemon, config), name=daemon)
        freed = lock.wait_until_free(STOP_TIMEOUT_HOSTED_SECONDS)
        by_name[daemon] = _row(
            daemon,
            enabled[daemon],
            "stopped" if freed else "failed",
            (
                f"was hosted in the service (pid {service_pid}); stopped with it"
                if freed
                else "hosted lock still held after the service stopped"
            ),
        )
    rows = [by_name[name] for name in ("poller", "gh-webhook", "service")]
    ok = all(row["outcome"] in ("stopped", "not-running") for row in rows)
    return {"services": rows, "ok": ok}


def status_all(config: Optional[dict] = None) -> Dict[str, Any]:
    """Per-service status; ``ok`` means every enabled service is running (R3.3)."""
    enabled = enabled_services(config)
    conf = service_config(config)
    lock = _service_lock(config)
    running = lock.is_held()
    rows: List[Dict[str, Any]] = [
        {
            "service": "service",
            "enabled": enabled["service"],
            "running": running,
            "pid": lock.holder() if running else 0,
            "url": base_url(config),
            "healthy": _healthy(config) if running else False,
            "mcp": {"enabled": conf["mcpEnabled"], "path": "/mcp"},
        }
    ]
    for daemon in ("gh-webhook", "poller"):
        status = core_daemons.daemon_status(daemon, config)
        status["service"] = status.pop("daemon")
        status["enabled"] = enabled[daemon]
        # issue-231: an ingress whose lock is held by the service's own pid is
        # running *inside* the service — reported as such, so an operator can
        # tell one process hosting three services from three processes.
        status["hosted"] = bool(
            running and status["running"] and status["pid"] == rows[0]["pid"]
        )
        rows.append(status)
    # The poller's progress beyond liveness (issue-191): the counters and
    # interval `poll status` used to report travel with the row, so removing
    # the command lost no fact (R2.4). Liveness stays the lock's answer alone.
    from ..poller.heartbeat import PollHeartbeat

    beat = PollHeartbeat.read(layout_from_config(config or {}).poll_status)
    rows[-1]["lastCycle"] = dict(beat.last_cycle) if beat else {}
    rows[-1]["intervalSeconds"] = beat.interval_seconds if beat else 0
    ok = all(row["running"] for row in rows if row["enabled"])
    return {"services": rows, "ok": ok}


def restart_logfile(config: Optional[dict] = None) -> str:
    """Where a scheduled restart's output goes (R4.5)."""
    return str(Path(layout_from_config(config or {}).root) / "logs" / "restart.out")


def schedule_restart(
    config: Optional[dict] = None,
    with_upgrade: bool = False,
    config_path: Optional[os.PathLike] = None,
) -> Dict[str, Any]:
    """Spawn a detached ``the-loop restart`` and return at once (R4.4).

    The service calls this to restart *itself*: it cannot stop synchronously
    and still answer, so the API's contract is scheduling. The argv is fixed —
    nothing caller-supplied beyond one boolean — and ``config_path`` is only
    ever the path this process already reads (the issue-222 property: no
    request can name another file).
    """
    logfile = restart_logfile(config)
    argv = [sys.executable, "-m", "the_loop"]
    if config_path is not None:
        argv += ["--config", str(config_path)]
    argv.append("restart")
    if with_upgrade:
        argv.append("--with-upgrade")
    log_fd = open_logfile(logfile)
    try:
        proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
            argv,
            stdout=log_fd,
            stderr=log_fd,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    finally:
        os.close(log_fd)
    eventlog.emit(
        "restart.scheduled",
        pid=proc.pid,
        withUpgrade=with_upgrade or None,
        logfile=logfile,
    )
    return {
        "scheduled": True,
        "pid": proc.pid,
        "withUpgrade": with_upgrade,
        "logfile": logfile,
    }
