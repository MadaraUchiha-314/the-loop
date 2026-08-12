"""Integration tests: GET /api/v1/sessions/transcript (issue-209, T2/T8).

The route as served, against a real registration and a real-format JSONL
fixture under a fake projects root (reached via ``CLAUDE_CONFIG_DIR`` — the
harness's own relocation mechanism doubling as the test seam). The negative
scenarios are the security design's mechanisms: the read is fail-closed to
``<id>.jsonl`` files inside the projects root, and every refusal is the same
404 shape.
"""

import json
import re

import pytest
from fastapi.testclient import TestClient

from the_loop.api.app import create_app
from the_loop.sessions.registry import Session, SessionRegistry
from the_loop.state import layout_from_config
from the_loop.workitem import WorkItemRef


REF = "github:octo/repo#35"
SID = "0f1c2d3e-aaaa-bbbb-cccc-000000000001"


def _config(tmp_path):
    return {"state": {"root": str(tmp_path / ".the-loop")}}


@pytest.fixture
def projects_root(tmp_path, monkeypatch):
    config_dir = tmp_path / "claude-config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    root = config_dir / "projects"
    root.mkdir(parents=True)
    return root


def _register(tmp_path, harness="claude", sid=SID):
    layout = layout_from_config(_config(tmp_path))
    registry = SessionRegistry(layout.local_dir)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness=harness,
            harness_session_id=sid,
            cwd=str(tmp_path),
        )
    )
    return registry


def _write_transcript(root, cwd, entries, sid=SID):
    project = root / re.sub(r"[^A-Za-z0-9]", "-", cwd)
    project.mkdir(parents=True, exist_ok=True)
    path = project / f"{sid}.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return path


#: Real Claude Code line shapes, so the same fixture format drives the UI tests.
TURNS = [
    {
        "type": "user",
        "timestamp": "2026-08-12T10:00:00Z",
        "message": {"role": "user", "content": "Fix the flaky test."},
    },
    {
        "type": "assistant",
        "timestamp": "2026-08-12T10:00:05Z",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Reading the test first."},
                {"type": "tool_use", "name": "Read", "input": {"file_path": "x"}},
            ],
        },
    },
    {
        "type": "user",
        "timestamp": "2026-08-12T10:00:06Z",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "content": "def test_x(): ..."}],
        },
    },
]


def test_the_trace_of_a_registered_session_is_served_with_its_tail(
    tmp_path, projects_root
):
    """
    Feature: the harness's own transcript is served over /api/v1
      Scenario: the trace of a registered session is served with its tail
        Given a registered Claude Code session whose transcript file exists
        When a client GETs /api/v1/sessions/transcript with a tail
        Then the response carries the resolved path, the whole file's line count,
          and the last N lines parsed as JSON objects, oldest first

    Requirement: docs/specs/issue-209/requirements.md R1.1, R1.2, R1.3, R3.1
    """
    _write_transcript(projects_root, str(tmp_path), TURNS)
    _register(tmp_path)
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/v1/sessions/transcript", params={"ref": REF, "tail": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["workItem"] == REF
    assert body["path"].endswith(f"{SID}.jsonl")
    assert body["totalLines"] == 3 and body["truncated"] is True
    assert [e["type"] for e in body["entries"]] == ["assistant", "user"]
    assert body["entries"][0]["message"]["content"][1]["name"] == "Read"


def test_a_closed_sessions_transcript_is_still_served(tmp_path, projects_root):
    """
    Feature: the harness's own transcript is served over /api/v1
      Scenario: a closed session's transcript is still served
        Given a session that was closed after its work completed
        When a client GETs /api/v1/sessions/transcript
        Then the transcript is served — the file outlives the registration

    Requirement: docs/specs/issue-209/requirements.md R1.4
    """
    _write_transcript(projects_root, str(tmp_path), TURNS)
    registry = _register(tmp_path)
    registry.close(WorkItemRef.parse(REF))
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/v1/sessions/transcript", params={"ref": REF})

    assert response.status_code == 200
    assert response.json()["totalLines"] == 3


