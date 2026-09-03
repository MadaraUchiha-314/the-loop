"""Unit tests for the event bus, the catalog, the envelope, the GitHub ledger and
the Slack renderer (issue-309). No network: `gh` and the Slack SDK are faked at
their injection points."""

from __future__ import annotations

import json
import logging

import pytest

from the_loop import eventlog
from the_loop.authz import is_self_authored
from the_loop.channels import envelope as env
from the_loop.channels.base import (
    Event,
    PostResult,
    PublishResult,
    ledger_name,
    load_channels,
    load_ledger,
)
from the_loop.channels.bus import broadcast, open_conversation, publish
from the_loop.channels.events import (
    APPROVAL_EVENTS,
    EVENTS,
    NOTIFICATION_EVENTS,
    PUBLISHABLE_EVENTS,
    SUBSCRIBABLE_EVENTS,
    is_recorded,
)
from the_loop.channels.github import GitHubLedger, issue_title
from the_loop.channels.publishers import (
    comment_publisher,
    conversation_opener,
    publish_comment,
)
from the_loop.channels.slack import (
    APPROVE_VALUE,
    CHANGES_VALUE,
    SlackChannelConfig,
    render_blocks,
)
from the_loop.control import ControlConfig, parse_command
from the_loop.identity import Principal

PERSON = Principal(ids={"github": "octocat", "slack": "U1"}, name="Octo")


class FakeChannel:
    """A subscriber that records what it was handed."""

    name = "fake"

    def __init__(self, subscribe=(), fail=False, name="fake"):
        self.name = name
        self._subscribe = set(subscribe)
        self.fail = fail
        self.posted = []

    def subscribes(self, event_type):
        return event_type in self._subscribe

    def may_publish(self, event_type):
        return False

    def post(self, event):
        if self.fail:
            raise RuntimeError("down")
        self.posted.append(event)
        return PostResult(channel=self.name, ok=True, thread="t1")


class FakeLedger:
    name = "github"

    def __init__(self, ok=True, ref="", url="https://gh/c/1"):
        self.records = []
        self.ok, self.ref, self.url = ok, ref, url

    def record(self, event):
        self.records.append(event)
        return PostResult(
            channel=self.name, ok=self.ok, url=self.url, ref=self.ref, error="nope"
        )


def an_event(event_type="session.awaiting_input", source="cli", **kw):
    return Event(
        event_type=event_type,
        work_item=kw.pop("work_item", "github:o/r#7"),
        text=kw.pop("text", "A or B?"),
        source=source,
        **kw,
    )


# -- the catalog (R1.1, R1.2, R1.5) -------------------------------------------------


def test_the_catalog_has_one_row_per_event_with_four_answers():
    for name in (
        "session.awaiting_input",
        *NOTIFICATION_EVENTS,
        "comment.human",
        "comment.agent",
        "work-item.reply",
        "gate.feedback",
        "control.command",
        "work-item.create",
    ):
        assert name in EVENTS, name
    assert set(PUBLISHABLE_EVENTS) == {
        "work-item.reply",
        "gate.feedback",
        "control.command",
        "work-item.create",
    }
    # A publishable event is never subscribable, and every subscribable one is
    # in the view the config parser and `channels status` read.
    assert not set(PUBLISHABLE_EVENTS) & set(SUBSCRIBABLE_EVENTS)
    assert set(SUBSCRIBABLE_EVENTS) == {
        n for n, spec in EVENTS.items() if spec.subscribable
    }
    assert set(APPROVAL_EVENTS) <= set(NOTIFICATION_EVENTS)


def test_recorded_is_the_ask_and_the_channel_events_and_nothing_else():
    """D6: notifications are not recorded — `request-review` already comments."""
    assert is_recorded("session.awaiting_input")
    for name in PUBLISHABLE_EVENTS:
        assert is_recorded(name), name
    for name in (*NOTIFICATION_EVENTS, "comment.human", "comment.agent"):
        assert not is_recorded(name), name
    assert not is_recorded("custom.notify")


