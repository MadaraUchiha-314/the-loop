"""Integration: two workers and a manager in one process (issue-374, T2, T8).

The manager's fleet transport is an in-process dispatcher onto FastAPI test clients,
so the three services are real applications joined without a socket. Every scenario
below is one of the requirement's promises about the aggregated surface.
"""

from __future__ import annotations

import json
from typing import Dict

import pytest
from fastapi.testclient import TestClient

from the_loop.api.app import create_app
from the_loop.manager.fleet import TransportError
from the_loop.state import layout_from_config, legacy_layout
from the_loop.workitem import WorkItemStore

A_URL, B_URL, C_URL = "http://laptop-a:4114", "http://ci-box:4114", "http://cloud-1:4114"
REF_A, REF_B, REF_HQ, SHARED = (
    "github:octo/repo#1",
    "github:octo/repo#2",
    "github:octo/repo#3",
    "github:octo/repo#9",
)


class Dispatcher:
    """A transport that hands a member's URL to its in-process client."""

    def __init__(self):
        self.clients: Dict[str, TestClient] = {}
        self.calls = []

    def __call__(self, method, url, body, timeout):
        self.calls.append((method, url))
        base, _, rest = url.partition("/api/v1")
        client = self.clients.get(base)
        if client is None:
            raise TransportError("connection refused")
        response = client.request(
            method,
            "/api/v1" + rest,
            content=body,
            headers={"Content-Type": "application/json"} if body else {},
        )
        return response.status_code, response.content


def _worker(tmp_path, name, refs):
    root = tmp_path / name
    config = {
        "state": {"root": str(root)},
        "instance": {"name": name, "scope": {"mode": "addressed"}},
        "service": {"port": 4114, "host": name},
    }
    layout = layout_from_config(config)
    store = WorkItemStore(layout.portable_dir, legacy=legacy_layout(layout))
    for ref in refs:
        store.write_section(
            ref, "control", {"ref": ref, "command": "start", "instance": name}
        )
    path = root / "cli-config.yaml"
    root.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'version: "0.10.0"\ninstance:\n  name: {name}\n  scope:\n    mode: addressed\n'
    )
    return TestClient(create_app(config, config_path=path)), config


@pytest.fixture
def fleet(tmp_path):
    dispatcher = Dispatcher()
    a, _ = _worker(tmp_path, "laptop-a", [REF_A, SHARED])
    b, _ = _worker(tmp_path, "ci-box", [REF_B, SHARED])
    dispatcher.clients[A_URL] = a
    dispatcher.clients[B_URL] = b
    root = tmp_path / "hq"
    root.mkdir()
    path = root / "cli-config.yaml"
    path.write_text(
        "# the manager\n"
        'version: "0.10.0"\n'
        "instance:\n  name: hq\n  role: manager\n  manager:\n"
        f"    instances:\n      - name: laptop-a\n        url: {A_URL}\n"
        f"      - name: ci-box\n        url: {B_URL}\n"
        f"      - name: cloud-1\n        url: {C_URL}\n"
        "    timeoutSeconds: 2\n"
    )
    import yaml

    config = yaml.safe_load(path.read_text())
    config["state"] = {"root": str(root)}
    layout = layout_from_config(config)
    WorkItemStore(layout.portable_dir, legacy=legacy_layout(layout)).write_section(
        REF_HQ, "control", {"ref": REF_HQ, "command": "start", "instance": "hq"}
    )
    app = create_app(config, config_path=path)
    app.state.facade.fleet._transport = dispatcher
    manager = TestClient(app)
    return {"manager": manager, "a": a, "b": b, "dispatcher": dispatcher, "path": path}


def test_a_list_read_on_the_manager_is_the_union_of_its_live_members(fleet):
    """
    Feature: a manager serves the fleet as one instance
      Scenario: A list read on the manager is the union of its live members
        Given a manager hq with its own work item and two live members plus one down
        When a client lists work items on the manager
        Then it sees hq's, laptop-a's and ci-box's rows, each stamped with its instance,
             the shared work item twice, and the header names cloud-1 as left out

    Requirement: docs/specs/issue-374/requirements.md R1.3, R2.2, R2.9
    """
    response = fleet["manager"].get("/api/v1/work-items")
    assert response.status_code == 200
    rows = [(r["ref"], r["instance"]) for r in response.json()]
    assert rows == [
        (REF_A, "laptop-a"),
        (REF_B, "ci-box"),
        (REF_HQ, "hq"),
        (SHARED, "ci-box"),
        (SHARED, "laptop-a"),
    ]
    assert response.headers["the-loop-instances-unreachable"] == "cloud-1"


