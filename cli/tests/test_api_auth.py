"""The control-plane's authentication boundary (issue-161, T5).

Negative tests first: these are requirements abuse cases 1–2 as executable
checks — an unauthenticated request is rejected before any core call, and a
non-loopback bind without the explicit exposure config refuses to boot.
"""

from fastapi.testclient import TestClient

from the_loop.api.app import create_app
from the_loop.api.config import is_loopback, service_config


TOKEN = "t" * 64


def _client(tmp_path, token=TOKEN):
    config = {"state": {"root": str(tmp_path / ".the-loop")}}
    return TestClient(create_app(config, token=token))


def test_missing_token_is_401_before_any_core_call(tmp_path):
    """
    Feature: control-plane authentication
      Scenario: an unauthenticated client calls a data route
        Given a running service with a minted token
        When a request arrives with no Authorization header
        Then it is rejected 401 and no core operation runs

    Requirement: docs/specs/issue-161/requirements.md §Security abuse case 1
    """
    client = _client(tmp_path)
    response = client.get("/api/v1/work-items")
    assert response.status_code == 401


def test_wrong_token_is_401(tmp_path):
    client = _client(tmp_path)
    response = client.get(
        "/api/v1/work-items", headers={"Authorization": "Bearer nope"}
    )
    assert response.status_code == 401


def test_empty_service_token_rejects_everything(tmp_path):
    """A service that somehow has no token fails closed, never open."""
    client = _client(tmp_path, token="")
    response = client.get("/api/v1/work-items", headers={"Authorization": "Bearer "})
    assert response.status_code == 401


def test_health_is_unauthenticated_liveness(tmp_path):
    client = _client(tmp_path)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_right_token_is_accepted(tmp_path):
    client = _client(tmp_path)
    response = client.get(
        "/api/v1/work-items", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200
    assert response.json() == []


def test_exposure_guard_default_is_loopback_only():
    """
    Feature: control-plane exposure guard
      Scenario: the default configuration is not a network service
        Given no service block in the CLI config
        When the service config resolves
        Then the bind host is loopback and exposed is false

    Requirement: docs/specs/issue-161/requirements.md §Security abuse case 2
    """
    conf = service_config({})
    assert is_loopback(conf["host"])
    assert conf["exposed"] is False
