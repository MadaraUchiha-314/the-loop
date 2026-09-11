"""Unit tests for issue-337: Execute / Start command buttons on the Slack channel,
the press outcome written onto the pressed message, and the `channels status`
steps. Spec: docs/specs/issue-337/{requirements,design,testing-plan}.md."""

from __future__ import annotations

import argparse
import json

import pytest

from the_loop import eventlog
from the_loop.channels import inbound
from the_loop.channels.base import InboundReply, OutboundEvent
from the_loop.channels.slack import (
    ACTION_PREFIX,
    BUTTON_NAMES,
    COMMAND_BUTTONS,
    DEFAULT_APP_TOKEN_ENV,
    DEFAULT_BOT_TOKEN_ENV,
    PHASE_SELECTION_MARKER,
    SlackBotChannel,
    SlackChannelConfig,
    expected_commands,
    render_blocks,
    render_reply_blocks,
)

CHECKLIST = (
    "🤖 _the-loop_ — **which phases does this work item need?**\n\n"
    "- [x] brainstorming\n- [x] design\n\n" + PHASE_SELECTION_MARKER
)


class FakeSlackClient:
    """The slice of ``slack_sdk.WebClient`` the channel uses, recorded — with
    ``chat_update`` (issue-337)."""

    def __init__(self, refuse_update: str = ""):
        self.posted = []
        self.reactions = []
        self.updates = []  # (channel, ts, text, blocks)
        self.refuse_update = refuse_update

    def chat_postMessage(self, *, channel, text, thread_ts=None, blocks=None):
        self.posted.append(
            {"channel": channel, "text": text, "thread_ts": thread_ts, "blocks": blocks}
        )
        return {"ok": True, "channel": channel, "ts": f"1700.{len(self.posted):06d}"}

    def chat_update(self, *, channel, ts, text, blocks=None):
        if self.refuse_update:
            raise RuntimeError(
                f"The request to the Slack API failed: {self.refuse_update}"
            )
        self.updates.append((channel, ts, text, blocks))
        return {"ok": True, "channel": channel, "ts": ts}

    def auth_test(self):
        return {"ok": True, "user_id": "UBOT"}

    def reactions_add(self, *, channel, name, timestamp):
        self.reactions.append((channel, timestamp, name))
        return {"ok": True}


def cli_config(tmp_path, authorized=("UHUMAN",), control=None, **slack):
    section = {"enabled": True, "channel": "C123", **slack}
    routing = {
        "authorizedUsers": [
            {"github": f"gh-{member}", "slack": member} for member in authorized
        ]
    }
    if control is not None:
        routing["control"] = control
    return {
        "state": {"root": str(tmp_path / "state")},
        "routing": routing,
        "channels": {"slack": section},
    }


def interactive_config(tmp_path, **slack):
    slack.setdefault("read", {"mode": "socket"})
    slack.setdefault("publish", ["work-item.reply", "gate.feedback", "control.command"])
    return cli_config(tmp_path, **slack)


def make_channel(tmp_path, client, config=None, **slack):
    config = config or interactive_config(tmp_path, **slack)
    return SlackBotChannel(
        SlackChannelConfig.from_mapping(config),
        tmp_path / "state" / "channels" / "slack.json",
        client_factory=lambda token: client,
    )


def checklist_event(text=CHECKLIST, event_type="comment.agent"):
    return OutboundEvent(
        event_type=event_type,
        work_item="github:o/r#7",
        text=text,
        url="https://github.com/o/r/issues/7#c1",
        detail={"author": "octocat"},
    )


def buttons(blocks):
    """Every button in ``blocks``, as ``(action_id, value_or_url)``."""
    out = []
    for block in blocks:
        if block.get("type") != "actions":
            continue
        for element in block["elements"]:
            out.append(
                (element["action_id"], element.get("value") or element.get("url"))
            )
    return out


