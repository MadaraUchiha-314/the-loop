"""`the-loop ask` through the service (issue-482, R3.1 · testing plan rows T6, T7).

A session the daemon spawned holds no credential, so its question must be posted by
the service that does. These tests pin the binding (`POST /api/v1/sessions/ask` reaches
`core.sessions.ask_session` with the caller's actor) and the CLI's routing choice.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from the_loop.api.app import create_app
from the_loop.cli import main
from the_loop.client import routing
from the_loop.core import sessions as core_sessions

REF = "github:octo/repo#5"


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def fake_ask(ref, question, config=None, summary="", default_answer="", actor=""):
        if not question.strip():
            raise ValueError("the question is empty; nothing to ask")
        calls.append(
            {
                "ref": ref,
                "question": question,
                "summary": summary,
                "default": default_answer,
                "actor": actor,
            }
        )
        return {"exitCode": 0, "messages": [{"stream": "out", "text": "asked"}]}

    monkeypatch.setattr(core_sessions, "ask_session", fake_ask)
    return calls


def test_the_route_asks_with_the_callers_actor(tmp_path, captured):
    """
    Feature: spawned sessions never receive a secret
      Scenario: a daemon-spawned session asks a question
        Given the service holds the credentials
        When the CLI POSTs /api/v1/sessions/ask with the question and its actor
        Then the service asks on the work item, recording the CLI's actor

    Requirement: docs/specs/issue-482/requirements.md R3.1
    """
    client = TestClient(create_app({"state": {"root": str(tmp_path / ".the-loop")}}))
    response = client.post(
        "/api/v1/sessions/ask",
        json={
            "ref": REF,
            "question": "Which auth?",
            "summary": "s",
            "default": "OAuth",
            "actor": "agent-user",
        },
    )
    assert response.status_code == 200, response.text
    assert captured == [
        {
            "ref": REF,
            "question": "Which auth?",
            "summary": "s",
            "default": "OAuth",
            "actor": "agent-user",
        }
    ]


def test_an_empty_question_is_a_400(tmp_path, captured):
    client = TestClient(create_app({"state": {"root": str(tmp_path / ".the-loop")}}))
    response = client.post("/api/v1/sessions/ask", json={"ref": REF, "question": " "})
    assert response.status_code == 400


@pytest.mark.routed
def test_the_cli_asks_through_a_running_service(monkeypatch, captured, capsys):
    from the_loop import client

    posted = []
    monkeypatch.setattr(client, "healthy", lambda *_a, **_k: True)
    monkeypatch.setattr(
        client.Client,
        "post",
        lambda self, path, body: (
            posted.append((path, body)) or {"exitCode": 0, "messages": []}
        ),
    )
    assert main(["ask", "--work-item", REF, "--question", "Which auth?"]) == 0
    assert posted and posted[0][0] == "/sessions/ask"
    assert posted[0][1]["ref"] == REF and posted[0][1]["question"] == "Which auth?"
    assert posted[0][1]["actor"] == core_sessions._local_actor()
    assert not captured  # nothing ran in-process


@pytest.mark.routed
def test_a_daemon_sessions_ask_without_a_service_exits_2(monkeypatch, captured, capsys):
    from the_loop import client

    monkeypatch.setenv("THE_LOOP_WORK_ITEM", REF)
    monkeypatch.setattr(client, "healthy", lambda *_a, **_k: False)
    assert main(["ask", "--work-item", REF, "--question", "Which auth?"]) == 2
    assert "holds no credentials" in capsys.readouterr().err
    assert not captured


@pytest.mark.routed
def test_outside_a_daemon_session_ask_still_runs_in_process(
    monkeypatch, captured, capsys
):
    """R3.4 — the escalation path keeps working where there is no daemon."""
    from the_loop import client

    for name in routing.SPAWNED_SESSION_ENVS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(client, "healthy", lambda *_a, **_k: False)
    assert main(["ask", "--work-item", REF, "--question", "Which auth?"]) == 0
    assert captured and captured[0]["question"] == "Which auth?"
    assert routing.IN_PROCESS_NOTE in capsys.readouterr().err
