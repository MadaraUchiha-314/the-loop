"""The live Slack check (issue-549 T4): the real pipeline against a real workspace.

Opt-in only. It is marked ``live_slack`` and skips unless ``THE_LOOP_LIVE_SLACK=1``,
so CI never posts to Slack. Slack does not document how its ``markdown`` block
draws tables and defused sequences, or whether an edit keeps link previews off;
this test is the proof the offline suite cannot give.

It drives the pipeline's own pieces (``build_short_form``, ``render_short_blocks``,
``render_long_form``, ``plan_message``, ``deliver`` / ``post_message``, the
``chat.update`` edit path and the status reactor's ``plan_status``) through
``slack_sdk``, reads every message back with ``conversations.history`` /
``conversations.replies``, and then deletes what it posted.

Environment (credentials by reference only, never printed):

* ``THE_LOOP_LIVE_SLACK=1``: run at all.
* ``THE_LOOP_SLACK_BOT_TOKEN``: the bot token (the name the channel reads).
* ``THE_LOOP_LIVE_SLACK_CHANNEL``: the test channel's conversation id. Not the
  central channel and not a work item's room.
* ``THE_LOOP_LIVE_SLACK_CLEANUP=1``: post nothing; delete any message an
  interrupted run left behind (every message carries a run marker).

The test never keeps what it posts: live checks are not for people to read. It
refuses a channel where the bot has posted anything but live checks, because
that is the central channel or a work item's room.
* ``THE_LOOP_LIVE_SLACK_REPORT=<path>``: write a redacted read-back summary
  there: block types, part order, previews present or not, reactions. No ids,
  no token, no channel name.

Run: ``cd cli && THE_LOOP_LIVE_SLACK=1 uv run python -m pytest -q -m live_slack
tests/test_slack_live.py``
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional

import pytest

from the_loop.channels.base import Event
from the_loop.channels.delivery import THREAD_OF_TOP, deliver, plan_message
from the_loop.channels.render import render_long_form
from the_loop.channels.shortform import build_short_form
from the_loop.channels.slack import render_short_blocks
from the_loop.channels.status import (
    STATUS_EMOJI,
    WAITING,
    WORKING,
    plan_status,
)

LIVE = os.environ.get("THE_LOOP_LIVE_SLACK") == "1"

pytestmark = [
    pytest.mark.live_slack,
    pytest.mark.skipif(
        not LIVE, reason="live Slack check: set THE_LOOP_LIVE_SLACK=1 to run"
    ),
]

TOKEN_ENV = "THE_LOOP_SLACK_BOT_TOKEN"
CHANNEL_ENV = "THE_LOOP_LIVE_SLACK_CHANNEL"
CLEANUP_ENV = "THE_LOOP_LIVE_SLACK_CLEANUP"
REPORT_ENV = "THE_LOOP_LIVE_SLACK_REPORT"

#: Every message this test posts carries this prefix and the run's id, so a
#: cleanup run can find what an interrupted run left.
MARKER_PREFIX = "the-loop-live-check"

#: How long Slack is given to unfurl a link before the read-back looks.
UNFURL_WAIT_S = 6.0

#: The sequences that must reach Slack inert (abuse cases 1, 2 and 4).
LIVE_SEQUENCES = ("<!here>", "<!channel>", "<@U00000000>")


# -- fixtures ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> Any:
    token = os.environ.get(TOKEN_ENV, "")
    channel = os.environ.get(CHANNEL_ENV, "")
    if not token or not channel:
        pytest.skip(f"live Slack check needs {TOKEN_ENV} and {CHANNEL_ENV} set")
    slack_sdk = pytest.importorskip("slack_sdk")
    return slack_sdk.WebClient(token=token)


@pytest.fixture(scope="module")
def channel() -> str:
    return os.environ.get(CHANNEL_ENV, "")


def _refuse_a_shared_channel(client: Any, channel: str) -> None:
    """Stop before posting when the bot has posted anything other than a live
    check in this channel: that is the central channel or a work item's room,
    and people read it."""
    bot_user: Optional[str] = client.auth_test().get("user_id")
    history = client.conversations_history(channel=channel, limit=200)
    for message in history.get("messages") or []:
        if message.get("user") != bot_user or message.get("subtype"):
            continue
        if MARKER_PREFIX not in json.dumps(message):
            pytest.fail(
                "the live check needs a dedicated test channel: the bot already "
                "posts here for people (the central channel or a room)"
            )


# -- the text ------------------------------------------------------------------------


def _long_text(marker: str) -> str:
    """A long form with everything the live check must see drawn: a table, a task
    list, nested lists, a code block long enough to split, a link that would
    unfurl, and the sequences that must stay inert."""
    code = "\n".join(
        f"line_{n:04d} = compute({n}, label='the quick brown fox jumps')"
        for n in range(260)
    )
    return (
        f"## Live check {marker}\n\n"
        "A table:\n\n"
        "| check | expected |\n"
        "|---|---|\n"
        "| table | drawn as a table |\n"
        "| task list | drawn with boxes |\n\n"
        "A task list:\n\n"
        "- [x] posted\n"
        "- [ ] read back\n\n"
        "Nested lists:\n\n"
        "- outer\n"
        "  - inner\n"
        "    - innermost\n\n"
        "Defused: <!here> <!channel> <@U00000000> "
        "[click](javascript:alert(1)) and <https://example.com|a label>.\n\n"
        "A link that would unfurl: https://github.com/MadaraUchiha-314/the-loop\n\n"
        f"```python\n{code}\n```\n\n"
        f"End of {marker}.\n"
    )


def _event(marker: str, text: str, summary: str) -> Event:
    return Event(
        event_type="comment.agent",
        work_item="github:MadaraUchiha-314/the-loop#549",
        text=text,
        url="https://github.com/MadaraUchiha-314/the-loop/issues/549",
        source="cli",
        summary=summary,
    )


def _plan(event: Event, channel: str, *, edit_ts: str = "", edit_parts=()) -> Any:
    short = build_short_form(event)
    long_form = render_long_form(event.text)
    return plan_message(
        event_id=f"live-{uuid.uuid4().hex}",
        channel=channel,
        short_text=short.fallback,
        short_blocks=render_short_blocks(event, short.text),
        parts=long_form.parts,
        parts_thread=THREAD_OF_TOP,
        edit_ts=edit_ts,
        edit_parts=edit_parts,
    )


# -- read-back -----------------------------------------------------------------------


def _message(client: Any, channel: str, ts: str) -> Dict[str, Any]:
    response = client.conversations_history(
        channel=channel, latest=ts, oldest=ts, inclusive=True, limit=1
    )
    messages = list(response.get("messages") or [])
    assert messages, "the posted message could not be read back"
    return dict(messages[0])


def _replies(client: Any, channel: str, ts: str) -> List[Dict[str, Any]]:
    response = client.conversations_replies(channel=channel, ts=ts, limit=200)
    messages = [dict(m) for m in response.get("messages") or []]
    return sorted(
        (m for m in messages if m.get("ts") != ts), key=lambda m: float(m["ts"])
    )


def _strings(value: Any) -> Iterator[str]:
    """Every string inside a block, at any depth: Slack may hand a ``markdown``
    block back as written or converted, and the check reads both."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _block_types(message: Mapping[str, Any]) -> List[str]:
    return [str(b.get("type")) for b in message.get("blocks") or []]


