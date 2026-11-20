"""The recap line after a long gap (issue-549, task 14, R9).

A person who comes back after more than 12 hours finds one line, opening the
next short form, that names what the loop did since they last spoke: built from
the loop's own events (phase changes, gate outcomes, completion), never from
model output, and inside the short form's 600-character cap.

Spec: docs/specs/issue-549/requirements.md R9, R10.2.
"""

from __future__ import annotations

import pytest

from the_loop.channels.base import Event
from the_loop.channels.preamble import RECAP_AFTER_S, change_of, recap_line
from the_loop.channels.shortform import SUMMARY_MAX_CHARS
from the_loop.channels.slack import DEFAULT_BOT_TOKEN_ENV
from test_channels import FakeSlackClient, make_channel

REF = "github:o/r#7"
T0 = 1_800_000_000.0


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")


class Clock:
    def __init__(self, now=T0):
        self.now = now

    def __call__(self):
        return self.now


def _channel(tmp_path, monkeypatch):
    client = FakeSlackClient()
    bot = make_channel(tmp_path, client)
    clock = Clock()
    monkeypatch.setattr(bot, "_now", clock)
    return client, bot, clock


def _event(event_type, **detail):
    return Event(
        event_type=event_type,
        work_item=REF,
        text=f"{event_type} happened.",
        detail={k: str(v) for k, v in detail.items()},
    )


def _short(post):
    return post["blocks"][0]["text"]["text"]


def test_recap_after_12h(tmp_path, monkeypatch):
    """R9.1, R9.3, R10.2: a person spoke, 13 hours passed while the loop moved
    (a phase change dropped from Slack as bookkeeping still counts, a gate was
    approved), and the next short form opens with the recap line."""
    client, bot, clock = _channel(tmp_path, monkeypatch)
    bot.post(_event("comment.agent"))
    bot.note_human(REF)

    clock.now += 3600
    bot.post(_event("phase.started", phase="design", node="design"))  # bookkeeping
    clock.now += 3600
    bot.post(
        _event(
            "phase.completed",
            phase="design",
            node="design-approval",
            outcome="approved",
        )
    )
    clock.now = T0 + 13 * 3600
    bot.post(_event("phase-approval-pending", node="tasks-approval"))

    text = _short(client.posted[-1])
    first, rest = text.split("\n", 1)
    assert first.startswith("🔁")
    assert "13h ago" in first
    assert "phase *design*" in first and "*design* approved" in first
    assert "happened" not in first  # not the events' words: the loop's record
    assert len(text) <= SUMMARY_MAX_CHARS  # R9.3: inside the cap

    # the next message, with nothing new since, carries no second recap
    bot.post(_event("comment.agent"))
    assert not _short(client.posted[-1]).startswith("🔁")


def test_no_recap_when_nothing_changed(tmp_path, monkeypatch):
    """R9.2: 13 hours of silence with no change recorded: no recap line."""
    client, bot, clock = _channel(tmp_path, monkeypatch)
    bot.post(_event("comment.agent"))
    bot.note_human(REF)
    clock.now = T0 + 13 * 3600

    bot.post(_event("phase-approval-pending", node="design-approval"))

    assert not _short(client.posted[-1]).startswith("🔁")


def test_no_recap_before_12h_or_when_no_human_spoke(tmp_path, monkeypatch):
    """R9.1, R9.2: under the threshold, or with no human message at all, there
    is no recap however much changed."""
    client, bot, clock = _channel(tmp_path, monkeypatch)
    bot.post(_event("phase.started", phase="design", node="design"))
    clock.now += 13 * 3600
    bot.post(_event("comment.agent"))
    assert not _short(client.posted[-1]).startswith("🔁")  # nobody spoke

    bot.note_human(REF)
    clock.now += 3600
    bot.post(_event("phase.started", phase="tasks", node="tasks"))
    clock.now += 11 * 3600
    bot.post(_event("comment.agent"))
    assert not _short(client.posted[-1]).startswith("🔁")  # only 12h, not more


def test_recap_line_names_the_newest_changes_and_counts_the_rest():
    changes = [
        {"at": str(T0 + n), "kind": "phase", "value": f"p{n}"} for n in range(1, 10)
    ]
    line = recap_line(
        changes, last_human=T0, recapped_at="", now=T0 + RECAP_AFTER_S + 60
    )
    assert "+3 earlier" in line and "*p9*" in line and "*p3*" not in line


def test_change_of_reads_identifiers_never_text():
    """R9.3: a change carries the runtime's identifiers; a value that is not
    one (markup, a mention) is left out rather than drawn."""
    assert change_of(_event("phase.started", phase="design")) == ("phase", "design")
    assert change_of(_event("phase.started", phase="<!here>")) is None
    assert change_of(_event("comment.agent")) is None
    assert change_of(_event("work-item-complete")) == ("complete", "")


def test_an_authorized_message_in_the_conversation_is_the_last_human_time(
    tmp_path, monkeypatch
):
    """R9.1: the inbound pipeline records when an authorized member last spoke
    in the work item's conversation; a stranger's message records nothing."""
    from conftest import _state_with_stores
    from test_channels_declared_integration import (
        REF as ROOM_REF,
        Sink,
        _message,
        cli_config,
        declare,
        socket,
    )

    monkeypatch.setattr("the_loop.channels.slack.SlackBotChannel._now", lambda self: T0)
    config = cli_config(tmp_path)
    declare(config)
    memory = lambda: _state_with_stores(  # noqa: E731
        tmp_path / "state" / "channels" / "slack.json"
    ).delivery_for(ROOM_REF)

    socket(config, _message("hello", user="USTRANGER"), Sink())
    assert memory()["lastHuman"] == ""
    socket(config, _message("hello", user="UHUMAN", ts="1700.000200"), Sink())
    assert memory()["lastHuman"] == str(T0)
