"""Integration tests: the-loop mounted inside somebody else's app (issue-212, T2).

Every test builds a *host* FastAPI application — one the-loop does not own, with its own
routes, its own middleware and (where it matters) its own lifespan — and asserts on what
the SDK does and does not do to it.
"""

import json
from contextlib import asynccontextmanager

import pytest
import yaml
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from the_loop.sdk import TheLoop
from the_loop.state import layout_from_config, legacy_layout
from the_loop.workitem import WorkItemStore


REF = "github:octo/repo#7"


def _config_file(tmp_path, *, mcp=False, extra=None):
    document = {
        "state": {"root": str(tmp_path / ".the-loop")},
        "service": {"hostIngresses": False, "mcp": {"enabled": mcp}},
    }
    document.update(extra or {})
    path = tmp_path / "cli-config.yaml"
    path.write_text(yaml.safe_dump(document))
    return path


def _loop(tmp_path, **kwargs):
    loop = TheLoop(config_path=_config_file(tmp_path, **kwargs))
    layout = layout_from_config(loop.config)
    store = WorkItemStore(layout.portable_dir, legacy=legacy_layout(layout))
    store.write_section(REF, "control", {"command": "start"})
    return loop


def test_a_host_application_serves_the_loop_under_its_own_prefix(tmp_path):
    """
    Feature: the-loop embedded in an existing FastAPI service
      Scenario: a host application serves the-loop's operations under its own prefix
        Given a FastAPI application with routes of its own
        When the-loop is mounted under /internal/the-loop
        Then its operations answer under that prefix, the host's own routes still answer,
          and the host's OpenAPI document describes both

    Requirement: docs/specs/issue-212/requirements.md R2.1, R2.2
    """
    loop = _loop(tmp_path)
    app = FastAPI(title="somebody else's service")

    @app.get("/orders")
    def orders():
        return [{"id": 1}]

    loop.mount(app, prefix="/internal/the-loop")
    client = TestClient(app)

    assert client.get("/orders").json() == [{"id": 1}]
    assert client.get("/internal/the-loop/api/v1/health").json()["status"] == "ok"
    assert [
        row["ref"] for row in client.get("/internal/the-loop/api/v1/work-items").json()
    ] == [REF]

    schema = client.get("/openapi.json").json()
    assert "/orders" in schema["paths"]
    assert "/internal/the-loop/api/v1/work-items" in schema["paths"]
    assert schema["info"]["title"] == "somebody else's service"


def test_core_errors_translate_without_host_exception_handlers(tmp_path):
    """
    Feature: the-loop embedded in an existing FastAPI service
      Scenario: a core LookupError becomes a 404 in a host app that registered no handlers
        Given a host application that registers no exception handlers
        When a caller asks for a malformed ref and then for a work item that is absent
        Then it receives 400 and 404 rather than 500s

    Requirement: docs/specs/issue-212/requirements.md R2.3
    """
    loop = _loop(tmp_path)
    app = FastAPI()
    loop.mount(app)
    client = TestClient(app)

    assert (
        client.get(
            "/the-loop/api/v1/work-items/one", params={"ref": "nope"}
        ).status_code
        == 400
    )
    missing = client.get(
        "/the-loop/api/v1/work-items/one", params={"ref": "github:octo/repo#404"}
    )
    assert missing.status_code == 404
    assert "detail" in missing.json()


def test_the_host_middleware_sees_every_the_loop_request(tmp_path):
    """
    Feature: the-loop embedded in an existing FastAPI service
      Scenario: the host application's middleware sees every the-loop request
        Given a host application with a transaction-id middleware
        When a the-loop operation is called
        Then the middleware ran for it and stamped the response, exactly as for the
          host's own routes

    Requirement: docs/specs/issue-212/requirements.md R3.1
    """
    loop = _loop(tmp_path)
    app = FastAPI()
    seen = []

    @app.middleware("http")
    async def transaction_id(request: Request, call_next):
        seen.append(request.url.path)
        response = await call_next(request)
        response.headers["x-transaction-id"] = "txn-1"
        return response

    loop.mount(app)
    response = TestClient(app).get("/the-loop/api/v1/health")

    assert response.headers["x-transaction-id"] == "txn-1"
    assert seen == ["/the-loop/api/v1/health"]


def test_an_injected_dependency_gates_every_operation(tmp_path):
    """
    Feature: the-loop embedded in an existing FastAPI service
      Scenario: an injected dependency gates every the-loop operation
        Given the-loop mounted with the host's own authorization dependency
        When an unauthorized caller reaches any the-loop operation
        Then it is refused before the operation executes, and an authorized one succeeds

    Requirement: docs/specs/issue-212/requirements.md R3.2
    """
    loop = _loop(tmp_path)
    executed = []

    def verify(request: Request):
        if request.headers.get("x-api-key") != "secret":
            raise HTTPException(status_code=401, detail="nope")
        executed.append(request.url.path)

    app = FastAPI()
    loop.mount(app, dependencies=[Depends(verify)])
    client = TestClient(app)

    assert client.get("/the-loop/api/v1/work-items").status_code == 401
    assert executed == []
    authorized = client.get(
        "/the-loop/api/v1/work-items", headers={"x-api-key": "secret"}
    )
    assert authorized.status_code == 200
    assert executed == ["/the-loop/api/v1/work-items"]


