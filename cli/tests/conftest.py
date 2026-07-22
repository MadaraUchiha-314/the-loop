"""Shared fixtures for the CLI test suite."""

import pytest

from the_loop import eventlog


@pytest.fixture(autouse=True)
def _hermetic_eventlog(monkeypatch):
    """Keep the process-wide event log out of the real working tree.

    CLI entry points call ``eventlog.configure_from_file`` which resolves a
    cwd-relative default path — under test that would append a real
    ``.the-loop/logs/events.jsonl`` into the repo. Stub it to a disabled log;
    tests that assert on the log configure their own tmp path explicitly.
    """
    eventlog.reset()
    monkeypatch.setattr(
        eventlog,
        "configure_from_file",
        lambda source: eventlog.configure(source, enabled=False),
    )
    yield
    eventlog.reset()
