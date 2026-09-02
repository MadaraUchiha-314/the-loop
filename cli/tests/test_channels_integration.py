"""Integration scenarios for channels (issue-245): ask fan-out, the reply
round-trip, Socket Mode convergence, and the daemon watcher.

Every scenario runs through the real modules with only the process boundaries
faked: the Slack SDK client (injected factory), the GitHub comment writer
(monkeypatched), and session delivery (monkeypatched ``reply_session``).
"""

from __future__ import annotations

import threading
import time

import pytest

from the_loop.authz import is_self_authored
from the_loop.channels import inbound, watcher
from the_loop.channels.slack import DEFAULT_BOT_TOKEN_ENV
from the_loop.core import sessions as core_sessions


class FakeSlackClient:
    def __init__(self):
        self.posted = []
        self.replies = {}

    def chat_postMessage(self, *, channel, text, thread_ts=None, blocks=None):
        self.posted.append(
            {"channel": channel, "text": text, "thread_ts": thread_ts, "blocks": blocks}
        )
        return {"ok": True, "channel": channel, "ts": f"1700.{len(self.posted):06d}"}

    def conversations_history(self, *, channel, oldest=None, limit=100):
        return {"ok": True, "messages": list(getattr(self, "history", []))}

    def conversations_replies(self, *, channel, ts, oldest=None, limit=200):
        return {"ok": True, "messages": list(self.replies.get(ts, []))}

    def auth_test(self):
        return {"ok": True, "user_id": "UBOT"}


def cli_config(tmp_path, authorized=("UHUMAN",), **slack):
    section = {"enabled": True, "channel": "C123", **slack}
    return {
        "state": {"root": str(tmp_path / "state")},
        # Identity in one place (issue-309): the Slack member id sits on a
        # person entry beside their GitHub login.
        "routing": {
            "authorizedUsers": [
                {"github": f"gh-{member}", "slack": member} for member in authorized
            ]
        },
        "channels": {"slack": section},
    }


def test_ask_lands_on_the_work_item_and_fans_out(tmp_path, monkeypatch):
    """Scenario: An asked question lands on the work item and fans out to Slack

    Given a CLI config with an enabled Slack channel subscribed to
      session.awaiting_input
    When the agent runs `the-loop ask` for its work item
    Then the question is posted on the work item first
    And the same question is posted to the Slack channel as a thread root
    And the thread binding is recorded so replies can be attributed

    Requirement: docs/specs/issue-245/requirements.md R1.1, R1.2, R2.3, R3.2
    """
    client = FakeSlackClient()
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)
    order = []
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (
            order.append("work-item")
            or (True, "", "https://github.com/o/r/issues/7#c1")
        ),
    )
    config = cli_config(tmp_path)

    result = core_sessions.ask_session("github:o/r#7", "A or B?", config=config)

    assert result["asked"] is True and result["exitCode"] == 0
    assert order == ["work-item"]  # the work item had it before any channel
    assert len(client.posted) == 1 and client.posted[0]["thread_ts"] is None
    assert "A or B?" in client.posted[0]["text"]
    from the_loop.channels.state import ChannelState

    state = ChannelState.load(tmp_path / "state" / "channels" / "slack.json")
    assert state.work_item_for("1700.000001") == "github:o/r#7"


def test_channel_outage_never_fails_the_ask(tmp_path, monkeypatch):
    """Scenario: A Slack outage leaves the ask outcome untouched

    Given an enabled Slack channel whose client raises on every call
    When the agent asks a question
    Then the work-item post succeeds and the exit code is 0
    And the channel failure is recorded, not raised

    Requirement: docs/specs/issue-245/requirements.md R1.2
    """

    class ExplodingClient:
        def chat_postMessage(self, **kwargs):
            raise RuntimeError("slack is down")

    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    monkeypatch.setattr(
        "the_loop.channels.slack.build_client", lambda token: ExplodingClient()
    )
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (True, "", "url"),
    )

    result = core_sessions.ask_session(
        "github:o/r#7", "A or B?", config=cli_config(tmp_path)
    )
    assert result["asked"] is True and result["exitCode"] == 0


