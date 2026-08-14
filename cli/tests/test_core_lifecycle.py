"""Unit tests for the whole-system lifecycle facade (issue-228, T1)."""

from types import SimpleNamespace

from the_loop.core import lifecycle


def _config(tmp_path, **blocks):
    return {"state": {"root": str(tmp_path / ".the-loop")}, **blocks}


# -- which services the config enables (D1) --------------------------------------


def test_defaults_enable_the_service_and_nothing_else(tmp_path):
    """
    Feature: `the-loop start` composes what the config enables
    Scenario: a config with no `enabled` keys anywhere
        Given a CLI config that predates issue-228
        When the enabled set is resolved
        Then the service is on and both ingresses are off (R5.3)
    Requirement: docs/specs/issue-228/requirements.md R5.3
    """
    assert lifecycle.enabled_services({}) == {
        "service": True,
        "gh-webhook": False,
        "poller": False,
    }


def test_explicit_flags_win(tmp_path):
    config = {
        "service": {"enabled": False},
        "webhooks": {"ghWebhook": {"enabled": True}},
        "polling": {"enabled": True},
    }
    assert lifecycle.enabled_services(config) == {
        "service": False,
        "gh-webhook": True,
        "poller": True,
    }


# -- start_all (R1) ---------------------------------------------------------------


def test_start_skips_disabled_services_naming_the_key(tmp_path, monkeypatch):
    """
    Feature: `the-loop start` composes what the config enables
    Scenario: everything disabled
        Given service.enabled false and both ingresses left at their defaults
        When start_all runs
        Then every row is `disabled` naming its config key, nothing spawns, ok
    Requirement: R1.2, R1.5
    """
    monkeypatch.setattr(
        lifecycle,
        "start_service",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not start")),
    )
    monkeypatch.setattr(
        lifecycle,
        "_start_daemon",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not start")),
    )
    report = lifecycle.start_all(_config(tmp_path, service={"enabled": False}))
    assert report["ok"] is True
    outcomes = {row["service"]: row for row in report["services"]}
    assert outcomes["service"]["outcome"] == "disabled"
    assert "service.enabled" in outcomes["service"]["detail"]
    assert "webhooks.ghWebhook.enabled" in outcomes["gh-webhook"]["detail"]
    assert "polling.enabled" in outcomes["poller"]["detail"]


def test_start_starts_every_enabled_service(tmp_path, monkeypatch):
    monkeypatch.setattr(
        lifecycle,
        "start_service",
        lambda config: {
            "running": True,
            "pid": 41,
            "detail": "started",
            "started": True,
        },
    )
    started = []
    monkeypatch.setattr(
        lifecycle,
        "_start_daemon",
        lambda daemon, config: (
            started.append(daemon)
            or {"service": daemon, "enabled": True, "outcome": "started", "detail": ""}
        ),
    )
    config = _config(
        tmp_path,
        webhooks={"ghWebhook": {"enabled": True}},
        polling={"enabled": True, "sources": [{"provider": "github"}]},
    )
    report = lifecycle.start_all(config)
    assert report["ok"] is True
    assert started == ["gh-webhook", "poller"]
    assert [row["outcome"] for row in report["services"]] == [
        "started",
        "started",
        "started",
    ]


def test_an_enabled_poller_with_no_sources_is_misconfigured(tmp_path, monkeypatch):
    """
    Feature: `the-loop start` composes what the config enables
    Scenario: polling.enabled true, polling.sources empty
        Given a config contradiction
        When start_all runs
        Then the poller row is `misconfigured` at plan time (no spawn whose
             failure lands only in a logfile), and ok is false
    Requirement: design.md D3
    """
    monkeypatch.setattr(
        lifecycle,
        "_start_daemon",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not spawn")),
    )
    report = lifecycle.start_all(
        _config(tmp_path, service={"enabled": False}, polling={"enabled": True})
    )
    row = next(r for r in report["services"] if r["service"] == "poller")
    assert row["outcome"] == "misconfigured"
    assert "polling.sources" in row["detail"]
    assert report["ok"] is False


def test_one_failed_service_never_hides_the_others(tmp_path, monkeypatch):
    """
    Feature: per-service failure isolation
    Scenario: the service raises while the webhook starts fine
        Given start_service raises
        When start_all runs
        Then the service row is `failed` with the reason, the webhook row is
             `started`, and ok is false (R1.4)
    Requirement: R1.4
    """
    monkeypatch.setattr(
        lifecycle,
        "start_service",
        lambda config: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        lifecycle,
        "_start_daemon",
        lambda daemon, config: {
            "service": daemon,
            "enabled": True,
            "outcome": "started",
            "detail": "",
        },
    )
    report = lifecycle.start_all(
        _config(tmp_path, webhooks={"ghWebhook": {"enabled": True}})
    )
    outcomes = {row["service"]: row["outcome"] for row in report["services"]}
    assert outcomes == {
        "service": "failed",
        "gh-webhook": "started",
        "poller": "disabled",
    }
    assert report["ok"] is False


