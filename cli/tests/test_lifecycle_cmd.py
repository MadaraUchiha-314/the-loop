"""``the-loop start|stop|status|restart`` command wiring (issue-228, T2)."""

import json

from the_loop.cli import build_parser, main
from the_loop.commands import lifecycle_cmd
from the_loop.core import lifecycle


def _report(ok=True, outcome="started"):
    return {
        "services": [
            {"service": "service", "enabled": True, "outcome": outcome, "detail": "d"},
            {
                "service": "gh-webhook",
                "enabled": False,
                "outcome": "disabled",
                "detail": "",
            },
            {
                "service": "poller",
                "enabled": False,
                "outcome": "disabled",
                "detail": "",
            },
        ],
        "ok": ok,
    }


def _quiet_eventlog(monkeypatch):
    monkeypatch.setattr(lifecycle_cmd.eventlog, "configure_from_file", lambda s: None)
    monkeypatch.setattr(lifecycle_cmd.eventlog, "emit", lambda *a, **k: None)


def test_the_lifecycle_commands_are_registered():
    """
    Feature: one lifecycle vocabulary
    Scenario: the CLI's command surface after issue-228
        Given the parser
        Then start, stop, status and restart exist and poll does not
    Requirement: R1, R2.1, R3, R4
    """
    parser = build_parser()
    text = parser.format_help()
    for name in ("start", "stop", "status", "restart"):
        assert f"{name}" in text
    try:
        parser.parse_args(["poll", "start"])
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover
        raise AssertionError("`poll` must be rejected as an unknown command")


def test_start_renders_the_report_and_exit_code(tmp_path, monkeypatch, capsys):
    """
    Feature: `the-loop start`
    Scenario: every enabled service comes up
        Given start_all reports started/disabled rows and ok
        When `the-loop start` runs
        Then one line per service is printed and the exit code is 0 (1 when not ok)
    Requirement: R1.2, R1.4, R1.5
    """
    monkeypatch.chdir(tmp_path)
    _quiet_eventlog(monkeypatch)
    monkeypatch.setattr(lifecycle, "start_all", lambda config: _report(ok=True))
    assert main(["start"]) == 0
    out = capsys.readouterr().out
    assert "service" in out and "disabled" in out and "started" in out

    monkeypatch.setattr(
        lifecycle, "start_all", lambda config: _report(ok=False, outcome="failed")
    )
    assert main(["start"]) == 1


def test_start_refuses_a_broken_config(tmp_path, monkeypatch, capsys):
    """
    Feature: `the-loop start`
    Scenario: the CLI config exists but cannot be parsed
        Given a half-saved cli-config.yaml
        When `the-loop start` runs
        Then it refuses (exit 2) rather than composing services against
             defaults the operator did not write
    Requirement: design.md §Error handling
    """
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".the-loop"
    config_dir.mkdir()
    (config_dir / "cli-config.yaml").write_text("routing: [broken\n")
    monkeypatch.setattr(
        lifecycle,
        "start_all",
        lambda config: (_ for _ in ()).throw(AssertionError("must not start")),
    )
    assert main(["start"]) == 2
    assert "cannot load the CLI config" in capsys.readouterr().err


def test_stop_renders_and_exits_by_ok(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _quiet_eventlog(monkeypatch)
    monkeypatch.setattr(
        lifecycle,
        "stop_all",
        lambda config: {
            "services": [
                {
                    "service": "poller",
                    "enabled": False,
                    "outcome": "not-running",
                    "detail": "",
                }
            ],
            "ok": True,
        },
    )
    assert main(["stop"]) == 0


def test_status_json_is_the_report(tmp_path, monkeypatch, capsys):
    """
    Feature: `the-loop status`
    Scenario: --format json
        Given a status report
        When `the-loop status --format json` runs
        Then stdout is that JSON document and the exit code follows ok (R3.3/R3.4)
    Requirement: R3.3, R3.4
    """
    monkeypatch.chdir(tmp_path)
    report = {
        "services": [
            {
                "service": "service",
                "enabled": True,
                "running": False,
                "pid": 0,
                "url": "http://127.0.0.1:4114",
                "healthy": False,
                "mcp": {"enabled": True, "path": "/mcp"},
            }
        ],
        "ok": False,
    }
    monkeypatch.setattr(lifecycle, "status_all", lambda config: report)
    assert main(["status", "--format", "json"]) == 1
    assert json.loads(capsys.readouterr().out) == report


def test_restart_is_stop_then_start(tmp_path, monkeypatch):
    """
    Feature: `the-loop restart`
    Scenario: plain restart
        Given stop_all and start_all both succeed
        When `the-loop restart` runs
        Then stop is composed before start and the exit code is 0 (R4.1)
    Requirement: R4.1
    """
    monkeypatch.chdir(tmp_path)
    _quiet_eventlog(monkeypatch)
    order = []
    monkeypatch.setattr(
        lifecycle,
        "stop_all",
        lambda config: order.append("stop") or {"services": [], "ok": True},
    )
    monkeypatch.setattr(
        lifecycle,
        "start_all",
        lambda config: order.append("start") or {"services": [], "ok": True},
    )
    assert main(["restart"]) == 0
    assert order == ["stop", "start"]


def test_a_failed_upgrade_never_leaves_the_system_down(tmp_path, monkeypatch):
    """
    Feature: `the-loop restart --with-upgrade`
    Scenario: the upgrade step fails
        Given the installer plan raises
        When `the-loop restart --with-upgrade` runs
        Then the start half still runs (on the current version) and the exit
             code is non-zero (R4.3)
    Requirement: R4.2, R4.3
    """
    monkeypatch.chdir(tmp_path)
    _quiet_eventlog(monkeypatch)
    order = []
    monkeypatch.setattr(
        lifecycle,
        "stop_all",
        lambda config: order.append("stop") or {"services": [], "ok": True},
    )
    monkeypatch.setattr(
        lifecycle,
        "start_all",
        lambda config: order.append("start") or {"services": [], "ok": True},
    )
    monkeypatch.setattr(
        lifecycle_cmd.RestartCommand,
        "_upgrade",
        staticmethod(lambda: order.append("upgrade") or False),
    )
    assert main(["restart", "--with-upgrade"]) == 1
    assert order == ["stop", "upgrade", "start"]
