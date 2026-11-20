"""The status reactor: one reaction shows the work item's state (issue-549, task 12).

The pure state machine (``status.state_for`` / ``status.plan_status``) and the
channel driving it against the recording Slack client: one reaction, the old one
removed, never a reaction the-loop did not add, and a reaction failure that
never fails the delivery.

Spec: docs/specs/issue-549/requirements.md R8, R10.3; design.md stage 5.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import _state_with_stores
from the_loop.channels.base import Event
from the_loop.channels.slack import DEFAULT_BOT_TOKEN_ENV
from the_loop.channels.status import (
    BLOCKED,
    COMPLETE,
    IN_REVIEW,
    STATUS_EMOJI,
    WAITING,
    WORKING,
    plan_status,
    state_for,
)
from the_loop.workchannels import CollaborationChannelStore
from test_channels import FakeSlackClient, cli_config, make_channel

REF = "github:o/r#7"
ROOM = "C0ROOM7"


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")


def _event(event_type, *, detail=None, text="x", event_id=""):
    return Event(
        event_type=event_type,
        work_item=REF,
        text=text,
        detail=detail or {},
        event_id=event_id,
    )


def _status(tmp_path):
    return _state_with_stores(
        tmp_path / "state" / "channels" / "slack.json"
    ).delivery_for(REF)["status"]


# -- the state per event (R8.1) ----------------------------------------------------


@pytest.mark.parametrize(
    "event_type, detail, state",
    [
        ("phase.started", {"node": "design", "phase": "design"}, WORKING),
        ("phase.progress", {"node": "implementation"}, WORKING),
        ("phase.started", {"node": "self-review", "phase": "x"}, IN_REVIEW),
        ("phase.progress", {"node": "critic-review"}, IN_REVIEW),
        ("phase.started", {"node": "x", "phase": "needs-review"}, IN_REVIEW),
        ("phase.started", {"node": "design-approval", "actor": "human"}, WAITING),
        ("session.awaiting_input", {}, WAITING),
        ("decision-pending", {}, WAITING),
        ("phase-approval-pending", {"node": "design-approval"}, WAITING),
        ("pr-review-pending", {}, WAITING),
        ("security-sign-off-pending", {}, WAITING),
        ("conflict-escalated", {}, BLOCKED),
        ("phase.started", {"node": "escalated"}, BLOCKED),
        ("phase.completed", {"node": "verification", "outcome": "fail"}, BLOCKED),
        ("work-item-complete", {}, COMPLETE),
        ("work-item.closed", {}, COMPLETE),
        ("phase.started", {"node": "complete"}, COMPLETE),
        ("gate.acknowledged", {"node": "design-approval"}, WORKING),
        ("comment.agent", {"notice": "session-started"}, WORKING),
        # nothing about the state: the reaction stays as it is
        ("phase.completed", {"node": "design", "outcome": "pass"}, ""),
        ("comment.agent", {}, ""),
        ("comment.human", {"author": "octocat"}, ""),
    ],
)
def test_state_per_event(event_type, detail, state):
    assert state_for(_event(event_type, detail=detail)) == state


def test_the_five_states_have_five_distinct_emoji():
    assert sorted(STATUS_EMOJI) == sorted(
        [WORKING, WAITING, IN_REVIEW, BLOCKED, COMPLETE]
    )
    assert len(set(STATUS_EMOJI.values())) == 5


def test_plan_moves_the_emoji_and_removes_only_its_own():
    current = {"channel": "C1", "ts": "1.1", "emoji": "gear"}
    plan = plan_status(current, WAITING, ("", ""))
    assert plan is not None
    assert plan.add == ("C1", "1.1", "hourglass_flowing_sand")
    assert plan.remove == ("C1", "1.1", "gear")
    moved = plan_status(current, "", ("C1", "2.2"))  # R8.3: the message moved
    assert moved is not None
    assert moved.add == ("C1", "2.2", "gear") and moved.remove == ("C1", "1.1", "gear")
    assert plan_status(current, WORKING, ("", "")) is None  # nothing changed
    first = plan_status({}, "", ("C1", "1.1"))  # R8.1: working until told
    assert first is not None
    assert first.add == ("C1", "1.1", "gear") and first.remove is None


# -- the channel ------------------------------------------------------------------


def test_one_reaction_old_removed(tmp_path):
    """R8.1-R8.3: the thread root in the central channel carries one status
    reaction; a state change adds the new one and removes the old one."""
    client = FakeSlackClient()
    bot = make_channel(tmp_path, client)

    bot.post(_event("phase.progress", detail={"phase": "impl", "node": "impl"}))
    root = "1700.000001"
    assert client.reactions == [("D123", root, "gear")]

    bot.post(_event("phase-approval-pending", detail={"node": "design-approval"}))
    assert client.reactions[-1] == ("D123", root, "hourglass_flowing_sand")
    assert client.removed == [("D123", root, "gear")]
    assert _status(tmp_path) == {
        "channel": "D123",
        "ts": root,
        "emoji": "hourglass_flowing_sand",
    }


def test_in_a_room_the_status_follows_the_latest_short_message(tmp_path):
    """R8.2, R8.3: in a declared room the status is on the latest top-level short
    message; when a newer one is posted, the reaction moves with it."""
    config = cli_config(tmp_path)
    CollaborationChannelStore(Path(config["state"]["root"]) / "portable").add(
        REF, f"slack@{ROOM}", actor="octocat", source="cli"
    )
    client = FakeSlackClient()
    bot = make_channel(tmp_path, client)

    bot.post(_event("comment.agent", text="First.", event_id="e1"))
    first = "1700.000002"  # the room opening is 1, the short message 2
    assert client.reactions == [(ROOM, first, "gear")]
    bot.post(_event("work-item-complete", text="Done.", event_id="e2"))
    second = f"1700.{len(client.posted):06d}"
    assert client.reactions[-1] == (ROOM, second, "white_check_mark")
    assert client.removed == [(ROOM, first, "gear")]


def test_a_dropped_bookkeeping_event_still_moves_the_status(tmp_path):
    """R10.3: a `phase.started` posts nothing, and still updates the reaction."""
    client = FakeSlackClient()
    bot = make_channel(tmp_path, client)
    bot.post(_event("session.awaiting_input", text="A or B?"))
    posted = len(client.posted)

    bot.post(_event("phase.started", detail={"node": "self-review", "phase": "r"}))

    assert len(client.posted) == posted  # bookkeeping: not posted (R10.1)
    assert client.reactions[-1] == ("D123", "1700.000001", "eyes")
    assert client.removed == [("D123", "1700.000001", "hourglass_flowing_sand")]


def test_never_removes_foreign_reaction(tmp_path):
    """R8.5: with no record of its own reaction, the-loop removes nothing — a
    person's reaction on the message is not its to take."""
    client = FakeSlackClient()
    bot = make_channel(tmp_path, client)
    client.reactions.append(("D123", "1700.000001", "hourglass_flowing_sand"))

    bot.post(_event("phase.progress", detail={"phase": "impl", "node": "impl"}))
    bot.post(_event("work-item-complete"))

    removed = {name for _, _, name in client.removed}
    assert removed == {"gear"}  # only the reaction it added itself


