"""Abuse cases for the embedded seam (issue-212, T10).

The security story of this work item is a boundary that *moves*: the standalone service
defends itself with the exposure guard and a CORS allowlist, and neither exists once the
router is inside somebody else's application. These tests pin what the SDK owes in
exchange — that the host's authorization cannot be routed around, and that the SDK does
not silently widen the host's own posture.
"""

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from the_loop.sdk import TheLoop


def _loop(tmp_path, *, mcp=False):
    path = tmp_path / "cli-config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "state": {"root": str(tmp_path / ".the-loop")},
                "service": {"hostIngresses": False, "mcp": {"enabled": mcp}},
            }
        )
    )
    return TheLoop(config_path=path)


def test_a_rejecting_dependency_cannot_be_bypassed_by_choosing_a_path(tmp_path):
    """
    Feature: authorization on an embedded control plane
      Scenario: a rejecting dependency cannot be bypassed by choosing a the-loop path
        Given the-loop mounted behind the host's authorization dependency
        When an unauthorized caller tries every mounted operation in turn
        Then every one of them is refused

    Requirement: docs/specs/issue-212/requirements.md §Security abuse case 2
    """
    loop = _loop(tmp_path)

    def verify(request: Request):
        raise HTTPException(status_code=401, detail="nope")

    app = FastAPI()
    report = loop.mount(app, dependencies=[Depends(verify)])
    client = TestClient(app)

    # Driven off the host app's own OpenAPI document, so the test asks the same
    # question a caller would: "what did this mount publish, and is any of it open?"
    schema = client.get("/openapi.json").json()
    checked = 0
    for path, operations in schema["paths"].items():
        if not path.startswith(report["prefix"]):
            continue
        for method in operations:
            response = client.request(method.upper(), path)
            assert response.status_code == 401, f"{method} {path}"
            checked += 1
    assert checked == report["operations"]


def test_mounting_adds_no_middleware_no_handlers_and_no_cors(tmp_path):
    """
    Feature: the SDK's footprint on a host application
      Scenario: mounting adds no middleware, no exception handlers and no CORS
        Given a host application recorded before the mount
        When the-loop is mounted into it
        Then its middleware stack, exception handlers, title and doc URLs are unchanged,
          and no Access-Control-Allow-Origin appears on a the-loop response

    Requirement: docs/specs/issue-212/requirements.md R3.3, R3.5
    """
    loop = _loop(tmp_path)
    app = FastAPI(title="host", docs_url="/docs", openapi_url="/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=["https://host.example"])

    before = {
        "middleware": len(app.user_middleware),
        "handlers": dict(app.exception_handlers),
        "title": app.title,
        "docs_url": app.docs_url,
        "openapi_url": app.openapi_url,
    }
    loop.mount(app)

    assert len(app.user_middleware) == before["middleware"]
    assert dict(app.exception_handlers) == before["handlers"]
    assert (app.title, app.docs_url, app.openapi_url) == (
        before["title"],
        before["docs_url"],
        before["openapi_url"],
    )

    # The host's own CORS policy is the only one in play: an origin it did not allow
    # gets no allow-origin header, and the-loop's `service.cors` default (which does
    # allow the dashboard origin) was never installed here.
    response = TestClient(app).get(
        "/the-loop/api/v1/health",
        headers={"Origin": "https://madarauchiha-314.github.io"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_an_empty_prefix_with_mcp_is_refused(tmp_path):
    """
    Feature: the SDK's footprint on a host application
      Scenario: an empty prefix with MCP enabled is refused rather than shadowing routes
        Given a host application and a config with MCP enabled
        When the-loop is mounted at the root
        Then the mount is refused with a message naming the shadowing hazard

    Requirement: docs/specs/issue-212/design.md D3
    """
    loop = _loop(tmp_path, mcp=True)
    try:
        loop.mount(FastAPI(), prefix="")
    except ValueError as exc:
        assert "shadow" in str(exc)
    else:  # pragma: no cover — the assertion is that it raises
        raise AssertionError("an empty prefix with MCP enabled must be refused")


def test_the_config_write_path_is_not_the_callers_to_choose(tmp_path):
    """
    Feature: writing the CLI config through an embedded control plane
      Scenario: a caller cannot redirect a config write to another file
        Given a mounted the-loop and a second, unrelated config file
        When a caller POSTs a config patch naming that other file
        Then the patch is applied to the file this process reads, and the other file is
          untouched

    Requirement: docs/specs/issue-212/requirements.md §Security abuse case 4, R4.4
    """
    loop = _loop(tmp_path)
    decoy = tmp_path / "someone-elses-config.yaml"
    decoy.write_text("routing:\n  enabled: false\n")

    app = FastAPI()
    loop.mount(app)
    response = TestClient(app).post(
        "/the-loop/api/v1/config",
        json={
            "patch": {"routing": {"enabled": True}},
            "path": str(decoy),  # ignored: the body model has no such field
        },
    )
    assert response.status_code == 200
    assert decoy.read_text() == "routing:\n  enabled: false\n"
    assert yaml.safe_load(loop.config_path.read_text())["routing"]["enabled"] is True
