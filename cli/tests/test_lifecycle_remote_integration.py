"""The remote executor protocol, end to end against the shipped server (issue-344, R4).

Feature: a lifecycle hook runs as a remote JSON-RPC service
  The same class an operator declares by `path` is hosted by `url`, unchanged. These
  scenarios start `HookServer` on a loopback port and drive it through `RemoteExecutor`,
  the client the daemon uses.
"""

from __future__ import annotations

import json
import threading
import urllib.request

import pytest

from the_loop import eventlog
from the_loop.lifecycle.contract import PhaseChanged, WorkItemStart, WorkItem
from the_loop.lifecycle.remote import (
    HookFailure,
    HookServer,
    RemoteExecutor,
    handle_request,
)
from the_loop.lifecycle.runner import Runner
from the_loop.sdk.hooks import LifecycleHooks


class Compliance(LifecycleHooks):
    def __init__(self):
        self.seen = []

    def work_item_start(self, ctx):
        self.seen.append(ctx)
        if ctx.actor == "mallory":
            ctx.proceed = False
            ctx.reason = "not on the roster"
            return ctx
        return None

    def phase_changed(self, ctx):
        raise RuntimeError("the server-side hook exploded")


@pytest.fixture
def server():
    srv = HookServer(Compliance(), host="127.0.0.1", port=0)  # executor: Compliance
    thread = srv.serve_in_thread()
    yield srv
    srv.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def events(tmp_path):
    path = tmp_path / "events.jsonl"
    eventlog.configure("test", path=path)
    yield lambda: list(eventlog.read_events(path))
    eventlog.reset()


def _remote(server, **kw):
    kw.setdefault("timeout", 5.0)
    return RemoteExecutor(name="remote", url=server.url, on=(), required=False, **kw)


def test_a_remote_executor_answers_a_point_over_json_rpc(server):
    """
    Feature: a lifecycle hook runs as a remote JSON-RPC service
      Scenario: a remote executor answers a point over JSON-RPC
        Given a HookServer hosting a LifecycleHooks subclass on loopback
        When the daemon's RemoteExecutor runs work_item_start for an actor the hook refuses
        Then the decision comes back and is applied, and facts are untouched
        And for an actor it accepts the result is a pass-through

    Requirement: docs/specs/issue-344/requirements.md R4.2
    """
    ex = _remote(server)
    refused = Runner([ex]).run(
        WorkItemStart(work_item=WorkItem.from_ref("github:o/r#1"), actor="mallory")
    )
    assert refused.proceed is False and refused.reason == "not on the roster"
    assert refused.work_item.ref == "github:o/r#1"
    allowed = Runner([ex]).run(
        WorkItemStart(work_item=WorkItem.from_ref("github:o/r#1"), actor="alice")
    )
    assert allowed.proceed is True
    seen = server.executor.seen  # type: ignore[attr-defined]
    assert seen[0].actor == "mallory"
    assert seen[0].loop == "", "unknown/absent facts default"


def test_a_remote_error_is_a_recorded_failure_not_a_stop(server, events):
    """
    Feature: a lifecycle hook runs as a remote JSON-RPC service
      Scenario: a remote error is a recorded failure, not a stop
        Given the server-side method raises
        When the point runs
        Then the-loop records hooks.failed with the server's message and continues unchanged

    Requirement: docs/specs/issue-344/requirements.md R6.1 (abuse case 3)
    """
    out = Runner([_remote(server)]).run(
        PhaseChanged(work_item=WorkItem.from_ref("github:o/r#1"), to_phase="design")
    )
    assert out.notify is True
    (failed,) = [e for e in events() if e["event"] == "hooks.failed"]
    assert "exploded" in failed["error"]


def test_an_unreachable_remote_is_a_recorded_failure_not_a_stop(events):
    ex = RemoteExecutor(
        name="gone", url="http://127.0.0.1:9/hooks", on=(), required=False, timeout=1.0
    )
    out = Runner([ex]).run(WorkItemStart(work_item=WorkItem.from_ref("github:o/r#1")))
    assert out.proceed is True
    (failed,) = [e for e in events() if e["event"] == "hooks.failed"]
    assert failed["hook"] == "gone"


def test_an_unreachable_required_remote_refuses_a_proceed_point():
    ex = RemoteExecutor(
        name="gate", url="http://127.0.0.1:9/hooks", on=(), required=True, timeout=1.0
    )
    out = Runner([ex]).run(WorkItemStart(work_item=WorkItem.from_ref("github:o/r#1")))
    assert out.proceed is False and "gate" in out.reason


def test_a_timeout_is_bounded():
    """Abuse case 3: a slow server costs timeoutSeconds, not a hung dispatch."""
    release = threading.Event()

    class Slow(LifecycleHooks):
        def work_item_start(self, ctx):
            release.wait(5)
            return None

    srv = HookServer(Slow(), host="127.0.0.1", port=0)
    thread = srv.serve_in_thread()
    try:
        ex = RemoteExecutor(
            name="slow", url=srv.url, on=(), required=False, timeout=0.3
        )
        with pytest.raises(HookFailure) as exc:
            ex.call(
                "work_item_start",
                WorkItemStart(work_item=WorkItem.from_ref("github:o/r#1")),
            )
        assert "timed out" in str(exc.value)
    finally:
        release.set()
        srv.shutdown()
        thread.join(timeout=5)


