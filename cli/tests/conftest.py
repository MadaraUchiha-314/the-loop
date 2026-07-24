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


class _NoopAnnouncer:
    """Stand-in for SessionAnnouncer that never shells out."""

    def __init__(self, *args, **kwargs):
        pass

    def announce(self, session, respawned=False):
        return False


@pytest.fixture(autouse=True)
def _hermetic_reactor(monkeypatch):
    """Dispatchers built without injected gh-writers must not shell out to gh.

    ``routing.reactions`` (issue-84) and ``routing.announce`` (issue-86) both
    default to enabled, so a bare ``RoutingConfig()`` would give every
    dispatcher test a real ``GitHubReactor``/``SessionAnnouncer`` — and CI
    runners ship a real ``gh``. Stub the classes the dispatcher instantiates;
    the reaction/announcement tests inject their own.
    """
    monkeypatch.setattr(dispatcher_mod, "GitHubReactor", _NoopReactor)
    monkeypatch.setattr(dispatcher_mod, "SessionAnnouncer", _NoopAnnouncer)


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
