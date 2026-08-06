"""The control-plane's network boundary (issue-161, T5).

The service carries **no in-app authentication** (owner decision, PR #162 — a
gateway owns auth). The boundary the service still enforces itself is the
**exposure guard**: it binds loopback by default and refuses a non-loopback
bind unless `service.exposed: true`. These tests pin that guard and confirm the
routes are reachable with no credential.
"""

from fastapi.testclient import TestClient

from the_loop.api.app import create_app
from the_loop.api.config import is_loopback, service_config


def _client(tmp_path):
    config = {"state": {"root": str(tmp_path / ".the-loop")}}
    return TestClient(create_app(config))


def test_routes_need_no_credential(tmp_path):
    """
    Feature: no in-app authentication
      Scenario: a client calls a data route with no Authorization header
        Given a running service (auth is the gateway's job)
        When a request arrives with no credential
        Then it is served normally

    Requirement: docs/specs/issue-161/requirements.md R3.1
    """
    client = _client(tmp_path)
    response = client.get("/api/v1/work-items")
    assert response.status_code == 200
    assert response.json() == []


def test_health_is_unauthenticated_liveness(tmp_path):
    client = _client(tmp_path)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_exposure_guard_default_is_loopback_only():
    """
    Feature: control-plane exposure guard
      Scenario: the default configuration is not a network service
        Given no service block in the CLI config
        When the service config resolves
        Then the bind host is loopback and exposed is false

    Requirement: docs/specs/issue-161/requirements.md §Security
    """
    conf = service_config({})
    assert is_loopback(conf["host"])
    assert conf["exposed"] is False


def test_non_loopback_requires_explicit_exposure():
    """A non-loopback host must not be served without the explicit opt-in —
    the guard `serve.py` enforces before binding."""
    conf = service_config({"service": {"host": "0.0.0.0"}})
    assert not is_loopback(conf["host"])
    assert conf["exposed"] is False  # → serve.py refuses to boot
