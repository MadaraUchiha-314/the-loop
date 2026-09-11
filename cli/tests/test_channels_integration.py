"""Integration scenarios for channels (issue-245): ask fan-out, the reply
round-trip, Socket Mode convergence, and the daemon watcher.

Every scenario runs through the real modules with only the process boundaries
faked: the Slack SDK client (injected factory), the GitHub comment writer
(monkeypatched), and session delivery (monkeypatched ``reply_session``).
"""

from __future__ import annotations

import json
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
        self.reactions = []  # (channel, ts, name) — issue-325
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

    def reactions_add(self, *, channel, name, timestamp):
        self.reactions.append((channel, timestamp, name))
        return {"ok": True}


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


# -- the start opens the conversation (issue-317) --------------------------------


def _start_setup(tmp_path, monkeypatch, client=None):
    """A real dispatcher (tmux and the harness faked) whose opener runs the real
    bus over the real Slack channel with the SDK client faked."""
    from conftest import FakeTmux, StubInteractiveAdapter
    from the_loop.channels.publishers import conversation_opener
    from the_loop.control import ControlConfig
    from the_loop.sessions import SessionRegistry
    from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig

    client = client or FakeSlackClient()
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)
    config = cli_config(tmp_path)
    registry = SessionRegistry(tmp_path / "local")
    tmux = FakeTmux()
    routing = RoutingConfig(
        registry_dir=str(tmp_path / "local"),
        portable_dir=str(tmp_path / "portable"),
        spawn_on_unmatched="labeled",
        auto_execute_label="the-loop: auto-execute",
        spawn_workdir=str(tmp_path),
        control=ControlConfig(),
        authorized_users=["gh-UHUMAN"],
    )
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=routing,
        tmux_runner=tmux,
        opener=conversation_opener(lambda: config),
    )
    return dispatcher, registry, tmux, client, config


def _start_events(body="the-loop start", labelled=True, author="gh-UHUMAN"):
    from the_loop.webhook.router import RoutedEvent, extract_work_items

    labels = [{"name": "the-loop: auto-execute"}] if labelled else []
    labeled = {
        "action": "labeled",
        "label": {"name": "the-loop: auto-execute"},
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15, "labels": labels},
        "sender": {"login": author},
    }
    comment = {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15, "labels": labels},
        "comment": {
            "id": 1,
            "body": body,
            "html_url": "https://c/1",
            "user": {"login": author},
        },
        "sender": {"login": author},
    }
    return (
        RoutedEvent(
            event="issues",
            action="labeled",
            delivery_id="l-1",
            work_items=extract_work_items("issues", labeled),
            payload=labeled,
            labeled=True,
        ),
        RoutedEvent(
            event="issue_comment",
            action="created",
            delivery_id="d-1",
            work_items=extract_work_items("issue_comment", comment),
            payload=comment,
            labeled=False,
        ),
    )


def _until(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


START_REF = "github:octo/repo#15"


def test_a_start_opens_the_work_items_thread_before_any_event(tmp_path, monkeypatch):
    """Scenario: A start opens the work item's thread before any event

    Given a Slack channel enabled and a labelled work item
    When an authorized user comments the start keyword
    Then the Slack channel carries exactly one message: the root naming the work item
    And the conversation is recorded with origin start
    And when the agent asks a question it is the thread's first reply

    Requirement: docs/specs/issue-317/requirements.md R1.1, R1.2, R1.7, R2.1
    """
    from the_loop.channels.state import ChannelState

    dispatcher, registry, tmux, client, config = _start_setup(tmp_path, monkeypatch)
    labeled, start = _start_events()
    try:
        dispatcher.handle(labeled)
        dispatcher.handle(start)
        assert _until(lambda: len(tmux.spawns) == 1)
    finally:
        dispatcher.stop(timeout=5)
    assert registry.find_by_work_item(START_REF) is not None
    assert len(client.posted) == 1
    root = client.posted[0]
    assert root["thread_ts"] is None and START_REF in root["text"]
    state_path = tmp_path / "state" / "channels" / "slack.json"
    record = ChannelState.load(state_path).conversation(START_REF)
    assert record is not None and record["origin"] == "start"
    assert record["thread"] == "1700.000001"

    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (True, "", "https://gh/c/1"),
    )
    result = core_sessions.ask_session(START_REF, "A or B?", config=config)
    assert result["asked"] is True
    assert len(client.posted) == 2
    assert client.posted[1]["thread_ts"] == "1700.000001"
    assert "A or B?" in client.posted[1]["text"]


