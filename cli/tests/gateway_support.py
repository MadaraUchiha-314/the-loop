"""Shared doubles for the gateway suites (issue-496): a gateway app over a real
SqliteStore in a temporary directory, and an event-log reader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import threading

import yaml
from conftest import FakeTmux, StubInteractiveAdapter
from fastapi import FastAPI
from fastapi.testclient import TestClient

from the_loop import eventlog
from the_loop.control import ControlConfig, ControlStore
from the_loop.gateway import config as gwconfig
from the_loop.gateway.client import GatewayClient
from the_loop.gateway.client_dispatch import Pipeline
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import Router
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(body), encoding="utf-8")
    return gwconfig.load_gateway_config(path)


class GatewayHarness:
    """A consume API over a real store, driven through FastAPI's TestClient."""

    # set by the suites that need them (the poll and Slack adapters)
    ingest: Any = None
    api: Any = None
    poll: Any = None
    watch: Any = None
    socket: Any = None

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
        base: Dict[str, Any] = dict(
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


class Instance:
    """One instance: its registry, dispatcher, router, pipeline and gateway client."""

    def __init__(
        self, gw: GatewayHarness, root: Path, name: str, actors=("octocat",), **routing
    ):
        self.root = root
        self.tmux = FakeTmux()
        self.registry = SessionRegistry(root / "sessions")
        config = RoutingConfig(
            dispatch_timeout_seconds=30,
            spawn_workdir=str(root),
            portable_dir=str(root / "portable"),
            **{
                "control": ControlConfig(require_start_command=False),
                "auto_execute_labels": ["the-loop: auto-execute"],
                "authorized_users": ["octocat"],
                **routing,
            },
        )
        self.dispatcher = Dispatcher(
            registry=self.registry,
            adapters={"claude": StubInteractiveAdapter()},
            config=config,
            tmux_runner=self.tmux,
        )
        self.router = Router(
            events=[
                "issues",
                "issue_comment",
                "pull_request",
                "pull_request_review_comment",
            ],
            deduper=self.dispatcher.deduper,
            auto_execute_labels=config.auto_execute_labels,
            authorized_users=["octocat"],
            collaborators=self.dispatcher.collaborator_store,
            repositories=None,
        )
        self.cli_config: Dict[str, Any] = {
            "state": {"root": str(root / ".the-loop")},
            "instance": {"name": name},
            "gateway": {
                "url": "http://127.0.0.1:8790",
                "pollIntervalSeconds": 1,
                "longPollSeconds": 0,
                "actors": {"github": list(actors)},
            },
        }
        self.pipeline = Pipeline(
            router=self.router, dispatcher=self.dispatcher, cli_config=self.cli_config
        )
        self.control = ControlStore(root / "portable")
        self.client = GatewayClient(
            self.cli_config,
            threading.Event(),
            dispatch=self.pipeline.dispatch,
            claims=self.claims,
            transport=lambda m, p, b, t: self._call(gw, m, p, b),
            sleep=lambda s: None,
            rng=lambda: 0.5,
        )
        self.client.attach(
            self.registry, control_store=self.control, pipeline=self.pipeline
        )

    @staticmethod
    def _call(gw, method, path, body):
        response = gw.client.request(method, path, json=body)
        return response.status_code, (response.json() if response.content else None)

    def claims(self) -> List[Any]:
        return [
            (f"loop-{s.work_item.slug}", "driver")
            for s in self.registry.list_sessions()
            if s.is_live
        ]

    def register_session(self, ref: str = "github:o/r#14") -> None:
        item = WorkItemRef.parse(ref)
        self.registry.register(
            Session(
                work_item=item,
                harness="claude",
                harness_session_id="sess-1",
                cwd=str(self.root),
                tmux_target=f"loop-{item.slug}",
            )
        )

    def stop(self) -> None:
        self.dispatcher.stop()