def _has_preview(message: Mapping[str, Any]) -> bool:
    return bool(message.get("attachments"))


def _reactions(client: Any, channel: str, ts: str) -> List[str]:
    # Read from the message itself: ``reactions.get`` needs ``reactions:read``,
    # a scope the shipped manifest does not request.
    message = _message(client, channel, ts)
    return sorted(str(r.get("name")) for r in message.get("reactions") or [])


def _write_report(observed: Mapping[str, Any]) -> None:
    path = os.environ.get(REPORT_ENV, "")
    if not path:
        return
    lines = ["# Live Slack read-back (redacted)", ""]
    for key, value in observed.items():
        lines.append(f"- **{key}:** {json.dumps(value, ensure_ascii=False)}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _delete(client: Any, channel: str, ts_list: List[str]) -> None:
    for ts in reversed(ts_list):  # replies first, the parent last
        try:
            client.chat_delete(channel=channel, ts=ts)
        except Exception:  # noqa: BLE001 — already gone is fine
            pass


# -- the check -----------------------------------------------------------------------


@pytest.mark.skipif(os.environ.get(CLEANUP_ENV) == "1", reason="cleanup run")
def test_live_post_edit_react_and_delete(client, channel):
    """
    Scenario: the pipeline's messages read back from a real workspace as planned
      Given the bot token and a dedicated test channel, where the bot posts
        nothing for people
      When a short message and its long form (a table, a task list, nested lists,
        a code block that splits, defused sequences) are delivered, then edited
      Then every long-form part reads back as blocks Slack drew from markdown
        (Slack converts a markdown block to rich_text, header and table blocks),
        the table as a table block, in order, marked (n/m)
      And no message carries a link preview, after the post or after the edit
      And no broadcast or user mention reaches Slack live
      And the status reaction is added, swapped and removed

    Requirement: docs/specs/issue-549/requirements.md R2.1, R2.2, R5, R8;
                 design.md § Security design abuse cases 1-2
    """
    _refuse_a_shared_channel(client, channel)
    marker = f"{MARKER_PREFIX}-{uuid.uuid4().hex[:12]}"
    summary = (
        f"Live check {marker}: a short message, with the whole text in its thread."
    )
    event = _event(marker, _long_text(marker), summary)
    posted: List[str] = []
    observed: Dict[str, Any] = {}

    def record(delivered: Any) -> None:
        for ts in [delivered.top, *delivered.parts]:
            if ts and ts not in posted:
                posted.append(ts)

    try:
        plan = _plan(event, channel)
        assert len(plan.parts) >= 2, "the long code block should split the long form"
        delivered = deliver(client, plan, record=record)
        top = delivered.top
        time.sleep(UNFURL_WAIT_S)

        parent = _message(client, channel, top)
        replies = _replies(client, channel, top)
        total = len(plan.parts)
        marks = [
            next(
                (
                    f"({n}/{total})"
                    for n in range(1, total + 1)
                    if f"({n}/{total})" in "".join(_strings(reply.get("blocks")))
                ),
                "",
            )
            for reply in replies
        ]
        everything = json.dumps([parent, *replies])
        observed["top block types"] = _block_types(parent)
        observed["part block types"] = [_block_types(r) for r in replies]
        observed["table drawn as a table block"] = any(
            "table" in types for types in observed["part block types"]
        )
        observed["parts read back"] = len(replies)
        observed["part order"] = marks
        observed["preview after post"] = [_has_preview(m) for m in [parent, *replies]]
        observed["live sequences after post"] = [
            s for s in LIVE_SEQUENCES if s in everything
        ]
        observed["javascript link after post"] = '"url": "javascript:' in everything

        # The edit path (R6): the same plan shape, through chat.update.
        edited_event = _event(
            marker, _long_text(marker) + "\nEdited.\n", summary + " Edited."
        )
        edit_plan = _plan(
            edited_event, channel, edit_ts=top, edit_parts=delivered.parts
        )
        after = deliver(client, edit_plan, record=record)
        observed["edit kept the message"] = after.edited and after.top == top
        time.sleep(UNFURL_WAIT_S)
        edited_parent = _message(client, channel, top)
        edited_replies = _replies(client, channel, top)
        observed["preview after edit"] = [
            _has_preview(m) for m in [edited_parent, *edited_replies]
        ]

        # The status reactor (R8): waiting, then working, then none.
        sequence: List[List[str]] = []
        status: Mapping[str, str] = {}
        for state in (WAITING, WORKING):
            step = plan_status(status, state, (channel, top))
            assert step is not None and step.add is not None
            client.reactions_add(channel=channel, timestamp=top, name=step.add[2])
            if step.remove is not None:
                client.reactions_remove(
                    channel=channel, timestamp=top, name=step.remove[2]
                )
            status = step.status
            sequence.append(_reactions(client, channel, top))
        client.reactions_remove(channel=channel, timestamp=top, name=status["emoji"])
        sequence.append(_reactions(client, channel, top))
        observed["reactions"] = sequence
    finally:
        _write_report(observed)
        _delete(client, channel, posted)

    assert observed["top block types"][0] == "section"
    # Slack stores a markdown block as the blocks it drew from it: no part is
    # empty, and the table reached Slack as a real table (R2.2).
    assert all(types for types in observed["part block types"]), observed[
        "part block types"
    ]
    assert observed["table drawn as a table block"], observed["part block types"]
    assert observed["parts read back"] == total
    assert observed["part order"] == [f"({n}/{total})" for n in range(1, total + 1)]
    assert not any(observed["preview after post"])
    assert not any(observed["preview after edit"])
    assert observed["edit kept the message"]
    assert observed["live sequences after post"] == []
    assert observed["javascript link after post"] is False
    assert observed["reactions"] == [
        [STATUS_EMOJI[WAITING]],
        [STATUS_EMOJI[WORKING]],
        [],
    ]


@pytest.mark.skipif(os.environ.get(CLEANUP_ENV) != "1", reason="not a cleanup run")
def test_live_cleanup_deletes_left_messages(client, channel):
    """A ``THE_LOOP_LIVE_SLACK_CLEANUP=1`` run deletes what an interrupted run
    left: any of the bot's messages carrying the run marker, with its replies."""
    targets: List[str] = []
    bot_user: Optional[str] = client.auth_test().get("user_id")
    history = client.conversations_history(channel=channel, limit=200)
    for message in history.get("messages") or []:
        if message.get("user") != bot_user:
            continue
        if MARKER_PREFIX not in json.dumps(message):
            continue
        ts = str(message.get("ts"))
        targets.append(ts)
        if message.get("reply_count"):
            targets.extend(str(r["ts"]) for r in _replies(client, channel, ts))
    _delete(client, channel, list(dict.fromkeys(targets)))