def test_a_refused_start_opens_no_thread_scenario(tmp_path, monkeypatch):
    """Scenario: A refused start opens no thread

    Given a Slack channel enabled and a work item that is not armed
    When an authorized user comments the start keyword
    Then no session is spawned and nothing is posted to Slack
    And no conversation is recorded for the work item

    Requirement: docs/specs/issue-317/requirements.md R1.4
    """
    from the_loop.channels.state import ChannelState

    dispatcher, registry, tmux, client, _ = _start_setup(tmp_path, monkeypatch)
    _, start = _start_events(labelled=False)
    try:
        dispatcher.handle(start)
        assert _until(lambda: True, 0.2)
    finally:
        dispatcher.stop(timeout=5)
    assert tmux.spawns == [] and client.posted == []
    state_path = tmp_path / "state" / "channels" / "slack.json"
    assert ChannelState.load(state_path).conversation(START_REF) is None


def test_a_restarted_work_item_keeps_its_thread(tmp_path, monkeypatch):
    """Scenario: A restarted work item keeps its thread

    Given a work item that was started and then stopped
    When an authorized user starts it again
    Then a second session is spawned
    And the Slack channel still carries one root, bound to the same thread

    Requirement: docs/specs/issue-317/requirements.md R1.3
    """
    from the_loop.channels.state import ChannelState

    dispatcher, registry, tmux, client, _ = _start_setup(tmp_path, monkeypatch)
    labeled, start = _start_events()
    from dataclasses import replace

    _, stop = _start_events(body="the-loop stop")
    stop = replace(stop, delivery_id="d-2")
    again = replace(start, delivery_id="d-3")
    try:
        dispatcher.handle(labeled)
        dispatcher.handle(start)
        assert _until(lambda: len(tmux.spawns) == 1)
        dispatcher.handle(stop)
        assert _until(lambda: registry.find_by_work_item(START_REF) is None)
        dispatcher.handle(again)
        assert _until(lambda: len(tmux.spawns) == 2)
    finally:
        dispatcher.stop(timeout=5)
    assert len(client.posted) == 1
    state_path = tmp_path / "state" / "channels" / "slack.json"
    record = ChannelState.load(state_path).conversation(START_REF)
    assert record is not None and record["thread"] == "1700.000001"
    assert record["origin"] == "start"


def test_a_channel_outage_never_fails_the_spawn(tmp_path, monkeypatch):
    """Scenario: A Slack outage never fails the spawn

    Given a Slack channel whose API is down
    When an authorized user starts a labelled work item
    Then the session is spawned as before
    And the failure is recorded as channel.open_failed with ids only
    And no conversation is bound, so the next event opens the thread lazily

    Requirement: docs/specs/issue-317/requirements.md R1.5 (A3)
    """
    from the_loop import eventlog
    from the_loop.channels.state import ChannelState

    class Flaky(FakeSlackClient):
        down = True

        def chat_postMessage(self, **kwargs):
            if self.down:
                raise RuntimeError("slack is down")
            return super().chat_postMessage(**kwargs)

    log = []
    monkeypatch.setattr(
        eventlog, "emit", lambda name, level="info", **f: log.append((name, f))
    )
    client = Flaky()
    dispatcher, registry, tmux, client, config = _start_setup(
        tmp_path, monkeypatch, client=client
    )
    labeled, start = _start_events()
    try:
        dispatcher.handle(labeled)
        dispatcher.handle(start)
        assert _until(lambda: len(tmux.spawns) == 1)
    finally:
        dispatcher.stop(timeout=5)
    assert registry.find_by_work_item(START_REF) is not None
    failed = [f for name, f in log if name == "channel.open_failed"]
    assert len(failed) == 1
    assert failed[0]["channel"] == "slack" and failed[0]["work_item"] == START_REF
    assert "slack is down" in failed[0]["error"]
    state_path = tmp_path / "state" / "channels" / "slack.json"
    assert ChannelState.load(state_path).conversation(START_REF) is None

    client.down = False
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (True, "", "https://gh/c/1"),
    )
    core_sessions.ask_session(START_REF, "A or B?", config=config)
    assert len(client.posted) == 2  # the root, then the ask as its first reply
    record = ChannelState.load(state_path).conversation(START_REF)
    assert record is not None and record["origin"] == "event"


# -- issue-325: the acknowledgment on the Slack message itself ------------------------


