"""Integration scenarios for an instance that consumes from a gateway (issue-496,
T2/T10 — R3.8, R9.3, R10.3, R14.1, R14.2, R14.4, R14.5; non-functional Compatibility).

Feature: an instance with a gateway block runs no ingress of its own
"""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

from fastapi.testclient import TestClient

from gateway_support import write_gateway_config
from the_loop.api import ingress as ingress_mod
from the_loop.api.app import create_app
from the_loop.commands import gateway_cmd
from the_loop.core import lifecycle
from the_loop.gateway import client as gateway_client


def _instance_config(
    tmp_path: Path, url: str = "http://127.0.0.1:8790", **extra
) -> dict:
    config = {
        "state": {"root": str(tmp_path / ".the-loop")},
        "repositories": ["o/r"],
        "instance": {"name": "laptop-a"},
        "webhooks": {"ghWebhook": {"enabled": True}},
        "polling": {"enabled": True, "sources": [{"provider": "github"}]},
        "channels": {"slack": {"enabled": True, "read": {"mode": "socket"}}},
        "gateway": {
            "url": url,
            "pollIntervalSeconds": 1,
            "longPollSeconds": 0,
            "actors": {"github": ["octocat"]},
        },
    }
    config.update(extra)
    return config


def test_an_instance_with_a_gateway_block_runs_no_ingress_of_its_own(tmp_path):
    """
    Feature: an instance with a gateway block runs no ingress of its own
      Scenario: an instance with a gateway block runs no ingress of its own
        Given a config enabling the receiver, the poller and the Slack listener AND a
              gateway block
        When the hosted set is composed and status is read
        Then the only wanted ingress is the gateway client, the three read
             `off · gateway configured`, and health lists the client

    Requirement: docs/specs/issue-496/requirements.md#requirement-3 (R3.8), R10.3
    """
    config = _instance_config(tmp_path)
    enabled = lifecycle.enabled_services(config)
    assert enabled == {
        "service": True,
        "gh-webhook": False,
        "poller": False,
        "slack-listener": False,
        "gateway-client": True,
    }
    assert [name for name, _ in ingress_mod._wanted(config)] == ["gateway-client"]
    rows = {row["name"]: row for row in lifecycle.ingress_health(config)}
    assert rows["poller"]["detail"] == lifecycle.GATEWAY_OFF
    assert (
        rows["gh-webhook"]["enabled"] is False
        and rows["slack-listener"]["enabled"] is False
    )
    assert (
        rows["gateway-client"]["enabled"] is True
        and rows["gateway-client"]["running"] is False
    )
    report = lifecycle.status_all(config)
    services = {row["service"]: row for row in report["services"]}
    for name in ("gh-webhook", "poller", "slack-listener"):
        assert (
            services[name]["detail"] == "off · gateway configured"
            and services[name]["enabled"] is False
        )
    assert services["gateway-client"]["enabled"] is True
    assert (
        report["gateway"]["configured"] is True
        and report["gateway"]["state"] == "unknown"
    )
    assert report["ok"] is False  # the client is enabled and not running


def test_an_instance_without_a_gateway_block_hosts_the_receiver_poller_and_listener_as_before(
    tmp_path,
):
    """
    Feature: compatibility
      Scenario: an instance without a gateway block hosts the receiver, poller and
                listener as before
    Requirement: docs/specs/issue-496/requirements.md non-functional Compatibility; R14.2
    """
    config = _instance_config(tmp_path)
    del config["gateway"]
    enabled = lifecycle.enabled_services(config)
    assert enabled["gh-webhook"] and enabled["poller"] and enabled["slack-listener"]
    assert enabled["gateway-client"] is False
    assert [name for name, _ in ingress_mod._wanted(config)] == [
        "gh-webhook",
        "poller",
        "slack-listener",
    ]
    assert [row["name"] for row in lifecycle.ingress_health(config)] == [
        "poller",
        "gh-webhook",
        "slack-listener",
    ]
    report = lifecycle.status_all(config)
    assert report["gateway"] == {"configured": False, "state": "off"}
    assert all(
        row.get("detail", "") != lifecycle.GATEWAY_OFF for row in report["services"]
    )