# -- the envelope (R3.2, R3.7) -------------------------------------------------------


def test_the_envelope_round_trips_and_carries_every_id():
    body = env.stamp(
        "hello",
        env.Envelope(type="gate.feedback", source="slack", actor=PERSON.to_dict()),
    )
    parsed = env.parse(body)
    assert parsed is not None
    assert parsed.type == "gate.feedback" and parsed.source == "slack"
    assert parsed.actor == {"github": "octocat", "slack": "U1"}
    assert parsed.ts  # stamped
    assert env.has_envelope(body) and not env.has_envelope("hello")
    # Idempotent per (type, source): stamping twice writes once.
    assert (
        env.stamp(body, env.Envelope("gate.feedback", "slack")).count("the-loop:event")
        == 1
    )


@pytest.mark.parametrize(
    "junk",
    [
        "<!-- the-loop:event not json -->",
        '<!-- the-loop:event {"type":"x"} -->',  # no source
        '<!-- the-loop:event {"type":"x","source":"slack","actor":"me"} -->',
        '<!-- the-loop:event {"type":"x","source":"slack","extra":1} -->',
        "<!-- the-loop:event [1,2] -->",
        '<!-- the-loop:event {"type":"","source":"slack"} -->',
    ],
)
def test_anything_but_the_envelopes_own_shape_is_no_envelope(junk):
    assert env.parse(junk) is None


def test_an_envelope_value_cannot_close_the_html_comment_early():
    body = env.stamp("x", env.Envelope("t", "slack", actor={"slack": "--> <b>"}))
    parsed = env.parse(body)
    assert parsed is not None and parsed.actor["slack"] == "--> <b>"
    assert body.count("-->") == 1


# -- the bus (R1.3, R1.4, R8.1) -------------------------------------------------------


def test_publish_records_first_then_fans_out_and_skips_the_source(tmp_path):
    ledger = FakeLedger()
    slack = FakeChannel(subscribe=["session.awaiting_input"], name="slack")
    cli = FakeChannel(subscribe=["session.awaiting_input"], name="cli")
    result = publish(an_event(), channels=[slack, cli], ledger=ledger)
    assert isinstance(result, PublishResult)
    assert result.recorded and result.record is not None
    assert result.record.url == "https://gh/c/1"
    assert len(ledger.records) == 1
    # The record's URL rides onto the event every subscriber sees.
    assert slack.posted[0].url == "https://gh/c/1"
    assert cli.posted == []  # the source never hears its own event
    assert result.delivered


def test_publish_never_records_an_event_that_started_on_the_ledger():
    ledger = FakeLedger()
    slack = FakeChannel(subscribe=["comment.human"], name="slack")
    publish(an_event("comment.human", source="github"), channels=[slack], ledger=ledger)
    assert ledger.records == [] and len(slack.posted) == 1


def test_publish_honours_the_catalog_and_the_explicit_record_flag():
    ledger = FakeLedger()
    publish(
        an_event("phase-approval-pending", source="loop"), channels=[], ledger=ledger
    )
    assert ledger.records == []  # not recorded by catalog
    publish(
        an_event("phase-approval-pending", source="loop"),
        channels=[],
        ledger=ledger,
        record=True,
    )
    assert len(ledger.records) == 1
    publish(an_event(), channels=[], ledger=ledger, record=False)
    assert len(ledger.records) == 1


def test_a_failing_ledger_or_channel_is_a_result_never_an_exception(monkeypatch):
    log = []
    monkeypatch.setattr(eventlog, "emit", lambda event, **f: log.append((event, f)))
    ledger = FakeLedger(ok=False)
    down = FakeChannel(subscribe=["session.awaiting_input"], fail=True)
    result = publish(an_event(), channels=[down], ledger=ledger)
    assert not result.recorded and not result.delivered
    assert [name for name, _ in log] == [
        "bus.record_failed",
        "channel.post_failed",
        "bus.published",
    ]
    assert log[0][1]["ledger"] == "github"
    assert "A or B" not in json.dumps(log)  # ids only, never text


