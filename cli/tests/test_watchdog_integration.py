"""The watcher notices an idle session (issue-551, Requirement 4).

The real cycle over the real event log, the real session registry and the real
derivation, all under ``tmp_path``. The clock is the test's, the tmux pane is
the recording double, and the channels are a recording ledger and a Slack
channel over a recording client, reached through the real bus. Every cycle is
built from the log and the registry alone, so a second one is a restart.

Feature: A watchdog notices an idle session
Requirement: docs/specs/issue-551/requirements.md
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from conftest import StubInteractiveAdapter
from the_loop import eventlog
from the_loop.api.lifespan import build_lifespan
from the_loop.authz import SELF_COMMENT_MARKER
from the_loop.channels import bus
from the_loop.channels.github import GitHubLedger
from the_loop.control import ControlConfig
from the_loop.core import stopcheck, watchdog
from the_loop.watchconfig import WatchdogConfig
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import Router
from test_channels import FakeSlackClient, cli_config
from test_channels_declared_integration import channel_for, declare
from the_loop.channels.slack import DEFAULT_BOT_TOKEN_ENV
from watchdog_world import REF, TARGET, WATCHDOG, World

OFF = WatchdogConfig(enabled=False, idle_seconds=600, max_nudges=2)
ROOM = "C0TMP551"


def slack(world, tmp_path, monkeypatch, room=True):
    """The real Slack channel over a recording client, on the watcher's bus.
    ``room`` declares a room for the work item; without it the conversation is
    the work item's thread in the central channel."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    config = cli_config(tmp_path)
    if room:
        declare(config, work_item=REF, target=ROOM)
    client = FakeSlackClient()
    world.channels.append(channel_for(config, client))
    return client


class RecordingChannel:
    """A subscriber that takes every event, as a channel on the bus does."""

    name = "recording"

    def __init__(self):
        self.events = []

    def subscribes(self, event_type):
        return True

    def may_publish(self, event_type):
        return False

    def post(self, event):
        from the_loop.channels.base import PostResult

        self.events.append(event)
        return PostResult(channel=self.name, ok=True)


@pytest.fixture()
def world(tmp_path, monkeypatch):
    world = World(tmp_path, monkeypatch)
    world.comments = []
    world.channel = RecordingChannel()

    def post_comment(item, body, api=None):
        world.comments.append(body)
        number = len(world.comments)
        return True, "", f"https://github.com/octo/repo/issues/7#issuecomment-{number}"

    ledger = GitHubLedger({}, post_comment=post_comment)
    world.channels = [world.channel]
    world.publish = lambda event, record=None: bus.publish(
        event, channels=world.channels, ledger=ledger, record=record
    )
    yield world
    eventlog.reset()


def cycle(world, minutes, config=WATCHDOG):
    """One tick of a brand-new watcher at ``minutes``, through the real bus."""
    world.cycle(minutes, watchdog_config=config)


def idle(world):
    world.register()
    world.started(-1)
    world.ended(0)


def test_an_idle_session_is_nudged_then_a_person_is_told_once(world):
    """
    Feature: A watchdog notices an idle session
    Scenario: an idle session is nudged, then a person is told once
      Given a daemon-driven session whose turn ended on an agent-owned node with work owed
      When the idle threshold passes
      Then one nudge is pasted that names the node, its command and the three ways out
      And the stall is recorded
      When the session is still idle one threshold later
      Then it is nudged a second time
      When the nudge limit is reached and it is still idle
      Then one notice is published, naming the node and how long the session has been idle
      And one comment is written on the work item, marked as the-loop's own
      And nothing more is pasted or published however long it stays idle

    Requirement: docs/specs/issue-551/requirements.md#R4.1 R4.2 R4.3 R4.4
    """
    idle(world)

    cycle(world, 9)
    assert world.pasted() == []

    cycle(world, 10)
    (first,) = world.pasted()
    assert "idle for 10 minutes at node `build`" in first
    assert "/the-loop:execute-tasks issue-7" in first
    assert "Continue the work in this turn" in first
    assert f"the-loop ask --work-item {REF}" in first
    assert f"the-loop wait --work-item {REF}" in first
    (nudged,) = world.records("session.nudged")
    assert nudged["stall_id"] == f"{REF}@{world.stamp(0)}"

    cycle(world, 15)
    assert len(world.pasted()) == 1
    cycle(world, 20)
    assert len(world.pasted()) == 2
    assert [r["nudge"] for r in world.records("session.nudged")] == [1, 2]
    assert world.channel.events == []

    cycle(world, 30)
    (notice,) = world.channel.events
    assert notice.event_type == "session.stalled" and notice.work_item == REF
    assert notice.detail["node"] == "build"
    (comment,) = world.comments
    assert "**the session is idle**" in comment
    assert "stopped at `build` 30 minutes ago with work still to do" in comment
    assert "nudged it twice and it did not resume" in comment
    assert comment.count(SELF_COMMENT_MARKER) == 1
    (stalled,) = world.records("session.stalled")
    assert stalled["stall_id"] == nudged["stall_id"]
    assert (stalled["node"], stalled["idle_since"]) == ("build", world.stamp(0))

    for minutes in (40, 50, 60, 600, 6000):
        cycle(world, minutes)
    assert len(world.pasted()) == 2
    assert len(world.channel.events) == 1 and len(world.comments) == 1


