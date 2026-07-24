"""Shared fixtures for the CLI test suite."""

import pytest

from the_loop import eventlog
from the_loop.webhook import dispatcher as dispatcher_mod


class _NoopReactor:
    """Stand-in for GitHubReactor that never shells out."""

    def __init__(self, *args, **kwargs):
        pass

    def react(self, routed, state):
        return False


@pytest.fixture(autouse=True)
def _hermetic_reactor(monkeypatch):
    """Dispatchers built without an injected reactor must not shell out to gh.

    ``routing.reactions`` defaults to enabled (issue-84, owner decision), so a
    bare ``RoutingConfig()`` would give every dispatcher test a real
    ``GitHubReactor`` — and CI runners ship a real ``gh``. Stub the class the
    dispatcher instantiates; reaction tests inject their own reactor/runner.
    """
    monkeypatch.setattr(dispatcher_mod, "GitHubReactor", _NoopReactor)


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
