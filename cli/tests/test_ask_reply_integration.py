"""Integration tests: `the-loop ask` + POST /api/v1/sessions/reply (issue-208, T2/T8).

The two halves of the question/answer loop, exercised at their surfaces: the
CLI verb end-to-end with a fake ``gh``, and the reply route through the served
app with a fake tmux runner. The negative scenarios are the security design's
mechanisms — no respawn, pause honoured, marked bodies.
"""

import json

import pytest
from fastapi.testclient import TestClient

from the_loop import eventlog
from the_loop.api.app import create_app
from the_loop.authz import SELF_COMMENT_ATTRIBUTION, SELF_COMMENT_MARKER
from the_loop.cli import main
from the_loop.core import sessions as core_sessions
from the_loop.runner import TmuxResult
from the_loop.sessions.registry import Session, SessionRegistry
from the_loop.state import layout_from_config
from the_loop.workitem import WorkItemRef


REF = "github:octo/repo#7"


def _config(tmp_path):
    return {"state": {"root": str(tmp_path / ".the-loop")}}


def _register(tmp_path, tmux_target="loop-octo-repo-7"):
    layout = layout_from_config(_config(tmp_path))
    registry = SessionRegistry(layout.local_dir)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(tmp_path),
            tmux_target=tmux_target,
        )
    )
    return registry


def _capture_log(tmp_path):
    """Route module-level emits to a readable file for the duration of a test."""
    path = tmp_path / "captured-events.jsonl"
    eventlog.configure("test", path=path)
    return path


class _FakeRunner:
    delivered: "list[tuple[str, str]]" = []
    result: "TmuxResult | None" = None

    def __init__(self, *args, **kwargs):
        pass

    def deliver(self, session, prompt, timeout=None):
        _FakeRunner.delivered.append((session.work_item.ref, prompt))
        return _FakeRunner.result or TmuxResult(ok=True)


@pytest.fixture
def fake_runner(monkeypatch):
    _FakeRunner.delivered = []
    _FakeRunner.result = None
    monkeypatch.setattr(core_sessions, "TmuxRunner", _FakeRunner)
    return _FakeRunner


@pytest.fixture
def no_ticket_comment(monkeypatch):
    posted = []
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment",
        lambda item, body, gh_binary="gh": posted.append(body) or (True, ""),
    )
    return posted


