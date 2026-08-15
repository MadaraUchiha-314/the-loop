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