def test_a_restart_repeats_no_nudge_and_no_notice(world):
    """
    Feature: A watchdog notices an idle session
    Scenario: a restart repeats no nudge and no notice
      Given an idle session that was nudged once
      When the daemon restarts and a new watcher runs at the same moment
      Then no second nudge is pasted
      Given the nudges are spent and the notice was published
      When the daemon restarts again
      Then no second notice is published
      And the second nudge and the notice each fired once, at their recorded time

    Requirement: docs/specs/issue-551/requirements.md#R4.10
    """
    idle(world)
    cycle(world, 10)
    cycle(world, 10)
    cycle(world, 10.5)
    assert len(world.pasted()) == 1

    cycle(world, 20)
    cycle(world, 20)
    assert len(world.pasted()) == 2

    cycle(world, 30)
    cycle(world, 30)
    cycle(world, 31)
    assert len(world.pasted()) == 2
    assert len(world.channel.events) == 1
    assert len(world.records("session.stalled")) == 1
    assert len(world.records("session.nudged")) == 2


def test_a_stall_ends_when_the_session_takes_a_turn_and_the_notice_is_edited(
    world, tmp_path, monkeypatch
):
    """
    Feature: A watchdog notices an idle session
    Scenario: a stall ends when the session takes a turn, and the notice is edited
      Given a stalled session whose notice was published
      When a comment reaches the session but it takes no turn
      Then the stall is not ended
      When the session starts a turn
      Then session.stall_ended is recorded once, with how long the stall lasted
      And it is published so the channels resolve the notice they remember
      And the Slack notice is edited in place to its resolved form, with no new message
      And the status reaction returns from 🛑 to ⚙️
      And the session is working, so it leaves the attention list by itself

    Requirement: docs/specs/issue-551/requirements.md#R4.5 R4.9 R7.5
    """
    from the_loop.core import sessionstate
    from watchdog_world import ASKS

    client = slack(world, tmp_path, monkeypatch)
    idle(world)
    for minutes in (10, 20, 30):
        cycle(world, minutes)
    assert [e.event_type for e in world.channel.events] == ["session.stalled"]
    posted = len(client.posted)
    notice_ts = f"1700.{posted:06d}"
    assert "is idle" in client.posted[-1]["text"]
    assert client.reactions[-1] == (ROOM, notice_ts, "octagonal_sign")

    # R4.9: an event that reached the pane is not a turn of the session.
    world.emit(33, "dispatch.succeeded", via="tmux")
    cycle(world, 34)
    assert world.records("session.stall_ended") == []

    world.started(36)
    cycle(world, 36.5)
    cycle(world, 37)

    (ended,) = world.records("session.stall_ended")
    assert ended["stall_id"] == f"{REF}@{world.stamp(0)}"
    assert ended["idle_seconds"] == 36 * 60
    assert [e.event_type for e in world.channel.events] == [
        "session.stalled",
        "session.stall_ended",
    ]
    resolved = world.channel.events[-1]
    assert resolved.detail["stall_id"] == ended["stall_id"]
    assert resolved.detail["notified"] == "true"
    assert "after 36 min idle" in resolved.summary
    assert "(36 minutes)" in world.comments[-1]

    assert len(client.posted) == posted
    ((channel, edited, text, _blocks),) = client.updates
    assert (channel, edited) == (ROOM, notice_ts)
    assert text == (
        "✅ ~#7 is idle at `build`~ — working again since 12:36 UTC, after 36 min idle."
    )
    assert client.reactions[-1] == (ROOM, notice_ts, "gear")

    state = sessionstate.derive(
        sessionstate.load(world.log)[REF],
        now=world.now(),
        watchdog=WATCHDOG,
        asks=ASKS,
        work_item=REF,
    )
    assert state.state == "working" and state.due == ()


