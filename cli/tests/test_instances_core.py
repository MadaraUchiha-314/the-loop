"""Unit tests for the fleet read and the registry writes (issue-374).

``core.instances``: the worker's self row, ``register``/``unregister`` writing
``instance.manager.instances`` through ``core.config.update_config`` (comments kept,
file byte-identical on refusal), the worker's refusal, and ``core.instance.assert_self``.

Spec: docs/specs/issue-374/design.md §6.
"""

from __future__ import annotations

import pytest

from the_loop.core import instance as core_instance
from the_loop.core import instances as core_instances

MANAGER_CONFIG = """# the manager's config — this comment must survive a registration
version: "0.10.0"
instance:
  name: hq
  role: manager
  manager:
    instances: []   # filled in by the tab, the CLI or the API
"""


@pytest.fixture
def manager_file(tmp_path):
    path = tmp_path / "cli-config.yaml"
    path.write_text(MANAGER_CONFIG)
    return path


def _config(path):
    import yaml

    return yaml.safe_load(path.read_text())


def test_a_worker_lists_itself_as_one_live_row(tmp_path):
    """R3.1: the same row shape a manager reports for a member."""
    config = {"state": {"root": str(tmp_path)}, "instance": {"name": "laptop-a"}}
    doc = core_instances.list_instances(config)
    assert doc["role"] == "worker" and doc["name"] == "laptop-a"
    (row,) = doc["instances"]
    assert row["name"] == "laptop-a"
    assert row["url"] == "http://127.0.0.1:4114"
    assert row["state"] == "live"
    assert row["mode"] == "open"
    assert row["managedCount"] == 0 and row["sessionCount"] == 0
    assert row["version"] and row["probedAt"].endswith("Z")


def test_describe_instance_carries_the_session_count(tmp_path):
    doc = core_instance.describe_instance({"state": {"root": str(tmp_path)}})
    assert doc["sessionCount"] == 0
    assert doc["role"] == "worker"


def test_a_worker_refuses_to_register(tmp_path):
    """R4.4: the routes exist on every instance and do nothing on a worker."""
    path = tmp_path / "cli-config.yaml"
    path.write_text('version: "0.10.0"\ninstance:\n  name: laptop-a\n')
    with pytest.raises(ValueError) as excinfo:
        core_instances.register_instance(
            _config(path), "b", "http://b:1", config_path=path
        )
    assert "instance.role" in str(excinfo.value)
    with pytest.raises(ValueError):
        core_instances.unregister_instance(_config(path), "b", config_path=path)


def test_register_writes_the_registry_through_the_splice(manager_file):
    """R4.2: one write path — comments survive, the change is in the file."""
    result = core_instances.register_instance(
        _config(manager_file), "laptop-a", "http://10.0.0.5:4114/", config_path=manager_file
    )
    assert result["written"] is True and result["instance"] == "laptop-a"
    assert result["restartRequired"] == []
    text = manager_file.read_text()
    assert "this comment must survive" in text
    assert _config(manager_file)["instance"]["manager"]["instances"] == [
        {"name": "laptop-a", "url": "http://10.0.0.5:4114"}
    ]
    # A second one is appended, not replacing the first.
    core_instances.register_instance(
        _config(manager_file), "ci-box", "https://ci.example/the-loop", config_path=manager_file
    )
    names = [e["name"] for e in _config(manager_file)["instance"]["manager"]["instances"]]
    assert names == ["laptop-a", "ci-box"]


@pytest.mark.parametrize(
    "name, url, needle",
    [
        ("Laptop", "http://x:1", "name"),
        ("laptop-a", "ftp://x:1", "url"),
        ("laptop-a", "http://user:pw@x:1", "url"),
        ("laptop-a", "http://127.0.0.1:4114", "own"),
    ],
)
def test_register_refuses_an_invalid_entry_and_writes_nothing(
    manager_file, name, url, needle
):
    """R4.3, abuse case 1: validated as the reader validates; the file is untouched."""
    before = manager_file.read_text()
    with pytest.raises(ValueError) as excinfo:
        core_instances.register_instance(
            _config(manager_file), name, url, config_path=manager_file
        )
    assert needle in str(excinfo.value)
    assert manager_file.read_text() == before


def test_register_refuses_a_duplicate_name(manager_file):
    core_instances.register_instance(
        _config(manager_file), "a", "http://a:1", config_path=manager_file
    )
    before = manager_file.read_text()
    with pytest.raises(ValueError) as excinfo:
        core_instances.register_instance(
            _config(manager_file), "a", "http://a:2", config_path=manager_file
        )
    assert "already registered" in str(excinfo.value)
    assert manager_file.read_text() == before


def test_unregister_removes_the_entry_and_refuses_an_unknown_name(manager_file):
    core_instances.register_instance(
        _config(manager_file), "a", "http://a:1", config_path=manager_file
    )
    core_instances.register_instance(
        _config(manager_file), "b", "http://b:1", config_path=manager_file
    )
    result = core_instances.unregister_instance(
        _config(manager_file), "a", config_path=manager_file
    )
    assert result["instance"] == "a"
    assert [e["name"] for e in _config(manager_file)["instance"]["manager"]["instances"]] == ["b"]
    with pytest.raises(LookupError):
        core_instances.unregister_instance(
            _config(manager_file), "a", config_path=manager_file
        )


def test_registration_is_recorded_by_name_never_url(manager_file, monkeypatch):
    """The event log names people, hosts and binaries too easily; names only."""
    emitted = []
    monkeypatch.setattr(core_instances.eventlog, "emit", lambda *a, **k: emitted.append((a, k)))
    core_instances.register_instance(
        _config(manager_file), "a", "http://secret-host:1", config_path=manager_file
    )
    core_instances.unregister_instance(_config(manager_file), "a", config_path=manager_file)
    events = [a[0] for a, k in emitted]
    assert "instance.registered" in events and "instance.unregistered" in events
    assert not any("secret-host" in str(k) for a, k in emitted)


def test_assert_self_accepts_empty_and_own_name_and_refuses_a_foreign_one():
    """R2.6 (the worker half), abuse case 6."""
    config = {"instance": {"name": "laptop-a"}}
    core_instance.assert_self("", config)
    core_instance.assert_self("laptop-a", config)
    with pytest.raises(LookupError) as excinfo:
        core_instance.assert_self("ci-box", config)
    assert "ci-box" in str(excinfo.value)
    with pytest.raises(LookupError):
        core_instance.assert_self("anyone", {})