def seeded_thread(tmp_path, monkeypatch, client, config):
    """Post one ask through the channel so a bound thread exists, then seed
    a human reply into it."""
    from the_loop.channels.bus import broadcast

    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    results = broadcast(
        "session.awaiting_input",
        "github:o/r#7",
        "A or B?",
        cli_config=config,
        client_factory=lambda token: client,
    )
    thread = results[0].thread
    client.replies[thread] = [
        {"ts": thread, "user": "UBOT", "text": "A or B?"},
        {"ts": "1800.1", "user": "UHUMAN", "text": "go with A"},
    ]
    return thread


def test_thread_reply_is_mirrored_and_delivered(tmp_path, monkeypatch):
    """Scenario: A Slack thread reply is mirrored to the ticket and delivered
    to the waiting session

    Given a bound Slack thread for a work item with a waiting session
    When an authorized member replies in the thread and a poll cycle runs
    Then the reply is posted on the work item as the-loop's own marked comment
    And the reply is delivered through the reply path without a ticket comment
      of its own
    And a second poll cycle processes nothing (the cursor advanced)

    Requirement: docs/specs/issue-245/requirements.md R1.3, R4.1, R4.6, R5.2, R5.4
    """
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    seeded_thread(tmp_path, monkeypatch, client, config)

    mirrors, deliveries = [], []
    monkeypatch.setattr(
        "the_loop.comments.post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (
            mirrors.append((item.ref, body)) or (True, "", "")
        ),
    )
    monkeypatch.setattr(
        core_sessions,
        "reply_session",
        lambda ref, text, actor="", comment=True, config=None: (
            deliveries.append({"ref": ref, "actor": actor, "comment": comment})
            or {"delivered": True}
        ),
    )

    summary = inbound.poll_once(config, client_factory=lambda token: client)
    assert summary["processed"] == 1
    ref, body = mirrors[0]
    assert ref == "github:o/r#7"
    assert is_self_authored(body) and "go with A" in body
    assert deliveries == [
        {"ref": "github:o/r#7", "actor": "slack:UHUMAN", "comment": False}
    ]

    assert (
        inbound.poll_once(config, client_factory=lambda token: client)["replies"] == 0
    )


def test_reply_with_no_session_still_lands_on_the_ticket(tmp_path, monkeypatch):
    """Scenario: A reply with no session left still lands on the work item

    Given a bound thread whose work item has no registered session
    When an authorized reply arrives
    Then the mirror is posted on the work item
    And the delivery failure is recorded, not raised

    Requirement: docs/specs/issue-245/requirements.md R5.4
    """
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    seeded_thread(tmp_path, monkeypatch, client, config)

    mirrors = []
    monkeypatch.setattr(
        "the_loop.comments.post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": mirrors.append(body) or (True, "", ""),
    )

    def no_session(ref, text, actor="", comment=True, config=None):
        raise LookupError("no session registered")

    monkeypatch.setattr(core_sessions, "reply_session", no_session)

    summary = inbound.poll_once(config, client_factory=lambda token: client)
    assert summary["processed"] == 1 and summary["delivered"] == 0
    assert len(mirrors) == 1 and is_self_authored(mirrors[0])


def test_unauthorized_reply_is_neither_mirrored_nor_delivered(tmp_path, monkeypatch):
    """Scenario: An unauthorized Slack reply is dropped whole

    Given a bound thread and an empty authorizedUsers allow-list
    When a reply arrives
    Then nothing is mirrored and nothing is delivered

    Requirement: docs/specs/issue-245/requirements.md R5.1
    """
    client = FakeSlackClient()
    config = cli_config(tmp_path, authorized=())
    seeded_thread(tmp_path, monkeypatch, client, config)

    mirrors, deliveries = [], []
    monkeypatch.setattr(
        "the_loop.comments.post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": mirrors.append(body) or (True, "", ""),
    )
    monkeypatch.setattr(
        core_sessions,
        "reply_session",
        lambda *a, **k: deliveries.append(a) or {"delivered": True},
    )

    summary = inbound.poll_once(config, client_factory=lambda token: client)
    assert summary["dropped"] == 1
    assert mirrors == [] and deliveries == []


