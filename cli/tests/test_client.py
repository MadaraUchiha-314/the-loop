"""The CLI client's fail-closed behaviour (issue-161, T8, R2.3)."""

import pytest

from the_loop import client


def _unreachable_config(tmp_path, auto_start: bool):
    return {
        "state": {"root": str(tmp_path / ".the-loop")},
        # A port nothing listens on; autoStart per scenario.
        "service": {"port": 1, "autoStart": auto_start},
    }


def test_unreachable_with_autostart_off_fails_closed(tmp_path):
    """
    Feature: service-only execution
      Scenario: no service and auto-start disabled
        Given service.autoStart is false and nothing listens
        When the client ensures a service
        Then it raises pointing at `the-loop service start`, and never falls
             back to in-process execution

    Requirement: docs/specs/issue-161/requirements.md R2.3
    """
    with pytest.raises(client.ServiceUnavailable) as excinfo:
        client.ensure_service(_unreachable_config(tmp_path, auto_start=False))
    message = str(excinfo.value)
    assert "the-loop start" in message
    # No extras any more (owner decision, PR #162): an unreachable service is a
    # lifecycle problem, so the message must not send anyone to `pip install`.
    assert "pip install" not in message


def test_autostart_attempts_a_spawn_then_still_fails_closed(tmp_path, monkeypatch):
    """With autoStart on, the client spawns a service; if it never becomes
    healthy it still raises rather than degrading to local execution."""
    spawned = []
    monkeypatch.setattr(client, "_spawn_service", lambda: spawned.append(True))
    monkeypatch.setattr(client, "_AUTOSTART_TIMEOUT", 0.3)
    with pytest.raises(client.ServiceUnavailable):
        client.ensure_service(_unreachable_config(tmp_path, auto_start=True))
    assert spawned == [True]


def test_api_error_carries_status_and_detail():
    error = client.ApiError(404, "no record for work item x")
    assert error.status == 404
    assert "no record" in str(error)


def test_the_auto_started_service_carries_the_config_this_process_resolved(
    tmp_path, monkeypatch
):
    """A service auto-started by an unrelated command reads the operator's config.

    `the_loop.api.serve` has no `--config`; without the variable it re-resolves from its
    inherited working directory, which is how one configuration ended up with two state
    roots and a `status` that read the wrong heartbeat (issue-339, R1.5).
    """
    from the_loop import cli_config
    from the_loop import client as client_mod

    captured = {}

    class FakePopen:
        def __init__(self, argv, **kwargs):
            captured["argv"] = argv
            captured["env"] = kwargs.get("env")

    selected = tmp_path / "chosen" / ".the-loop" / "cli-config.yaml"
    selected.parent.mkdir(parents=True)
    selected.write_text("version: '0.7.0'\n")
    monkeypatch.setattr(client_mod.subprocess, "Popen", FakePopen)
    cli_config.set_override(selected)
    try:
        client_mod._spawn_service()
    finally:
        cli_config.set_override(None)

    assert captured["argv"][-2:] == ["-m", "the_loop.api.serve"]
    assert captured["env"][cli_config.CLI_CONFIG_ENV] == str(selected)