def a_press(
    action_id=f"{ACTION_PREFIX}command:execute",
    value="the-loop execute",
    author="UHUMAN",
    ts="1750.5",
    thread="1700.1",
):
    return {
        "type": "block_actions",
        "user": {"id": author},
        "channel": {"id": "C123"},
        "message": {
            "ts": ts,
            "thread_ts": thread,
            "text": "the-loop: comment.agent on github:o/r#7",
            "blocks": render_blocks(
                checklist_event(),
                "normal",
                commands={"execute": "the-loop execute"},
            ),
        },
        "container": {"message_ts": ts, "thread_ts": thread},
        "actions": [{"action_id": action_id, "value": value}],
        "action_ts": "1900.1",
    }


# -- R1: the config and the renderer -------------------------------------------


def test_command_buttons_need_socket_and_the_grant(tmp_path):
    """R1.4 (decision-103 D5 restated): a command button is rendered only where
    a press can be received AND acted on."""
    on = SlackChannelConfig.from_mapping(interactive_config(tmp_path))
    assert on.command_buttons and on.interactive
    poll = SlackChannelConfig.from_mapping(
        interactive_config(tmp_path, read={"mode": "poll"})
    )
    assert not poll.command_buttons
    no_grant = SlackChannelConfig.from_mapping(
        interactive_config(tmp_path, publish=["work-item.reply", "gate.feedback"])
    )
    assert not no_grant.command_buttons and no_grant.interactive


def test_keyword_reads_the_configured_vocabulary(tmp_path):
    """R1.5: the value is the CONFIGURED keyword — an operator's rename is the
    button's value, a disabled keyword is no button, an unknown command is ""."""
    default = SlackChannelConfig.from_mapping(interactive_config(tmp_path))
    assert default.keyword("execute") == "the-loop execute"
    assert default.keyword("start") == "the-loop start"
    assert default.keyword("nonesuch") == ""
    assert default.command_buttons_for("execute", "start") == {
        "execute": "the-loop execute",
        "start": "the-loop start",
    }
    renamed = SlackChannelConfig.from_mapping(
        interactive_config(
            tmp_path, control={"keywords": {"execute": "loop go", "start": ""}}
        )
    )
    assert renamed.command_buttons_for("execute", "start") == {"execute": "loop go"}
    poll = SlackChannelConfig.from_mapping(
        interactive_config(tmp_path, read={"mode": "poll"})
    )
    assert poll.command_buttons_for("execute") == {}


def test_expected_commands_reads_the_marker_on_agent_comments_only():
    """R1.1: the phase-selection checklist mirror — and nothing else — expects
    `execute`."""
    assert expected_commands(checklist_event()) == ("execute",)
    assert expected_commands(checklist_event(text="no marker here")) == ()
    assert expected_commands(checklist_event(event_type="comment.human")) == ()
    assert expected_commands(checklist_event(event_type="session.awaiting_input")) == ()


def test_the_marker_is_the_selection_hooks():
    """R1.1: the renderer keys on the hook's own marker, pinned so a rename in
    either place fails here rather than silently losing the button."""
    from the_loop.graph.hooks.selection import SELECTION_MARKER

    assert PHASE_SELECTION_MARKER == SELECTION_MARKER


def test_the_checklist_mirror_earns_an_execute_button_with_the_keyword_as_value(
    tmp_path, monkeypatch
):
    """R1.1, R1.5: posted through the channel, the checklist carries a link button
    and an Execute button whose value is the keyword and whose action_id is under
    the prefix the action handler reads."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    make_channel(tmp_path, client).post(checklist_event())
    reply = client.posted[-1]  # the root came first (issue-312)
    assert buttons(reply["blocks"]) == [
        (f"{ACTION_PREFIX}open", "https://github.com/o/r/issues/7#c1"),
        (f"{ACTION_PREFIX}command:execute", "the-loop execute"),
    ]
    execute = reply["blocks"][-1]["elements"][1]
    assert execute["text"]["text"] == "Execute" and execute["style"] == "primary"


def test_no_command_button_without_socket_and_the_grant(tmp_path, monkeypatch):
    """R1.4 / A7: in poll mode, or without `control.command`, the same message
    carries the link button alone — a button nobody can receive is worse than none."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    for slack in (
        {"read": {"mode": "poll"}},
        {"publish": ["work-item.reply", "gate.feedback"]},
    ):
        client = FakeSlackClient()
        make_channel(tmp_path, client, **slack).post(checklist_event())
        assert buttons(client.posted[-1]["blocks"]) == [
            (f"{ACTION_PREFIX}open", "https://github.com/o/r/issues/7#c1")
        ]


