"""The assembled app's cross-origin behaviour (issue-211, T2/T8).

`test_api_cors.py` pins what the config resolves to; this file pins what a browser
actually gets back — which origins are echoed, what a preflight answers, and what stays
untouched when the feature is switched off. The service still carries no in-app
authentication, so every assertion here is about **who may read a response**, never about
who may connect: that boundary is `service.exposed`'s and is not reachable from this
block.
"""

import pytest
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from the_loop import eventlog
from the_loop.api import serve
from the_loop.api.app import create_app

ALLOWED = "https://madarauchiha-314.github.io"


def _client(tmp_path, cors=None):
    config = {"state": {"root": str(tmp_path / ".the-loop")}}
    if cors is not None:
        config["service"] = {"cors": cors}
    return TestClient(create_app(config))


def test_an_allowed_origin_reads_the_control_plane(tmp_path):
    """
    Feature: configurable cross-origin access
      Scenario: an allowed origin reads the control plane
        Given the default configuration
        When the published dashboard's origin calls /api/v1/work-items
        Then the response carries Access-Control-Allow-Origin for that origin

    Requirement: docs/specs/issue-211/requirements.md R1.1
    """
    response = _client(tmp_path).get("/api/v1/work-items", headers={"Origin": ALLOWED})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example.com",
        # A suffix lookalike: exact-string comparison, never a prefix match.
        "https://madarauchiha-314.github.io.evil.tld",
        # Same host, wrong scheme — an origin is scheme + host + port.
        "http://madarauchiha-314.github.io",
    ],
)
def test_an_unlisted_origin_gets_no_allow_origin_header(tmp_path, origin):
    """
    Feature: configurable cross-origin access
      Scenario: an unlisted origin gets no allow-origin header
        Given the default configuration
        When a page on another origin calls the control plane
        Then no Access-Control-Allow-Origin header comes back, so the browser
             discards the response

    Requirement: docs/specs/issue-211/requirements.md R1.3, R1.4
    """
    response = _client(tmp_path).get("/api/v1/work-items", headers={"Origin": origin})
    assert "access-control-allow-origin" not in response.headers


def test_a_preflight_is_answered_without_running_the_operation(tmp_path, monkeypatch):
    """
    Feature: configurable cross-origin access
      Scenario: a preflight is answered without running the operation
        Given the default configuration
        When the browser preflights a POST from the allowed origin
        Then the allowed methods and headers come back from the middleware
             itself, the route is never entered, and nothing is audited —
             a preflight is not an operation

    Requirement: docs/specs/issue-211/requirements.md R1.2
    """
    # The middleware is installed outermost, so it must short-circuit before
    # `_audit` ever sees the request. `sessions/control` is the sharp end of
    # that claim: entering it would post a control keyword to a work item.
    emitted: list = []
    monkeypatch.setattr(eventlog, "emit", lambda *a, **k: emitted.append(a))

    response = _client(tmp_path).options(
        "/api/v1/sessions/control",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()
    assert emitted == []


def test_a_private_network_preflight_is_answered_for_an_allowed_origin(tmp_path):
    """
    Feature: a public page reaching a loopback service
      Scenario: a private-network preflight is answered for an allowed origin
        Given the default configuration
        When Chromium preflights with Access-Control-Request-Private-Network
        Then Access-Control-Allow-Private-Network: true comes back

    Requirement: docs/specs/issue-211/requirements.md R2.3
    """
    response = _client(tmp_path).options(
        "/api/v1/work-items",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Private-Network": "true",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-private-network") == "true"


def test_a_private_network_preflight_can_be_declined(tmp_path):
    """The switch declines a request the origin allowlist already admitted; it
    never widens the allowlist."""
    response = _client(
        tmp_path, cors={"allowOrigins": [ALLOWED], "allowPrivateNetwork": False}
    ).options(
        "/api/v1/work-items",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Private-Network": "true",
        },
    )
    assert "access-control-allow-private-network" not in response.headers


def test_an_empty_origin_list_leaves_the_service_exactly_as_it_was(tmp_path):
    """
    Feature: cross-origin access is opt-out-able
      Scenario: an empty origin list leaves the service exactly as it was
        Given service.cors.allowOrigins is []
        When the app is built
        Then no CORS middleware is installed and no origin is echoed —
             the pre-issue-211 behaviour, byte for byte

    Requirement: docs/specs/issue-211/requirements.md R2.4
    """
    config = {
        "state": {"root": str(tmp_path / ".the-loop")},
        "service": {"cors": {"allowOrigins": []}},
    }
    app = create_app(config)
    assert not any(mw.cls is CORSMiddleware for mw in app.user_middleware)
    response = TestClient(app).get("/api/v1/work-items", headers={"Origin": ALLOWED})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_a_same_origin_call_is_unaffected(tmp_path):
    """No Origin header at all — the CLI, curl, the MCP client — is served as before."""
    response = _client(tmp_path).get("/api/v1/health")
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_the_mcp_transport_still_refuses_a_foreign_origin(tmp_path):
    """
    Feature: the MCP endpoint is not a browser surface
      Scenario: the MCP transport still refuses a foreign origin
        Given CORS allows the dashboard's origin for /api/v1
        When that origin posts to /mcp
        Then the SDK's DNS-rebinding protection refuses it — the CORS block
             cannot widen the MCP transport's own allowlist

    Requirement: docs/specs/issue-211/requirements.md §Security considerations, abuse case 5
    """
    # The MCP app's session manager only runs inside the lifespan, so this
    # client is entered rather than used bare. `Host` is set to one the
    # transport accepts, so the refusal below can only be the Origin check —
    # otherwise this would pass on the host check alone and prove nothing.
    with _client(tmp_path) as client:
        response = client.post(
            "/mcp",
            headers={
                "Host": "127.0.0.1:4114",
                "Origin": ALLOWED,
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
    assert response.status_code == 403
    assert "Origin" in response.text


def test_serve_refuses_an_invalid_cors_configuration(tmp_path, monkeypatch):
    """
    Feature: an unsafe CORS configuration fails closed
      Scenario: an invalid CORS configuration stops the service before it binds
        Given allowOrigins contains "*" and allowCredentials is true
        When `the-loop service start` boots the service
        Then it exits 2 without taking the run lock or binding a port

    Requirement: docs/specs/issue-211/requirements.md R3.1, R3.2
    """
    config = {
        "state": {"root": str(tmp_path / ".the-loop")},
        "service": {"cors": {"allowOrigins": ["*"], "allowCredentials": True}},
    }
    monkeypatch.setattr(serve, "load_cli_config", lambda *_a, **_k: config)
    monkeypatch.setattr(
        serve, "default_cli_config_path", lambda: tmp_path / "cli-config.yaml"
    )
    acquired = []
    monkeypatch.setattr(
        serve.RunLock, "acquire", lambda self: acquired.append(self) or True
    )

    assert serve.main() == 2
    assert acquired == []
