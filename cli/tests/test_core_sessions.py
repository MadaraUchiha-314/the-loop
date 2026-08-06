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