def test_mcp_answers_under_a_prefix_with_the_host_lifespan_still_running(tmp_path):
    """
    Feature: the-loop embedded in an existing FastAPI service
      Scenario: the MCP endpoint answers under a prefix with the host's lifespan running
        Given a host application that already has a lifespan of its own
        When the-loop is mounted and an MCP client initialises against <prefix>/mcp
        Then the session manager answers, and the host's lifespan ran too

    Requirement: docs/specs/issue-212/requirements.md R2.5, R3.4
    """
    loop = _loop(tmp_path, mcp=True)
    host_lifespan = []

    @asynccontextmanager
    async def my_lifespan(app):
        host_lifespan.append("startup")
        yield
        host_lifespan.append("shutdown")

    app = FastAPI(lifespan=my_lifespan)
    report = loop.mount(app, mcp_allowed_hosts=["testserver"])
    assert report["mcp"] == {"mounted": True, "path": "/the-loop/mcp"}

    with TestClient(app) as client:
        assert host_lifespan == ["startup"]
        response = client.post(
            "/the-loop/mcp",
            headers={"Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        assert response.status_code == 200
        assert "the-loop" in response.text
        # The REST surface under the same prefix is not shadowed by the MCP mount.
        assert client.get("/the-loop/api/v1/health").status_code == 200
    assert host_lifespan == ["startup", "shutdown"]


def test_mounting_mcp_without_the_lifespan_refuses_instead_of_serving(tmp_path):
    """
    Feature: the-loop embedded in an existing FastAPI service
      Scenario: mounting MCP without composing the lifespan refuses instead of serving
        Given the-loop mounted with lifespan=False and no composition by the caller
        When an MCP client calls <prefix>/mcp
        Then it is told the lifespan is not running, rather than meeting an unstarted
          session manager

    Requirement: docs/specs/issue-212/requirements.md R2.6
    """
    loop = _loop(tmp_path, mcp=True)
    app = FastAPI()
    loop.mount(app, lifespan=False, mcp_allowed_hosts=["testserver"])

    with TestClient(app) as client:
        response = client.post(
            "/the-loop/mcp",
            headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
    assert response.status_code == 503
    assert "lifespan" in response.json()["detail"]


def test_the_caller_can_compose_the_lifespan_themselves(tmp_path):
    """
    Feature: the-loop embedded in an existing FastAPI service
      Scenario: the caller composes the-loop's lifespan inside their own
        Given a host lifespan that enters the-loop's explicitly
        When the application starts and an MCP client initialises
        Then both lifespans ran and the MCP endpoint answers

    Requirement: docs/specs/issue-212/requirements.md R3.4, R2.5
    """
    loop = _loop(tmp_path, mcp=True)
    order = []

    @asynccontextmanager
    async def lifespan(app):
        order.append("host-in")
        async with loop.lifespan(app):
            order.append("loop-in")
            yield
        order.append("host-out")

    app = FastAPI(lifespan=lifespan)
    loop.mount(app, lifespan=False, mcp_allowed_hosts=["testserver"])

    with TestClient(app) as client:
        response = client.post(
            "/the-loop/mcp",
            headers={"Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        assert response.status_code == 200
    assert order == ["host-in", "loop-in", "host-out"]


def test_a_config_edited_on_disk_is_live_on_the_next_embedded_request(tmp_path):
    """
    Feature: the-loop embedded in an existing FastAPI service
      Scenario: a config edited on disk is live on the next embedded request
        Given a mounted the-loop serving a work item from one state root
        When the CLI config is edited to point at a different state root
        Then the next request answers from the new one, with no restart

    Requirement: docs/specs/issue-212/requirements.md R4.3
    """
    loop = _loop(tmp_path)
    app = FastAPI()
    loop.mount(app)
    client = TestClient(app)
    assert len(client.get("/the-loop/api/v1/work-items").json()) == 1

    document = yaml.safe_load(loop.config_path.read_text())
    document["state"] = {"root": str(tmp_path / "elsewhere")}
    loop.config_path.write_text(yaml.safe_dump(document))

    assert client.get("/the-loop/api/v1/work-items").json() == []


def test_an_embedded_operation_lands_in_the_event_log(tmp_path):
    """
    Feature: the-loop embedded in an existing FastAPI service
      Scenario: an embedded operation lands in the event log as api.request
        Given a mounted the-loop
        When an operation and then the health probe are called
        Then the operation is recorded as api.request and the probe is not

    Requirement: docs/specs/issue-212/requirements.md NFR4
    """
    from the_loop import eventlog

    log = tmp_path / "events.jsonl"
    eventlog.configure("service", path=log)
    try:
        loop = _loop(tmp_path)
        app = FastAPI()
        loop.mount(app, prefix="/embedded")
        client = TestClient(app)
        client.get("/embedded/api/v1/work-items")
        client.get("/embedded/api/v1/health")
    finally:
        eventlog.reset()

    records = [json.loads(line) for line in log.read_text().splitlines()]
    paths = [row.get("path") for row in records if row["event"] == "api.request"]
    assert paths == ["/embedded/api/v1/work-items"]


@pytest.mark.parametrize("verb,path", [("get", "/the-loop/api/v1/health")])
def test_mounting_twice_is_the_callers_business_not_a_crash(tmp_path, verb, path):
    """Two mounts of the same TheLoop into two apps stay independent."""
    loop = _loop(tmp_path)
    first, second = FastAPI(), FastAPI()
    loop.mount(first)
    loop.mount(second)
    assert getattr(TestClient(first), verb)(path).status_code == 200
    assert getattr(TestClient(second), verb)(path).status_code == 200
