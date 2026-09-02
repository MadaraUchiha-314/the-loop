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
        self.history = []  # top-level messages, for the kickoff read

    def chat_postMessage(self, *, channel, text, thread_ts=None, blocks=None):
        self.posted.append(
            {"channel": channel, "text": text, "thread_ts": thread_ts, "blocks": blocks}
        )
        return {"ok": True, "channel": channel, "ts": f"1700.{len(self.posted):06d}"}

    def conversations_history(self, *, channel, oldest=None, limit=100):
        return {"ok": True, "messages": list(self.history)}

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
    And the same question is posted to Slack as the first reply in the work
      item's thread, whose root names the work item (issue-312)
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
    assert len(client.posted) == 2 and client.posted[0]["thread_ts"] is None
    assert "github:o/r#7" in client.posted[0]["text"]  # the root is the work item's
    assert client.posted[1]["thread_ts"] == "1700.000001"
    assert "A or B?" in client.posted[1]["text"]
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
    assert len(client.posted) == 2  # the work item's root, then the event as a reply
    assert "phase-approval-pending" in client.posted[1]["text"]
    assert client.posted[1]["thread_ts"] == "1700.000001"

    unsubscribed = notify(ctx(["session.awaiting_input"]))
    assert unsubscribed.status == "skip"
    assert len(client.posted) == 2  # nothing further posted

    from the_loop.graph.integrations import TransportUnavailable, resolve

    with pytest.raises(TransportUnavailable, match="channels.slack"):
        resolve("slack", {})


# -- the thread is the work item's (issue-312) ----------------------------------


def _enabled_client(monkeypatch, client=None):
    client = client or FakeSlackClient()
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)
    return client


def test_every_message_about_a_work_item_is_a_reply_in_its_one_thread(
    tmp_path, monkeypatch
):
    """Scenario: Every message about a work item is a reply in its one thread

    Given a Slack channel subscribed to the ask, a notification and the comments
    When the ask, a graph notification and a human comment are published for one
      work item, from different publishers
    Then one thread is opened, its root names the work item
    And every one of the three messages is a reply into it

    Requirement: docs/specs/issue-312/requirements.md R1.1, R1.2, R1.3, R2.1
    """
    from the_loop.channels.base import Event
    from the_loop.channels.bus import publish
    from the_loop.channels.publishers import publish_comment
    from the_loop.channels.state import ChannelState

    client = _enabled_client(monkeypatch)
    config = cli_config(
        tmp_path,
        subscribe=["session.awaiting_input", "phase-approval-pending", "comment.human"],
    )
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (True, "", "https://gh/o/r/issues/7#c1"),
    )
    core_sessions.ask_session("github:o/r#7", "A or B?", config=config)
    publish(
        Event(
            event_type="phase-approval-pending",
            work_item="github:o/r#7",
            text="design.md is ready",
            url="https://github.com/o/r/issues/7",
        ),
        config,
    )
    publish_comment(
        "human", "github:o/r#7", "octocat", "B, please", "https://gh/c/2", config
    )

    assert len(client.posted) == 4
    root, *replies = client.posted
    assert root["thread_ts"] is None
    assert "github:o/r#7" in root["blocks"][0]["text"]["text"]
    assert all(reply["thread_ts"] == "1700.000001" for reply in replies)
    assert "A or B?" in replies[0]["text"]
    assert "design.md is ready" in replies[1]["text"]
    assert "B, please" in replies[2]["text"]
    state = ChannelState.load(tmp_path / "state" / "channels" / "slack.json")
    record = state.conversation("github:o/r#7")
    assert record is not None and record["thread"] == "1700.000001"