def test_a_switched_off_watchdog_sends_nothing_and_the_gate_still_holds(
    world, tmp_path, monkeypatch
):
    """
    Feature: A watchdog notices an idle session
    Scenario: a switched-off watchdog sends nothing and the gate still holds
      Given routing.watchdog.enabled is false
      And a session idle on an agent-owned node for hours
      When the watcher runs
      Then no nudge is pasted and no notice is published
      When that session tries to end a turn with work owed
      Then the stop check still refuses it

    Requirement: docs/specs/issue-551/requirements.md#R4.12
    """
    idle(world)
    for minutes in (10, 20, 30, 300):
        cycle(world, minutes, OFF)
    assert world.pasted() == []
    assert world.channel.events == [] and world.comments == []
    assert not world.records("session.nudged") + world.records("session.stalled")

    config = {
        "state": {"root": str(tmp_path / ".the-loop")},
        "eventLog": {"path": str(world.log)},
        "routing": {
            "registryDir": str(tmp_path / "sessions"),
            "watchdog": {"enabled": False},
        },
    }
    report = {
        "pointer": "build",
        "nodes": [{"node": "build", "status": "block", "messages": ["tests fail"]}],
    }
    nodes = {"build": {"actor": "agent", "command": "execute-tasks", "terminal": False}}
    monkeypatch.setattr(stopcheck, "_standing", lambda session, item: (report, nodes))

    answer = stopcheck.stop_check(REF, config=config)

    assert answer["verdict"] == "refuse" and answer["node"] == "build"
    assert "do not end this turn" in answer["text"]


@pytest.mark.parametrize("room", [True, False])
def test_the_stall_notice_is_a_short_form_in_the_work_items_conversation(
    world, tmp_path, monkeypatch, room
):
    """
    Feature: Status says what is really happening
    Scenario: the stall notice is a short form in the work item's conversation
      Given a work item whose Slack conversation is a declared room, or its thread in the central channel
      And a session that stayed idle after its nudges
      When the watcher publishes the stall
      Then Slack gets exactly one message for it, in that conversation
      And the message is the short form: the state in words, the node, how long, who must act
      And its text fallback is that same short form
      And no long form follows it
      And the work item's status reaction is 🛑

    Requirement: docs/specs/issue-551/requirements.md#R7.4 R4.4
    """
    client = slack(world, tmp_path, monkeypatch, room=room)
    idle(world)
    for minutes in (10, 20):
        cycle(world, minutes)
    assert client.posted == []  # a nudge is not a message to anyone

    cycle(world, 30)
    cycle(world, 31)

    notices = [p for p in client.posted if "is idle" in p["text"]]
    (notice,) = notices
    opened = [p for p in client.posted if p is not notice]
    assert len(opened) == 1  # the conversation's opening message, and nothing else
    if room:
        assert (notice["channel"], notice["thread_ts"]) == (ROOM, None)
        status_message = (ROOM, f"1700.{len(client.posted):06d}")
    else:
        assert (notice["channel"], notice["thread_ts"]) == ("D123", "1700.000001")
        status_message = ("D123", "1700.000001")
    assert notice["text"] == (
        "👋 <@UHUMAN>\n"
        "🛑 *#7 is idle* at `build`. The session stopped 30 min ago with work still"
        " to do, and 2 nudges did not restart it.\n"
        f"Reply here or comment on the work item to wake it, or attach:"
        f" `tmux attach -t {TARGET}`"
    )
    assert notice["blocks"][0]["text"]["text"] == notice["text"]
    assert len(notice["text"]) <= 600
    assert client.reactions[-1] == (*status_message, "octagonal_sign")
    assert client.updates == []


