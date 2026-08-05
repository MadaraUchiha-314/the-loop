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
        Then it raises naming `the-loop service start` and the [service] extra,
             and never falls back to in-process execution

    Requirement: docs/specs/issue-161/requirements.md R2.3
    """
    with pytest.raises(client.ServiceUnavailable) as excinfo:
        client.ensure_service(_unreachable_config(tmp_path, auto_start=False))
    message = str(excinfo.value)
    assert "the-loop service start" in message
    assert "the-loopy-one[service]" in message


def test_unreachable_with_autostart_but_no_extra_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "_service_extra_available", lambda: False)
    spawned = []
    monkeypatch.setattr(client, "_spawn_service", lambda: spawned.append(True))
    with pytest.raises(client.ServiceUnavailable):
        client.ensure_service(_unreachable_config(tmp_path, auto_start=True))
    assert spawned == []


def test_api_error_carries_status_and_detail():
    error = client.ApiError(404, "no record for work item x")
    assert error.status == 404
    assert "no record" in str(error)