def test_the_instance_api_serves_the_gateway_document(tmp_path):
    """
    Feature: an instance with a gateway block runs no ingress of its own
      Scenario: GET /api/v1/gateway describes the client for the dashboard card
    Requirement: docs/specs/issue-496/requirements.md#requirement-10 (R10.3)
    """
    config = _instance_config(tmp_path)
    config["service"] = {"hostIngresses": False}
    with TestClient(
        create_app(config, config_path=tmp_path / "cli-config.yaml")
    ) as client:
        doc = client.get("/api/v1/gateway").json()
        assert doc["configured"] is True and doc["state"] == "unknown"
        assert doc["instance"] == "laptop-a" and doc["mode"] == {
            "pollIntervalSeconds": 1,
            "longPollSeconds": 0,
        }
    off = _instance_config(tmp_path)
    del off["gateway"]
    off["service"] = {"hostIngresses": False}
    with TestClient(
        create_app(off, config_path=tmp_path / "cli-config.yaml")
    ) as client:
        assert client.get("/api/v1/gateway").json() == {
            "configured": False,
            "state": "off",
        }


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_gateway_and_an_instance_share_one_machine_on_loopback(tmp_path, monkeypatch):
    """
    Feature: an instance with a gateway block runs no ingress of its own
      Scenario: a gateway and an instance share one machine on loopback
        Given a real gateway process on a loopback port and an instance whose gateway
              URL is that loopback address, started in that order
        When the instance's service hosts its ingresses
        Then the only hosted ingress is the gateway client, it connects (the gateway's
             instances view lists laptop-a with a live lease), GET /api/v1/gateway says
             connected, the Daemons rows say off · gateway configured, and the two
             processes have separate state roots and pidfiles; stopping the gateway
             turns the client unreachable without any fallback to local ingresses

    Requirement: docs/specs/issue-496/requirements.md#requirement-14 (R14.1, R14.2,
                 R14.4, R14.5), R3.8
    """
    port = _free_port()
    gateway_config = write_gateway_config(
        tmp_path / "gw",
        listen={"host": "127.0.0.1", "port": port},
        github={"poll": {"enabled": False}},
        slack={"socket": {"enabled": False}},
    )
    monkeypatch.setenv(
        "PYTHONPATH",
        str(Path(__file__).resolve().parents[1])
        + os.pathsep
        + os.environ.get("PYTHONPATH", ""),
    )
    started = gateway_cmd.start_gateway(gateway_config, wait=30)
    assert started["running"], started
    try:
        config = _instance_config(tmp_path / "inst", url=f"http://127.0.0.1:{port}")
        config_path = tmp_path / "inst" / ".the-loop" / "cli-config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config))
        with TestClient(create_app(config, config_path=config_path)) as client:
            deadline = time.monotonic() + 10
            doc = {}
            while time.monotonic() < deadline:
                doc = client.get("/api/v1/gateway").json()
                if doc.get("state") == "connected":
                    break
                time.sleep(0.1)
            assert doc.get("state") == "connected", doc
            assert doc["instance"] == "laptop-a" and doc["health"]["ok"] is True
            assert doc["queue"]["instance"] == "laptop-a"
            health = client.get("/api/v1/health").json()
            rows = {row["name"]: row for row in health["ingresses"]}
            assert rows["gateway-client"]["running"] is True
            assert (
                rows["poller"]["detail"] == lifecycle.GATEWAY_OFF
                and not rows["poller"]["running"]
            )
            listed = gateway_cmd._get(gateway_config, "instances")
            assert listed is not None
            (row,) = [r for r in listed["instances"] if r["instance"] == "laptop-a"]
            assert row["leaseLive"] is True and row["actors"] == {"github": ["octocat"]}
            assert gateway_client.current() is not None
            # separate roots, separate pidfiles
            assert gateway_config.pidfile.is_file()
            assert (
                Path(config["state"]["root"]).resolve()
                != gateway_config.state_root.resolve()
            )
            # the gateway goes away: the client reports unreachable and starts nothing of its own
            gateway_cmd.stop_gateway(gateway_config)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                doc = client.get("/api/v1/gateway").json()
                if doc.get("state") == "unreachable":
                    break
                time.sleep(0.1)
            assert doc.get("state") == "unreachable", doc
            rows = {
                row["name"]: row
                for row in client.get("/api/v1/health").json()["ingresses"]
            }
            assert not rows["poller"]["running"] and not rows["gh-webhook"]["running"]
            assert lifecycle.gateway_line(doc).startswith("unreachable · retrying")
    finally:
        gateway_cmd.stop_gateway(gateway_config)
    assert gateway_client.current() is None


def test_the_gateway_line_wording(tmp_path):
    assert lifecycle.gateway_line({"configured": False}) == "not configured"
    assert (
        lifecycle.gateway_line(
            {
                "configured": True,
                "state": "connected",
                "url": "http://127.0.0.1:8790",
                "mode": {"longPollSeconds": 20},
            }
        )
        == "connected · long-poll http://127.0.0.1:8790"
    )
    assert (
        lifecycle.gateway_line(
            {
                "configured": True,
                "state": "connected",
                "url": "u",
                "mode": {"longPollSeconds": 0},
            }
        )
        == "connected · polling u"
    )
    assert (
        lifecycle.gateway_line(
            {
                "configured": True,
                "state": "refused",
                "error": "duplicate-instance",
                "refusedBy": "p1",
            }
        )
        == "refused · duplicate-instance (409) — held by p1"
    )
    assert (
        lifecycle.gateway_line({"configured": True, "state": "unreachable", "url": "u"})
        == "unreachable · retrying u"
    )
    assert (
        lifecycle.gateway_line(
            {"configured": True, "state": "connecting", "attempt": 3}
        )
        == "connecting · attempt 3"
    )