def test_the_bearer_token_travels_only_when_its_variable_is_set(monkeypatch):
    """
    Feature: a lifecycle hook runs as a remote JSON-RPC service
      Scenario: the bearer token travels only when its variable is set
        Given a server that requires a bearer token named by tokenEnv
        When the variable is set, the call is authorised
        And when it is unset, no request is sent and the call is the hook's failure
        And a wrong token is refused by the server

    Requirement: docs/specs/issue-344/requirements.md R4.3 (abuse case 5)
    """
    monkeypatch.setenv("HOOKS_TOKEN", "s3cret")
    srv = HookServer(Compliance(), host="127.0.0.1", port=0, token_env="HOOKS_TOKEN")
    thread = srv.serve_in_thread()
    try:
        ex = RemoteExecutor(
            name="c",
            url=srv.url,
            on=(),
            required=False,
            timeout=5.0,
            token_env="HOOKS_TOKEN",
        )
        assert (
            ex.call(
                "work_item_start",
                WorkItemStart(work_item=WorkItem.from_ref("github:o/r#1")),
            )
            is None
        )
        monkeypatch.delenv("HOOKS_TOKEN")
        before = len(srv.executor.seen)  # type: ignore[attr-defined]
        with pytest.raises(HookFailure) as exc:
            ex.call(
                "work_item_start",
                WorkItemStart(work_item=WorkItem.from_ref("github:o/r#1")),
            )
        assert "HOOKS_TOKEN" in str(exc.value)
        assert len(srv.executor.seen) == before, "nothing was sent"  # type: ignore[attr-defined]
        monkeypatch.setenv("HOOKS_TOKEN", "wrong-on-the-client")
        monkeypatch.setenv("SERVER_TOKEN", "s3cret")
        srv.token_env = "SERVER_TOKEN"
        with pytest.raises(HookFailure) as exc:
            ex.call(
                "work_item_start",
                WorkItemStart(work_item=WorkItem.from_ref("github:o/r#1")),
            )
        assert "401" in str(exc.value)
    finally:
        srv.shutdown()
        thread.join(timeout=5)


def test_extra_headers_are_sent(server):
    class Echo(LifecycleHooks):
        pass

    ex = _remote(server, headers={"X-Team": "platform"})
    seen = {}

    real = urllib.request.urlopen

    def spy(req, timeout=None):
        seen.update({k.lower(): v for k, v in req.header_items()})
        return real(req, timeout=timeout)

    import the_loop.lifecycle.remote as remote_mod

    remote_mod.urlopen = spy
    try:
        ex.call(
            "work_item_start",
            WorkItemStart(work_item=WorkItem.from_ref("github:o/r#1")),
        )
    finally:
        remote_mod.urlopen = real
    assert seen["x-team"] == "platform"
    assert seen["content-type"] == "application/json"


def test_a_result_may_change_decisions_only(server):
    """Abuse case 2: a server that returns a fact does not move the-loop."""

    class Sneaky(LifecycleHooks):
        def work_item_start(self, ctx):
            ctx.work_item = WorkItem.from_ref("github:evil/r#9")
            ctx.loop = "acme-evil-loop"
            ctx.reason = "decided"
            return ctx

    srv = HookServer(Sneaky(), host="127.0.0.1", port=0)
    thread = srv.serve_in_thread()
    try:
        out = Runner(
            [RemoteExecutor(name="s", url=srv.url, on=(), required=False, timeout=5.0)]
        ).run(
            WorkItemStart(
                work_item=WorkItem.from_ref("github:o/r#1"), loop="pdlc-work-item-loop"
            )
        )
        assert out.work_item.ref == "github:o/r#1" and out.loop == "pdlc-work-item-loop"
        assert out.reason == "decided"
    finally:
        srv.shutdown()
        thread.join(timeout=5)


def test_the_server_speaks_json_rpc_errors():
    body = handle_request(Compliance(), b"not json")
    assert json.loads(body)["error"]["code"] == -32700
    body = handle_request(
        Compliance(),
        json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "nope", "params": {}}
        ).encode(),
    )
    assert json.loads(body)["error"]["code"] == -32601
    body = handle_request(
        Compliance(),
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "work_item_start"}).encode(),
    )
    assert json.loads(body)["error"]["code"] == -32600
    body = handle_request(
        Compliance(),
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "work_item_start",
                "params": {"work_item": "github:o/r#1", "proceed": "yes"},
            }
        ).encode(),
    )
    assert json.loads(body)["error"]["code"] == -32602
    body = handle_request(
        Compliance(),
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "phase_changed",
                "params": {"work_item": "github:o/r#1"},
            }
        ).encode(),
    )
    out = json.loads(body)
    assert out["error"]["code"] == -32000 and out["id"] == 7
    body = handle_request(
        Compliance(),
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "work_item_start",
                "params": {"work_item": "github:o/r#1", "actor": "mallory"},
            }
        ).encode(),
    )
    out = json.loads(body)
    assert out == {
        "jsonrpc": "2.0",
        "id": 8,
        "result": {"proceed": False, "reason": "not on the roster"},
    }


def test_the_client_refuses_a_response_that_is_not_its_own(monkeypatch):
    import the_loop.lifecycle.remote as remote_mod

    class _Resp:
        status = 200

        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    for body in (
        b"[]",
        b"{}",
        json.dumps({"jsonrpc": "2.0", "id": 999, "result": None}).encode(),
        b"{bad",
    ):
        monkeypatch.setattr(
            remote_mod, "urlopen", lambda req, timeout=None, body=body: _Resp(body)
        )
        ex = RemoteExecutor(
            name="x", url="https://hooks.example/", on=(), required=False, timeout=1.0
        )
        with pytest.raises(HookFailure):
            ex.call(
                "work_item_start",
                WorkItemStart(work_item=WorkItem.from_ref("github:o/r#1")),
            )


def test_health_answers_without_a_token(server):
    with urllib.request.urlopen(server.url.rstrip("/") + "/health", timeout=5) as resp:
        assert json.loads(resp.read()) == {"ok": True, "points": list(server.points)}
