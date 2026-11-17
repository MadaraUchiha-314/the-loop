"""The service masks session credential values in caller text (issue-533, R5.1).

Every route a session's verb reaches with free text scrubs it before the facade —
and so before the bus, Slack, GitHub, Jira or the event log — sees it.

Spec: docs/specs/issue-533/design.md § Where the scrub is applied · row T1/T8.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from the_loop import sessioncreds
from the_loop.api.routes import API_PREFIX, build_router
from the_loop.cli_config import ConfigHolder

VALUE = "session-credential-value-533"


class _Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return {"ok": True}

        return record


@pytest.fixture
def client(tmp_path, monkeypatch):
    sessioncreds._forget_all()
    monkeypatch.setenv("SESSION_GH_TOKEN", VALUE)
    config = {
        "env": {"sessionCredentials": [{"name": "GH_TOKEN", "from": "SESSION_GH_TOKEN"}]}
    }
    holder = ConfigHolder(config, tmp_path / "cli-config.yaml")
    facade = _Recorder()
    app = FastAPI()
    app.include_router(build_router(holder, facade=facade))
    yield TestClient(app), facade
    sessioncreds._forget_all()


PASTED = f"my env says GH_TOKEN={VALUE}"


@pytest.mark.parametrize(
    "path, body",
    [
        ("/sessions/ask", {"ref": "github:o/r#1", "question": PASTED, "summary": PASTED}),
        ("/sessions/reply", {"ref": "github:o/r#1", "text": PASTED}),
        ("/work-items/comments", {"ref": "github:o/r#1", "body": PASTED}),
        ("/work-items/tickets", {"repository": "o/r", "title": PASTED, "body": PASTED}),
        (
            "/work-items/pull-requests",
            {"ref": "github:o/r#1", "title": PASTED, "body": PASTED, "head": "b"},
        ),
        (
            "/graph/force",
            {"repo": ".", "workItem": "issue-1", "toNode": "design", "reason": PASTED},
        ),
        (
            "/graph/skip",
            {"repo": ".", "workItem": "issue-1", "nodes": ["design"], "reason": PASTED},
        ),
    ],
)
def test_abuse_533_a4_a_pasted_token_is_masked_before_the_facade(client, path, body):
    """
    Feature: opt-in session credentials, never on argv
      Scenario: a steered agent pastes its token into text it sends the service
        Given a session credential GH_TOKEN is configured
        When the agent's verb sends text containing the value
        Then the facade receives the text with the value masked

    Requirement: docs/specs/issue-533/requirements.md R5.1
    """
    http, facade = client
    response = http.post(f"{API_PREFIX}{path}", json=body)
    assert response.status_code == 200, response.text
    assert facade.calls, "the route reached no facade method"
    assert VALUE not in repr(facade.calls)
    assert sessioncreds.MASK in repr(facade.calls)