def test_an_accepted_reply_is_acknowledged_on_the_reply_itself(tmp_path, monkeypatch):
    """Scenario: An accepted Slack reply is acknowledged on the reply itself

    Given a bound Slack thread for a work item with a waiting session
    When an authorized member replies in the thread and a poll cycle runs
    Then the reply's own message carries the received reaction before the record
    And the completed reaction once the reply is recorded and delivered
    And the ticket record and the session delivery are exactly as before

    Requirement: docs/specs/issue-325/requirements.md R1.1, R1.2, R1.5
    """
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    seeded_thread(tmp_path, monkeypatch, client, config)
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

    summary = inbound.poll_once(config, client_factory=lambda token: client)
    assert summary["processed"] == 1 and summary["delivered"] == 1
    assert len(mirrors) == 1 and deliveries == ["slack:UHUMAN"]
    assert client.reactions == [
        ("C123", "1800.1", "eyes"),
        ("C123", "1800.1", "white_check_mark"),
    ]
    # Cursor semantics are untouched: a second cycle sees nothing, reacts to nothing.
    inbound.poll_once(config, client_factory=lambda token: client)
    assert len(client.reactions) == 2


def test_a_socket_message_and_a_button_press_are_acknowledged(tmp_path, monkeypatch):
    """Scenario: A button press is acknowledged on the message carrying the button

    Given a bound thread on a channel reading over Socket Mode with the gate grant
    When a message event arrives over Socket Mode
    Then the message itself is acknowledged received then completed
    When an authorized member presses Approve on a message in that thread
    Then the message carrying the button is acknowledged, not the press's own ts

    Requirement: docs/specs/issue-325/requirements.md R1.1, R1.2, R1.5
    """
    client = FakeSlackClient()
    config = cli_config(
        tmp_path,
        publish=["work-item.reply", "gate.feedback"],
        read={"mode": "socket"},
    )
    thread = seeded_thread(tmp_path, monkeypatch, client, config)
    monkeypatch.setattr(
        "the_loop.comments.post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (True, "", ""),
    )
    monkeypatch.setattr(
        core_sessions,
        "reply_session",
        lambda ref, text, actor="", comment=True, config=None: {"delivered": True},
    )
    monkeypatch.setattr(inbound, "_at_human_gate", lambda ref, cfg: False)

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
        client_factory=lambda token: client,
    )
    assert outcome["outcome"] == "processed"
    assert client.reactions == [
        ("C123", "1800.9", "eyes"),
        ("C123", "1800.9", "white_check_mark"),
    ]

    client.reactions.clear()
    monkeypatch.setattr(inbound, "_at_human_gate", lambda ref, cfg: True)
    outcome = inbound.handle_socket_action(
        {
            "type": "block_actions",
            "user": {"id": "UHUMAN"},
            "channel": {"id": "C123"},
            "message": {"ts": "1750.5", "thread_ts": thread},
            "container": {"message_ts": "1750.5", "thread_ts": thread},
            "actions": [{"action_id": "the-loop:approve", "value": "approved"}],
            "action_ts": "1900.1",
        },
        config,
        client_factory=lambda token: client,
    )
    assert outcome["outcome"] == "processed" and outcome["event"] == "gate.feedback"
    assert client.reactions == [
        ("C123", "1750.5", "eyes"),
        ("C123", "1750.5", "white_check_mark"),
    ]


def test_a_slack_that_refuses_the_reaction_never_fails_the_delivery(
    tmp_path, monkeypatch
):
    """Scenario: A Slack that refuses the reaction never fails the delivery

    Given a bound thread and a bot token without the reactions:write scope
    When an authorized reply arrives and a poll cycle runs
    Then the reply is recorded and delivered exactly as before
    And each refused reaction is one channel.reaction_failed event

    Requirement: docs/specs/issue-325/requirements.md R3.1
    """
    from the_loop import eventlog

    class Scopeless(FakeSlackClient):
        def reactions_add(self, *, channel, name, timestamp):
            raise RuntimeError("The request to the Slack API failed: missing_scope")

    client = Scopeless()
    config = cli_config(tmp_path)
    seeded_thread(tmp_path, monkeypatch, client, config)
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
    log = tmp_path / "events.jsonl"
    eventlog.configure("test", path=log, enabled=True)
    try:
        summary = inbound.poll_once(config, client_factory=lambda token: client)
    finally:
        eventlog.reset()
    assert summary["processed"] == 1 and summary["delivered"] == 1
    assert len(mirrors) == 1 and deliveries == ["slack:UHUMAN"]
    failed = [
        json.loads(line)
        for line in log.read_text().splitlines()
        if '"channel.reaction_failed"' in line
    ]
    assert [e["state"] for e in failed] == ["received", "completed"]


# -- the /the-loop slash command (issue-334) ------------------------------------------


def _slash(text, user="UHUMAN", trigger="t-1"):
    return {
        "command": "/the-loop",
        "text": text,
        "user_id": user,
        "channel_id": "C123",
        "trigger_id": trigger,
        "response_url": "https://hooks.slack.com/commands/T/1/x",
    }