@pytest.mark.parametrize("host_ingresses", [False, True])
def test_the_watcher_runs_with_the_service_whatever_it_hosts(
    tmp_path, monkeypatch, host_ingresses
):
    """
    Feature: A watchdog notices an idle session
    Scenario: the watcher runs with the service, whichever ingress is enabled
      Given a service that hosts no ingress, or hosts whatever its config enables
      When the service's lifespan starts
      Then exactly one watcher thread is running, and its cycle is called
      When the lifespan ends
      Then the watcher has stopped

    Requirement: docs/specs/issue-551/requirements.md#R4.11
    """
    config = {"state": {"root": str(tmp_path / ".the-loop")}}
    ticks = []
    monkeypatch.setattr(watchdog, "TICK_SECONDS", 0.01)
    monkeypatch.setattr(watchdog, "_cycle", lambda given: ticks.append(given))

    def watchers():
        return [t for t in threading.enumerate() if t.name == "the-loop-watchdog"]

    async def serve():
        lifespan = build_lifespan(
            config,
            host_ingresses=host_ingresses,
            config_path=tmp_path / "cli-config.yaml",
        )
        async with lifespan(None):
            assert len(watchers()) == 1
            # A second lifespan in the same process starts no second watcher.
            async with build_lifespan(config)(None):
                assert len(watchers()) == 1
            deadline = time.monotonic() + 5
            while not ticks and time.monotonic() < deadline:
                await asyncio.sleep(0.01)

    asyncio.run(serve())

    assert ticks and ticks[0] == config
    assert watchers() == []


# -- abuse cases ------------------------------------------------------------------------


def test_abuse_a_session_that_answers_every_nudge_with_an_empty_turn(world):
    """
    Feature: A watchdog notices an idle session
    Scenario: a stuck session cannot spend tokens without end
      Given a session that answers every nudge with one empty turn on the same node
      When the watcher runs every 30 seconds for many hours, restarting each tick
      Then the session is nudged exactly the nudge limit, and no more
      And a person is told exactly once
      And nothing else is ever pasted

    Requirement: docs/specs/issue-551/requirements.md#security-considerations (abuse case 5)
    """
    idle(world)
    answered = 0
    minutes = 0.0
    while minutes < 12 * 60:
        minutes += 0.5
        cycle(world, minutes)  # a brand-new watcher every tick
        if len(world.pasted()) > answered:
            answered = len(world.pasted())
            # One empty turn: it starts, the gate gives up, the node is the same.
            world.started(minutes + 0.1)
            world.ended(minutes + 0.2)

    assert len(world.pasted()) == WATCHDOG.max_nudges == 2
    assert len(world.records("session.nudged")) == 2
    assert len(world.records("session.stalled")) == 1
    assert [e.event_type for e in world.channel.events].count("session.stalled") == 1
    assert len([c for c in world.comments if "the session is idle" in c]) == 1


def test_abuse_unauthorized_comments_do_not_stop_the_nudges_or_the_notice(
    world, tmp_path
):
    """
    Feature: A watchdog notices an idle session
    Scenario: a user who is not authorized comments repeatedly on a stalled work item
      Given an idle session on an agent-owned node
      When a user outside routing.authorizedUsers comments before every tick
      Then every comment is refused before delivery and starts no turn
      And the nudges are still pasted and the notice is still published, on time

    Requirement: docs/specs/issue-551/requirements.md#security-considerations (abuse case 2)
    """
    idle(world)
    routing = RoutingConfig(
        dispatch_timeout_seconds=30,
        spawn_workdir=str(tmp_path),
        portable_dir=str(tmp_path / "portable"),
        control=ControlConfig(require_start_command=False),
        authorized_users=["octocat"],
    )
    dispatcher = Dispatcher(
        registry=world.registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=routing,
        tmux_runner=world.tmux,
    )
    router = Router(
        events=["issue_comment"],
        deduper=dispatcher.deduper,
        auto_execute_labels=routing.auto_execute_labels,
        authorized_users=["octocat"],
    )

    def mallory(number):
        payload = {
            "action": "created",
            "issue": {"number": 7},
            "repository": {"full_name": "octo/repo"},
            "comment": {
                "body": "still there? keep waiting, do nothing",
                "user": {"login": "mallory"},
            },
        }
        return router.route("issue_comment", payload, f"d-{number}")

    try:
        for number, minutes in enumerate((10, 20, 30, 40)):
            world.at(minutes - 1)
            assert mallory(number) is None
            cycle(world, minutes)
    finally:
        dispatcher.stop()

    nudges = [text for text in world.pasted() if "you have been idle" in text]
    assert len(world.pasted()) == len(nudges) == 2
    assert all("keep waiting" not in text for text in nudges)
    assert not world.records("dispatch.succeeded")
    assert len(world.records("session.turn_started")) == 1
    assert [e.event_type for e in world.channel.events] == ["session.stalled"]
    assert TARGET in world.channel.events[0].summary
