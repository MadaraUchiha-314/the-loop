"""`the-loop instances list|register|unregister` and the fleet lines in `status`
(issue-374 R3.3, R4.6)."""

from __future__ import annotations

import json

import yaml

from the_loop.cli import main
from the_loop.commands import instances_cmd, lifecycle_cmd
from the_loop.core import lifecycle

MANAGER = """# keep me
version: "0.10.0"
instance:
  name: hq
  role: manager
  manager:
    instances: []
"""


def _quiet(monkeypatch):
    monkeypatch.setattr(instances_cmd.eventlog, "configure_from_file", lambda s: None)
    monkeypatch.setattr(instances_cmd.eventlog, "emit", lambda *a, **k: None)


def _write(tmp_path, text):
    root = tmp_path / ".the-loop"
    root.mkdir(exist_ok=True)
    path = root / "cli-config.yaml"
    path.write_text(text)
    return path


def test_list_on_a_worker_prints_its_one_row(tmp_path, monkeypatch, capsys):
    """
    Feature: `the-loop instances`
      Scenario: list on a worker
        Given a worker named laptop-a
        When `the-loop instances list` runs
        Then one row prints, laptop-a, live, marked as this instance
    Requirement: docs/specs/issue-374/requirements.md R4.6, R3.1
    """
    monkeypatch.chdir(tmp_path)
    _quiet(monkeypatch)
    _write(tmp_path, 'version: "0.10.0"\ninstance:\n  name: laptop-a\n')
    assert main(["instances", "list"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("name")
    assert (
        out[1].startswith("laptop-a")
        and "live" in out[1]
        and "(this instance)" in out[1]
    )
    assert main(["instances", "list", "--format", "json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["role"] == "worker" and doc["instances"][0]["name"] == "laptop-a"


def test_register_on_a_worker_exits_2_naming_the_role(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _quiet(monkeypatch)
    path = _write(tmp_path, 'version: "0.10.0"\ninstance:\n  name: laptop-a\n')
    before = path.read_text()
    assert main(["instances", "register", "b", "http://b:1"]) == 2
    assert "instance.role" in capsys.readouterr().err
    assert path.read_text() == before


def test_register_and_unregister_write_the_managers_file(tmp_path, monkeypatch, capsys):
    """
    Feature: `the-loop instances`
      Scenario: register on a manager
        Given a manager's config with a comment in it
        When `the-loop instances register laptop-a http://10.0.0.5:4114` runs
        Then the registry in the file holds the entry and the comment survives
    Requirement: docs/specs/issue-374/requirements.md R4.2, R4.6
    """
    monkeypatch.chdir(tmp_path)
    _quiet(monkeypatch)
    path = _write(tmp_path, MANAGER)
    assert main(["instances", "register", "laptop-a", "http://10.0.0.5:4114"]) == 0
    assert "registered laptop-a" in capsys.readouterr().out
    assert "# keep me" in path.read_text()
    assert yaml.safe_load(path.read_text())["instance"]["manager"]["instances"] == [
        {"name": "laptop-a", "url": "http://10.0.0.5:4114"}
    ]
    assert main(["instances", "register", "Laptop", "http://x:1"]) == 2
    assert "name must fit" in capsys.readouterr().err
    assert main(["instances", "unregister", "nobody"]) == 1
    assert main(["instances", "unregister", "laptop-a"]) == 0
    assert yaml.safe_load(path.read_text())["instance"]["manager"]["instances"] == []


def test_no_action_is_usage_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["instances"]) == 2
    assert "needs an action" in capsys.readouterr().err


def test_status_prints_the_fleet_on_a_manager(tmp_path, monkeypatch, capsys):
    """
    Feature: `the-loop status`
      Scenario: the fleet lines (issue-374)
        Given a status report carrying a manager's instances document
        When `the-loop status` runs in text form
        Then a headline names the manager and one row prints per instance
    Requirement: docs/specs/issue-374/requirements.md R3.3
    """
    monkeypatch.chdir(tmp_path)
    report = {
        "services": [],
        "instance": {
            "name": "hq",
            "role": "manager",
            "scope": {"mode": "open", "workItems": []},
            "managed": [],
        },
        "instances": {
            "role": "manager",
            "name": "hq",
            "instances": [
                {
                    "name": "hq",
                    "url": "http://127.0.0.1:4114",
                    "state": "live",
                    "version": "1",
                    "mode": "open",
                    "managedCount": 0,
                    "sessionCount": 0,
                },
                {
                    "name": "laptop-a",
                    "url": "http://10.0.0.5:4114",
                    "state": "live",
                    "version": "1",
                    "mode": "addressed",
                    "managedCount": 4,
                    "sessionCount": 2,
                },
                {
                    "name": "cloud-1",
                    "url": "http://10.0.0.9:4114",
                    "state": "unreachable",
                    "detail": "connection refused",
                },
            ],
        },
        "ok": True,
    }
    monkeypatch.setattr(
        lifecycle, "status_all", lambda config, config_path=None: report
    )
    monkeypatch.setattr(lifecycle_cmd, "_config_or_error", lambda: {})
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "instances   hq [manager] — this instance + 2 registered, 1 of 2 live" in out
    assert "laptop-a" in out and "cloud-1" in out and "connection refused" in out

    report["instances"] = {
        "role": "worker",
        "name": "a",
        "instances": [{"name": "a", "state": "live"}],
    }
    report["instance"]["role"] = "worker"
    assert main(["status"]) == 0
    assert "instances " not in capsys.readouterr().out


def test_status_all_carries_the_fleet_document(tmp_path):
    doc = lifecycle.status_all(
        {"state": {"root": str(tmp_path)}, "instance": {"name": "a"}}
    )
    assert doc["instances"]["role"] == "worker"
    assert [row["name"] for row in doc["instances"]["instances"]] == ["a"]