def test_broadcast_is_publish_without_a_record():
    ledger = FakeLedger()
    fake = FakeChannel(subscribe=["phase-approval-pending"])
    posts = broadcast("phase-approval-pending", "github:o/r#7", "x", channels=[fake])
    assert len(posts) == 1 and posts[0].ok and ledger.records == []


def test_the_ledger_is_github_and_an_unknown_name_never_resolves_to_none(caplog):
    assert ledger_name({}) == "github"
    assert ledger_name({"channels": {"ledger": "github"}}) == "github"
    with caplog.at_level(logging.ERROR, logger="the-loop.channels"):
        assert ledger_name({"channels": {"ledger": "jira"}}) == "github"
    assert any("channels.ledger" in r.message for r in caplog.records)
    assert isinstance(load_ledger({}), GitHubLedger)
    assert load_channels({}) == []  # the ledger is not a subscriber


# -- the ledger's record shapes (R3.3–R3.6, A7, A8) -----------------------------------


def ledger_with_fakes(cli_config=None):
    posts, issues = [], []

    def post(item, body, gh_binary="gh"):
        posts.append((item.ref, body, gh_binary))
        return True, "", "https://gh/c/9"

    def create(repo, title, body, labels, gh_binary="gh"):
        issues.append((repo, title, body, list(labels), gh_binary))
        return True, "", "github:o/r#42", "https://gh/o/r/issues/42"

    return (
        GitHubLedger(cli_config, post_comment=post, create_issue=create),
        posts,
        issues,
    )


def test_the_ask_record_is_the_marked_question_with_an_envelope():
    ledger, posts, _ = ledger_with_fakes()
    result = ledger.record(an_event(actor=PERSON))
    assert result.ok and result.url == "https://gh/c/9"
    ref, body, _ = posts[0]
    assert ref == "github:o/r#7"
    assert body.startswith("A or B?") and is_self_authored(body)
    parsed = env.parse(body)
    assert parsed is not None
    assert parsed and parsed.type == "session.awaiting_input" and parsed.source == "cli"


def test_a_reply_record_is_marked_quoted_and_defanged():
    ledger, posts, _ = ledger_with_fakes({"routing": {"control": {"keywords": {}}}})
    ledger.record(
        an_event(
            "work-item.reply", source="slack", text="please the-loop stop", actor=PERSON
        )
    )
    body = posts[0][1]
    assert is_self_authored(body)
    assert "> please" in body and "Octo" in body and "slack:U1" in body
    assert parse_command(body.split("<!--")[0], ControlConfig()).command is None


@pytest.mark.parametrize("event_type", ["gate.feedback", "control.command"])
def test_a_relayed_record_is_unmarked_with_the_words_intact(event_type):
    """R3.5 — the ledger's ingress must read it as the person's own comment."""
    ledger, posts, _ = ledger_with_fakes()
    ledger.record(
        an_event(
            event_type, source="slack", text="the-loop start\napproved", actor=PERSON
        )
    )
    body = posts[0][1]
    assert not is_self_authored(body)
    assert parse_command(body, ControlConfig()).command == "start"
    assert "approved" in body and "slack" in body
    parsed = env.parse(body)
    assert parsed is not None
    assert parsed and parsed.type == event_type
    assert parsed.actor == {"github": "octocat", "slack": "U1"}  # A8: from config