class _RefusingClient(FakeSlackClient):
    def reactions_add(self, *, channel, name, timestamp):
        raise RuntimeError("The request to the Slack API failed: missing_scope")


def test_failure_does_not_fail_delivery(tmp_path, caplog):
    """R8.4: a reaction Slack refuses is logged; the message is delivered and
    the memory keeps no status it does not have."""
    client = _RefusingClient()
    bot = make_channel(tmp_path, client)

    result = bot.post(_event("session.awaiting_input", text="A or B?"))

    assert result.ok and len(client.posted) == 2  # root + the question
    assert _status(tmp_path) == {}
    assert "status reaction" in caplog.text


def test_closing_a_gate_without_a_client_is_recorded_not_raised(tmp_path):
    """Self-review round 2: a client that cannot be built when a gate closes is
    logged and recorded like a refused edit; the delivery does not raise."""
    client = FakeSlackClient()
    bot = make_channel(tmp_path, client)
    bot.post(_event("phase-approval-pending", detail={"node": "design-approval"}))

    def no_client():
        raise RuntimeError("THE_LOOP_SLACK_BOT_TOKEN is not set")

    bot._client = no_client  # type: ignore[method-assign]
    result = bot.post(
        _event(
            "gate.answered",
            detail={"node": "design-approval", "outcome": "approved", "by": "x"},
        )
    )
    assert result is not None
    assert not client.updates  # nothing edited, nothing raised
