"""Integration tests: the CLI config over /api/v1 (issue-222, T4/T5/T10/T14).

Every app here is pointed at a `tmp_path` config through ``create_app(config_path=…)``, so
no test reads or writes this repository's `.the-loop/cli-config.yaml` or the operator's
`~/.the-loop/cli-config.yaml`.
"""

import json
from pathlib import Path
from typing import cast

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from the_loop import eventlog
from the_loop.api.app import create_app
from the_loop.cli_config import load_cli_config
from the_loop.reload import Reloader

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "skills" / "the-loop" / "templates" / "cli-config.yaml"


@pytest.fixture()
def config_path(tmp_path) -> Path:
    path = tmp_path / ".the-loop" / "cli-config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def _client(config_path: Path) -> TestClient:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return TestClient(create_app(config, config_path=config_path))


def test_the_config_and_its_schema_are_served(config_path):
    """
    Feature: the Settings tab reads the config the daemon runs on
      Scenario: a client fetches the config and its schema
        Given a service pointed at a config file
        When the client GETs /api/v1/config and /api/v1/config/schema
        Then it receives the parsed file with its path, and a schema with no $ref left

    Requirement: docs/specs/issue-222/requirements.md R1.1, R1.3
    """
    client = _client(config_path)

    document = client.get("/api/v1/config")
    assert document.status_code == 200
    assert document.json()["path"] == str(config_path)
    assert document.json()["exists"] is True
    assert document.json()["config"]["routing"]["enabled"] is False

    schema = client.get("/api/v1/config/schema")
    assert schema.status_code == 200
    assert "$ref" not in json.dumps(schema.json())
    assert (
        schema.json()["properties"]["routing"]["properties"]["enabled"]["type"]
        == "boolean"
    )


def test_a_machine_with_no_config_is_not_an_error(tmp_path):
    """
    Feature: the Settings tab works before anything is configured
      Scenario: the resolved config file does not exist
        Given a service pointed at a path with no file
        When the client GETs /api/v1/config
        Then it receives 200, exists: false, and the path it would write

    Requirement: docs/specs/issue-222/requirements.md R1.2
    """
    path = tmp_path / "cli-config.yaml"
    response = TestClient(create_app({}, config_path=path)).get("/api/v1/config")
    assert response.status_code == 200
    assert response.json() == {
        "path": str(path),
        "exists": False,
        "version": "",
        "config": {},
    }


def test_a_save_writes_the_file_and_reports_what_it_changed(config_path):
    """
    Feature: saving from the Settings tab
      Scenario: the operator changes one value
        Given a service pointed at a commented config
        When the client POSTs a sparse patch
        Then the file holds the change with its comments, and the response names the key

    Requirement: docs/specs/issue-222/requirements.md R2.1, R2.2, R5.6
    """
    client = _client(config_path)
    before = config_path.read_text(encoding="utf-8")

    response = client.post(
        "/api/v1/config", json={"patch": {"routing": {"enabled": True}}}
    )
    assert response.status_code == 200
    assert response.json()["changed"] == ["routing.enabled"]
    assert response.json()["written"] is True

    after = config_path.read_text(encoding="utf-8")
    assert yaml.safe_load(after)["routing"]["enabled"] is True
    assert _comments(after) == _comments(before)


def test_an_invalid_save_is_400_and_the_file_is_untouched(config_path):
    """
    Feature: an invalid config never reaches disk
      Scenario: a patch names an unknown key
        Given a service pointed at a config file
        When the client POSTs a patch the schema refuses
        Then the response is 400 naming the key, and the file is byte-identical

    Requirement: docs/specs/issue-222/requirements.md R3.1, R3.5
    """
    client = _client(config_path)
    before = config_path.read_bytes()

    response = client.post("/api/v1/config", json={"patch": {"routing": {"nope": 1}}})
    assert response.status_code == 400
    assert "routing.nope" in response.json()["detail"]
    assert config_path.read_bytes() == before


def test_the_unbootable_cors_pairing_is_refused_at_write_time(config_path):
    """
    Feature: a save cannot leave the service unable to restart
      Scenario: allowOrigins ["*"] with credentials
        Given a service whose boot guard refuses that pairing
        When the client tries to save it
        Then the response is 400 and the file is byte-identical

    Requirement: docs/specs/issue-222/requirements.md R3.3
    """
    client = _client(config_path)
    before = config_path.read_bytes()
    response = client.post(
        "/api/v1/config",
        json={
            "patch": {
                "service": {"cors": {"allowOrigins": ["*"], "allowCredentials": True}}
            }
        },
    )
    assert response.status_code == 400
    assert config_path.read_bytes() == before


