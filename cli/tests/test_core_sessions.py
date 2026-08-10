"""Unit tests for the core facade's session surface (issue-161, T3)."""

import pytest

from the_loop.core import sessions as core_sessions
from the_loop.sessions.registry import Session, SessionRegistry
from the_loop.state import layout_from_config
from the_loop.workitem import WorkItemRef


REF = "github:octo/repo#5"


def _config(tmp_path):
    return {"state": {"root": str(tmp_path / ".the-loop")}}


def _register(tmp_path):
    layout = layout_from_config(_config(tmp_path))
    registry = SessionRegistry(layout.local_dir)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(tmp_path),
        )
    )


def test_list_sessions_reports_registered_sessions(tmp_path):
    _register(tmp_path)
    sessions = core_sessions.list_sessions(config=_config(tmp_path))
    assert len(sessions) == 1
    # ``ref`` is the flat string every caller keys on; ``workItem`` stays the
    # registry's own object, so nothing is projected away.
    assert sessions[0]["ref"] == REF
    assert sessions[0]["workItem"]["ref"] == REF
    assert sessions[0]["status"] == "active"
    assert sessions[0]["control"] is None


def test_get_session_missing_is_lookup_error(tmp_path):
    with pytest.raises(LookupError):
        core_sessions.get_session(REF, config=_config(tmp_path))


def test_control_session_rejects_unknown_verb_before_spawning(tmp_path):
    with pytest.raises(ValueError):
        core_sessions.control_session(REF, "detonate")


def test_control_session_rejects_malformed_ref_before_spawning(tmp_path):
    with pytest.raises(ValueError):
        core_sessions.control_session("not-a-ref", "start")


# -- cleanup (issue-186) ---------------------------------------------------------


def test_cleanup_is_one_of_the_control_verbs():
    """So the CLI, the HTTP route and the MCP tool all reach one implementation."""
    assert "cleanup" in core_sessions.CONTROL_VERBS


def test_cleanup_reports_each_irreversible_fact_on_its_own_line(tmp_path, monkeypatch):
    """Losing a checkout means losing what was uncommitted in it — say so."""
    from the_loop.cleanup import SESSION, TMUX, WORKSPACE, CleanupOutcome

    class FakeDispatcher:
        def __init__(self):
            self.asked = None

        def cleanup_work_item(self, ref, **kwargs):
            self.asked = (ref, kwargs)
            return CleanupOutcome(
                ref=ref.ref,
                removed=(TMUX, WORKSPACE, SESSION),
                endpoints=(REF, "github:octo/repo#6"),
            )

        def stop(self, timeout=None):
            pass

    class FakeRouting:
        workspace = type("W", (), {"root": "/ws"})()

    fake = FakeDispatcher()
    monkeypatch.setattr(
        core_sessions, "_dispatcher_for", lambda *a, **k: (fake, FakeRouting())
    )

    result = core_sessions.control_session(
        REF, "cleanup", comment=False, config=_config(tmp_path)
    )

    text = "\n".join(m["text"] for m in result["messages"])
    assert result["effect"] == "cleaned" and result["exitCode"] == 0
    assert "github:octo/repo#6" in text
    assert "uncommitted work in it is gone" in text
    assert "machine-local session record" in text
    assert "portable record" in text
    assert fake.asked is not None and fake.asked[1]["source"] == "cli"


def test_cleanup_with_nothing_left_is_not_an_error(tmp_path, monkeypatch):
    from the_loop.cleanup import CleanupOutcome

    class FakeDispatcher:
        def cleanup_work_item(self, ref, **kwargs):
            return CleanupOutcome(ref=ref.ref)

        def stop(self, timeout=None):
            pass

    monkeypatch.setattr(
        core_sessions,
        "_dispatcher_for",
        lambda *a, **k: (
            FakeDispatcher(),
            type("R", (), {"workspace": type("W", (), {"root": ""})()})(),
        ),
    )

    result = core_sessions.control_session(
        REF, "cleanup", comment=False, config=_config(tmp_path)
    )

    assert result["effect"] == "nothing-to-clean"
    assert result["exitCode"] == 0


def test_cleanup_is_recorded_whether_or_not_it_found_anything(tmp_path, monkeypatch):
    """A disarming verb: a torn-down item must not re-spawn on the next event."""
    from the_loop.cleanup import CleanupOutcome
    from the_loop.control import ControlStore

    class FakeDispatcher:
        def cleanup_work_item(self, ref, **kwargs):
            return CleanupOutcome(ref=ref.ref)

        def stop(self, timeout=None):
            pass

    monkeypatch.setattr(
        core_sessions,
        "_dispatcher_for",
        lambda *a, **k: (
            FakeDispatcher(),
            type("R", (), {"workspace": type("W", (), {"root": ""})()})(),
        ),
    )
    config = _config(tmp_path)
    layout = layout_from_config(config)
    store = ControlStore(layout.portable_dir)
    store.record(REF, "start", source="cli", actor="octocat")

    core_sessions.control_session(REF, "cleanup", comment=False, config=config)

    record = store.get(REF)
    assert record is not None and record.command == "cleanup"
    assert store.start_requested(REF) is False