def _all_grants(tmp_path, **slack):
    return cli_config(
        tmp_path,
        read={"mode": "socket"},
        kickoff={"repo": "o/r"},
        publish=[
            "work-item.reply",
            "control.command",
            "instance.command",
            "standing.command",
        ],
        **slack,
    )


def test_a_slash_command_start_records_what_a_thread_keyword_records(
    tmp_path, monkeypatch
):
    """Scenario: A slash command start records what a thread keyword records

    Given an authorized member and a channel granted control.command
    When they run `/the-loop start #7` and, separately, type `the-loop start`
         in the work item's bound thread
    Then both land on the ledger as an unmarked comment carrying the keyword
         intact and an envelope naming the person
    And the ledger's own parser reads both as `start`
    And the slash command delivers nothing into any session itself

    Requirement: docs/specs/issue-334/requirements.md R1.1, R1.2, R3.3
    """
    from the_loop.channels import commands
    from the_loop.channels.envelope import parse as parse_envelope
    from the_loop.control import ControlConfig, parse_command

    commands.reset_seen()
    config = _all_grants(tmp_path)
    client = FakeSlackClient()
    thread = seeded_thread(tmp_path, monkeypatch, client, config)

    records, deliveries, answers = [], [], []
    monkeypatch.setattr(
        "the_loop.comments.post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (
            records.append((item.ref, body)) or (True, "", "https://x/c1")
        ),
    )
    monkeypatch.setattr(
        core_sessions,
        "reply_session",
        lambda ref, text, actor="", comment=True, config=None: (
            deliveries.append(actor) or {"delivered": True}
        ),
    )

    outcome = commands.handle_slash_command(
        _slash("start #7"),
        config,
        respond=lambda url, text: answers.append((url, text)) or True,
    )
    assert outcome["outcome"] == "recorded" and outcome["workItem"] == "github:o/r#7"
    typed = inbound.handle_socket_event(
        {
            "type": "message",
            "channel": "C123",
            "thread_ts": thread,
            "ts": "1800.1",
            "user": "UHUMAN",
            "text": "the-loop start",
        },
        config,
        client_factory=lambda token: client,
    )
    assert typed["outcome"] == "processed" and typed["event"] == "control.command"

    assert len(records) == 2 and deliveries == []
    for ref, body in records:
        assert ref == "github:o/r#7"
        assert not is_self_authored(body)
        assert parse_command(body, ControlConfig()).command == "start"
        envelope = parse_envelope(body)
        assert envelope is not None and envelope.type == "control.command"
        assert envelope.source == "slack"
        assert envelope.actor == {"github": "gh-UHUMAN", "slack": "UHUMAN"}
    assert answers[0][0].startswith("https://hooks.slack.com/")
    assert "https://x/c1" in answers[0][1]


def test_a_slash_command_status_answers_from_the_facade(tmp_path, monkeypatch):
    """Scenario: A slash command status answers from the facade

    Given an authorized member and a channel granted instance.command
    When they run `/the-loop status`
    Then the answer is rendered from core.lifecycle.status_all's document
    And it is posted ephemerally through the command's response_url

    Requirement: docs/specs/issue-334/requirements.md R2.1, R3.5
    """
    from the_loop.channels import commands
    from the_loop.core import lifecycle

    commands.reset_seen()
    monkeypatch.setattr(
        lifecycle,
        "status_all",
        lambda config=None, config_path=None: {
            "instance": {"name": "laptop-b", "scope": {"mode": "open"}},
            "services": [
                {"service": "service", "enabled": True, "running": False, "pid": 0}
            ],
            "standingSessions": [],
            "ok": False,
        },
    )
    sent = []
    monkeypatch.setattr(
        commands, "_send_webhook", lambda url, text: sent.append((url, text)) or True
    )
    outcome = commands.handle_slash_command(_slash("status"), _all_grants(tmp_path))
    assert outcome == {
        "outcome": "ok",
        "family": "instance",
        "verb": "status",
        "answered": True,
    }
    assert sent[0][0] == "https://hooks.slack.com/commands/T/1/x"
    assert "laptop-b" in sent[0][1] and "service: stopped (enabled)" in sent[0][1]


def test_a_slash_command_starts_a_standing_session(tmp_path, monkeypatch):
    """Scenario: A slash command starts a standing session

    Given an authorized member and a channel granted standing.command
    When they run `/the-loop standing start supervisor`
    Then core.standing.control_standing is called with that name and verb
    And the member is told the outcome

    Requirement: docs/specs/issue-334/requirements.md R2.2, R3.5
    """
    from the_loop.channels import commands
    from the_loop.core import standing

    commands.reset_seen()
    calls = []
    monkeypatch.setattr(
        standing,
        "control_standing",
        lambda name, verb, config=None, registry_dir="": (
            calls.append((name, verb))
            or {"sessions": [{"name": name, "outcome": "started", "detail": "up"}]}
        ),
    )
    answers = []
    outcome = commands.handle_slash_command(
        _slash("standing start supervisor"),
        _all_grants(tmp_path),
        respond=lambda url, text: answers.append(text) or True,
    )
    assert outcome["outcome"] == "ok" and outcome["standing"] == "supervisor"
    assert calls == [("supervisor", "start")]
    assert "supervisor: started" in answers[0]