def test_a_kickoff_record_is_an_issue_with_only_configured_labels():
    """R3.6, A7 — unmarked (armable), enveloped, labels from config alone."""
    ledger, _, issues = ledger_with_fakes(
        {"integrations": {"github": {"cli": {"binary": "hub"}}}}
    )
    result = ledger.record(
        Event(
            event_type="work-item.create",
            work_item="",
            text="# Ship the thing\n\nlabels: evil\nthe details",
            source="slack",
            actor=PERSON,
            detail={"repo": "o/r", "labels": "the-loop: auto-execute, bug"},
        )
    )
    assert result.ok and result.ref == "github:o/r#42"
    repo, title, body, labels, binary = issues[0]
    assert (repo, title, labels, binary) == (
        "o/r",
        "Ship the thing",
        ["the-loop: auto-execute", "bug"],
        "hub",
    )
    assert not is_self_authored(body)
    parsed = env.parse(body)
    assert parsed is not None and parsed.type == "work-item.create"
    assert "Opened from the **slack** channel" in body


def test_a_kickoff_without_a_repo_records_nothing():
    ledger, _, issues = ledger_with_fakes()
    result = ledger.record(
        Event(event_type="work-item.create", work_item="", text="x", source="slack")
    )
    assert not result.ok and "kickoff-disabled" in result.error and issues == []


def test_issue_titles_are_the_first_line_capped():
    assert issue_title("\n\n## Fix login \n\nbody") == "Fix login"
    assert issue_title("") == "Work item from a channel"
    assert len(issue_title("x" * 200)) == 80


def test_the_ledger_refuses_a_non_github_ref_and_a_standing_ref():
    ledger, posts, _ = ledger_with_fakes()
    assert not ledger.record(an_event(work_item="jira:PROJ-1")).ok
    assert not ledger.record(an_event(work_item="standing:supervisor")).ok
    assert posts == []


# -- ingress publishers (R6.1, A10) ----------------------------------------------------


def test_publish_comment_skips_enveloped_records_and_unknown_kinds(monkeypatch):
    seen = []
    monkeypatch.setattr(
        "the_loop.channels.bus.publish",
        lambda event, cfg, **k: seen.append(event) or PublishResult(),
    )
    enveloped = env.stamp("hi", env.Envelope("work-item.reply", "slack"))
    assert (
        publish_comment("human", "github:o/r#7", "octocat", enveloped, "", {}) is False
    )
    assert publish_comment("nope", "github:o/r#7", "octocat", "hi", "", {}) is False
    assert publish_comment("human", "github:o/r#7", "octocat", "  ", "", {}) is False
    publish_comment("agent", "github:o/r#7", "octocat", "hi", "https://c", {})
    assert len(seen) == 1
    assert seen[0].event_type == "comment.agent" and seen[0].source == "github"
    assert seen[0].url == "https://c" and seen[0].detail == {"author": "octocat"}


def test_the_daemon_publisher_reads_the_config_per_call(monkeypatch):
    seen = []
    monkeypatch.setattr(
        "the_loop.channels.publishers.publish_comment",
        lambda *a: seen.append(a) or True,
    )
    configs = [{}, {"channels": {"slack": {"enabled": True}}}]
    publisher = comment_publisher(lambda: configs.pop(0))
    publisher("human", "github:o/r#7", "a", "b", "")  # no channels: not even built
    publisher("human", "github:o/r#7", "a", "b", "")
    assert len(seen) == 1
    broken = comment_publisher(lambda: (_ for _ in ()).throw(OSError("mid-edit")))
    broken("human", "github:o/r#7", "a", "b", "")  # never raises
    assert len(seen) == 1


# -- Slack rendering (R4.2, R4.3, R4.5) -------------------------------------------------


def _types(blocks):
    return [b["type"] for b in blocks]


def _buttons(blocks):
    actions = [b for b in blocks if b["type"] == "actions"]
    return [e["action_id"] for b in actions for e in b["elements"]]


