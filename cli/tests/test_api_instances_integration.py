"""Integration tests: the `instances` family and the `instance` parameter on a worker
(issue-374, T2 — the worker half)."""

from fastapi.testclient import TestClient

from the_loop.api.app import create_app
from the_loop.state import layout_from_config, legacy_layout
from the_loop.workitem import WorkItemStore

REF = "github:octo/repo#7"


def _client(tmp_path, name="laptop-a"):
    config = {
        "state": {"root": str(tmp_path / ".the-loop")},
        "instance": {"name": name},
    }
    return TestClient(create_app(config, config_path=tmp_path / "cli-config.yaml")), config


def test_a_worker_serves_the_fleet_family_and_names_itself(tmp_path):
    """
    Feature: the fleet read on every role
      Scenario: a worker answers GET /api/v1/instances with itself
        Given a worker named laptop-a
        When a client lists the instances
        Then it sees one live row, laptop-a, and role worker

    Requirement: docs/specs/issue-374/requirements.md R3.1
    """
    client, _ = _client(tmp_path)
    response = client.get("/api/v1/instances")
    assert response.status_code == 200
    doc = response.json()
    assert doc["role"] == "worker" and doc["name"] == "laptop-a"
    assert [row["name"] for row in doc["instances"]] == ["laptop-a"]
    assert doc["instances"][0]["state"] == "live"
    assert client.get("/api/v1/instance").json()["role"] == "worker"


def test_a_worker_refuses_registration_naming_the_role(tmp_path):
    """
    Feature: registration on a worker
      Scenario: the routes exist on a worker and do nothing
        Given a worker
        When a client registers or unregisters an instance
        Then it gets 400 naming instance.role and nothing is written

    Requirement: docs/specs/issue-374/requirements.md R4.4
    """
    client, _ = _client(tmp_path)
    response = client.post(
        "/api/v1/instances/register", json={"name": "b", "url": "http://b:1"}
    )
    assert response.status_code == 400
    assert "instance.role" in response.json()["detail"]
    assert not (tmp_path / "cli-config.yaml").exists()
    response = client.post("/api/v1/instances/unregister", json={"name": "b"})
    assert response.status_code == 400


def test_a_worker_accepts_only_its_own_name_as_instance(tmp_path):
    """
    Feature: the instance parameter is part of the one contract
      Scenario: a worker is asked for another instance
        Given a worker named laptop-a holding a work item
        When a client reads the work item with instance=laptop-a and instance=ci-box
        Then the first answers as without the parameter and the second is 404

    Requirement: docs/specs/issue-374/requirements.md R2.6; abuse case 6
    """
    client, config = _client(tmp_path)
    layout = layout_from_config(config)
    WorkItemStore(layout.portable_dir, legacy=legacy_layout(layout)).write_section(
        REF, "control", {"command": "start"}
    )
    own = client.get("/api/v1/work-items/one", params={"ref": REF, "instance": "laptop-a"})
    assert own.status_code == 200 and own.json()["ref"] == REF
    foreign = client.get(
        "/api/v1/work-items/one", params={"ref": REF, "instance": "ci-box"}
    )
    assert foreign.status_code == 404
    assert "ci-box" in foreign.json()["detail"]
    # A POST carries it in the body.
    refused = client.post(
        "/api/v1/sessions/control",
        json={"ref": REF, "verb": "pause", "instance": "ci-box"},
    )
    assert refused.status_code == 404
    # The self-keyed reads too.
    assert client.get("/api/v1/config", params={"instance": "ci-box"}).status_code == 404
    assert client.get("/api/v1/health", params={"instance": "laptop-a"}).status_code == 200


def test_a_worker_never_sets_the_partial_header(tmp_path):
    client, _ = _client(tmp_path)
    response = client.get("/api/v1/work-items")
    assert response.status_code == 200
    assert "the-loop-instances-unreachable" not in {k.lower() for k in response.headers}