def test_an_unlisted_members_slash_command_leaves_nothing(tmp_path, monkeypatch):
    """Scenario: An unlisted member's slash command leaves nothing

    Given a channel granted every command family
    When a member outside routing.authorizedUsers runs `/the-loop restart`
    Then nothing is scheduled, nothing is recorded and nothing is answered

    Requirement: docs/specs/issue-334/requirements.md R3.1
    """
    from the_loop.channels import commands
    from the_loop.core import lifecycle

    commands.reset_seen()
    monkeypatch.setattr(
        lifecycle,
        "schedule_restart",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    monkeypatch.setattr(
        commands,
        "_send_webhook",
        lambda url, text: (_ for _ in ()).throw(AssertionError("must not answer")),
    )
    outcome = commands.handle_slash_command(
        _slash("restart", user="UEVIL"), _all_grants(tmp_path)
    )
    assert outcome == {"outcome": "unauthorized-actor"}


def test_a_socket_listener_catches_up_after_downtime(tmp_path, monkeypatch):
    """Scenario: A Socket Mode listener catches up on what was posted while down

    Given a socket-mode channel with a bound thread
    And a member replied in it while no listener was connected
    When the listener connects and runs its catch-up read
    Then the reply is mirrored and delivered exactly once
    And Slack's later retry of the same message is dropped as a duplicate
    And a second catch-up processes nothing

    Requirement: docs/specs/issue-334/requirements.md R2.6
    """
    from the_loop.channels import slack as slack_mod

    client = FakeSlackClient()
    config = cli_config(tmp_path, read={"mode": "socket"})
    thread = seeded_thread(tmp_path, monkeypatch, client, config)  # the reply: 1800.1
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)

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

    summary = slack_mod.catch_up(config)
    assert summary["processed"] == 1 and summary["delivered"] == 1
    assert len(mirrors) == 1 and deliveries == ["slack:UHUMAN"]

    retried = inbound.handle_socket_event(
        {
            "type": "message",
            "channel": "C123",
            "thread_ts": thread,
            "ts": "1800.1",
            "user": "UHUMAN",
            "text": "go with A",
        },
        config,
        client_factory=lambda token: client,
    )
    assert retried["outcome"] == "duplicate"
    assert len(mirrors) == 1 and len(deliveries) == 1

    again = slack_mod.catch_up(config)
    assert again["processed"] == 0
    assert len(mirrors) == 1 and len(deliveries) == 1


# -- issue-337: command buttons, the outcome on the message ------------------------


class UpdatingSlackClient(FakeSlackClient):
    """The fake plus ``chat_update`` (issue-337)."""

    def __init__(self, refuse_update=""):
        super().__init__()
        self.updates = []
        self.refuse_update = refuse_update

    def chat_update(self, *, channel, ts, text, blocks=None):
        if self.refuse_update:
            raise RuntimeError(
                f"The request to the Slack API failed: {self.refuse_update}"
            )
        self.updates.append(
            {"channel": channel, "ts": ts, "text": text, "blocks": blocks}
        )
        return {"ok": True, "channel": channel, "ts": ts}


def _button_ids(blocks):
    return [
        element["action_id"]
        for block in blocks or []
        if block.get("type") == "actions"
        for element in block["elements"]
    ]


def _press(message, action_id, value, author="UHUMAN"):
    return {
        "type": "block_actions",
        "user": {"id": author},
        "channel": {"id": message["channel"]},
        "message": {
            "ts": message["ts"],
            "thread_ts": message["thread_ts"],
            "text": message["text"],
            "blocks": message["blocks"],
        },
        "container": {"message_ts": message["ts"], "thread_ts": message["thread_ts"]},
        "actions": [{"action_id": action_id, "value": value}],
        "action_ts": "1900.1",
    }


def _checklist_through_the_channel(client, config):
    """The phase-selection checklist as the ledger's ingress mirrors it — a
    `comment.agent` carrying the hook's marker — posted into the work item's thread."""
    from the_loop.channels.publishers import publish_comment
    from the_loop.graph.hooks.selection import SELECTION_MARKER

    publish_comment(
        "agent",
        "github:o/r#7",
        "the-operator",
        "🤖 _the-loop_ — **which phases does this work item need?**\n\n"
        "- [x] brainstorming\n- [x] design\n\n" + SELECTION_MARKER,
        "https://github.com/o/r/issues/7#c1",
        config,
    )
    posted = client.posted[-1]
    return {**posted, "ts": f"1700.{len(client.posted):06d}"}


