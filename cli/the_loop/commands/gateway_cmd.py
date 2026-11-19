"""``the-loop gateway start|stop|status|restart|subjects|instances`` (issue-496, R9).

The gateway is run the way the service is: a pidfile under its own state root as the
lock, a logfile beside it, a foreground entry point (``python -m the_loop.gateway.serve``)
that ``start`` spawns detached and ``stop`` signals. ``status`` reports the pid, the
enabled ingresses, the Socket Mode connection state, the store path, the instances
fetched within the lease window and the keys that need a restart; ``subjects`` and
``instances`` render the gateway's read-only views (R9.2).

``--config`` here names the **gateway** config (``gateway-config.yaml``), not the CLI
config: these verbs read nothing of an instance's.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .. import strings
from ..daemonize import open_logfile
from ..gateway.config import (
    ConfigError,
    GatewayConfig,
    load_gateway_config,
    load_gateway_env_file,
)
from ..runlock import RunLock
from .base import Command, register

STOP_TIMEOUT_S = 15.0
START_TIMEOUT_S = 20.0


def running_base_url(config: GatewayConfig) -> str:
    """The address the running process bound, when it recorded one — the file's
    `listen` may already say otherwise while the change waits for a restart (R8.6)."""
    try:
        recorded = config.listen_file.read_text(encoding="utf-8").strip()
    except OSError:
        recorded = ""
    return f"http://{recorded}" if recorded else config.base_url


def _get(
    config: GatewayConfig, path: str, timeout: float = 3.0
) -> Optional[Dict[str, Any]]:
    url = f"{running_base_url(config)}/api/v1/gateway/{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 — loopback by default
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def status_report(config: GatewayConfig) -> Dict[str, Any]:
    lock = RunLock(str(config.pidfile), name="gateway")
    running = lock.is_held()
    health = _get(config, "health") if running else None
    instances = _get(config, "instances") if running else None
    now_live = [
        row["instance"]
        for row in (instances or {}).get("instances", [])
        if row.get("leaseLive")
    ]
    return {
        "running": running,
        "pid": lock.holder() if running else 0,
        "pidfile": str(config.pidfile),
        "logfile": str(config.logfile),
        "configPath": str(config.path),
        "listen": running_base_url(config).replace("http://", ""),
        "listenInFile": f"{config.listen.host}:{config.listen.port}",
        "store": str(config.store.path),
        "reachable": health is not None,
        "ingresses": (health or {}).get("ingresses", {}),
        "slackSocket": ((health or {}).get("slack") or {}).get("socket", "unknown"),
        # whether this gateway posts to Slack for its instances (issue-519, R6.2):
        # `on`, or the reason it does not
        "slackPosting": ((health or {}).get("slack") or {}).get("posting", "unknown"),
        "queues": ((health or {}).get("store") or {}).get("queues", {}),
        "held": ((health or {}).get("store") or {}).get("held", 0),
        "instancesLive": now_live,
        "restartRequired": (health or {}).get("restartRequired", []),
        # which declared secret NAMES resolve in this process's environment — names
        # and booleans only, never a value (security review SEC-10a)
        "secretsSet": {
            name: bool(os.environ.get(name)) for name in config.secret_names()
        },
    }


def start_gateway(
    config: GatewayConfig, *, wait: float = START_TIMEOUT_S
) -> Dict[str, Any]:
    lock = RunLock(str(config.pidfile), name="gateway")
    if lock.is_held():
        return {
            "verb": "start",
            "running": True,
            "pid": lock.holder(),
            "output": strings.t("cli.gateway.start.already-running"),
        }
    config.state_root.mkdir(parents=True, exist_ok=True)
    config.logfile.parent.mkdir(parents=True, exist_ok=True)
    log_fd = open_logfile(config.logfile)
    try:
        proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
            [
                sys.executable,
                "-m",
                "the_loop.gateway.serve",
                "--config",
                str(config.path),
            ],
            stdout=log_fd,
            stderr=log_fd,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=dict(os.environ),
        )
    finally:
        os.close(log_fd)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return {
                "verb": "start",
                "running": False,
                "pid": proc.pid,
                "exitCode": proc.returncode,
                "output": strings.t(
                    "cli.gateway.start.exited",
                    returncode=proc.returncode,
                    logfile=config.logfile,
                ),
            }
        if _get(config, "health", timeout=1.0) is not None:
            return {
                "verb": "start",
                "running": True,
                "pid": proc.pid,
                "output": strings.t(
                    "cli.gateway.start.spawned",
                    pid=proc.pid,
                    base_url=config.base_url,
                    logfile=config.logfile,
                ),
            }
        time.sleep(0.2)
    return {
        "verb": "start",
        "running": True,
        "pid": proc.pid,
        "output": strings.t(
            "cli.gateway.start.no-health",
            pid=proc.pid,
            wait=wait,
            logfile=config.logfile,
        ),
    }


def stop_gateway(
    config: GatewayConfig, *, timeout: Optional[float] = None
) -> Dict[str, Any]:
    """SIGTERM the process and wait for its pidfile. The gateway releases its
    long-polls on the signal, so the wait is short; the timeout still covers one full
    `consume.maxWaitSeconds` in case it cannot (an older process, say)."""
    if timeout is None:
        timeout = max(STOP_TIMEOUT_S, float(config.consume.max_wait_s) + 5.0)
    lock = RunLock(str(config.pidfile), name="gateway")
    if not lock.is_held():
        return {
            "verb": "stop",
            "running": False,
            "pid": 0,
            "output": strings.t("cli.gateway.stop.not-running"),
        }
    pid = lock.holder()
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    if lock.wait_until_free(timeout):
        return {
            "verb": "stop",
            "running": False,
            "pid": pid,
            "output": strings.t("cli.gateway.stop.stopped", pid=pid),
        }
    return {
        "verb": "stop",
        "running": True,
        "pid": pid,
        "output": strings.t("cli.gateway.stop.did-not-stop", pid=pid, timeout=timeout),
    }


def _table(rows: List[List[str]]) -> str:
    if not rows:
        return ""
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]
    return "\n".join(
        "  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
        for row in rows
    )


def subjects_lines(doc: Dict[str, Any]) -> List[str]:
    rows = [
        [
            strings.t("cli.gateway.subjects.header.subject"),
            strings.t("cli.gateway.subjects.header.claimants"),
            strings.t("cli.gateway.subjects.header.events"),
            strings.t("cli.gateway.subjects.header.held"),
            strings.t("cli.gateway.subjects.header.pending"),
            strings.t("cli.gateway.subjects.header.oldest"),
            strings.t("cli.gateway.subjects.header.dead"),
        ]
    ]
    for row in doc.get("subjects", []):
        claimants = (
            ", ".join(
                f"{c['instance']} ({c['role']})" for c in row.get("claimants", [])
            )
            or "-"
        )
        rows.append(
            [
                row["subject"],
                claimants,
                str(row.get("events", 0)),
                str(row.get("held", 0)),
                str(row.get("pending", 0)),
                _age(row.get("oldestPendingAt")),
                str(row.get("dead", 0)),
            ]
        )
    return (
        _table(rows).splitlines()
        if len(rows) > 1
        else [strings.t("cli.gateway.subjects.none")]
    )


def instances_lines(doc: Dict[str, Any]) -> List[str]:
    rows = [
        [
            strings.t("cli.gateway.instances.header.instance"),
            strings.t("cli.gateway.instances.header.lease"),
            strings.t("cli.gateway.instances.header.last-fetch"),
            strings.t("cli.gateway.instances.header.backlog"),
            strings.t("cli.gateway.instances.header.committed"),
            strings.t("cli.gateway.instances.header.actors"),
            strings.t("cli.gateway.instances.header.claims"),
        ]
    ]
    for row in doc.get("instances", []):
        actors = (
            ", ".join(
                f"{p}:{','.join(v)}" for p, v in (row.get("actors") or {}).items() if v
            )
            or "-"
        )
        claims = (
            ", ".join(f"{c['subject']} ({c['role']})" for c in row.get("claims", []))
            or "-"
        )
        rows.append(
            [
                row["instance"],
                strings.t("cli.gateway.instances.live")
                if row.get("leaseLive")
                else strings.t("cli.gateway.instances.expired"),
                _age(row.get("lastFetchAt")),
                str(row.get("backlog", 0)),
                str(row.get("committed", 0)),
                actors,
                claims,
            ]
        )
    return (
        _table(rows).splitlines()
        if len(rows) > 1
        else [strings.t("cli.gateway.instances.none")]
    )


def _age(iso: Optional[str]) -> str:
    if not iso:
        return "-"
    from datetime import datetime, timezone

    try:
        then = datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return iso
    seconds = int((datetime.now(timezone.utc) - then).total_seconds())
    if seconds < 60:
        return strings.t("cli.gateway.age.seconds", seconds=seconds)
    if seconds < 3600:
        return strings.t("cli.gateway.age.minutes", minutes=seconds // 60)
    return strings.t("cli.gateway.age.hours", hours=seconds // 3600)


def status_lines(report: Dict[str, Any]) -> List[str]:
    lines = [
        strings.t(
            "cli.gateway.status.gateway",
            state=strings.t("cli.gateway.status.running")
            if report["running"]
            else strings.t("cli.gateway.status.stopped"),
        )
        + (
            strings.t("cli.gateway.status.pid", pid=report["pid"])
            if report["running"]
            else ""
        ),
        strings.t("cli.gateway.status.listen", listen=report["listen"])
        + (
            ""
            if report["reachable"] or not report["running"]
            else strings.t("cli.gateway.status.not-answering")
        )
        + (
            strings.t(
                "cli.gateway.status.listen-in-file",
                listen_in_file=report["listenInFile"],
            )
            if report.get("listenInFile") and report["listenInFile"] != report["listen"]
            else ""
        ),
        strings.t("cli.gateway.status.store", store=report["store"]),
        strings.t("cli.gateway.status.config", config_path=report["configPath"]),
        strings.t("cli.gateway.status.pidfile", pidfile=report["pidfile"]),
        strings.t("cli.gateway.status.log", logfile=report["logfile"]),
    ]
    if report["running"] and report["reachable"]:
        ingresses = (
            ", ".join(f"{k}={v}" for k, v in sorted(report["ingresses"].items())) or "-"
        )
        lines.append(strings.t("cli.gateway.status.ingresses", ingresses=ingresses))
        lines.append(
            strings.t(
                "cli.gateway.status.slack-socket", slack_socket=report["slackSocket"]
            )
        )
        lines.append(
            strings.t(
                "cli.gateway.status.slack-posting",
                slack_posting=report.get("slackPosting", "unknown"),
            )
        )
        lines.append(
            strings.t("cli.gateway.status.instances-live")
            + (
                ", ".join(report["instancesLive"])
                or strings.t("cli.gateway.status.none")
            )
        )
        lines.append(strings.t("cli.gateway.status.held", held=report["held"]))
        if report["restartRequired"]:
            lines.append(
                strings.t("cli.gateway.status.restart-required")
                + ", ".join(report["restartRequired"])
            )
    return lines


@register
class GatewayCommand(Command):
    name = "gateway"
    help = strings.t("cli.gateway.help")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        # `--config` and `--format` are accepted before AND after the verb
        # (`the-loop gateway start --config …` is how the testing plan writes it): a
        # parent parser puts the same options on every verb's subparser.
        common = argparse.ArgumentParser(add_help=False)
        common.add_argument(
            "--config",
            "-c",
            dest="config",
            default=None,
            help=strings.t("cli.gateway.config.help"),
        )
        common.add_argument("--format", choices=["text", "json"], default="text")
        for action in common._actions:  # noqa: SLF001 — the same options on the parent
            parser._add_action(action)  # noqa: SLF001
        sub = parser.add_subparsers(dest="verb", metavar="<verb>")
        sub.required = True
        for verb, help_text in (
            ("start", strings.t("cli.gateway.start.help")),
            ("stop", strings.t("cli.gateway.stop.help")),
            ("restart", strings.t("cli.gateway.restart.help")),
            ("status", strings.t("cli.gateway.status.help")),
            ("subjects", strings.t("cli.gateway.subjects.help")),
            (
                "instances",
                strings.t("cli.gateway.instances.help"),
            ),
        ):
            sub.add_parser(verb, help=help_text, parents=[common])

    def run(self, args: argparse.Namespace) -> int:
        # `the-loop --config X gateway …` names the gateway config too: the global flag
        # is read by the CLI as its own config override; here it means ours.
        from .. import cli_config as cli_config_mod

        path = args.config or cli_config_mod._override  # noqa: SLF001 — the peeked flag
        load_gateway_env_file(path)
        try:
            config = load_gateway_config(path)
        except ConfigError as exc:
            print(exc, file=sys.stderr)
            return 2
        verb = args.verb
        report: Dict[str, Any]
        if verb == "start":
            report = start_gateway(config)
        elif verb == "stop":
            report = stop_gateway(config)
        elif verb == "restart":
            stopped = stop_gateway(config)
            report = {"stop": stopped, "start": start_gateway(config)}
            report["output"] = f"{stopped['output']}; {report['start']['output']}"
            report["running"] = report["start"]["running"]
        elif verb == "status":
            report = status_report(config)
        elif verb in ("subjects", "instances"):
            doc = _get(config, verb)
            if doc is None:
                print(
                    strings.t(
                        "cli.gateway.run.the-gateway-at-is-not",
                        base_url=config.base_url,
                    ),
                    file=sys.stderr,
                )
                return 1
            if args.format == "json":
                print(json.dumps(doc, indent=2))
            else:
                lines = (
                    subjects_lines(doc) if verb == "subjects" else instances_lines(doc)
                )
                print("\n".join(lines))
            return 0
        else:  # pragma: no cover - argparse enforces the choices
            return 2
        if args.format == "json":
            print(json.dumps(report, indent=2))
        elif verb == "status":
            print("\n".join(status_lines(report)))
        else:
            print(report["output"])
        if verb == "status":
            return 0
        return 0 if report.get("running") == (verb != "stop") else 1