def test_render_blocks_is_header_text_and_a_link_button():
    event = an_event(url="https://gh/o/r/issues/7", actor=PERSON)
    blocks = render_blocks(event, "normal")
    assert _types(blocks) == ["header", "section", "actions"]
    assert "Question from the agent" in blocks[0]["text"]["text"]
    assert "Octo" in blocks[0]["text"]["text"]
    assert blocks[1]["text"]["text"] == "A or B?"
    assert _buttons(blocks) == ["the-loop:open"]
    assert blocks[2]["elements"][0]["url"] == "https://gh/o/r/issues/7"


def test_render_blocks_verbosity_levels_are_strict_supersets():
    event = an_event(url="https://x", detail={"actor": "agent", "excerpt": "## R1"})
    quiet = render_blocks(event, "quiet")
    normal = render_blocks(event, "normal")
    verbose = render_blocks(event, "verbose")
    assert _types(quiet) == ["header", "actions"]
    assert _types(normal) == ["header", "section", "section", "actions"]  # + excerpt
    assert _types(verbose) == ["header", "section", "section", "context", "actions"]
    assert "*actor:* agent" in verbose[3]["elements"][0]["text"]


def test_render_blocks_caps_text_and_points_at_the_link():
    event = an_event(text="x" * 5000, url="https://x")
    blocks = render_blocks(event, "normal", max_chars=400)
    text = blocks[1]["text"]["text"]
    assert text.startswith("x" * 400) and "more characters — see the link" in text


@pytest.mark.parametrize("event_type", APPROVAL_EVENTS)
def test_approve_buttons_only_when_interactive(event_type):
    event = an_event(event_type, source="loop", url="https://x")
    assert _buttons(render_blocks(event, "normal", interactive=False)) == [
        "the-loop:open"
    ]
    blocks = render_blocks(event, "normal", interactive=True)
    assert _buttons(blocks) == ["the-loop:open", "the-loop:approve", "the-loop:changes"]
    values = [e.get("value") for e in blocks[-1]["elements"]]
    assert values == [None, APPROVE_VALUE, CHANGES_VALUE]


def test_a_non_approval_event_never_carries_approve_buttons():
    blocks = render_blocks(
        an_event("comment.human", source="github"), "normal", interactive=True
    )
    assert "the-loop:approve" not in _buttons(blocks)


def test_interactive_needs_socket_mode_and_the_grant():
    base = {"channels": {"slack": {"enabled": True, "channel": "C1"}}}
    assert SlackChannelConfig.from_mapping(base).interactive is False
    socket = {"channels": {"slack": {"enabled": True, "read": {"mode": "socket"}}}}
    assert SlackChannelConfig.from_mapping(socket).interactive is False
    both = {
        "channels": {
            "slack": {
                "enabled": True,
                "read": {"mode": "socket"},
                "publish": ["work-item.reply", "gate.feedback"],
            }
        }
    }
    assert SlackChannelConfig.from_mapping(both).interactive is True


# -- grants (R2.1–R2.5) -------------------------------------------------------------


def test_publish_grants_default_to_reply_and_ignore_what_the_catalog_forbids(caplog):
    assert SlackChannelConfig.from_mapping({}).publish == ("work-item.reply",)
    with caplog.at_level(logging.WARNING, logger="the-loop.channels"):
        config = SlackChannelConfig.from_mapping(
            {
                "channels": {
                    "slack": {
                        "publish": [
                            "gate.feedback",
                            "phase-approval-pending",  # subscribable, not publishable
                            "typo.event",
                            "gate.feedback",
                        ]
                    }
                }
            }
        )
    assert config.publish == ("gate.feedback",)
    assert sum("not a publishable event" in r.message for r in caplog.records) == 2
    assert SlackChannelConfig.from_mapping(
        {"channels": {"slack": {"publish": "gate.feedback"}}}
    ).publish == ("work-item.reply",)


def test_slack_member_ids_come_from_routing_authorized_users():
    """R5.3 — the channel reads the `slack` id of each person entry."""
    config = SlackChannelConfig.from_mapping(
        {
            "routing": {
                "authorizedUsers": [
                    "octocat",
                    {"github": "dana", "slack": "U2"},
                    {"slack": "U3"},
                ]
            },
            "channels": {"slack": {"enabled": True}},
        }
    )
    assert config.authorized_users == ("U2", "U3")
    assert len(config.principals) == 3


