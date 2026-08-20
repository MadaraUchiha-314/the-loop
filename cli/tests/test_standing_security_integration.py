"""One negative test per trust boundary in the standing-sessions design (issue-277, T8).

The boundaries: the two session namespaces cannot address each other; a message never
spawns a session; the control plane's session surfaces do not leak across; and the
directive a session is given cannot be replaced by the operator's own prompt.
"""

from __future__ import annotations

import pytest

from the_loop.api.app import create_app
from the_loop.api import mcp as api_mcp
from the_loop.core import sessions as core_sessions
from the_loop.core import standing as core_standing
from the_loop.sessions.registry import Session, SessionRegistry
from the_loop.standing import StandingRecord, StandingRegistry, standing_ref
from the_loop.state import layout_from_config
from the_loop.workitem import WorkItemRef


def _config(tmp_path):
    return {
        "state": {"root": str(tmp_path / ".the-loop")},
        "standingSessions": {"enabled": True, "sessions": [{"name": "supervisor"}]},
    }


def test_the_two_session_namespaces_cannot_address_each_other(tmp_path):
    """
    Feature: standing sessions
      Scenario: the two session namespaces cannot address each other
        Given a registered work-item session and a recorded standing session
        When each is addressed with the other's identifier
        Then neither resolves, and neither registry lists the other's entry

    Requirement: docs/specs/issue-277/requirements.md R3.1, R3.2
    """
    config = _config(tmp_path)
    layout = layout_from_config(config)
    SessionRegistry(layout.local_dir).register(
        Session(
            work_item=WorkItemRef.parse("github:octo/repo#5"),
            harness="claude",
            harness_session_id="conv-work-item",
            cwd=str(tmp_path),
        )
    )
    StandingRegistry(layout.standing_dir).write(
        StandingRecord(
            name="supervisor", harness="claude", harness_session_id="conv-standing"
        )
    )

    # A standing ref is not a work item…
    with pytest.raises(ValueError):
        core_sessions.get_session(standing_ref("supervisor"), config=config)
    # …and a work-item ref is not a standing session.
    with pytest.raises(LookupError):
        core_standing.get_standing("github:octo/repo#5", config=config)

    # Neither listing shows the other's entry.
    assert [row["ref"] for row in core_sessions.list_sessions(config=config)] == [
        "github:octo/repo#5"
    ]
    assert [row["name"] for row in core_standing.list_standing(config=config)] == [
        "supervisor"
    ]


def test_a_standing_record_never_lands_in_the_session_registry_directory(tmp_path):
    """The router reads `local/`; standing records live one level down, so a
    directory scan for session records cannot pick one up."""
    config = _config(tmp_path)
    layout = layout_from_config(config)
    StandingRegistry(layout.standing_dir).write(StandingRecord(name="supervisor"))

    assert core_sessions.list_sessions(config=config) == []


def test_a_message_never_spawns_a_standing_session(tmp_path, monkeypatch):
    """
    Feature: standing sessions
      Scenario: a message into a stopped standing session refuses instead of spawning one
        Given a declared standing session that has never been started
        When a message is sent to it
        Then the send is refused, naming the start command
        And no tmux session is created

    Requirement: docs/specs/issue-277/requirements.md R3.4
    """
    spawned = []
    monkeypatch.setattr(
        core_standing,
        "TmuxRunner",
        lambda **kwargs: type(
            "_NeverSpawns",
            (),
            {
                "spawn_in": lambda *a, **k: spawned.append(a) or None,
                "has_live_session": staticmethod(lambda target: False),
            },
        )(),
    )

    with pytest.raises(LookupError) as excinfo:
        core_standing.say_standing("supervisor", "hello", config=_config(tmp_path))

    assert "the-loop standing start supervisor" in str(excinfo.value)
    assert spawned == []


def test_standing_lifecycle_is_not_reachable_over_mcp():
    """An agent that could stop a standing session could stop the one supervising
    it, and bringing a harness process into — or out of — existence is an
    operator's act. Same reasoning that keeps `restart` and `sessions reset` off
    this surface."""
    import asyncio

    tools = {tool.name for tool in asyncio.run(api_mcp.build_server({}).list_tools())}

    assert "say_to_standing_session" in tools
    assert "list_standing_sessions" in tools
    assert "get_standing_session" in tools
    for forbidden in ("control", "create", "delete", "start", "stop", "restart"):
        assert not any("standing" in name and forbidden in name for name in tools), (
            f"{forbidden} reached the MCP surface"
        )


def test_a_created_session_cannot_be_addressed_as_a_work_item(tmp_path):
    """The namespace split holds for created sessions too: they are recorded in
    the standing registry, which nothing that resolves refs ever reads."""
    config = _config(tmp_path)
    config["standingSessions"] = {"enabled": True, "sessions": []}
    StandingRegistry(layout_from_config(config).standing_dir).write(
        StandingRecord(name="triage", harness="claude")
    )

    assert core_sessions.list_sessions(config=config) == []
    with pytest.raises(ValueError):
        core_sessions.get_session(standing_ref("triage"), config=config)


def test_the_rest_surface_maps_refusals_onto_the_documented_codes(tmp_path):
    """400 for a caller mistake, 404 for a name that is not there — the mapping
    the authored contract publishes."""
    from fastapi.testclient import TestClient

    app = create_app(_config(tmp_path))
    with TestClient(app) as client:
        assert (
            client.get("/api/v1/standing-sessions/one?name=nobody").status_code == 404
        )
        assert (
            client.post(
                "/api/v1/standing-sessions/control",
                json={"name": "supervisor", "verb": "detonate"},
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/v1/standing-sessions/say",
                json={"name": "supervisor", "text": "  "},
            ).status_code
            == 400
        )
        # create: a name the config already declares is the caller's mistake
        assert (
            client.post(
                "/api/v1/standing-sessions/create", json={"name": "supervisor"}
            ).status_code
            == 400
        )
        # delete: a declared session is 400, an uncreated one is 404
        assert (
            client.post(
                "/api/v1/standing-sessions/delete", json={"name": "supervisor"}
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/v1/standing-sessions/delete", json={"name": "nobody"}
            ).status_code
            == 404
        )