def test_a_work_item_with_no_session_has_no_transcript_to_serve(
    tmp_path, projects_root
):
    """
    Feature: the transcript route is fail-closed
      Scenario: a work item with no session has no transcript to serve
        Given a work item with no registered session
        When a client GETs /api/v1/sessions/transcript
        Then the response is 404 with guidance

    Requirement: docs/specs/issue-209/requirements.md R2.3
    """
    client = TestClient(create_app(_config(tmp_path)))
    response = client.get("/api/v1/sessions/transcript", params={"ref": REF})
    assert response.status_code == 404
    assert "no session registered" in response.json()["detail"]


def test_a_cursor_sessions_transcript_location_is_not_guessed_at(
    tmp_path, projects_root
):
    """
    Feature: the transcript route is fail-closed
      Scenario: a Cursor session's transcript location is not guessed at
        Given a registered Cursor session
        When a client GETs /api/v1/sessions/transcript
        Then the response is 404 naming the reason

    Requirement: docs/specs/issue-209/requirements.md R2.4
    """
    _register(tmp_path, harness="cursor")
    client = TestClient(create_app(_config(tmp_path)))
    response = client.get("/api/v1/sessions/transcript", params={"ref": REF})
    assert response.status_code == 404
    assert "undocumented" in response.json()["detail"]


def test_a_session_without_a_transcript_yet_is_a_404_naming_the_path(
    tmp_path, projects_root
):
    """
    Feature: the transcript route is fail-closed
      Scenario: a session that has not written a transcript yet is a 404 naming the path
        Given a registered session whose transcript file does not exist
        When a client GETs /api/v1/sessions/transcript
        Then the response is 404 naming the derived path, so the operator can
          see where the service looked

    Requirement: docs/specs/issue-209/requirements.md R2.5
    """
    _register(tmp_path)
    client = TestClient(create_app(_config(tmp_path)))
    response = client.get("/api/v1/sessions/transcript", params={"ref": REF})
    assert response.status_code == 404
    assert f"{SID}.jsonl" in response.json()["detail"]


def test_a_crafted_session_id_cannot_walk_the_read_outside_the_root(
    tmp_path, projects_root
):
    """
    Feature: the transcript route serves transcripts, not the filesystem
      Scenario: a crafted session id cannot walk the read outside the projects root
        Given a registration whose session id attempts path traversal
        And a file outside the projects root that the traversal would reach
        When a client GETs /api/v1/sessions/transcript
        Then the response is 404 and the outside file's content is never served

    Requirement: docs/specs/issue-209/requirements.md R2.2 (abuse case 1)
    """
    secret = tmp_path / "secret.jsonl"
    secret.write_text('{"stolen": true}\n')
    _register(tmp_path, sid="../../../secret")
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/v1/sessions/transcript", params={"ref": REF})

    assert response.status_code == 404
    assert "stolen" not in response.text


def test_a_symlink_escape_is_indistinguishable_from_a_missing_file(
    tmp_path, projects_root
):
    """
    Feature: the transcript route serves transcripts, not the filesystem
      Scenario: a symlink planted in the projects root cannot leak an outside file
        Given a symlink at the derived transcript path pointing outside the root
        When a client GETs /api/v1/sessions/transcript
        Then the response is the same 404 a missing file gets, and the target
          is never served

    Requirement: docs/specs/issue-209/requirements.md R2.1 (abuse case 1)
    """
    outside = tmp_path / "outside.jsonl"
    outside.write_text('{"stolen": true}\n')
    project = projects_root / re.sub(r"[^A-Za-z0-9]", "-", str(tmp_path))
    project.mkdir(parents=True)
    (project / f"{SID}.jsonl").symlink_to(outside)
    _register(tmp_path)
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/v1/sessions/transcript", params={"ref": REF})

    assert response.status_code == 404
    assert "no transcript at" in response.json()["detail"]
    assert "stolen" not in response.text


def test_bad_arguments_are_refused_by_the_route(tmp_path, projects_root):
    """
    Feature: the transcript route is fail-closed
      Scenario: a malformed ref or a negative tail is a caller mistake
        When a client GETs /api/v1/sessions/transcript with a malformed ref
        Then the response is 400
        When the tail is negative
        Then the response is 422 from validation

    Requirement: docs/specs/issue-209/requirements.md R2.6
    """
    client = TestClient(create_app(_config(tmp_path)))
    assert (
        client.get(
            "/api/v1/sessions/transcript", params={"ref": "not-a-ref"}
        ).status_code
        == 400
    )
    assert (
        client.get(
            "/api/v1/sessions/transcript", params={"ref": REF, "tail": -1}
        ).status_code
        == 422
    )
