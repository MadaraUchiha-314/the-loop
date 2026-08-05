"""``the-loop service`` / ``the-loop ui`` — control-plane lifecycle (issue-161).

``service start|stop|status`` manage the API service process with the same
discipline as the other daemons (issue-159): the pidfile is the flock, start is
idempotent, stop signals and waits. ``ui dev|build`` delegate to the frontend's
own toolchain (``npm --prefix ui``) as an argv list, never a shell, and report
a clear skip when npm is absent. These are **bootstrap commands** — they manage
the installation and the service process itself, so they are the exceptions to
the service-only execution rule (decision-058).
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from typing import Optional

from .base import Command, register
from .. import eventlog
from ..api.config import base_url, service_pidfile
from ..runlock import RunLock

_STOP_TIMEOUT_SECONDS = 30.0
_START_TIMEOUT_SECONDS = 15.0

_INSTALL_HINT = (
    "the [service] extra is not installed; run "
    "`pip install 'the-loopy-one[service]'` (or the uv/pipx equivalent)"
)


def _service_extra_available() -> bool:
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        return False
    return True


def _healthy(config: dict) -> bool:
    from .. import client

    return client.healthy(config)


@register
class ServiceCommand(Command):
    name = "service"
    help = "Run the control-plane API service (start | stop | status)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        actions = parser.add_subparsers(dest="action", metavar="<action>")
        actions.required = True
        start = actions.add_parser("start", help="Start the API service")
        start.set_defaults(_action=self._start)
        stop = actions.add_parser("stop", help="Stop a running API service")
        stop.add_argument(
            "--timeout",
            type=float,
            default=_STOP_TIMEOUT_SECONDS,
            help="Seconds to wait for the service to exit (default: 30).",
        )
        stop.set_defaults(_action=self._stop)
        status = actions.add_parser("status", help="Report the service's state")
        status.set_defaults(_action=self._status)

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("service")
        return args._action(args)

    # -- verbs -----------------------------------------------------------------

    def _start(self, args: argparse.Namespace) -> int:
        config = _load_config()
        lock = RunLock(service_pidfile(config), name="service")
        if lock.is_held():
            print(f"service already running (pid {lock.holder()})")
            return 0
        if not _service_extra_available():
            print(f"error: {_INSTALL_HINT}", file=sys.stderr)
            return 1
        subprocess.Popen(  # noqa: S603 — fixed argv, no shell
            [sys.executable, "-m", "the_loop.api.serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.monotonic() + _START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if _healthy(config):
                print(f"service started at {base_url(config)}")
                return 0
            time.sleep(0.25)
        print(
            "error: service did not become healthy; check the event log "
            "(`the-loop events --source service`)",
            file=sys.stderr,
        )
        return 1

    def _stop(self, args: argparse.Namespace) -> int:
        config = _load_config()
        lock = RunLock(service_pidfile(config), name="service")
        if not lock.is_held():
            print("service is not running")
            return 0
        pid = lock.holder()
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if lock.wait_until_free(args.timeout):
            print(f"service stopped (pid {pid})")
            return 0
        print(
            f"error: service (pid {pid}) did not exit within {args.timeout:.0f}s",
            file=sys.stderr,
        )
        return 1

    def _status(self, args: argparse.Namespace) -> int:
        config = _load_config()
        lock = RunLock(service_pidfile(config), name="service")
        if lock.is_held():
            health = "healthy" if _healthy(config) else "unresponsive"
            print(f"running (pid {lock.holder()}, {base_url(config)}, {health})")
            return 0
        print("not running")
        return 0


@register
class UiCommand(Command):
    name = "ui"
    help = "Serve or build the control-plane UI (dev | build)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        actions = parser.add_subparsers(dest="action", metavar="<action>")
        actions.required = True
        for verb, help_text in (
            ("dev", "Run the UI dev server against a local API service"),
            ("build", "Build the static, hostable UI bundle"),
        ):
            sub = actions.add_parser(verb, help=help_text)
            sub.set_defaults(_verb=verb)

    def run(self, args: argparse.Namespace) -> int:
        ui_dir = _repo_ui_dir()
        if ui_dir is None:
            print(
                "error: no ui/ directory here — run from a the-loop checkout",
                file=sys.stderr,
            )
            return 1
        npm = shutil.which("npm")
        if npm is None:
            print(
                "skipped: npm is not on PATH; install Node.js to run the UI",
                file=sys.stderr,
            )
            return 1
        argv = [npm, "--prefix", str(ui_dir), "run", args._verb]
        print("+ " + " ".join(argv))
        proc = subprocess.run(argv)  # noqa: S603 — fixed argv, no shell
        return proc.returncode


def _load_config() -> dict:
    from ..cli_config import default_cli_config_path, load_cli_config

    try:
        return load_cli_config(default_cli_config_path())
    except Exception:
        return {}


def _repo_ui_dir() -> Optional[Path]:
    candidate = Path.cwd() / "ui"
    return candidate if (candidate / "package.json").is_file() else None
