"""Health reports on what the service is hosting, not a constant (issue-339).

`GET /api/v1/health` answered `{"status":"ok","version":…}` whatever was running. On the
reporter's box it said `ok` for 17 hours while the poller it was supposed to be hosting
was absent and no GitHub comment was read. These scenarios pin the corrected report — and
the one thing about it that must NOT change: a degraded service still answers 200, so the
CLI's auto-start loop still terminates.

Spec: docs/specs/issue-339/design.md §D3, §D4 · Testing plan rows T2, T8.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from the_loop import client as client_mod
from the_loop import eventlog
from the_loop.api import ingress as ingress_mod
from the_loop.api.app import create_app
from the_loop.runlock import RunLock
from the_loop.state import layout_from_config

POLLING = {"enabled": True, "sources": [{"provider": "github", "repos": ["octo/repo"]}]}


def _config(tmp_path, **extra):
    config = {"state": {"root": str(tmp_path / ".the-loop")}}
    config.update(extra)
    return config


def _hold(config, daemon="poller"):
    """Hold the ingress's pidfile lock, as a hosted or standalone ingress does."""
    layout = layout_from_config(config)
    Path(layout.root).mkdir(parents=True, exist_ok=True)
    lock = RunLock(
        layout.poll_pidfile if daemon == "poller" else layout.pidfile, name=daemon
    )
    assert lock.acquire()
    return lock


def test_health_is_degraded_and_names_its_files_when_an_enabled_poller_is_absent(
    tmp_path,
):
    """
    Feature: a health surface that reports on what it hosts
      Scenario: health reports degraded, and names the files it is using, when an
                enabled poller is absent
        Given polling.enabled is true and nothing holds the poller's lock
        When a client GETs /api/v1/health
        Then the status is degraded, the poller row says why, and the response names
             the config path and the state root this process resolved

    Requirement: docs/specs/issue-339/bugfix.md R2.1, R2.3
    """
    config = _config(tmp_path, polling=POLLING)
    path = tmp_path / ".the-loop" / "cli-config.yaml"
    response = TestClient(create_app(config, config_path=path)).get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["configPath"] == str(path)
    assert body["stateRoot"] == str(tmp_path / ".the-loop")
    poller = next(row for row in body["ingresses"] if row["name"] == "poller")
    assert poller["enabled"] is True and poller["running"] is False
    assert "polling.enabled is true" in poller["detail"]
    assert "poll.pid" in poller["detail"]


def test_health_is_ok_when_every_enabled_ingress_holds_its_lock(tmp_path):
    """
    Feature: a health surface that reports on what it hosts
      Scenario: health reports ok when every enabled ingress holds its lock
        Given polling.enabled is true and a poller holds the lock
        When a client GETs /api/v1/health
        Then the status is ok and the poller row carries no complaint

    Requirement: docs/specs/issue-339/bugfix.md R2.2
    """
    config = _config(tmp_path, polling=POLLING)
    lock = _hold(config)
    try:
        body = TestClient(create_app(config)).get("/api/v1/health").json()
    finally:
        lock.release()

    assert body["status"] == "ok"
    poller = next(row for row in body["ingresses"] if row["name"] == "poller")
    assert poller["running"] is True and poller["detail"] == ""


def test_health_is_ok_when_nothing_is_enabled(tmp_path):
    """
    Feature: a health surface that reports on what it hosts
      Scenario: an ingress nobody enabled is not an outage
        Given no ingress is enabled
        When a client GETs /api/v1/health
        Then the status is ok and every row is reported as disabled and not running

    Requirement: docs/specs/issue-339/bugfix.md R2.2
    """
    body = TestClient(create_app(_config(tmp_path))).get("/api/v1/health").json()

    assert body["status"] == "ok"
    assert [row["enabled"] for row in body["ingresses"]] == [False, False, False]
    assert all(row["detail"] == "" for row in body["ingresses"])


def test_security_a_degraded_health_is_still_reachable_and_carries_no_secret(
    tmp_path, monkeypatch
):
    """
    Feature: a health surface that reports on what it hosts
      Scenario: degraded is a body, not a status code (abuse cases AC3, AC4)
        Given an enabled poller that is not running
        When the CLI's liveness probe reads /api/v1/health
        Then it still reports the service as reachable, so ensure_service does not
             spawn a second one
        And the body carries exactly the declared fields — no pid, no environment value

    Requirement: docs/specs/issue-339/bugfix.md R2.4, AC3, AC4
    """
    monkeypatch.setenv("A_SECRET_THE_SERVICE_CAN_READ", "s3cret-value")
    config = _config(tmp_path, polling=POLLING)
    client = TestClient(create_app(config))
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    spawned = []
    monkeypatch.setattr(client_mod, "_spawn_service", lambda: spawned.append(1))
    monkeypatch.setattr(client_mod, "healthy", lambda cfg=None, timeout=2.0: True)
    client_mod.ensure_service(config)
    assert spawned == []

    body = response.json()
    # The whole surface, declared: a path an operator already had to know to reach this
    # loopback service is not an escalation, a process id or a secret would be.
    assert set(body) == {"status", "version", "configPath", "stateRoot", "ingresses"}
    assert all(
        set(row) == {"name", "enabled", "running", "detail"}
        for row in body["ingresses"]
    )
    assert "s3cret-value" not in response.text