def test_no_request_field_can_name_another_file(config_path, tmp_path):
    """
    Feature: the config route writes one file
      Scenario: a caller tries to redirect the write
        Given a service pointed at a config file
        When the client POSTs a body carrying a `path`
        Then the extra field changes nothing: the resolved file is the one written

    Requirement: docs/specs/issue-222/requirements.md R1.4, §Security abuse case 1
    """
    elsewhere = tmp_path / "elsewhere.yaml"
    client = _client(config_path)
    response = client.post(
        "/api/v1/config",
        json={"patch": {"routing": {"enabled": True}}, "path": str(elsewhere)},
    )
    assert response.status_code == 200
    assert response.json()["path"] == str(config_path)
    assert not elsewhere.exists()


def test_a_write_is_recorded_as_key_paths_never_values(config_path, tmp_path):
    """
    Feature: a config change is a visible act
      Scenario: an operator widens who may command the loop
        Given an event log
        When routing.authorizedUsers is saved
        Then the trail records the key path and the file, and not the value

    Requirement: docs/specs/issue-222/requirements.md §Security abuse case 2
    """
    log = tmp_path / "events.jsonl"
    eventlog.configure("test", path=log, enabled=True)
    try:
        _client(config_path).post(
            "/api/v1/config", json={"patch": {"routing": {"authorizedUsers": ["mole"]}}}
        )
    finally:
        eventlog.reset()  # the log is process-wide; leave the next test unconfigured
    records = [
        json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
    ]
    updates = [record for record in records if record["event"] == "config.updated"]
    assert updates and updates[0]["keys"] == ["routing.authorizedUsers"]
    assert "mole" not in log.read_text(encoding="utf-8")


def test_a_saved_change_is_live_on_the_next_request(config_path):
    """
    Feature: a saved change needs no restart
      Scenario: the service answers from the config it just wrote
        Given a service whose in-process config was loaded at boot
        When a change is saved through the API
        Then the next request sees the new value

    Requirement: docs/specs/issue-222/requirements.md R4.2
    """
    client = _client(config_path)
    assert (
        client.get("/api/v1/config").json()["config"]["polling"]["intervalSeconds"]
        == 60
    )

    client.post("/api/v1/config", json={"patch": {"polling": {"intervalSeconds": 15}}})

    assert (
        client.get("/api/v1/config").json()["config"]["polling"]["intervalSeconds"]
        == 15
    )
    # ...and the value the *routes* run on moved with it, not just the file.
    assert _holder(client).current["polling"]["intervalSeconds"] == 15


def test_a_daemon_watching_the_file_sees_a_saved_change(config_path):
    """
    Feature: a saved change reaches the daemons with no extra signalling
      Scenario: the poller's reloader is watching while an operator saves from the UI
        Given a Reloader baselined on the config file, as the poller and receiver hold
        When a change is saved through the API
        Then the reloader rebuilds, and the rebuilt config carries the new value

    Requirement: docs/specs/issue-222/requirements.md R4.1
    """
    reloader = Reloader(config_path, lambda: load_cli_config(config_path, strict=True))
    assert reloader.poll_for_change() is None  # nothing has changed yet

    _client(config_path).post(
        "/api/v1/config", json={"patch": {"routing": {"maxConcurrentDispatches": 9}}}
    )

    rebuilt = reloader.poll_for_change()
    assert rebuilt is not None
    assert rebuilt["routing"]["maxConcurrentDispatches"] == 9


def test_a_hand_edit_is_picked_up_too(config_path):
    """
    Feature: a saved change needs no restart
      Scenario: the operator edits the file directly
        Given a running service
        When the config file is changed outside the API
        Then the next request serves the edited config

    Requirement: docs/specs/issue-222/requirements.md R4.3
    """
    client = _client(config_path)
    client.get("/api/v1/config")  # baseline

    text = config_path.read_text(encoding="utf-8").replace(
        "intervalSeconds: 60", "intervalSeconds: 21"
    )
    config_path.write_text(text, encoding="utf-8")

    assert (
        client.get("/api/v1/config").json()["config"]["polling"]["intervalSeconds"]
        == 21
    )
    assert _holder(client).current["polling"]["intervalSeconds"] == 21


def test_a_file_that_becomes_unparseable_keeps_the_previous_config(config_path):
    """
    Feature: a mid-edit file does not reset the service to defaults
      Scenario: the config is saved in a broken state by an editor
        Given a running service
        When the file becomes invalid YAML
        Then the routes keep the last good config (and the read route says it is broken)

    Requirement: docs/specs/issue-222/requirements.md R1.5, R4.3
    """
    client = _client(config_path)
    client.get("/api/v1/config")

    config_path.write_text("routing: [unclosed\n", encoding="utf-8")

    assert client.get("/api/v1/config").status_code == 400
    assert _holder(client).current["polling"]["intervalSeconds"] == 60


def _holder(client: TestClient):
    """What the app's routes are actually running on — not what the file says."""
    return cast(FastAPI, client.app).state.config_holder


def _comments(text: str) -> list:
    return [line for line in text.splitlines() if line.lstrip().startswith("#")]