def test_socket_event_reaches_the_same_pipeline(tmp_path, monkeypatch):
    """Scenario: A Socket Mode message reaches the same pipeline as a polled
    reply

    Given a bound Slack thread
    When a message event for that thread arrives over Socket Mode
    Then it is mirrored and delivered exactly as a polled reply would be
    And a message outside any bound thread is dropped as unmapped

    Requirement: docs/specs/issue-245/requirements.md R4.2, R4.4
    """
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    thread = seeded_thread(tmp_path, monkeypatch, client, config)

    mirrors, deliveries = [], []
    monkeypatch.setattr(
        "the_loop.comments.post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": mirrors.append(body) or (True, "", ""),
    )
    monkeypatch.setattr(
        core_sessions,
        "reply_session",
        lambda ref, text, actor="", comment=True, config=None: (
            deliveries.append(actor) or {"delivered": True}
        ),
    )

    outcome = inbound.handle_socket_event(
        {
            "type": "message",
            "channel": "C123",
            "thread_ts": thread,
            "ts": "1800.9",
            "user": "UHUMAN",
            "text": "go with A",
        },
        config,
    )
    assert outcome["outcome"] == "processed"
    assert len(mirrors) == 1 and deliveries == ["slack:UHUMAN"]

    stray = inbound.handle_socket_event(
        {
            "type": "message",
            "channel": "C123",
            "thread_ts": "9999.9",
            "ts": "1801.0",
            "user": "UHUMAN",
            "text": "hello?",
        },
        config,
    )
    assert stray["outcome"] == "unmapped"


def test_watcher_fetches_on_interval_and_stops_with_daemon(tmp_path, monkeypatch):
    """Scenario: The channels watcher fetches on its interval and stops with
    its daemon

    Given an enabled Slack channel with read mode poll
    When the watcher is started with a stop event
    Then poll cycles run repeatedly until the event is set
    And with the channel disabled or read mode off, no watcher starts

    Requirement: docs/specs/issue-245/requirements.md R4.1, R4.3
    """
    cycles = []
    monkeypatch.setattr(
        inbound, "poll_once", lambda config, **kwargs: cycles.append(1) or {}
    )
    config = cli_config(tmp_path, read={"mode": "poll", "intervalSeconds": 1})
    stop = threading.Event()
    thread = watcher.start_watcher(config, stop, interval_override=0.01)
    assert thread is not None
    deadline = time.monotonic() + 2.0
    while len(cycles) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    stop.set()
    thread.join(timeout=2.0)
    assert len(cycles) >= 3 and not thread.is_alive()

    assert watcher.start_watcher({"state": {"root": str(tmp_path)}}, stop) is None
    assert (
        watcher.start_watcher(cli_config(tmp_path, read={"mode": "off"}), stop) is None
    )
    assert (
        watcher.start_watcher(cli_config(tmp_path, read={"mode": "socket"}), stop)
        is None
    )


def test_graph_notification_flows_through_the_channels(tmp_path, monkeypatch):
    """Scenario: A graph notification reaches the Slack channel through the
    channels layer

    Given a Slack channel subscribed to phase-approval-pending
    When the graph's notify hook fires for that event
    Then the notification is posted to Slack through the channel filter
    And with no channel subscribed the hook reports a skip, not a failure
    And the old integrations.slack webhook is a named refusal

    Requirement: docs/specs/issue-245/requirements.md R1.1, R2.1 (owner's
    convergence decision on PR #267)
    """
    from the_loop.graph.contract import HookContext, WorkItem
    from the_loop.graph.hooks.sideeffects import notify

    client = FakeSlackClient()
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)

    def ctx(events):
        config = cli_config(tmp_path, subscribe=events)
        config["notifications"] = {"events": {"phase-approval-pending": ["approver"]}}
        return HookContext(
            work_item=WorkItem(id="issue-7", ref="github:o/r#7", spec_dir=tmp_path),
            node={"id": "design"},
            boundary="entry",
            repo=tmp_path,
            config=config,
            params={"event": "phase-approval-pending"},
        )

    subscribed = notify(ctx(["phase-approval-pending"]))
    assert subscribed.status == "pass" and subscribed.data["delivered"] is True
    assert len(client.posted) == 1
    assert "phase-approval-pending" in client.posted[0]["text"]

    unsubscribed = notify(ctx(["session.awaiting_input"]))
    assert unsubscribed.status == "skip"
    assert len(client.posted) == 1  # nothing further posted

    from the_loop.graph.integrations import TransportUnavailable, resolve

    with pytest.raises(TransportUnavailable, match="channels.slack"):
        resolve("slack", {})