def test_an_enabled_ingress_that_cannot_start_writes_an_error_event(
    tmp_path, monkeypatch
):
    """
    Feature: a component that fails to come up says so where the trail is read
      Scenario: an enabled ingress that cannot start writes an error event, a disabled
                one writes none
        Given polling is enabled with no sources, and the webhook receiver is disabled
        When the service starts its hosted ingresses
        Then an ingress.hosted_failed event names the poller and the reason
        And nothing is recorded for the ingress nobody enabled

    Requirement: docs/specs/issue-339/bugfix.md R3.1, R3.3, AC5
    """
    log = tmp_path / "events.jsonl"
    monkeypatch.setattr(eventlog, "configure_from_file", lambda source: None)
    eventlog.configure("service", path=str(log), enabled=True)
    try:
        hosted = ingress_mod.start_hosted_ingresses(
            _config(tmp_path, polling={"enabled": True, "sources": []})
        )
    finally:
        eventlog.reset()

    assert hosted == []
    records = [__import__("json").loads(line) for line in log.read_text().splitlines()]
    failures = [r for r in records if r["event"] == "ingress.hosted_failed"]
    assert len(failures) == 1
    assert failures[0]["ingress"] == "poller"
    assert failures[0]["level"] == "error"
    assert "polling.sources is empty" in failures[0]["reason"]
    assert not [r for r in records if r["event"] == "ingress.hosted"]


def test_a_slack_channel_that_wants_no_hosted_listener_is_not_a_failure(
    tmp_path, monkeypatch
):
    """
    Feature: a component that fails to come up says so where the trail is read
      Scenario: read.mode poll is a configuration, not a failure
        Given channels.slack is enabled with read.mode poll, which hosts no listener
        When the service starts its hosted ingresses
        Then nothing is hosted and no ingress.hosted_failed is recorded

    Requirement: docs/specs/issue-339/bugfix.md R3.3
    """
    log = tmp_path / "events.jsonl"
    monkeypatch.setattr(eventlog, "configure_from_file", lambda source: None)
    eventlog.configure("service", path=str(log), enabled=True)
    try:
        hosted = ingress_mod.start_hosted_ingresses(
            _config(
                tmp_path,
                channels={"slack": {"enabled": True, "read": {"mode": "poll"}}},
            )
        )
    finally:
        eventlog.reset()

    assert hosted == []
    assert not log.exists() or "hosted_failed" not in log.read_text()


def test_a_hosted_loop_that_ends_on_its_own_drops_its_lock_and_says_so(
    tmp_path, monkeypatch
):
    """
    Feature: a health surface that reports on what it hosts
      Scenario: the poller thread dies during startup
        Given a hosted poller whose run loop returns at once (a missing dependency)
        When the service has finished starting its ingresses
        Then the poller's lock is released, so status and health both report it down
        And an ingress.hosted_failed event says the loop ended without a shutdown

    Requirement: docs/specs/issue-339/bugfix.md R2.1, R3.1

    The lock IS liveness (issue-159), and a hosted ingress holds it under the
    *service's* pid — so a thread that exited while the service kept running was
    reported as a healthy poller. That is the outage's exact shape.
    """
    import time

    from the_loop.poller import daemon as poller_daemon

    log = tmp_path / "events.jsonl"
    config = _config(tmp_path, polling=POLLING)
    monkeypatch.setattr(eventlog, "configure_from_file", lambda source: None)
    monkeypatch.setattr(
        poller_daemon, "_run_locked", lambda *a, **k: 1
    )  # a dependency check that fails
    eventlog.configure("service", path=str(log), enabled=True)
    try:
        hosted = ingress_mod.start_hosted_ingresses(config)
        layout = layout_from_config(config)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not RunLock(layout.poll_pidfile, name="poller").is_held():
                break
            time.sleep(0.02)
        ingress_mod.stop_hosted_ingresses(hosted)
        records = [
            __import__("json").loads(line) for line in log.read_text().splitlines()
        ]
    finally:
        eventlog.reset()

    assert not RunLock(layout.poll_pidfile, name="poller").is_held()
    poller = next(
        row
        for row in TestClient(create_app(config))
        .get("/api/v1/health")
        .json()["ingresses"]
        if row["name"] == "poller"
    )
    assert poller["running"] is False
    failures = [r for r in records if r["event"] == "ingress.hosted_failed"]
    assert [r["ingress"] for r in failures] == ["poller"]
    assert "ended on its own" in failures[0]["reason"]
