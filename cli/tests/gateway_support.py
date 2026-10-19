"""Shared doubles for the gateway suites (issue-496): a gateway app over a real
SqliteStore in a temporary directory, and an event-log reader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from the_loop import eventlog
from the_loop.gateway import config as gwconfig
from the_loop.gateway.consume import GatewayState, mount
from the_loop.gateway.envelope import Envelope
from the_loop.gateway.store import SqliteStore


def write_gateway_config(tmp_path: Path, **over: Any) -> gwconfig.GatewayConfig:
    body: Dict[str, Any] = {
        "version": "1",
        "state": {"root": str(tmp_path / "gw-state")},
        "listen": {"host": "127.0.0.1", "port": 8790},
        "repositories": ["o/r"],
        "consume": {
            "maxBatch": 16,
            "maxWaitSeconds": 5,
            "leaseSeconds": {"min": 1, "max": 60},
        },
    }
    body.update(over)
    path = tmp_path / "gateway-config.yaml"
    path.write_text(yaml.safe_dump(body), encoding="utf-8")
    return gwconfig.load_gateway_config(path)


class GatewayHarness:
    """A consume API over a real store, driven through FastAPI's TestClient."""

    def __init__(self, tmp_path: Path, **config_over: Any) -> None:
        self.config = write_gateway_config(tmp_path, **config_over)
        self.store = SqliteStore(
            self.config.store.path,
            retention_days=self.config.store.retention_days,
            max_attempts=self.config.store.max_attempts,
        )
        self.state = GatewayState(self.config, self.store)
        self.app = FastAPI()
        mount(self.app, self.state)
        self.client = TestClient(self.app)
        self.events_path = tmp_path / "events.jsonl"
        eventlog.configure("gateway", path=self.events_path, enabled=True)

    def close(self) -> None:
        self.store.close()

    # -- shortcuts ------------------------------------------------------------------------

    def fetch(
        self,
        instance: str,
        *,
        peer: str = "p",
        cursor: int = 0,
        max: int = 16,
        wait: float = 0,
        lease: float = 30,
        commit: Optional[Iterable[Dict[str, Any]]] = None,
    ):
        return self.client.post(
            "/api/v1/gateway/fetch",
            json={
                "instance": instance,
                "peer": peer,
                "cursor": cursor,
                "max": max,
                "wait": wait,
                "lease": lease,
                "commit": list(commit or []),
            },
        )

    def claim(self, instance: str, subject: str, role: str = "driver"):
        return self.client.put(
            "/api/v1/gateway/claims",
            json={"instance": instance, "subject": subject, "role": role},
        )

    def register(self, instance: str, actors: Dict[str, List[str]], peer: str = "p"):
        return self.client.put(
            "/api/v1/gateway/actors",
            json={"instance": instance, "peer": peer, "actors": actors},
        )

    def bind(self, ref: str, provider: str, key: str):
        return self.client.post(
            "/api/v1/gateway/bindings",
            json={"ref": ref, "provider": provider, "key": key},
        )

    def append(
        self, n: int = 1, *, subject: str = "loop-github-o-r-14", consumers=(), **over
    ):
        base = dict(
            subject=subject,
            provider="github",
            source="webhook",
            delivery_id=f"d-{n}",
            kind="issue_comment",
            payload={"n": n},
            work_item="github:o/r#14",
            actor="octocat",
        )
        base.update(over)
        return self.store.append(Envelope(**base), list(consumers))

    def events(self, name: Optional[str] = None) -> List[dict]:
        if not self.events_path.is_file():
            return []
        rows = [
            json.loads(line)
            for line in self.events_path.read_text().splitlines()
            if line
        ]
        return [r for r in rows if name is None or r["event"] == name]
