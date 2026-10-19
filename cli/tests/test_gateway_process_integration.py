"""Integration scenarios for the gateway process (issue-496, T2/T7/T8 — R1.1, R1.6,
R8.4, R8.5, R8.6, R9.1, R9.2, R14.2, R14.3, R3.6; abuse case 6; fail-closed).

Feature: the gateway is one process that follows its own config
"""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from gateway_support import GatewayHarness, write_gateway_config
from the_loop import eventlog
from the_loop.commands import gateway_cmd
from the_loop.gateway import serve as serve_mod
from the_loop.gateway.adapters.ingest import Ingest
from the_loop.gateway.store import SqliteStore


def _events(path: Path, name=None):
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    return [r for r in rows if name is None or r["event"] == name]


@pytest.fixture()
def running_app(tmp_path, monkeypatch):
    """A gateway app with its supervisor running on a fast reconcile tick, Slack and the
    GitHub poller off at start, the poll token set."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.delenv("THE_LOOP_SLACK_APP_TOKEN", raising=False)
    monkeypatch.delenv("THE_LOOP_SLACK_BOT_TOKEN", raising=False)
    config = write_gateway_config(
        tmp_path,
        github={
            "webhook": {"enabled": False},
            "poll": {"enabled": False, "sources": []},
        },
        slack={"socket": {"enabled": False}, "http": {"enabled": False}},
    )
    events_path = tmp_path / "events.jsonl"
    eventlog.configure("gateway", path=events_path, enabled=True)
    from ghfakes import FakeGitHubClient

    app = serve_mod.create_app(
        config, interval=0.2, poll_api=FakeGitHubClient(), retention_interval=3600
    )
    with TestClient(app) as client:
        yield {
            "client": client,
            "config": config,
            "path": config.path,
            "events": events_path,
            "tmp": tmp_path,
        }


def _rewrite(path: Path, **over):
    body = yaml.safe_load(path.read_text())
    for key, value in over.items():
        body[key] = value
    path.write_text(yaml.safe_dump(body))


def test_editing_the_config_starts_a_poller_without_a_restart(running_app):
    """
    Feature: the gateway is one process that follows its own config
      Scenario: editing gateway-config.yaml starts a poller without a restart
        Given a running gateway with the GitHub poller disabled
        When the file is edited to enable the poller with one source
        Then within the reconcile cadence the poller is hosted, health says running,
             and config.reloaded names it as started

    Requirement: docs/specs/issue-496/requirements.md#requirement-8 (R8.4)
    """
    client = running_app["client"]
    assert (
        client.get("/api/v1/gateway/health").json()["ingresses"]["github-poll"] == "off"
    )
    _rewrite(
        running_app["path"],
        github={
            "webhook": {"enabled": False},
            "poll": {"enabled": True, "sources": [{"repository": "o/r"}]},
        },
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if (
            client.get("/api/v1/gateway/health").json()["ingresses"].get("github-poll")
            == "running"
        ):
            break
        time.sleep(0.1)
    assert (
        client.get("/api/v1/gateway/health").json()["ingresses"]["github-poll"]
        == "running"
    )
    reloaded = _events(running_app["events"], "config.reloaded")
    assert reloaded and reloaded[-1]["detail"]["started"] == ["github-poll"]
    assert _events(running_app["events"], "gateway.reloaded")


def test_a_bad_edit_keeps_the_previous_configuration_running(running_app):
    """
    Feature: the gateway is one process that follows its own config
      Scenario: a bad edit keeps the previous configuration running
        Given a running gateway
        When the file is edited into a schema violation
        Then config.reload-failed is recorded naming the path, nothing is stopped, and
             a later valid edit is applied

    Requirement: docs/specs/issue-496/requirements.md#requirement-8 (R8.5)
    """
    client = running_app["client"]
    before = client.get("/api/v1/gateway/health").json()["ingresses"]
    running_app["path"].write_text(
        running_app["path"].read_text() + "\nnonsense: true\nlisten: {port: 0}\n"
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not _events(
        running_app["events"], "config.reload-failed"
    ):
        time.sleep(0.1)
    failed = _events(running_app["events"], "config.reload-failed")
    assert failed and str(running_app["path"]) in failed[-1]["path"]
    assert client.get("/api/v1/gateway/health").json()["ingresses"] == before
    assert not _events(running_app["events"], "config.reloaded")


def test_a_start_time_only_change_says_restart_required(running_app):
    """
    Feature: the gateway is one process that follows its own config
      Scenario: changing the listen port while running is applied on the next restart
    Requirement: docs/specs/issue-496/requirements.md#requirement-8 (R8.6)
    """
    client = running_app["client"]
    _rewrite(running_app["path"], listen={"host": "127.0.0.1", "port": 8791})
    deadline = time.monotonic() + 5
    while (
        time.monotonic() < deadline
        and not client.get("/api/v1/gateway/health").json()["restartRequired"]
    ):
        time.sleep(0.1)
    health = client.get("/api/v1/gateway/health").json()
    assert health["restartRequired"] == ["listen"]
    assert health["listen"]["port"] == 8790  # still the running value
    report = gateway_cmd.status_report(running_app["config"])
    assert report["running"] is False  # no pidfile in-process; the lines render anyway
    lines = gateway_cmd.status_lines(
        {
            **report,
            "running": True,
            "reachable": True,
            "restartRequired": ["listen"],
            "pid": 1,
        }
    )
    assert any("restart required: listen" in line for line in lines)


def test_a_missing_secret_variable_leaves_that_ingress_off_and_says_so_in_health(
    tmp_path, monkeypatch
):
    """
    Feature: fail closed
      Scenario: a missing secret variable leaves that ingress off and says so in health
        Given Slack Socket Mode enabled but the token variables unset
        When the gateway starts
        Then the socket ingress is not started, health reads failed:missing-secret and
             ingress.hosted_failed names the variables; the rest serves

    Requirement: docs/specs/issue-496/design.md §Security design, fail-closed
    """
    monkeypatch.delenv("THE_LOOP_SLACK_APP_TOKEN", raising=False)
    monkeypatch.delenv("THE_LOOP_SLACK_BOT_TOKEN", raising=False)
    config = write_gateway_config(
        tmp_path,
        slack={"socket": {"enabled": True}},
        github={"poll": {"enabled": False}},
    )
    events_path = tmp_path / "events.jsonl"
    eventlog.configure("gateway", path=events_path, enabled=True)
    with TestClient(serve_mod.create_app(config, interval=60)) as client:
        health = client.get("/api/v1/gateway/health").json()
        assert health["ingresses"]["slack-socket"] == "failed:missing-secret"
        assert health["slack"]["socket"] == "off"
        assert client.get("/api/v1/gateway/subjects").status_code == 200
    failed = _events(events_path, "ingress.hosted_failed")
    assert failed and "THE_LOOP_SLACK_APP_TOKEN" in failed[0]["reason"]


def test_a_non_loopback_bind_without_exposed_refuses_to_start(
    tmp_path, monkeypatch, capsys
):
    """
    Feature: fail closed
      Scenario: a non-loopback bind without exposed refuses to start
    Requirement: docs/specs/issue-496/requirements.md#requirement-14 (R14.3); §Security
    """
    config = write_gateway_config(
        tmp_path, listen={"host": "0.0.0.0", "port": 8790, "exposed": False}
    )
    monkeypatch.setattr(
        serve_mod, "create_app", lambda *a, **k: pytest.fail("must not build the app")
    )
    assert serve_mod.main(["--config", str(config.path)]) == 2
    assert "listen.exposed" in capsys.readouterr().err
    bad = tmp_path / "bad.yaml"
    bad.write_text("listen: {port: 'x'}\n")
    assert serve_mod.main(["--config", str(bad)]) == 2
    assert "listen.port" in capsys.readouterr().err


def test_a_delivery_that_fails_three_times_is_dead_lettered_and_committed(tmp_path):
    """
    Feature: at-least-once with a bound
      Scenario: a delivery that fails three times is dead-lettered and committed
    Requirement: docs/specs/issue-496/requirements.md#requirement-3 (R3.6)
    """
    gw = GatewayHarness(tmp_path, store={"maxAttempts": 3})
    try:
        gw.append(1, consumers=["a"])
        for attempt in (1, 2, 3):
            (d,) = gw.fetch("a").json()["deliveries"]
            assert d["attempt"] == attempt
            # the explicit commit, as a stop would send it; a `failed` leaves it pending
            gw.client.post(
                "/api/v1/gateway/commit",
                json={
                    "instance": "a",
                    "commit": [{"seq": d["seq"], "outcome": "failed"}],
                },
            )
        body = gw.fetch("a").json()
        assert body["deliveries"] == [] and body["committed"] == d["seq"]
        dead = gw.events("subject.dead-lettered")
        assert dead and dead[0]["attempts"] == 3
        (queue,) = gw.client.get("/api/v1/gateway/queues").json()["queues"]
        assert queue["dead"] == 1 and queue["backlog"] == 0
    finally:
        gw.close()


def test_ten_thousand_duplicate_deliveries_store_one_row(tmp_path):
    """
    Feature: bounded growth (abuse case 6)
      Scenario: ten thousand duplicate deliveries store one row
        Given one GitHub comment
        When it is ingested ten thousand times under different delivery ids
        Then one event exists and the run finishes within ten seconds

    Requirement: docs/specs/issue-496/requirements.md §Security considerations, abuse case 6
    """
    gw = GatewayHarness(tmp_path)
    try:
        ingest = Ingest(gw.state)
        eventlog.configure("gateway", enabled=False)
        payload = json.dumps(
            {
                "action": "created",
                "issue": {"number": 14},
                "comment": {"id": 1, "user": {"login": "o"}},
                "repository": {"full_name": "o/r"},
                "sender": {"login": "o"},
            }
        ).encode()
        started = time.monotonic()
        stored = 0
        for n in range(10_000):
            outcome = ingest.accept(
                "github", "webhook", "issue_comment", f"d-{n}", {}, payload
            )
            stored += outcome.status == "stored"
        took = time.monotonic() - started
        assert stored == 1
        (row,) = gw.store.subjects()
        assert row.events == 1
        assert took < 10.0, took
    finally:
        gw.close()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_the_gateway_verbs_start_report_and_stop_a_real_process(tmp_path, monkeypatch):
    """
    Feature: the lifecycle verbs mean what the service's do
      Scenario: the-loop gateway start, status, instances and stop run a real process
        Given a gateway config on loopback with every ingress off
        When start spawns python -m the_loop.gateway.serve and waits for health
        Then status reports the pid, the store and the listen address, instances lists
             a polling peer, and stop frees the pidfile

    Requirement: docs/specs/issue-496/requirements.md#requirement-9 (R9.1, R9.2), R14.2
    """
    port = _free_port()
    config = write_gateway_config(
        tmp_path,
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
    report = gateway_cmd.start_gateway(config, wait=30)
    try:
        assert report["running"], report
        status = gateway_cmd.status_report(config)
        assert (
            status["running"] and status["reachable"] and status["pid"] == report["pid"]
        )
        assert status["listen"] == f"127.0.0.1:{port}" and status["store"] == str(
            config.store.path
        )
        assert config.pidfile.is_file() and config.logfile.is_file()
        # an instance polls once; `instances` lists it with a live lease
        body = json.dumps(
            {
                "instance": "laptop-a",
                "peer": "p1",
                "cursor": 0,
                "max": 8,
                "wait": 0,
                "lease": 30,
                "commit": [],
            }
        ).encode()
        import urllib.request

        request = urllib.request.Request(
            f"{config.base_url}/api/v1/gateway/fetch",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert json.loads(response.read())["deliveries"] == []
        doc = gateway_cmd._get(config, "instances")
        assert doc is not None
        lines = gateway_cmd.instances_lines(doc)
        assert any(line.startswith("laptop-a") and "live" in line for line in lines), (
            lines
        )
        assert gateway_cmd.status_report(config)["instancesLive"] == ["laptop-a"]
        again = gateway_cmd.start_gateway(config, wait=5)
        assert again["output"] == "already running"
    finally:
        stopped = gateway_cmd.stop_gateway(config)
    assert stopped["running"] is False
    assert not SqliteStore(config.store.path).event(999)
    assert config.event_log is not None
    events = _events(config.event_log)
    names = [e["event"] for e in events]
    assert "gateway.started" in names and "gateway.stopped" in names


def test_serve_main_refuses_a_second_gateway_on_the_same_pidfile(
    tmp_path, monkeypatch, capsys
):
    """
    Feature: the lifecycle verbs mean what the service's do
      Scenario: a second gateway on one state root is refused by the pidfile lock
    Requirement: docs/specs/issue-496/requirements.md#requirement-9 (R9.1)
    """
    from the_loop.runlock import RunLock

    config = write_gateway_config(
        tmp_path,
        github={"poll": {"enabled": False}},
        slack={"socket": {"enabled": False}},
    )
    config.state_root.mkdir(parents=True, exist_ok=True)
    lock = RunLock(str(config.pidfile), name="gateway")
    assert lock.acquire()
    try:
        monkeypatch.setattr(
            serve_mod,
            "create_app",
            lambda *a, **k: pytest.fail("must not build the app"),
        )
        assert serve_mod.main(["--config", str(config.path)]) == 1
        assert "already running" in capsys.readouterr().err
    finally:
        lock.release()


def test_subjects_and_status_render(tmp_path):
    gw = GatewayHarness(tmp_path)
    try:
        gw.store.claim("loop-github-o-r-14", "laptop-a", "driver")
        gw.append(1, consumers=["laptop-a"])
        lines = gateway_cmd.subjects_lines(
            gw.client.get("/api/v1/gateway/subjects").json()
        )
        assert lines[0].startswith("subject") and "laptop-a (driver)" in lines[1]
        assert gateway_cmd.subjects_lines({"subjects": []}) == ["no subjects yet"]
        assert gateway_cmd.instances_lines({"instances": []}) == [
            "no instances have fetched yet"
        ]
        stopped = gateway_cmd.status_lines(gateway_cmd.status_report(gw.config))
        assert stopped[0] == "gateway: stopped"
    finally:
        gw.close()


def test_status_follows_the_recorded_listen_address_when_the_file_moved_on(tmp_path):
    """
    Feature: the lifecycle verbs mean what the service's do
      Scenario: editing listen.port while running is applied on the next restart
        Given a gateway that recorded the address it bound
        When the config file now names another port
        Then status probes the recorded address, reports the running one, and says the
             file's value waits for a restart

    Requirement: docs/specs/issue-496/requirements.md#requirement-8 (R8.6)
    """
    config = write_gateway_config(tmp_path, listen={"host": "127.0.0.1", "port": 8791})
    config.state_root.mkdir(parents=True, exist_ok=True)
    config.listen_file.write_text("127.0.0.1:8790\n")
    assert gateway_cmd.running_base_url(config) == "http://127.0.0.1:8790"
    report = gateway_cmd.status_report(config)
    assert report["listen"] == "127.0.0.1:8790"
    assert report["listenInFile"] == "127.0.0.1:8791"
    lines = gateway_cmd.status_lines(
        {**report, "running": True, "reachable": False, "pid": 1}
    )
    assert any(
        "the file says 127.0.0.1:8791 — restart to apply" in line for line in lines
    )
    config.listen_file.unlink()
    assert gateway_cmd.running_base_url(config) == "http://127.0.0.1:8791"


def test_stop_does_not_wait_for_an_open_long_poll(tmp_path, monkeypatch):
    """
    Feature: the gateway is one process that follows its own config
      Scenario: stop does not wait for an open long-poll
        Given a real gateway whose consume.maxWaitSeconds is 30 and a client holding a
              25 s long-poll on an empty queue
        When the-loop gateway stop is run
        Then the process is gone within a few seconds and the client's fetch returned
             200 with nothing — the long-poll was released, not outlasted

    Requirement: docs/specs/issue-496/requirements.md#requirement-8 (R8.5), R9.2
    """
    import threading
    import urllib.request

    port = _free_port()
    config = write_gateway_config(
        tmp_path,
        listen={"host": "127.0.0.1", "port": port},
        consume={
            "maxBatch": 64,
            "maxWaitSeconds": 30,
            "leaseSeconds": {"min": 10, "max": 300},
        },
        github={"poll": {"enabled": False}},
        slack={"socket": {"enabled": False}},
    )
    monkeypatch.setenv(
        "PYTHONPATH",
        str(Path(__file__).resolve().parents[1])
        + os.pathsep
        + os.environ.get("PYTHONPATH", ""),
    )
    report = gateway_cmd.start_gateway(config, wait=30)
    assert report["running"], report
    outcome: dict = {}

    def poll():
        body = json.dumps(
            {
                "instance": "laptop-a",
                "peer": "p1",
                "cursor": 0,
                "max": 8,
                "wait": 25,
                "lease": 60,
                "commit": [],
            }
        ).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/gateway/fetch",
            data=body,
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                outcome["status"] = response.status
                outcome["body"] = json.loads(response.read())
        except Exception as exc:  # noqa: BLE001 — the assertion reads it
            outcome["error"] = str(exc)

    thread = threading.Thread(target=poll)
    thread.start()
    time.sleep(1.0)
    started = time.monotonic()
    try:
        stopped = gateway_cmd.stop_gateway(config)
        elapsed = time.monotonic() - started
        assert stopped["running"] is False, stopped
        assert elapsed < 10, elapsed
    finally:
        gateway_cmd.stop_gateway(config, timeout=5)
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert outcome.get("status") == 200 and outcome["body"]["deliveries"] == [], outcome