def test_a_renamed_keyword_is_the_buttons_value(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    make_channel(tmp_path, client, control={"keywords": {"execute": "loop go"}}).post(
        checklist_event()
    )
    assert (f"{ACTION_PREFIX}command:execute", "loop go") in buttons(
        client.posted[-1]["blocks"]
    )


def test_a_disabled_keyword_renders_no_button(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    make_channel(tmp_path, client, control={"keywords": {"execute": ""}}).post(
        checklist_event()
    )
    assert all(
        not action.startswith(f"{ACTION_PREFIX}command:")
        for action, _ in buttons(client.posted[-1]["blocks"])
    )


def test_render_blocks_puts_command_buttons_before_the_approval_pair():
    """A command button is the message's call to action; the Approve pair stays
    where issue-309 put it, after."""
    event = checklist_event(event_type="phase-approval-pending")
    blocks = render_blocks(
        event, "normal", interactive=True, commands={"execute": "the-loop execute"}
    )
    assert [a for a, _ in buttons(blocks)] == [
        f"{ACTION_PREFIX}open",
        f"{ACTION_PREFIX}command:execute",
        f"{ACTION_PREFIX}approve",
        f"{ACTION_PREFIX}changes",
    ]
    assert render_blocks(event, "normal", commands={}) == render_blocks(event, "normal")


def test_reply_blocks_carry_the_start_button():
    """R1.2: the kickoff reply's blocks — a section and, with a command, one
    actions block; with none, the section alone."""
    blocks = render_reply_blocks("Opened github:o/r#42", {"start": "the-loop start"})
    assert blocks[0] == {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "Opened github:o/r#42"},
    }
    assert buttons(blocks) == [(f"{ACTION_PREFIX}command:start", "the-loop start")]
    assert blocks[1]["elements"][0]["text"]["text"] == "Start"
    assert render_reply_blocks("Opened github:o/r#42", {}) == [blocks[0]]


def test_the_button_tables_agree():
    """Every command button has a name for the outcome line, and the names are
    the labels a member saw."""
    for command, label in COMMAND_BUTTONS.items():
        assert BUTTON_NAMES[f"{ACTION_PREFIX}command:{command}"] == label
    assert BUTTON_NAMES[f"{ACTION_PREFIX}approve"] == "Approve"
    assert BUTTON_NAMES[f"{ACTION_PREFIX}changes"] == "Request changes"


# -- R2: the outcome on the pressed message ------------------------------------


def press_reply(author="UHUMAN", ts="1750.5"):
    return InboundReply(
        channel="slack",
        work_item="github:o/r#7",
        author=author,
        text="the-loop execute",
        thread="1700.1",
        ts=ts,
        channel_id="C123",
    )


def test_report_press_rewrites_the_message_with_the_outcome(tmp_path, monkeypatch):
    """R2.1, R2.2: a landed press — the command button gone, the link kept, a
    context line naming the button, the member, the record and its link."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    channel = make_channel(tmp_path, client)
    press = a_press()
    ok = channel.report_press(
        press_reply(),
        press["message"],
        f"{ACTION_PREFIX}command:execute",
        {
            "outcome": "processed",
            "event": "control.command",
            "mirrored": True,
            "url": "https://github.com/o/r/issues/7#c9",
        },
    )
    assert ok is True and len(client.updates) == 1
    channel_id, ts, text, blocks = client.updates[0]
    assert (channel_id, ts) == ("C123", "1750.5")
    assert buttons(blocks) == [
        (f"{ACTION_PREFIX}open", "https://github.com/o/r/issues/7#c1")
    ]
    assert blocks[0] == press["message"]["blocks"][0]  # the header survives
    line = blocks[-1]
    assert line["type"] == "context"
    words = line["elements"][0]["text"]
    assert words.startswith("✅ *Execute*")
    assert "<@UHUMAN>" in words
    assert "recorded on <https://github.com/o/r/issues/7#c9|github:o/r#7>" in words
    assert "next ingress" in words
    assert text.startswith(press["message"]["text"]) and "Execute" in text


def test_a_failed_press_keeps_the_buttons_and_says_why(tmp_path, monkeypatch):
    """R2.2: a press whose record did not land keeps every button — the retry —
    beside a ⚠️ line carrying the ledger's error."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    press = a_press()
    make_channel(tmp_path, client).report_press(
        press_reply(),
        press["message"],
        f"{ACTION_PREFIX}command:execute",
        {
            "outcome": "processed",
            "event": "control.command",
            "mirrored": False,
            "error": "gh exited 1",
        },
    )
    _, _, _, blocks = client.updates[0]
    assert buttons(blocks) == buttons(press["message"]["blocks"])
    words = blocks[-1]["elements"][0]["text"]
    assert words.startswith("⚠️ *Execute*") and "not recorded: gh exited 1" in words


@pytest.mark.parametrize(
    "event,outcome,expected",
    [
        (
            "gate.feedback",
            {"mirrored": True, "url": "https://x/c2"},
            "answer of record",
        ),
        ("work-item.reply", {"mirrored": True, "delivered": True}, "delivered"),
        (
            "work-item.reply",
            {"mirrored": True, "delivered": False, "error": "no session"},
            "not delivered: no session",
        ),
    ],
)
def test_the_press_line_says_what_each_kind_did(
    tmp_path, monkeypatch, event, outcome, expected
):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    make_channel(tmp_path, client).report_press(
        press_reply(),
        a_press()["message"],
        f"{ACTION_PREFIX}approve",
        {"outcome": "processed", "event": event, **outcome},
    )
    assert expected in client.updates[0][3][-1]["elements"][0]["text"]


def test_an_approve_press_is_reported_too(tmp_path, monkeypatch):
    """R2.4: the issue-309 pair gets the same edit — both of its buttons go."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    message = {
        "ts": "1750.5",
        "text": "Approval needed",
        "blocks": render_blocks(
            checklist_event(event_type="phase-approval-pending"),
            "normal",
            interactive=True,
        ),
    }
    make_channel(tmp_path, client).report_press(
        press_reply(),
        message,
        f"{ACTION_PREFIX}approve",
        {"outcome": "processed", "event": "gate.feedback", "mirrored": True},
    )
    _, _, _, blocks = client.updates[0]
    assert buttons(blocks) == [
        (f"{ACTION_PREFIX}open", "https://github.com/o/r/issues/7#c1")
    ]
    assert blocks[-1]["elements"][0]["text"].startswith("✅ *Approve*")


def test_the_press_report_never_echoes_the_value_or_a_token(tmp_path, monkeypatch):
    """R2.6 / A4: the line is fixed words, the button's name from its action_id,
    the member id, the ref and the record URL — never the payload's text."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-supersecret")
    client = FakeSlackClient()
    message = a_press()["message"]
    message["blocks"][-1]["elements"][1]["text"]["text"] = "Launch the missiles"
    reply = InboundReply(
        channel="slack",
        work_item="github:o/r#7",
        author="UHUMAN",
        text="the-loop execute; rm -rf /",
        thread="1700.1",
        ts="1750.5",
        channel_id="C123",
    )
    make_channel(tmp_path, client).report_press(
        reply,
        message,
        f"{ACTION_PREFIX}command:execute",
        {"outcome": "processed", "event": "control.command", "mirrored": True},
    )
    _, _, text, blocks = client.updates[0]
    line = blocks[-1]["elements"][0]["text"]
    for forbidden in ("rm -rf", "Launch", "xoxb"):
        assert forbidden not in line and forbidden not in text.splitlines()[-1]
    assert "*Execute*" in line


def test_a_refused_update_is_an_event_and_false(tmp_path, monkeypatch):
    """R2.3 / A5: Slack refuses to edit a message the bot did not post — the
    report is `channel.press_report_failed` and the outcome is untouched."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    log = tmp_path / "events.jsonl"
    eventlog.configure("test", path=log, enabled=True)
    try:
        client = FakeSlackClient(refuse_update="cant_update_message")
        ok = make_channel(tmp_path, client).report_press(
            press_reply(),
            a_press()["message"],
            f"{ACTION_PREFIX}command:execute",
            {"outcome": "processed", "event": "control.command", "mirrored": True},
        )
    finally:
        eventlog.reset()
    assert ok is False and client.updates == []
    events = [json.loads(line) for line in log.read_text().splitlines()]
    failed = [e for e in events if e["event"] == "channel.press_report_failed"]
    assert len(failed) == 1
    assert failed[0]["action"] == f"{ACTION_PREFIX}command:execute"
    assert "cant_update_message" in failed[0]["error"]
    assert "the-loop execute" not in log.read_text()


def test_report_press_without_a_token_is_quiet(tmp_path, monkeypatch):
    monkeypatch.delenv(DEFAULT_BOT_TOKEN_ENV, raising=False)
    client = FakeSlackClient()
    ok = make_channel(tmp_path, client).report_press(
        press_reply(),
        a_press()["message"],
        f"{ACTION_PREFIX}command:execute",
        {"outcome": "processed", "event": "control.command", "mirrored": True},
    )
    assert ok is False and client.updates == []


def test_a_message_without_blocks_gets_its_text_and_the_line(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    make_channel(tmp_path, client).report_press(
        press_reply(),
        {"ts": "1750.5", "text": "plain"},
        f"{ACTION_PREFIX}command:execute",
        {"outcome": "processed", "event": "control.command", "mirrored": True},
    )
    _, _, _, blocks = client.updates[0]
    assert [b["type"] for b in blocks] == ["section", "context"]
    assert blocks[0]["text"]["text"] == "plain"


def test_a_press_report_event_carries_the_action_never_text(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    log = tmp_path / "events.jsonl"
    eventlog.configure("test", path=log, enabled=True)
    try:
        make_channel(tmp_path, FakeSlackClient()).report_press(
            press_reply(),
            a_press()["message"],
            f"{ACTION_PREFIX}command:execute",
            {"outcome": "processed", "event": "control.command", "mirrored": True},
        )
    finally:
        eventlog.reset()
    events = [json.loads(line) for line in log.read_text().splitlines()]
    reported = [e for e in events if e["event"] == "channel.press_reported"]
    assert len(reported) == 1
    assert reported[0]["action"] == f"{ACTION_PREFIX}command:execute"
    assert reported[0]["outcome"] == "landed"
    assert reported[0]["work_item"] == "github:o/r#7"
    assert "the-loop execute" not in log.read_text()
    for name in ("channel.press_reported", "channel.press_report_failed"):
        assert name in eventlog.EVENT_TYPES


# -- the pipeline: a press through the ordinary path ----------------------------


def _wire(monkeypatch, records, deliveries=None, record_ok=True):
    monkeypatch.setattr(
        "the_loop.comments.post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (
            records.append((item.ref, body))
            or ((True, "", "https://x/c9") if record_ok else (False, "gh exited 1", ""))
        ),
    )
    monkeypatch.setattr(
        "the_loop.core.sessions.reply_session",
        lambda ref, text, actor="", comment=True, config=None: (
            (deliveries if deliveries is not None else []).append(text)
            or {"delivered": True}
        ),
    )
    monkeypatch.setattr(inbound, "_at_human_gate", lambda ref, cfg: False)


def _bind(tmp_path, monkeypatch, client, config):
    """A bound thread, opened by posting the checklist through the channel."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    channel = make_channel(tmp_path, client, config=config)
    channel.post(checklist_event())
    return client.posted[0]["channel"], "1700.000001", client.posted[-1]


def test_process_reply_carries_the_records_url(tmp_path, monkeypatch):
    """R2.1: the outcome dict names where the record lives, so the report can
    link it; the dropped shapes are unchanged."""
    records = []
    _wire(monkeypatch, records)
    config = interactive_config(tmp_path)
    client = FakeSlackClient()
    _, thread, _ = _bind(tmp_path, monkeypatch, client, config)
    outcome = inbound.process_reply(
        InboundReply(
            channel="slack",
            work_item="github:o/r#7",
            author="UHUMAN",
            text="the-loop execute",
            thread=thread,
            ts="1800.1",
            channel_id="C123",
        ),
        SlackChannelConfig.from_mapping(config),
        config,
    )
    assert outcome["outcome"] == "processed" and outcome["event"] == "control.command"
    assert outcome["mirrored"] is True and outcome["url"] == "https://x/c9"
    assert "error" not in outcome
    assert inbound.process_reply(
        InboundReply(
            channel="slack",
            work_item="github:o/r#7",
            author="UEVIL",
            text="the-loop execute",
            thread=thread,
            ts="1800.2",
        ),
        SlackChannelConfig.from_mapping(config),
        config,
    ) == {"outcome": "unauthorized-actor"}


def test_an_unlisted_members_press_edits_nothing(tmp_path, monkeypatch):
    """A1 / R2.3: dropped before the record, no edit, no answer — a refusal
    leaves no mark (decision-111 D1)."""
    records = []
    _wire(monkeypatch, records)
    config = interactive_config(tmp_path)
    client = FakeSlackClient()
    _, thread, _ = _bind(tmp_path, monkeypatch, client, config)
    outcome = inbound.handle_socket_action(
        a_press(author="UEVIL", thread=thread),
        config,
        client_factory=lambda token: client,
    )
    assert outcome == {"outcome": "unauthorized-actor"}
    assert records == [] and client.updates == [] and client.reactions == []


def test_a_press_after_the_grant_was_removed_is_dropped_and_edits_nothing(
    tmp_path, monkeypatch
):
    """A3: the grant is checked at press time, after classification — a button
    rendered under a grant since withdrawn is `unpublishable-event`."""
    records = []
    _wire(monkeypatch, records)
    client = FakeSlackClient()
    _, thread, _ = _bind(tmp_path, monkeypatch, client, interactive_config(tmp_path))
    withdrawn = interactive_config(tmp_path, publish=["work-item.reply"])
    outcome = inbound.handle_socket_action(
        a_press(thread=thread), withdrawn, client_factory=lambda token: client
    )
    assert outcome == {"outcome": "unpublishable-event"}
    assert records == [] and client.updates == []


def test_a_crafted_value_is_judged_as_text(tmp_path, monkeypatch):
    """A2: a payload value that is not a keyword is a reply, judged by the
    ordinary grants — here not granted, so dropped; nothing runs, nothing edits."""
    records, deliveries = [], []
    _wire(monkeypatch, records, deliveries)
    config = interactive_config(tmp_path, publish=["control.command"])
    client = FakeSlackClient()
    _, thread, _ = _bind(tmp_path, monkeypatch, client, config)
    outcome = inbound.handle_socket_action(
        a_press(value="rm -rf / && echo pwned", thread=thread),
        config,
        client_factory=lambda token: client,
    )
    assert outcome == {"outcome": "unpublishable-event"}
    assert records == [] and deliveries == [] and client.updates == []


def test_two_presses_are_judged_independently(tmp_path, monkeypatch):
    """A6: a double press before the first edit lands is two records — the
    ingress and the gates absorb a repeated keyword."""
    records = []
    _wire(monkeypatch, records)
    config = interactive_config(tmp_path)
    client = FakeSlackClient()
    _, thread, _ = _bind(tmp_path, monkeypatch, client, config)
    for _ in range(2):
        outcome = inbound.handle_socket_action(
            a_press(thread=thread), config, client_factory=lambda token: client
        )
        assert outcome["outcome"] == "processed"
    assert len(records) == 2 and len(client.updates) == 2


# -- R3: `channels status` says how --------------------------------------------


def _status(tmp_path, monkeypatch, capsys, config):
    from the_loop.commands.channels_cmd import ChannelsCommand

    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    (tmp_path / "cli-config.yaml").write_text(json.dumps(config), encoding="utf-8")
    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    assert ChannelsCommand().run(parser.parse_args(["status"])) == 0
    return capsys.readouterr().out


def test_status_names_both_button_sets_and_the_missing_steps(
    tmp_path, monkeypatch, capsys
):
    """R3.1, R3.2: a 13.9.0 default (poll, no grants, no app token) — both sets
    off, and every step printed, with the token's presence and never a value."""
    monkeypatch.delenv(DEFAULT_APP_TOKEN_ENV, raising=False)
    out = _status(tmp_path, monkeypatch, capsys, cli_config(tmp_path))
    assert "buttons:      Approve / Request changes: off · Execute / Start: off" in out
    assert "1. mint an app-level token" in out
    assert "App-Level Tokens" in out and "connections:write" in out
    assert f"export it as {DEFAULT_APP_TOKEN_ENV} (now: unset)" in out
    assert "2. set channels.slack.read.mode: socket (now: poll)" in out
    assert "3. add to channels.slack.publish: gate.feedback" in out
    assert "control.command (Execute / Start)" in out
    assert "4. the-loop restart" in out


def test_status_prints_no_steps_when_buttons_are_on(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(DEFAULT_APP_TOKEN_ENV, "xapp-supersecret")
    out = _status(tmp_path, monkeypatch, capsys, interactive_config(tmp_path))
    assert "buttons:      Approve / Request changes: on · Execute / Start: on" in out
    assert "mint an app-level token" not in out and "the-loop restart" not in out
    assert "xapp-supersecret" not in out


def test_status_prints_only_the_steps_that_apply(tmp_path, monkeypatch, capsys):
    """Socket mode and the gate grant, no app token, no control.command: the
    Approve pair is on paper but nothing can connect — steps 1, 3 and 4 only."""
    monkeypatch.delenv(DEFAULT_APP_TOKEN_ENV, raising=False)
    out = _status(
        tmp_path,
        monkeypatch,
        capsys,
        interactive_config(tmp_path, publish=["work-item.reply", "gate.feedback"]),
    )
    assert "buttons:      Approve / Request changes: on · Execute / Start: off" in out
    assert "1. mint an app-level token" in out
    assert "read.mode: socket" not in out.split("buttons:")[1].split("kickoff:")[0]
    # Only the steps that apply, numbered contiguously: token, grant, restart.
    assert "2. add to channels.slack.publish: control.command (Execute / Start)" in out
    assert "gate.feedback (Approve" not in out
    assert "3. the-loop restart" in out and "4." not in out.split("kickoff:")[0]
    monkeypatch.setenv(DEFAULT_APP_TOKEN_ENV, "xapp-set")
    out = _status(tmp_path, monkeypatch, capsys, interactive_config(tmp_path))
    assert "Execute / Start: on" in out and "1. mint" not in out
