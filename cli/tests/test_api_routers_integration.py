"""Integration tests: /api/v1 routes over the core facade (issue-161, T6)."""

import json

from fastapi.testclient import TestClient

from the_loop.api.app import create_app
from the_loop.state import layout_from_config, legacy_layout
from the_loop.workitem import WorkItemStore


REF = "github:octo/repo#7"


def _client(tmp_path):
    config = {"state": {"root": str(tmp_path / ".the-loop")}}
    return TestClient(create_app(config)), config


def test_work_items_round_trip(tmp_path):
    """
    Feature: control-plane work-item reads
      Scenario: a client lists and fetches work items
        Given a portable record written by an ingress
        When the client lists work items and fetches one by ref
        Then it sees the same durable record the stores hold

    Requirement: docs/specs/issue-161/requirements.md R3.1, R3.3
    """
    client, config = _client(tmp_path)
    layout = layout_from_config(config)
    store = WorkItemStore(layout.portable_dir, legacy=legacy_layout(layout))
    store.write_section(REF, "control", {"command": "start"})

    listed = client.get("/api/v1/work-items")
    assert listed.status_code == 200
    assert [r["ref"] for r in listed.json()] == [REF]

    one = client.get("/api/v1/work-items/one", params={"ref": REF})
    assert one.status_code == 200
    assert one.json()["control"]["command"] == "start"


def test_missing_work_item_is_404_and_malformed_ref_is_400(tmp_path):
    """
    Feature: control-plane input validation
      Scenario: bad input is rejected at the transport edge
        Given a running service
        When a client asks for a malformed ref or an unknown work item
        Then it receives 400 or 404 and no core state is touched

    Requirement: docs/specs/issue-161/requirements.md §Security abuse case 3
    """
    client, _ = _client(tmp_path)
    missing = client.get(
        "/api/v1/work-items/one", params={"ref": "github:octo/repo#404"}
    )
    assert missing.status_code == 404
    malformed = client.get("/api/v1/work-items/one", params={"ref": "not-a-ref"})
    assert malformed.status_code == 400


def test_graph_check_runs_against_a_repo_path(tmp_path):
    """
    Feature: control-plane graph reads
      Scenario: a client asks where a work item stands
        Given this repository's own checked-in spec for issue-161
        When the client POSTs /graph/check with the repo path
        Then it receives the same report `the-loop check` computes

    Requirement: docs/specs/issue-161/requirements.md R1.1, R1.2
    """
    import pathlib

    client, _ = _client(tmp_path)
    repo_root = str(pathlib.Path(__file__).resolve().parents[2])
    response = client.post(
        "/api/v1/graph/check",
        json={"repo": repo_root, "workItem": "issue-161", "recompute": True},
    )
    assert response.status_code == 200
    assert response.json()["workItem"] == "issue-161"


def test_graph_check_rejects_a_bad_repo_path(tmp_path):
    client, _ = _client(tmp_path)
    response = client.post(
        "/api/v1/graph/check",
        json={"repo": str(tmp_path / "nope"), "workItem": "issue-1"},
    )
    assert response.status_code == 400


def test_sessions_daemons_attention_and_events(tmp_path):
    """
    Feature: control-plane operational reads
      Scenario: a client loads the operational surfaces
        Given a machine with no sessions and stopped daemons
        When the client reads sessions, daemons, attention and event types
        Then every surface answers with well-formed, empty-safe payloads

    Requirement: docs/specs/issue-161/requirements.md R6.3
    """
    client, _ = _client(tmp_path)
    assert client.get("/api/v1/sessions").json() == []
    daemons = client.get("/api/v1/daemons").json()
    assert {d["daemon"] for d in daemons} == {"poller", "gh-webhook"}
    assert all(d["running"] is False for d in daemons)
    assert isinstance(client.get("/api/v1/attention").json(), list)
    assert "api.request" in client.get("/api/v1/events/types").json()


def test_session_control_rejects_unknown_verb(tmp_path):
    client, _ = _client(tmp_path)
    response = client.post(
        "/api/v1/sessions/control",
        json={"ref": REF, "verb": "detonate"},
    )
    assert response.status_code == 400


def test_api_operations_are_audited(tmp_path, monkeypatch):
    """
    Feature: control-plane observability
      Scenario: every API operation lands in the event log
        Given an event log configured for the service
        When a client performs a read
        Then an api.request record is appended

    Requirement: docs/specs/issue-161/requirements.md R3.5
    """
    from the_loop import eventlog

    log = tmp_path / "events.jsonl"
    eventlog.configure("service", path=log)
    try:
        client, _ = _client(tmp_path)
        client.get("/api/v1/work-items")
    finally:
        eventlog.reset()
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert any(
        r["event"] == "api.request" and r["path"] == "/api/v1/work-items"
        for r in records
    )


def test_restart_schedules_a_detached_fixed_argv_process(tmp_path, monkeypatch):
    """
    Feature: whole-system restart over the API
      Scenario: a client asks the service to restart itself
        Given the service cannot stop synchronously and still answer
        When POST /api/v1/restart runs (withUpgrade true)
        Then a detached `the-loop restart --with-upgrade` is spawned with a
             fixed argv carrying the config path this process already reads,
             and the response reports the schedule at once

    Requirement: docs/specs/issue-228/requirements.md R4.4, R4.5
    """
    from types import SimpleNamespace

    from the_loop.core import lifecycle

    spawned = {}

    def fake_popen(argv, **kwargs):
        spawned["argv"] = argv
        spawned["kwargs"] = kwargs
        return SimpleNamespace(pid=99)

    monkeypatch.setattr(lifecycle.subprocess, "Popen", fake_popen)
    client, _ = _client(tmp_path)
    response = client.post("/api/v1/restart", json={"withUpgrade": True})
    assert response.status_code == 200
    body = response.json()
    assert body["scheduled"] is True
    assert body["withUpgrade"] is True
    assert body["pid"] == 99
    assert spawned["argv"][-2:] == ["restart", "--with-upgrade"]
    assert "--config" in spawned["argv"]
    assert spawned["kwargs"]["start_new_session"] is True

    plain = client.post("/api/v1/restart", json={})
    assert plain.json()["withUpgrade"] is False
    assert spawned["argv"][-1] == "restart"