def test_an_execute_press_records_what_a_typed_execute_records(tmp_path, monkeypatch):
    """Scenario: An Execute press records what a typed the-loop execute records, and the message says so

    Given a channel over Socket Mode granted control.command, subscribed to comment.agent
    When the phase-selection checklist is mirrored into the work item's thread
    Then the message carries an Execute button whose value is the configured keyword
    When an authorized member presses it
    Then the ledger holds an unmarked comment the ingress's parser reads as `execute`,
         with an envelope naming the person — the same record a typed keyword makes
    And the Slack code delivers nothing into any session itself
    And the pressed message is edited: the Execute button gone, the link kept, a line
         naming the button, the member and the record's link
    And the message still carries the issue-325 reactions

    Requirement: docs/specs/issue-337/requirements.md R1.1, R1.3, R2.1, R2.2, R2.5
    """
    from the_loop.channels.envelope import parse as parse_envelope
    from the_loop.control import ControlConfig, parse_command

    client = UpdatingSlackClient()
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)
    config = cli_config(
        tmp_path,
        read={"mode": "socket"},
        subscribe=["comment.agent"],
        publish=["work-item.reply", "control.command"],
    )
    records, deliveries = [], []
    monkeypatch.setattr(
        "the_loop.comments.post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (
            records.append((item.ref, body)) or (True, "", "https://x/c9")
        ),
    )
    monkeypatch.setattr(
        core_sessions,
        "reply_session",
        lambda ref, text, actor="", comment=True, config=None: (
            deliveries.append(text) or {"delivered": True}
        ),
    )
    monkeypatch.setattr(inbound, "_at_human_gate", lambda ref, cfg: False)

    message = _checklist_through_the_channel(client, config)
    assert _button_ids(message["blocks"]) == [
        "the-loop:open",
        "the-loop:command:execute",
    ]
    button = message["blocks"][-1]["elements"][1]
    assert button["value"] == "the-loop execute"

    outcome = inbound.handle_socket_action(
        _press(message, button["action_id"], button["value"]),
        config,
        client_factory=lambda token: client,
    )
    assert outcome["outcome"] == "processed" and outcome["event"] == "control.command"
    assert deliveries == []
    assert len(records) == 1
    ref, body = records[0]
    assert ref == "github:o/r#7" and not is_self_authored(body)
    assert parse_command(body, ControlConfig()).command == "execute"
    envelope = parse_envelope(body)
    assert envelope is not None and envelope.type == "control.command"
    assert envelope.actor == {"github": "gh-UHUMAN", "slack": "UHUMAN"}

    assert len(client.updates) == 1
    edit = client.updates[0]
    assert edit["ts"] == message["ts"] and edit["channel"] == "C123"
    assert _button_ids(edit["blocks"]) == ["the-loop:open"]
    line = edit["blocks"][-1]["elements"][0]["text"]
    assert line.startswith("✅ *Execute*") and "<@UHUMAN>" in line
    assert "<https://x/c9|github:o/r#7>" in line
    assert [name for _, ts, name in client.reactions if ts == message["ts"]] == [
        "eyes",
        "white_check_mark",
    ]