# -- stop_all (R3.1) --------------------------------------------------------------


def test_stop_ignores_the_enabled_flags(tmp_path, monkeypatch):
    """
    Feature: `the-loop stop` stops what is running
    Scenario: a service disabled after it was started
        Given every enabled flag is false
        When stop_all runs
        Then both daemons and the service are still asked to stop (R3.1)
    Requirement: R3.1
    """
    asked = []
    monkeypatch.setattr(
        lifecycle.core_daemons,
        "control_daemon",
        lambda daemon, verb, config: (
            asked.append((daemon, verb))
            or {"exitCode": 0, "pid": 7, "output": "stopped"}
        ),
    )
    monkeypatch.setattr(
        lifecycle,
        "stop_service",
        lambda config: (
            asked.append(("service", "stop"))
            or {"running": False, "pid": 7, "detail": "stopped", "stopped": True}
        ),
    )
    report = lifecycle.stop_all(_config(tmp_path, service={"enabled": False}))
    assert asked == [("poller", "stop"), ("gh-webhook", "stop"), ("service", "stop")]
    assert report["ok"] is True


def test_stop_reports_not_running_idempotently(tmp_path, monkeypatch):
    monkeypatch.setattr(
        lifecycle.core_daemons,
        "control_daemon",
        lambda daemon, verb, config: {"exitCode": 0, "pid": 0, "output": "not running"},
    )
    monkeypatch.setattr(
        lifecycle,
        "stop_service",
        lambda config: {
            "running": False,
            "pid": 0,
            "detail": "not running",
            "stopped": False,
        },
    )
    report = lifecycle.stop_all(_config(tmp_path))
    assert report["ok"] is True
    assert all(row["outcome"] == "not-running" for row in report["services"])


# -- status_all (R3.2/R3.3) -------------------------------------------------------


def test_status_ok_means_every_enabled_service_is_running(tmp_path, monkeypatch):
    """
    Feature: `the-loop status` is a health check
    Scenario: nothing runs, only the service is enabled
        Given the default enabled set and no live process
        When status_all runs
        Then ok is false; with service.enabled false it becomes vacuously true
    Requirement: R3.3
    """
    down = lifecycle.status_all(_config(tmp_path))
    assert down["ok"] is False
    vacuous = lifecycle.status_all(_config(tmp_path, service={"enabled": False}))
    assert vacuous["ok"] is True
    rows = {row["service"]: row for row in vacuous["services"]}
    assert rows["service"]["mcp"] == {"enabled": True, "path": "/mcp"}
    assert rows["poller"]["running"] is False
    assert rows["gh-webhook"]["running"] is False


# -- schedule_restart (R4.4/R4.5) -------------------------------------------------


def test_schedule_restart_spawns_a_fixed_detached_argv(tmp_path, monkeypatch):
    """
    Feature: POST /api/v1/restart schedules, never blocks
    Scenario: the service asks for its own restart
        Given a config path the service already reads
        When schedule_restart runs (with and without the upgrade)
        Then the spawned argv is fixed — interpreter, module, the config path
             it already reads, the verb, at most the one flag — detached, with
             output at logs/restart.out under the state root
    Requirement: R4.4, R4.5, requirements.md §Security
    """
    spawned = {}

    def fake_popen(argv, **kwargs):
        spawned["argv"] = argv
        spawned["kwargs"] = kwargs
        return SimpleNamespace(pid=4242)

    monkeypatch.setattr(lifecycle.subprocess, "Popen", fake_popen)
    config = _config(tmp_path)

    plain = lifecycle.schedule_restart(config, config_path=tmp_path / "cli-config.yaml")
    assert plain == {
        "scheduled": True,
        "pid": 4242,
        "withUpgrade": False,
        "logfile": str(tmp_path / ".the-loop" / "logs" / "restart.out"),
    }
    assert spawned["argv"][1:3] == ["-m", "the_loop"]
    assert spawned["argv"][-1] == "restart"
    assert "--config" in spawned["argv"]
    assert spawned["kwargs"]["start_new_session"] is True

    upgraded = lifecycle.schedule_restart(config, with_upgrade=True)
    assert upgraded["withUpgrade"] is True
    assert spawned["argv"][-1] == "--with-upgrade"
    assert spawned["argv"][-2] == "restart"