def test_the_fleet_and_the_health_name_every_state(fleet):
    """
    Feature: the fleet read
      Scenario: A member going away degrades health and shows in the fleet
        Given the fleet above
        When a client reads /instances and /health on the manager
        Then hq is first and live, the members are live and cloud-1 unreachable,
             and health is degraded naming cloud-1

    Requirement: docs/specs/issue-374/requirements.md R2.9, R3.1
    """
    doc = fleet["manager"].get("/api/v1/instances").json()
    assert doc["role"] == "manager" and doc["name"] == "hq"
    assert [(r["name"], r["state"]) for r in doc["instances"]] == [
        ("hq", "live"),
        ("laptop-a", "live"),
        ("ci-box", "live"),
        ("cloud-1", "unreachable"),
    ]
    assert doc["instances"][3]["detail"] == "connection refused"
    assert doc["instances"][1]["managedCount"] == 2
    health = fleet["manager"].get("/api/v1/health").json()
    assert health["status"] == "degraded" and health["role"] == "manager"
    assert [r["name"] for r in health["instances"] if r["state"] != "live"] == ["cloud-1"]
    instance = fleet["manager"].get("/api/v1/instance").json()
    assert instance["role"] == "manager"
    assert {(r["ref"], r["instance"]) for r in instance["managed"]} >= {
        (REF_HQ, "hq"),
        (REF_A, "laptop-a"),
        (REF_B, "ci-box"),
    }


def test_a_keyed_read_routes_to_the_member_that_manages_the_ref(fleet):
    """
    Feature: keyed operations route
      Scenario: A keyed read routes to the member that manages the ref
        Given the fleet above
        When a client reads one work item by ref on the manager
        Then the member that manages it answers, stamped with its instance,
             and the manager's own answers for its own

    Requirement: docs/specs/issue-374/requirements.md R2.3
    """
    one = fleet["manager"].get("/api/v1/work-items/one", params={"ref": REF_B})
    assert one.status_code == 200
    assert one.json()["instance"] == "ci-box" and one.json()["ref"] == REF_B
    own = fleet["manager"].get("/api/v1/work-items/one", params={"ref": REF_HQ})
    assert own.status_code == 200 and own.json()["instance"] == "hq"
    missing = fleet["manager"].get("/api/v1/work-items/one", params={"ref": "github:octo/repo#404"})
    assert missing.status_code == 404


def test_an_ambiguous_ref_is_refused_and_sent_to_neither(fleet):
    """
    Feature: ambiguity refuses
      Scenario: An ambiguous ref is refused and sent to neither
        Given a work item declared on two members
        When a client stops it on the manager without naming an instance
        Then the answer is 409 naming both, no member received the verb,
             and naming one routes the verb to it

    Requirement: docs/specs/issue-374/requirements.md R2.4; abuse case 5
    """
    before = len(fleet["dispatcher"].calls)
    response = fleet["manager"].post(
        "/api/v1/sessions/control", json={"ref": SHARED, "verb": "stop"}
    )
    assert response.status_code == 409
    assert set(response.json()["candidates"]) == {"laptop-a", "ci-box"}
    sent = [url for _, url in fleet["dispatcher"].calls[before:] if "/sessions/control" in url]
    assert sent == []
    routed = fleet["manager"].post(
        "/api/v1/sessions/control",
        json={"ref": SHARED, "verb": "stop", "instance": "ci-box"},
    )
    # ci-box answers for itself (a stop on a work item with no session is a
    # recorded control command there, as on any worker), stamped ci-box.
    assert routed.status_code == 200 and routed.json()["instance"] == "ci-box"
    assert [url for _, url in fleet["dispatcher"].calls if "/sessions/control" in url] == [
        B_URL + "/api/v1/sessions/control"
    ]


def test_an_unknown_instance_sends_nothing(fleet):
    """Abuse case 6."""
    before = len(fleet["dispatcher"].calls)
    response = fleet["manager"].get("/api/v1/config", params={"instance": "nobody"})
    assert response.status_code == 404
    assert len(fleet["dispatcher"].calls) == before
    down = fleet["manager"].get("/api/v1/config", params={"instance": "cloud-1"})
    assert down.status_code == 502
    assert down.json()["instance"] == "cloud-1"


def test_an_operation_without_instance_is_the_managers_own(fleet):
    """
    Feature: a manager is also a worker
      Scenario: an operation without instance reaches the manager's own state
        Given the fleet above
        When a client reads the config and the daemons on the manager without instance
        Then the config is hq's own file, and the daemons list carries hq's rows
             stamped hq beside the members'

    Requirement: docs/specs/issue-374/requirements.md R1.3, R2.5, R2.7
    """
    config = fleet["manager"].get("/api/v1/config").json()
    assert config["config"]["instance"]["name"] == "hq"
    daemons = fleet["manager"].get("/api/v1/daemons").json()
    assert {row["instance"] for row in daemons} == {"hq", "laptop-a", "ci-box"}


