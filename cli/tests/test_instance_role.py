"""Unit tests for the instance role and the manager's registry (issue-374).

``role``, ``manager.instances`` (validated by index), the two boot refusals under
``strict=True`` and the warn-and-``worker`` reading otherwise, the clamped numbers, the
boot-only ``instance.role`` in ``restartRequired``, and the schema.

Spec: docs/specs/issue-374/design.md §1.
"""

from __future__ import annotations

import logging

import pytest

from the_loop import configschema
from the_loop.core import config as core_config
from the_loop.instance import (
    MANAGER,
    WORKER,
    InstanceConfig,
    InstanceConfigError,
    ManagerConfig,
    Member,
)


def test_the_role_defaults_to_worker():
    """R1.2: a config without `role` is a worker, byte-for-byte 19.14.1."""
    config = InstanceConfig.from_mapping({"name": "laptop-a"})
    assert config.role == WORKER
    assert config.manager == ManagerConfig()
    assert config.is_manager is False


def test_a_manager_reads_its_registry_and_numbers():
    """R1.1: `role`, `manager.instances`, the two numbers."""
    config = InstanceConfig.from_mapping(
        {
            "name": "hq",
            "role": "manager",
            "manager": {
                "instances": [
                    {"name": "laptop-a", "url": "http://10.0.0.5:4114/"},
                    {"name": "ci-box", "url": "https://ci.example/the-loop"},
                ],
                "timeoutSeconds": 3,
                "probeIntervalSeconds": 7.5,
            },
        }
    )
    assert config.role == MANAGER and config.is_manager
    assert config.manager.members == (
        Member("laptop-a", "http://10.0.0.5:4114"),
        Member("ci-box", "https://ci.example/the-loop"),
    )
    assert config.manager.timeout_seconds == 3.0
    assert config.manager.probe_interval_seconds == 7.5
    assert config.manager.member("ci-box") == Member("ci-box", "https://ci.example/the-loop")
    assert config.manager.member("nope") is None


@pytest.mark.parametrize(
    "entry",
    [
        {"name": "Laptop", "url": "http://x:1"},  # grammar
        {"name": "laptop-a", "url": "ftp://x:1"},  # scheme
        {"name": "laptop-a", "url": "http://user:pw@x:1"},  # userinfo
        {"name": "laptop-a"},  # no url
        {"url": "http://x:1"},  # no name
        "http://x:1",  # not a mapping
    ],
)
def test_the_registry_skips_an_invalid_entry_by_index(entry, caplog):
    """R1.6: a bad entry is warned about by position and skipped; the rest are kept."""
    with caplog.at_level(logging.WARNING, logger="the-loop.instance"):
        config = InstanceConfig.from_mapping(
            {
                "name": "hq",
                "role": "manager",
                "manager": {"instances": [entry, {"name": "ok", "url": "http://ok:1"}]},
            }
        )
    assert config.manager.members == (Member("ok", "http://ok:1"),)
    assert "manager.instances[0]" in caplog.text
    # The value itself is never echoed — a config is data pasted from anywhere.
    assert "user:pw" not in caplog.text


def test_the_registry_skips_a_duplicate_name_and_the_managers_own_address(caplog):
    with caplog.at_level(logging.WARNING, logger="the-loop.instance"):
        config = InstanceConfig.from_mapping(
            {
                "name": "hq",
                "role": "manager",
                "manager": {
                    "instances": [
                        {"name": "a", "url": "http://a:1"},
                        {"name": "a", "url": "http://a:2"},
                        {"name": "me", "url": "http://127.0.0.1:4114"},
                    ]
                },
            },
            own_url="http://127.0.0.1:4114",
        )
    assert config.manager.members == (Member("a", "http://a:1"),)
    assert "manager.instances[1]" in caplog.text
    assert "manager.instances[2]" in caplog.text


def test_the_numbers_clamp_upward_and_tolerate_junk():
    config = InstanceConfig.from_mapping(
        {
            "name": "hq",
            "role": "manager",
            "manager": {"timeoutSeconds": 0, "probeIntervalSeconds": "junk"},
        }
    )
    assert config.manager.timeout_seconds == 1.0
    assert config.manager.probe_interval_seconds == 15.0


def test_an_unknown_role_reads_as_worker_with_a_warning(caplog):
    """R1.5 (the lenient readers): `status` must still answer."""
    with caplog.at_level(logging.WARNING, logger="the-loop.instance"):
        config = InstanceConfig.from_mapping({"name": "hq", "role": "manger"})
    assert config.role == WORKER
    assert "instance.role" in caplog.text


def test_a_manager_refuses_to_boot_on_an_unknown_role():
    """R1.5: under `strict=True` (serve.py) a mistyped role is refused, not narrowed."""
    with pytest.raises(InstanceConfigError) as excinfo:
        InstanceConfig.from_mapping({"name": "hq", "role": "manger"}, strict=True)
    assert "instance.role" in str(excinfo.value)
    assert "worker" in str(excinfo.value) and "manager" in str(excinfo.value)


def test_a_manager_refuses_to_boot_unnamed():
    """R1.5: a manager stamps its own rows with its name, so it needs one."""
    with pytest.raises(InstanceConfigError) as excinfo:
        InstanceConfig.from_mapping({"role": "manager"}, strict=True)
    assert "instance.name" in str(excinfo.value)
    # Leniently, the same config is a worker with a warning.
    assert InstanceConfig.from_mapping({"role": "manager"}).role == WORKER


def test_a_worker_with_a_registry_keeps_it_but_is_not_a_manager():
    """The block is read whole; only `role` decides what the service does with it."""
    config = InstanceConfig.from_mapping(
        {"name": "a", "manager": {"instances": [{"name": "b", "url": "http://b:1"}]}}
    )
    assert config.role == WORKER
    assert config.manager.members == (Member("b", "http://b:1"),)


def test_the_role_is_boot_only_and_the_registry_is_hot():
    """R1.4: `instance.role` needs a restart; `instance.manager.*` does not."""
    assert core_config._restart_required(["instance.role"]) == ["instance.role"]
    assert core_config._restart_required(["instance.manager.instances"]) == []
    assert core_config._restart_required(["instance.name"]) == []


def test_the_schema_accepts_the_block_and_refuses_an_unknown_key():
    """R1.1: the authored schema carries the keys; `additionalProperties: false` holds."""
    good = {
        "version": "0.10.0",
        "instance": {
            "name": "hq",
            "role": "manager",
            "manager": {
                "instances": [{"name": "laptop-a", "url": "http://10.0.0.5:4114"}],
                "timeoutSeconds": 10,
                "probeIntervalSeconds": 15,
            },
        },
    }
    assert configschema.validate(good) == []
    bad = {"version": "0.10.0", "instance": {"role": "boss"}}
    assert configschema.validate(bad)
    extra = {"version": "0.10.0", "instance": {"manager": {"members": []}}}
    assert configschema.validate(extra)
    unnamed_entry = {
        "version": "0.10.0",
        "instance": {"manager": {"instances": [{"url": "http://x:1"}]}},
    }
    assert configschema.validate(unnamed_entry)