def test_reply_is_pasted_into_the_waiting_session(
    tmp_path, fake_runner, no_ticket_comment
):
    """
    Feature: answering an agent through the control plane
      Scenario: an operator's reply is pasted into the waiting session
        Given a work item with an active registered session
        When the operator POSTs /api/v1/sessions/reply with text and an actor
        Then the text is delivered into the session's pane under a provenance header
        And a session.reply_sent event is recorded
        And the ticket receives a marked report comment quoting the reply

    Requirement: docs/specs/issue-208/requirements.md R2.1, R2.2, R2.6
    """
    _register(tmp_path)
    log = _capture_log(tmp_path)
    client = TestClient(create_app(_config(tmp_path)))

    response = client.post(
        "/api/v1/sessions/reply",
        json={"ref": REF, "text": "Use OAuth.", "actor": "onika"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["delivered"] is True and body["exitCode"] == 0
    ref, prompt = fake_runner.delivered[0]
    assert ref == REF
    assert "the-loop control plane (onika)" in prompt
    assert prompt.endswith("Use OAuth.")
    events = [json.loads(line) for line in log.read_text().splitlines()]
    sent = [e for e in events if e["event"] == "session.reply_sent"]
    assert sent and sent[0]["work_item"] == REF and sent[0]["actor"] == "onika"
    assert any(
        SELF_COMMENT_MARKER in c and "> Use OAuth." in c for c in no_ticket_comment
    )


def test_reply_without_a_session_is_404_and_never_spawns(tmp_path, fake_runner):
    """
    Feature: the reply route is fail-closed
      Scenario: a reply to a work item with no session is refused without spawning
        Given a work item with no registered session
        When the operator POSTs /api/v1/sessions/reply
        Then the response is 404 and nothing was delivered or spawned

    Requirement: docs/specs/issue-208/requirements.md R2.3 (abuse case 2)
    """
    client = TestClient(create_app(_config(tmp_path)))
    response = client.post(
        "/api/v1/sessions/reply", json={"ref": REF, "text": "Use OAuth."}
    )
    assert response.status_code == 404
    assert "never spawns" in response.json()["detail"]
    assert not fake_runner.delivered


def test_reply_to_a_dead_pane_is_404_not_a_respawn(
    tmp_path, fake_runner, no_ticket_comment
):
    """
    Feature: the reply route is fail-closed
      Scenario: a reply to a session whose pane is gone is refused without respawning
        Given a registered session whose tmux pane has died
        When the operator POSTs /api/v1/sessions/reply
        Then the response is 404 with guidance and no respawn is attempted
        And no session.reply_sent event is recorded

    Requirement: docs/specs/issue-208/requirements.md R2.3 (abuse case 2)
    """
    _register(tmp_path)
    _FakeRunner.result = TmuxResult(ok=False, session_missing=True, error="gone")
    log = _capture_log(tmp_path)
    client = TestClient(create_app(_config(tmp_path)))

    response = client.post(
        "/api/v1/sessions/reply", json={"ref": REF, "text": "Use OAuth."}
    )

    assert response.status_code == 404
    assert "answer on the ticket" in response.json()["detail"]
    events = [json.loads(line) for line in log.read_text().splitlines()]
    assert not [e for e in events if e["event"] == "session.reply_sent"]


def test_reply_to_a_paused_session_is_400(tmp_path, fake_runner):
    """
    Feature: the reply route is fail-closed
      Scenario: a reply to a paused session is refused
        Given a registered session an operator has paused
        When the operator POSTs /api/v1/sessions/reply
        Then the response is 400 telling them to resume first, and nothing is delivered

    Requirement: docs/specs/issue-208/requirements.md R2.4 (abuse case 3)
    """
    registry = _register(tmp_path)
    registry.pause(WorkItemRef.parse(REF))
    client = TestClient(create_app(_config(tmp_path)))

    response = client.post(
        "/api/v1/sessions/reply", json={"ref": REF, "text": "Use OAuth."}
    )

    assert response.status_code == 400
    assert "paused" in response.json()["detail"]
    assert not fake_runner.delivered


def test_empty_or_malformed_replies_are_400(tmp_path, fake_runner):
    """
    Feature: the reply route is fail-closed
      Scenario: an empty reply is refused
        Given a registered session
        When the operator POSTs /api/v1/sessions/reply with whitespace text or a bad ref
        Then the response is 400 and nothing is delivered

    Requirement: docs/specs/issue-208/requirements.md R2.5
    """
    _register(tmp_path)
    client = TestClient(create_app(_config(tmp_path)))
    assert (
        client.post(
            "/api/v1/sessions/reply", json={"ref": REF, "text": "  \n"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/sessions/reply", json={"ref": "not-a-ref", "text": "hi"}
        ).status_code
        == 400
    )
    assert not fake_runner.delivered


def test_the_ask_verb_posts_a_marked_question_and_records_the_wait(
    tmp_path, monkeypatch, capsys
):
    """
    Feature: agents ask through a verb
      Scenario: the ask verb posts a marked question and records the wait
        Given a spawned agent that needs a human answer
        When it runs `the-loop ask --work-item <ref> --question <text>`
        Then the question lands on the ticket with the loop-prevention marker
          and attribution stamped centrally
        And a session.awaiting_input event carries the question and comment URL
        And the attention surface reports the work item as awaiting-input

    Requirement: docs/specs/issue-208/requirements.md R1.1, R1.2, R3.1 (abuse case 5)
    """
    posted = {}

    def fake_post(item, body, gh_binary="gh"):
        posted["ref"], posted["body"] = item.ref, body
        return True, "", "https://github.com/octo/repo/issues/7#issuecomment-3"

    monkeypatch.setattr(core_sessions, "post_issue_comment_with_url", fake_post)
    log_path = layout_from_config(_config(tmp_path)).event_log
    monkeypatch.setattr(
        eventlog,
        "configure_from_file",
        lambda source: eventlog.configure(source, path=log_path),
    )

    exit_code = main(["ask", "--work-item", REF, "--question", "Which auth mode?"])

    assert exit_code == 0
    assert posted["ref"] == REF
    assert posted["body"].startswith("Which auth mode?")
    assert SELF_COMMENT_MARKER in posted["body"]
    assert SELF_COMMENT_ATTRIBUTION in posted["body"]
    out = capsys.readouterr().out
    assert "asked on github:octo/repo#7" in out
    events = list(eventlog.read_events(log_path))
    asked = [e for e in events if e["event"] == "session.awaiting_input"]
    assert asked and asked[0]["question"] == "Which auth mode?"
    assert asked[0]["comment_url"].endswith("#issuecomment-3")
    assert asked[0]["comment_posted"] is True

    from the_loop.core import attention

    waiting = [
        i
        for i in attention.list_attention(_config(tmp_path))
        if i["kind"] == "awaiting-input"
    ]
    assert waiting and waiting[0]["workItem"] == REF


def test_the_ask_verb_records_the_wait_even_when_gh_fails(
    tmp_path, monkeypatch, capsys
):
    """
    Feature: agents ask through a verb
      Scenario: the question never reached the ticket but the wait is still recorded
        Given a spawned agent whose gh call fails
        When it runs `the-loop ask`
        Then the exit code is non-zero and the failure is reported
        And a session.awaiting_input event with comment_posted false is still recorded,
          so the control plane can still carry an answer

    Requirement: docs/specs/issue-208/requirements.md R1.3
    """
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (False, "gh exited 1: boom", ""),
    )
    log_path = layout_from_config(_config(tmp_path)).event_log
    monkeypatch.setattr(
        eventlog,
        "configure_from_file",
        lambda source: eventlog.configure(source, path=log_path),
    )

    exit_code = main(["ask", "--work-item", REF, "--question", "Which auth mode?"])

    assert exit_code == 1
    assert "boom" in capsys.readouterr().err
    asked = [
        e
        for e in eventlog.read_events(log_path)
        if e["event"] == "session.awaiting_input"
    ]
    assert (
        asked and asked[0]["comment_posted"] is False and asked[0]["level"] == "warning"
    )


def test_the_ask_verb_reads_a_question_file(tmp_path, monkeypatch):
    """
    Feature: agents ask through a verb
      Scenario: a multi-line markdown question survives shell quoting via a file
        Given a question written to a file
        When the agent runs `the-loop ask --question-file <path>`
        Then the file's content is what lands on the ticket

    Requirement: docs/specs/issue-208/requirements.md R1.1
    """
    posted = {}
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": posted.update(body=body) or (True, "", ""),
    )
    question = tmp_path / "question.md"
    question.write_text("## Two options\n\n- A\n- B\n")

    exit_code = main(["ask", "--work-item", REF, "--question-file", str(question)])

    assert exit_code == 0
    assert posted["body"].startswith("## Two options")


def test_the_ask_verb_refuses_an_empty_question(tmp_path, monkeypatch, capsys):
    """
    Feature: agents ask through a verb
      Scenario: an empty question is a caller mistake, not a comment
        When the agent runs `the-loop ask` with only whitespace
        Then the exit code is 2 and nothing is posted

    Requirement: docs/specs/issue-208/requirements.md R1.4
    """
    called = []
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment_with_url",
        lambda *a, **k: called.append(a) or (True, "", ""),
    )
    assert main(["ask", "--work-item", REF, "--question", "  "]) == 2
    assert "empty" in capsys.readouterr().err
    assert not called