def test_a_kickoff_reply_carries_start_and_its_press_records_the_keyword(
    tmp_path, monkeypatch
):
    """Scenario: A kickoff reply carries Start and its press records the start keyword

    Given the work-item.create and control.command grants over Socket Mode
    When an authorized member's top-level message becomes an issue
    Then the-loop's reply in that thread carries a Start button with the configured keyword
    When the member presses it
    Then the ledger holds an unmarked `the-loop start` on the new issue
    And the reply is edited to say so, its Start button gone

    Requirement: docs/specs/issue-337/requirements.md R1.2, R1.3, R2.1
    """
    from the_loop.control import ControlConfig, parse_command

    client = UpdatingSlackClient()
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)
    config = cli_config(
        tmp_path,
        read={"mode": "socket"},
        publish=["work-item.reply", "work-item.create", "control.command"],
        kickoff={"repo": "o/r", "labels": []},
    )
    records = []
    monkeypatch.setattr(
        "the_loop.comments.create_issue",
        lambda repo, title, body, labels, gh_binary="gh": (
            True,
            "",
            "github:o/r#42",
            "https://gh/o/r/issues/42",
        ),
    )
    monkeypatch.setattr(
        "the_loop.comments.post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (
            records.append((item.ref, body)) or (True, "", "https://x/c1")
        ),
    )
    monkeypatch.setattr(inbound, "_at_human_gate", lambda ref, cfg: False)

    outcome = inbound.handle_socket_event(
        {
            "type": "message",
            "channel": "C123",
            "ts": "1600.2",
            "user": "UHUMAN",
            "text": "Ship it",
        },
        config,
        client_factory=lambda token: client,
    )
    assert outcome["outcome"] == "created"
    reply = client.posted[-1]
    assert reply["thread_ts"] == "1600.2" and "github:o/r#42" in reply["text"]
    assert _button_ids(reply["blocks"]) == ["the-loop:command:start"]
    button = reply["blocks"][-1]["elements"][0]
    assert button["value"] == "the-loop start" and button["text"]["text"] == "Start"

    message = {**reply, "ts": f"1700.{len(client.posted):06d}"}
    pressed = inbound.handle_socket_action(
        _press(message, button["action_id"], button["value"]),
        config,
        client_factory=lambda token: client,
    )
    assert pressed["outcome"] == "processed" and pressed["event"] == "control.command"
    assert len(records) == 1 and records[0][0] == "github:o/r#42"
    assert parse_command(records[0][1], ControlConfig()).command == "start"
    assert not is_self_authored(records[0][1])
    edit = client.updates[0]
    assert edit["ts"] == message["ts"] and _button_ids(edit["blocks"]) == []
    assert edit["blocks"][-1]["elements"][0]["text"].startswith("✅ *Start*")


def test_an_unlisted_members_press_leaves_the_message_untouched(tmp_path, monkeypatch):
    """Scenario: An unlisted member's press edits nothing

    Given a message carrying an Execute button
    When a member outside routing.authorizedUsers presses it
    Then nothing is recorded, delivered, reacted to or edited — a refusal leaves no mark

    Requirement: docs/specs/issue-337/requirements.md R1.3, R2.3 (A1)
    """
    client = UpdatingSlackClient()
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)
    config = cli_config(
        tmp_path,
        read={"mode": "socket"},
        subscribe=["comment.agent"],
        publish=["work-item.reply", "control.command"],
    )
    records = []
    monkeypatch.setattr(
        "the_loop.comments.post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": records.append(body) or (True, "", ""),
    )
    message = _checklist_through_the_channel(client, config)
    outcome = inbound.handle_socket_action(
        _press(message, "the-loop:command:execute", "the-loop execute", author="UEVIL"),
        config,
        client_factory=lambda token: client,
    )
    assert outcome == {"outcome": "unauthorized-actor"}
    assert records == [] and client.updates == [] and client.reactions == []


def test_a_press_whose_record_was_refused_keeps_its_button(tmp_path, monkeypatch):
    """Scenario: A press whose record the ledger refused keeps its button and says why

    Given a message carrying an Execute button and a ledger that refuses the comment
    When an authorized member presses it
    Then the press is processed but not recorded, marked ⚠️
    And the message is edited to say it was not recorded, with the ledger's error,
         and the Execute button stays so the member can press again

    Requirement: docs/specs/issue-337/requirements.md R2.2, R2.3
    """
    client = UpdatingSlackClient()
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)
    config = cli_config(
        tmp_path,
        read={"mode": "socket"},
        subscribe=["comment.agent"],
        publish=["work-item.reply", "control.command"],
    )
    monkeypatch.setattr(
        "the_loop.comments.post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (False, "gh exited 1: rate limited", ""),
    )
    monkeypatch.setattr(inbound, "_at_human_gate", lambda ref, cfg: False)
    message = _checklist_through_the_channel(client, config)
    outcome = inbound.handle_socket_action(
        _press(message, "the-loop:command:execute", "the-loop execute"),
        config,
        client_factory=lambda token: client,
    )
    assert outcome["outcome"] == "processed" and outcome["mirrored"] is False
    edit = client.updates[0]
    assert _button_ids(edit["blocks"]) == ["the-loop:open", "the-loop:command:execute"]
    line = edit["blocks"][-1]["elements"][0]["text"]
    assert line.startswith("⚠️ *Execute*") and "not recorded: gh exited 1" in line
    assert [name for _, ts, name in client.reactions if ts == message["ts"]] == [
        "eyes",
        "warning",
    ]


# -- long text is digested, never truncated (issue-338) ---------------------------


def _long_agent_comment():
    from test_channels_digest import REPORT

    return REPORT