def test_two_writers_open_one_thread(tmp_path, monkeypatch):
    """Scenario: Two writers open one thread

    Given no conversation is bound to a work item
    When two writers deliver its first events at the same moment
    Then exactly one root is posted
    And the other writer's event is a reply into it

    Requirement: docs/specs/issue-312/requirements.md R1.4
    """
    from the_loop.channels.base import Event
    from the_loop.channels.slack import SlackBotChannel, SlackChannelConfig

    lock = threading.Lock()

    class Slow(FakeSlackClient):
        """A root post takes long enough for the second writer to arrive."""

        def chat_postMessage(self, *, channel, text, thread_ts=None, blocks=None):
            if thread_ts is None:
                time.sleep(0.2)
            with lock:
                return super().chat_postMessage(
                    channel=channel, text=text, thread_ts=thread_ts, blocks=blocks
                )

    client = _enabled_client(monkeypatch, Slow())
    config = cli_config(tmp_path)
    state_path = tmp_path / "state" / "channels" / "slack.json"
    slack_config = SlackChannelConfig.from_mapping(config)

    def writer(text):
        SlackBotChannel(slack_config, state_path, client_factory=lambda t: client).post(
            Event(
                event_type="session.awaiting_input", work_item="github:o/r#7", text=text
            )
        )

    threads = [threading.Thread(target=writer, args=(f"q{n}",)) for n in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    roots = [p for p in client.posted if p["thread_ts"] is None]
    assert len(roots) == 1
    assert len(client.posted) == 3
    assert {p["thread_ts"] for p in client.posted if p["thread_ts"]} == {"1700.000001"}


def test_a_kickoff_thread_is_the_work_items_conversation(tmp_path, monkeypatch):
    """Scenario: A kickoff thread is the work item's conversation

    Given the work-item.create grant and a kickoff repo
    When an authorized member's top-level message becomes an issue
    Then that thread is recorded as the work item's conversation, origin kickoff
    And the next event for the work item is a reply into it — no root is opened

    Requirement: docs/specs/issue-312/requirements.md R1.5, R3.1
    """
    from the_loop.channels.base import Event
    from the_loop.channels.bus import publish
    from the_loop.channels.state import ChannelState

    client = _enabled_client(monkeypatch)
    config = cli_config(
        tmp_path,
        publish=["work-item.reply", "work-item.create"],
        kickoff={"repo": "o/r", "labels": []},
    )
    monkeypatch.setattr(
        "the_loop.comments.create_issue",
        lambda repo, title, body, labels, gh_binary="gh": (
            True,
            "",
            "github:o/r#42",
            "https://gh/o/r/issues/42",
        ),
    )
    client.history = [{"ts": "1600.1", "user": "UHUMAN", "text": "baseline"}]
    inbound.poll_once(config)
    client.history.append({"ts": "1600.2", "user": "UHUMAN", "text": "Ship it"})
    assert inbound.poll_once(config)["created"] == 1

    state = ChannelState.load(tmp_path / "state" / "channels" / "slack.json")
    record = state.conversation("github:o/r#42")
    assert record is not None
    assert record["thread"] == "1600.2" and record["origin"] == "kickoff"

    publish(
        Event(
            event_type="session.awaiting_input",
            work_item="github:o/r#42",
            text="A or B?",
        ),
        config,
        record=False,
    )
    assert all(p["thread_ts"] == "1600.2" for p in client.posted)


def test_a_pre_issue_312_state_file_keeps_its_threads(tmp_path, monkeypatch):
    """Scenario: A pre-issue-312 state file keeps its threads

    Given a slack.json written by 13.0.1 — threads and cursors, no conversations
    When an event for a bound work item is posted
    Then it is a reply into the thread that file bound — no root is opened
    And the file is rewritten with the conversation keyed by work item

    Requirement: docs/specs/issue-312/requirements.md R3.4
    """
    import json

    from the_loop.channels.base import Event
    from the_loop.channels.bus import publish

    client = _enabled_client(monkeypatch)
    config = cli_config(tmp_path)
    path = tmp_path / "state" / "channels" / "slack.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "threads": {"1500.1": {"workItem": "github:o/r#7", "channel": "C123"}},
                "cursors": {"1500.1": "1500.3"},
            }
        ),
        encoding="utf-8",
    )
    publish(
        Event(event_type="session.awaiting_input", work_item="github:o/r#7", text="?"),
        config,
        record=False,
    )
    assert len(client.posted) == 1 and client.posted[0]["thread_ts"] == "1500.1"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["conversations"]["github:o/r#7"]["thread"] == "1500.1"
    assert raw["cursors"]["1500.1"] == "1500.3"


def test_channels_threads_lists_the_conversation(tmp_path, monkeypatch, capsys):
    """Scenario: channels threads lists the conversation

    Given a work item whose ask opened a thread
    When the operator runs `the-loop channels threads`
    Then the work item, its channel, its thread and how it was opened are listed
    And no token appears

    Requirement: docs/specs/issue-312/requirements.md R3.3
    """
    import argparse
    import json

    from the_loop.commands.channels_cmd import ChannelsCommand

    _enabled_client(monkeypatch)
    config = cli_config(tmp_path)
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (True, "", "https://gh/o/r/issues/7#c1"),
    )
    core_sessions.ask_session("github:o/r#7", "A or B?", config=config)
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    (tmp_path / "cli-config.yaml").write_text(json.dumps(config), encoding="utf-8")
    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    assert ChannelsCommand().run(parser.parse_args(["threads"])) == 0
    out = capsys.readouterr().out
    assert "github:o/r#7" in out and "C123" in out and "1700.000001" in out
    assert "event" in out and "xoxb-test" not in out