def test_kickoff_needs_the_grant_and_a_repo():
    def cfg(**slack):
        return SlackChannelConfig.from_mapping(
            {"channels": {"slack": {"enabled": True, "channel": "C1", **slack}}}
        )

    assert cfg().kickoff_enabled is False
    assert cfg(publish=["work-item.create"]).kickoff_enabled is False
    assert cfg(kickoff={"repo": "o/r"}).kickoff_enabled is False
    granted = cfg(
        publish=["work-item.create"], kickoff={"repo": "o/r", "labels": ["x"]}
    )
    assert granted.kickoff_enabled is True and granted.kickoff_labels == ("x",)


# -- the start opens the conversation (issue-317) -------------------------------------


class OpeningChannel(FakeChannel):
    """A channel with a conversation to open."""

    def __init__(self, fail=False, name="slack"):
        super().__init__(name=name, fail=fail)
        self.opened = []

    def open(self, work_item):
        if self.fail:
            raise RuntimeError("down")
        self.opened.append(work_item)
        return PostResult(channel=self.name, ok=True, thread="t-root")


def test_open_conversation_opens_on_every_channel_that_can_and_skips_the_ledger():
    """R1.6, R3.1: every channel with `open` is asked; one without (the ledger
    shape) is skipped; an empty work item opens nothing."""
    slack = OpeningChannel(name="slack")
    other = OpeningChannel(name="other")
    plain = FakeChannel(name="plain")  # no `open`: nothing to do
    results = open_conversation("github:o/r#7", channels=[slack, plain, other])
    assert [r.channel for r in results] == ["slack", "other"]
    assert all(r.ok and r.thread == "t-root" for r in results)
    assert slack.opened == ["github:o/r#7"] and other.opened == ["github:o/r#7"]
    assert open_conversation("", channels=[slack]) == [] and slack.opened == [
        "github:o/r#7"
    ]


def test_a_failing_open_is_a_result_and_an_event_never_an_exception(monkeypatch):
    """R1.5, R2.2: a channel that raises is `channel.open_failed`, ids only, and
    the other channels are still asked."""
    log = []
    monkeypatch.setattr(eventlog, "emit", lambda event, **f: log.append((event, f)))
    down = OpeningChannel(fail=True, name="slack")
    fine = OpeningChannel(name="other")
    results = open_conversation("github:o/r#7", channels=[down, fine])
    assert [(r.channel, r.ok) for r in results] == [("slack", False), ("other", True)]
    assert results[0].error == "down"
    assert [name for name, _ in log] == ["channel.open_failed"]
    assert log[0][1]["channel"] == "slack" and log[0][1]["work_item"] == "github:o/r#7"
    assert fine.opened == ["github:o/r#7"]


def test_the_daemon_opener_reads_the_config_per_call_and_needs_a_channels_section(
    monkeypatch,
):
    """R3.1: the comment publisher's shape — config per call, nothing built
    without a `channels` section, a raising getter opens nothing, never raises."""
    seen = []
    monkeypatch.setattr(
        "the_loop.channels.bus.open_conversation",
        lambda ref, cli_config=None, **kw: seen.append((ref, cli_config)) or [],
    )
    configs = [{}, {"channels": {"slack": {"enabled": True}}}]
    opener = conversation_opener(lambda: configs.pop(0))
    opener("github:o/r#7")  # no channels: not even built
    opener("github:o/r#7")
    assert seen == [("github:o/r#7", {"channels": {"slack": {"enabled": True}}})]
    broken = conversation_opener(lambda: (_ for _ in ()).throw(OSError("mid-edit")))
    broken("github:o/r#7")  # never raises
    assert len(seen) == 1
