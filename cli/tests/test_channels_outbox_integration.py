"""Integration scenarios for the undelivered-event outbox (issue-409).

The incident the issue reports, walked end to end through the real modules: a
session asks, the Slack channel refuses every post, and — before this work item —
the question was gone. Here it is queued, named on `the-loop status`, and
delivered by the first drain after the channel recovers. The Slack SDK client and
the GitHub writer are faked at their injection points; nothing touches a network.
"""

from __future__ import annotations

import json

import pytest

from the_loop import eventlog
from the_loop.channels import outbox
from the_loop.channels.slack import DEFAULT_BOT_TOKEN_ENV
from the_loop.core import lifecycle
from the_loop.core import sessions as core_sessions

REF = "github:octo/repo#7"
OPERATOR = "octocat"


class FakeSlackClient:
    """The workspace, with a switch for the outage the report describes."""

    def __init__(self):
        self.posted = []
        self.error = ""  # set to a Slack error code to refuse every post

    def chat_postMessage(self, *, channel, text, thread_ts=None, blocks=None):
        if self.error:
            return {"ok": False, "error": self.error}
        self.posted.append({"channel": channel, "text": text, "thread_ts": thread_ts})
        return {"ok": True, "channel": channel, "ts": f"1700.{len(self.posted):06d}"}

    def auth_test(self):
        return {"ok": True, "user_id": "UBOT"}


def cli_config(tmp_path):
    return {
        "state": {"root": str(tmp_path / "state")},
        "routing": {"authorizedUsers": [{"github": OPERATOR, "name": "Octo"}]},
        "channels": {
            "ledger": "github",
            "slack": {"enabled": True, "channel": "D123"},
        },
    }


@pytest.fixture
def slack(monkeypatch):
    client = FakeSlackClient()
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)
    return client


@pytest.fixture
def ticket(monkeypatch):
    """Every ledger write lands here; the ticket is never the thing that fails."""
    written = []

    def write(item, body, gh_binary="gh"):
        written.append((item.ref, body))
        return True, "", f"https://gh/c/{len(written)}"

    monkeypatch.setattr("the_loop.comments.post_issue_comment_with_url", write)
    monkeypatch.setattr(core_sessions, "post_issue_comment_with_url", write)
    return written


@pytest.fixture
def log(tmp_path):
    path = tmp_path / "events.jsonl"
    eventlog.configure("test", path=path)
    return path


def test_a_question_no_channel_took_is_queued_then_delivered_when_it_recovers(
    tmp_path, slack, ticket, log
):
    """Scenario: a question no channel took is queued, surfaced, then delivered

    Given a Slack channel subscribed to session.awaiting_input whose posts fail
    When a session runs `the-loop ask`
    Then the question is recorded on the ticket and the ask still succeeds
    And no room heard it, so the bus queues the event and warns
    And the verb tells the session that nobody was paged
    And `the-loop status` names the backlog without changing its exit code
    When the channel recovers and a drain cycle runs
    Then the question reaches the room, the queue empties and status goes quiet

    Requirement: docs/specs/issue-409/bugfix.md R1.1, R2.1, R2.2, R3.1, R4.1-R4.4
    """
    config = cli_config(tmp_path)
    slack.error = "channel_not_found"  # the report's rotated-token symptom

    result = core_sessions.ask_session(REF, "A or B?", config=config)

    # The ticket is still the record, and a channel outage never fails the ask.
    assert result["asked"] is True and result["exitCode"] == 0  # R4.4
    assert len(ticket) == 1 and ticket[0][0] == REF
    assert slack.posted == []

    # The event is queued rather than lost (R1.1), with everything a re-post needs.
    queued = outbox.entries(config)
    assert len(queued) == 1
    assert queued[0]["event"]["eventType"] == "session.awaiting_input"
    assert queued[0]["event"]["text"] == "A or B?"
    assert queued[0]["lastError"].startswith("slack: ")
    assert queued[0]["channels"] == ["slack"]

    # The session is told, plainly (R4.2), and the event carries the count (R4.3).
    notes = "\n".join(m["text"] for m in result["messages"] if m["stream"] == "err")
    assert "NO channel took this question" in notes and "queued for redelivery" in notes
    asked = [
        e for e in eventlog.read_events(log) if e["event"] == "session.awaiting_input"
    ]
    assert asked and asked[0]["channels_posted"] == 0
    warned = [
        e for e in eventlog.read_events(log) if e["event"] == "channel.undelivered"
    ]
    assert warned and warned[0]["level"] == "warning"
    assert "A or B" not in json.dumps(warned)  # ids only

    # The operator's own surface stops being green (R3.1) — without moving `ok`.
    report = lifecycle.status_all(config)
    assert report["channelDelivery"]["pending"] == 1
    line = lifecycle.undelivered_line(report)
    assert "1 event(s) undelivered" in line and "slack" in line
    # No daemon is running in this test, so the line must not promise a retry.
    assert "nothing is draining them" in line
    assert (
        f"retried every {outbox.DRAIN_INTERVAL_SECONDS}s"
        in lifecycle.undelivered_line(
            dict(report, services=[{"service": "poller", "running": True}])
        )
    )
    assert report["ok"] == lifecycle.status_all(cli_config(tmp_path / "clean"))["ok"]

    # The operator fixes the token; the next drain delivers the backlog (R2.2).
    slack.error = ""
    assert outbox.drain(config) == {"attempted": 1, "delivered": 1, "pending": 0}
    assert any("A or B?" in post["text"] for post in slack.posted)
    late = [
        e for e in eventlog.read_events(log) if e["event"] == "channel.delivered_late"
    ]
    assert late and late[0]["work_item"] == REF

    assert lifecycle.undelivered_line(lifecycle.status_all(config)) == ""  # R3.2


def test_a_delivered_question_queues_nothing_and_status_stays_quiet(
    tmp_path, slack, ticket
):
    """Scenario: a question the channel takes leaves no backlog behind

    Given a healthy Slack channel
    When a session runs `the-loop ask`
    Then the room has the question
    And nothing is queued, so `the-loop status` says nothing about delivery

    Requirement: docs/specs/issue-409/bugfix.md R1.2, R3.2
    """
    config = cli_config(tmp_path)

    assert core_sessions.ask_session(REF, "A or B?", config=config)["asked"] is True

    assert any("A or B?" in post["text"] for post in slack.posted)
    assert outbox.entries(config) == []
    report = lifecycle.status_all(config)
    assert report["channelDelivery"] == {
        "pending": 0,
        "oldest": "",
        "waitedSeconds": 0,
        "lastError": "",
    }
    assert lifecycle.undelivered_line(report) == ""


def test_a_status_whose_outbox_cannot_be_read_still_answers(tmp_path, monkeypatch):
    """Scenario: an unreadable backlog never takes `status` down with it

    Given an outbox that raises when it is read
    When `the-loop status` builds its report
    Then it reports no backlog and still answers about the services

    Requirement: docs/specs/issue-409/bugfix.md R3.4, R3.5
    """
    monkeypatch.setattr(
        outbox,
        "summary",
        lambda config: (_ for _ in ()).throw(OSError("permission denied")),
    )
    report = lifecycle.status_all(cli_config(tmp_path))
    assert report["channelDelivery"]["pending"] == 0
    assert [row["service"] for row in report["services"]]
    assert lifecycle.undelivered_line(report) == ""
