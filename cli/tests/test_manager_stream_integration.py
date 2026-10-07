"""Socket-level integration: a manager's stream fans two real workers' streams in
(issue-374, T2 — the one scenario that needs real processes).

Three `python -m the_loop.api.serve` processes on ephemeral loopback ports, joined
over HTTP as they would be in production: the manager's upstream connections are
`urllib` reading each worker's `/api/v1/stream`. Slow by nature (a few seconds of
boot), so it is one test, marked as such.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _config(root: Path, name: str, port: int, extra: str = "") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".the-loop" / "cli-config.yaml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        'version: "0.12.0"\n'
        f"instance:\n  name: {name}\n{extra}"
        "webhooks:\n  ghWebhook:\n    enabled: false\n"
        "polling:\n  enabled: false\n"
        "routing:\n  enabled: false\n"
        f"service:\n  host: 127.0.0.1\n  port: {port}\n  hostIngresses: false\n"
        "  mcp:\n    enabled: false\n"
        "  stream:\n    keepAliveSeconds: 1\n"
    )
    return path


def _serve(config: Path, log: Path) -> subprocess.Popen:
    env = dict(os.environ, THE_LOOP_CLI_CONFIG=str(config))
    env.pop("THE_LOOP_SERVICE_LOCAL", None)
    return subprocess.Popen(  # noqa: S603 — fixed argv
        [sys.executable, "-m", "the_loop.api.serve"],
        env=env,
        cwd=str(config.parent.parent),
        stdout=open(log, "wb"),
        stderr=subprocess.STDOUT,
    )


def _wait_healthy(port: int, seconds: float = 30.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/v1/health", timeout=1
            ):
                return
        except Exception:
            time.sleep(0.2)
    raise AssertionError(f"service on {port} never became healthy")


def _post(port: int, path: str, body: dict) -> None:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        response.read()


@pytest.mark.routed
def test_the_managers_stream_fans_two_workers_in_over_sockets(tmp_path):
    """
    Feature: the manager's stream
      Scenario: A member's event reaches the manager's stream stamped and resumable
        Given two workers and a manager running as real services on loopback
        When a browser holds the manager's stream open and a worker's config changes
        Then the worker's config.updated frame arrives stamped with the worker's name
             and an id carrying one offset per instance

    Requirement: docs/specs/issue-374/requirements.md R2.8
    """
    ports = {name: _free_port() for name in ("laptop-a", "ci-box", "hq")}
    configs = {
        "laptop-a": _config(tmp_path / "laptop-a", "laptop-a", ports["laptop-a"]),
        "ci-box": _config(tmp_path / "ci-box", "ci-box", ports["ci-box"]),
        "hq": _config(
            tmp_path / "hq",
            "hq",
            ports["hq"],
            extra=(
                "  role: manager\n  manager:\n    instances:\n"
                f"      - name: laptop-a\n        url: http://127.0.0.1:{ports['laptop-a']}\n"
                f"      - name: ci-box\n        url: http://127.0.0.1:{ports['ci-box']}\n"
                "    timeoutSeconds: 3\n    probeIntervalSeconds: 2\n"
            ),
        ),
    }
    processes = {
        name: _serve(config, tmp_path / f"{name}.log")
        for name, config in configs.items()
    }
    try:
        for name, port in ports.items():
            _wait_healthy(port)
        request = urllib.request.Request(
            f"http://127.0.0.1:{ports['hq']}/api/v1/stream",
            headers={"Accept": "text/event-stream"},
        )
        response = urllib.request.urlopen(request, timeout=20)
        # Let the manager's upstreams connect, then change a worker's config.
        time.sleep(2)
        _post(
            ports["laptop-a"],
            "/config",
            {"patch": {"instance": {"scope": {"mode": "locked"}}}},
        )
        seen_id = None
        seen = None
        deadline = time.monotonic() + 20
        current_id = None
        while time.monotonic() < deadline:
            line = response.readline().decode("utf-8", "replace").rstrip("\n")
            if line.startswith("id: "):
                current_id = line[4:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                if (
                    data.get("event") == "config.updated"
                    and data.get("instance") == "laptop-a"
                ):
                    seen, seen_id = data, current_id
                    break
        response.close()
        assert seen is not None, (
            "the worker's config.updated never reached the manager's stream"
        )
        assert seen["keys"] == ["instance.scope.mode"]
        assert seen_id is not None and "laptop-a=" in seen_id and "hq=" in seen_id
        # The fleet read agrees, and the worker's own file changed.
        with urllib.request.urlopen(
            f"http://127.0.0.1:{ports['hq']}/api/v1/instances", timeout=5
        ) as fleet:
            rows = json.load(fleet)["instances"]
        assert [(r["name"], r["state"]) for r in rows] == [
            ("hq", "live"),
            ("laptop-a", "live"),
            ("ci-box", "live"),
        ]
        assert "mode: locked" in configs["laptop-a"].read_text()
    finally:
        for process in processes.values():
            process.terminate()
        for process in processes.values():
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