def test_a_long_agent_comment_reaches_slack_as_a_digest(tmp_path, monkeypatch):
    """Scenario: A long agent comment reaches Slack as a digest that leads with
    the ask

    Given a Slack channel subscribed to comment.agent with maxChars 600
    When the ledger's ingress publishes an agent comment longer than that,
      carrying a code fence, a traceback, a table and absolute paths, and
      ending with a question
    Then the Slack section opens with that question in bold
    And carries no fence, no traceback, no table and no /home path — pointers
      instead — within maxChars, and closes with the link to the full comment
    And the phone's notification text (the fallback) leads with the same ask
    And nothing was written to the ledger — a mirror is never re-recorded

    Requirement: docs/specs/issue-338/requirements.md R1.1, R1.3, R1.5, R2.1, R3.1, R3.2
    """
    from the_loop.channels.publishers import publish_comment

    client = _enabled_client(monkeypatch)
    config = cli_config(tmp_path, subscribe=["comment.agent"], maxChars=600)
    records = []
    monkeypatch.setattr(
        "the_loop.comments.post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": records.append(body) or (True, "", ""),
    )

    publish_comment(
        "agent",
        "github:o/r#338",
        "the-loop",
        _long_agent_comment(),
        "https://gh/o/r/issues/338#c9",
        config,
    )

    assert records == []
    reply = client.posted[-1]
    section = reply["blocks"][1]["text"]["text"]
    assert section.startswith("*Which one should I take?*")
    assert len(section) <= 600
    for gone in ("```", "Traceback", "| case |", "/home/user"):
        assert gone not in section
    assert "_⟨code: 2 lines⟩_" in section
    assert section.rstrip().endswith(
        "_… full text: <https://gh/o/r/issues/338#c9|GitHub>_"
    )
    assert "*Which one should I take?*" in reply["text"]
    assert reply["blocks"][-1]["elements"][0]["url"] == "https://gh/o/r/issues/338#c9"


def test_a_short_comment_reaches_slack_untouched(tmp_path, monkeypatch):
    """Scenario: A short comment reaches Slack untouched

    Given a Slack channel subscribed to comment.human
    When a collaborator's two-line comment is published
    Then the Slack section is that comment, whole and in order, with no pointer
      and no closing line — only the-loop's own marker drawn away
    And the fallback text is what 13.10.0 sent

    Requirement: docs/specs/issue-338/requirements.md R4.1, R3.3
    """
    from the_loop.channels.publishers import publish_comment

    client = _enabled_client(monkeypatch)
    config = cli_config(tmp_path, subscribe=["comment.human"])
    body = "Go with B.\nThe cap stays at 1500 — see `docs/guide/slack.md`."

    publish_comment("human", "github:o/r#338", "octocat", body, "https://gh/c", config)

    reply = client.posted[-1]
    assert reply["blocks"][1]["text"]["text"] == body
    assert "full text" not in reply["blocks"][1]["text"]["text"]
    assert reply["text"].endswith("\n\n" + body)


def test_a_notifications_artifact_excerpt_is_digested_too(tmp_path, monkeypatch):
    """Scenario: A notification's artifact excerpt is digested too

    Given a Slack channel subscribed to phase-approval-pending with maxChars 500
    And a work item whose requirements.md is longer than that
    When the graph's notify hook fires for the requirements approval
    Then the message's excerpt section is a digest within maxChars that closes
      with the work item's link, and the short notification text is untouched

    Requirement: docs/specs/issue-338/requirements.md R1.1, R4.1
    """
    from the_loop.graph.contract import HookContext, WorkItem
    from the_loop.graph.hooks.sideeffects import notify

    client = _enabled_client(monkeypatch)
    spec_dir = tmp_path / "specs" / "issue-338"
    spec_dir.mkdir(parents=True)
    (spec_dir / "requirements.md").write_text(
        "---\ntype: requirements\n---\n# Requirements: the digest\n\n"
        "## Introduction\n\nIs this the shape you want?\n\n"
        + "\n\n".join(
            f"Paragraph {n} says something about requirement {n}." for n in range(60)
        ),
        encoding="utf-8",
    )
    config = cli_config(tmp_path, subscribe=["phase-approval-pending"], maxChars=500)
    ctx = HookContext(
        work_item=WorkItem(id="issue-338", ref="github:o/r#338", spec_dir=spec_dir),
        node={"id": "requirements-approval"},
        boundary="entry",
        repo=tmp_path,
        config=config,
        params={"event": "phase-approval-pending", "artifact": "requirements.md"},
    )

    assert notify(ctx).status == "pass"
    reply = client.posted[-1]
    text_section, excerpt_section = reply["blocks"][1], reply["blocks"][2]
    assert "requirements-approval" in text_section["text"]["text"]
    excerpt = excerpt_section["text"]["text"]
    assert excerpt.startswith("*Is this the shape you want?*")
    assert len(excerpt) <= 500
    assert excerpt.rstrip().endswith(
        "_… full text: <https://github.com/o/r/issues/338|GitHub>_"
    )