def test_a_proxied_config_write_lands_on_the_members_file(fleet, tmp_path):
    """
    Feature: manage one instance individually
      Scenario: a proxied config write lands on the member's file
        Given the fleet above
        When a client saves a change with instance=laptop-a on the manager
        Then laptop-a's file changes and the manager's does not

    Requirement: docs/specs/issue-374/requirements.md R2.7, R5.4; abuse case 7
    """
    manager_before = fleet["path"].read_text()
    response = fleet["manager"].post(
        "/api/v1/config",
        json={"patch": {"instance": {"scope": {"mode": "locked"}}}, "instance": "laptop-a"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["written"] is True and response.json()["instance"] == "laptop-a"
    assert "mode: locked" in (tmp_path / "laptop-a" / "cli-config.yaml").read_text()
    assert fleet["path"].read_text() == manager_before


def test_a_registration_through_the_api_equals_a_hand_edit(fleet):
    """
    Feature: the registry converges on the file
      Scenario: A registration from the API equals a hand edit and is live next request
        Given the manager above
        When a client registers cloud-2 through the API
        Then the file holds it with its comment intact, and the next fleet read
             shows cloud-2 unreachable — no restart

    Requirement: docs/specs/issue-374/requirements.md R1.4, R4.1–R4.3
    """
    response = fleet["manager"].post(
        "/api/v1/instances/register", json={"name": "cloud-2", "url": "http://cloud-2:4114"}
    )
    assert response.status_code == 200, response.text
    text = fleet["path"].read_text()
    assert "# the manager" in text and "cloud-2" in text
    names = [r["name"] for r in fleet["manager"].get("/api/v1/instances").json()["instances"]]
    assert names[-1] == "cloud-2"
    assert fleet["manager"].post(
        "/api/v1/instances/register", json={"name": "cloud-2", "url": "http://x:1"}
    ).status_code == 400
    assert fleet["manager"].post("/api/v1/instances/unregister", json={"name": "cloud-2"}).status_code == 200
    assert fleet["manager"].post("/api/v1/instances/unregister", json={"name": "cloud-2"}).status_code == 404


def test_a_mismatched_member_is_neither_served_nor_sent_to(tmp_path):
    """
    Feature: a member is trusted by its name
      Scenario: A mismatched member is served from nowhere
        Given a manager registering a URL that answers as a different name
        When the fleet is listed and the member's ref is read
        Then the member is mismatched, its rows are absent, and nothing but the
             probe reached it

    Requirement: docs/specs/issue-374/requirements.md R6.1, R6.3; abuse case 2
    """
    dispatcher = Dispatcher()
    other, _ = _worker(tmp_path, "someone-else", [REF_A])
    dispatcher.clients[A_URL] = other
    root = tmp_path / "hq"
    root.mkdir()
    path = root / "cli-config.yaml"
    path.write_text(
        'version: "0.10.0"\ninstance:\n  name: hq\n  role: manager\n  manager:\n'
        f"    instances:\n      - name: laptop-a\n        url: {A_URL}\n"
    )
    import yaml

    config = yaml.safe_load(path.read_text())
    config["state"] = {"root": str(root)}
    app = create_app(config, config_path=path)
    app.state.facade.fleet._transport = dispatcher
    manager = TestClient(app)
    rows = manager.get("/api/v1/instances").json()["instances"]
    assert rows[1]["state"] == "mismatched" and "someone-else" in rows[1]["detail"]
    assert manager.get("/api/v1/work-items").json() == []
    assert manager.get("/api/v1/work-items/one", params={"ref": REF_A}).status_code == 404
    assert manager.get("/api/v1/config", params={"instance": "laptop-a"}).status_code == 502
    assert {url for _, url in dispatcher.calls} <= {A_URL + "/api/v1/instance"}


def test_the_registered_name_overwrites_a_members_claim(fleet):
    """Abuse case 9: a member's own `instance` field never survives the stamp."""
    a = fleet["a"]
    layout = layout_from_config(
        {"state": {"root": str(fleet["path"].parent.parent / "laptop-a")}}
    )
    store = WorkItemStore(layout.portable_dir, legacy=legacy_layout(layout))
    store.write_section(
        "github:octo/repo#7", "control", {"ref": "github:octo/repo#7", "command": "start"}
    )
    store.write_section("github:octo/repo#7", "instance", "ci-box")  # a claim
    rows = fleet["manager"].get("/api/v1/work-items").json()
    claimed = [r for r in rows if r["ref"] == "github:octo/repo#7"]
    assert claimed and claimed[0]["instance"] == "laptop-a"
    assert a.get("/api/v1/work-items/one", params={"ref": "github:octo/repo#7"}).status_code == 200
