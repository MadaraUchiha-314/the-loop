"""Unit tests for issue-349: an unresolved Slack kickoff is ASKED about rather than
refused — the declared repositories as Block Kit options, the message held in a
capped and expiring pending record, and the pick finishing the kickoff through the
path a resolved prefix already takes.

Spec: docs/specs/issue-349/{requirements,design,testing-plan}.md — rows T2 (the
pending record), T3 (rendering and the payload read), T4 (the fork), T5 (the
answer) and T11 (abuse cases A1-A10). The resolver's own additions are T1, in
test_channels_kickoff.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from the_loop import eventlog
from the_loop.channels import inbound
from the_loop.channels.base import InboundReply
from the_loop.channels.slack import (
    BUTTON_CHOICE_LIMIT,
    BUTTON_NAMES,
    DEFAULT_BOT_TOKEN_ENV,
    KICKOFF_REPO_ACTION,
    OPTION_LIMIT,
    SlackBotChannel,
    SlackChannelConfig,
    action_value,
    is_kickoff_repo_action,
    render_kickoff_question,
)
from the_loop.channels.state import PENDING_CAP, PENDING_TTL_SECONDS, ChannelState

DECLARED = [
    "expertise-help/slim-gym",
    "expertise-help/agent-sims",
    "jchou2/devbox",
    "other-org/slim-gym",
]


class FakeSlackClient:
    """The slice of ``slack_sdk.WebClient`` this path uses, recorded."""

    def __init__(self, refuse_post: str = ""):
        self.posted = []
        self.reactions = []
        self.updates = []
        self.refuse_post = refuse_post

    def chat_postMessage(self, *, channel, text, thread_ts=None, blocks=None):
        if self.refuse_post:
            raise RuntimeError(self.refuse_post)
        self.posted.append(
            {"channel": channel, "text": text, "thread_ts": thread_ts, "blocks": blocks}
        )
        return {"ok": True, "channel": channel, "ts": f"1700.{len(self.posted):06d}"}

    def chat_update(self, *, channel, ts, text, blocks=None):
        self.updates.append((channel, ts, text, blocks))
        return {"ok": True, "channel": channel, "ts": ts}

    def chat_getPermalink(self, *, channel, message_ts):
        return {"ok": True, "permalink": f"https://slack/{channel}/{message_ts}"}

    def auth_test(self):
        return {"ok": True, "user_id": "UBOT"}

    def reactions_add(self, *, channel, name, timestamp):
        self.reactions.append((channel, timestamp, name))
        return {"ok": True}


def cli_config(
    tmp_path,
    *,
    mode="socket",
    declared=DECLARED,
    kickoff_repo="",
    authorized=("UHUMAN",),
    publish=("work-item.reply", "work-item.create"),
):
    return {
        "state": {"root": str(tmp_path / "state")},
        "repositories": list(declared),
        "routing": {
            "authorizedUsers": [
                {"github": f"gh-{member}", "slack": member} for member in authorized
            ]
        },
        "channels": {
            "slack": {
                "enabled": True,
                "channel": "C123",
                "publish": list(publish),
                "read": {"mode": mode},
                "kickoff": {
                    "repo": kickoff_repo,
                    "labels": ["the-loop: auto-execute"],
                },
            }
        },
    }


def a_message(text="flaky teardown in the batch runner", author="UHUMAN", ts="1900.1"):
    return InboundReply(
        channel="slack",
        work_item="",
        author=author,
        text=text,
        thread=ts,
        ts=ts,
        top_level=True,
        channel_id="C123",
    )


def make_channel(config, tmp_path, client):
    return SlackBotChannel(
        SlackChannelConfig.from_mapping(config),
        tmp_path / "state" / "channels" / "slack.json",
        client_factory=lambda token: client,
    )


class creator:
    """The ``create_issue`` seam, recording what reached ``gh --repo``."""

    def __init__(self, ok: bool = True, ref: str = "github:o/r#42"):
        self.ok = ok
        self.ref = ref
        self.calls: list = []

    def __call__(self, repo, title, body, labels, gh_binary="gh"):
        self.calls.append(
            {"repo": repo, "title": title, "body": body, "labels": labels}
        )
        if self.ok:
            number = self.ref.rsplit("#")[-1]
            return True, "", self.ref, f"https://github.com/o/r/issues/{number}"
        return False, "gh exited 1", "", ""


def live(state, ts):
    """``state.pending_for(ts)``, asserted present — the tests that call this are
    the ones whose point is that a question is still answerable."""
    record = state.pending_for(ts)
    assert record is not None
    return record


def run_kickoff(tmp_path, client, config=None, message=None, create_issue=None, **kw):
    config = config or cli_config(tmp_path, **kw)
    return (
        inbound.process_kickoff(
            message or a_message(),
            SlackChannelConfig.from_mapping(config),
            config,
            channel=make_channel(config, tmp_path, client),
            post_comment=lambda *a, **k: (True, ""),
            create_issue=create_issue or creator(),
        ),
        config,
    )


def a_press(value, *, author="UHUMAN", thread="1900.1", action=None, select=False):
    """A ``block_actions`` payload for the repository picker."""
    element = (
        {
            "action_id": action or KICKOFF_REPO_ACTION,
            "selected_option": {"value": value},
        }
        if select
        else {"action_id": action or f"{KICKOFF_REPO_ACTION}:0", "value": value}
    )
    return {
        "type": "block_actions",
        "user": {"id": author},
        "channel": {"id": "C123"},
        "message": {
            "ts": "1950.7",
            "thread_ts": thread,
            "text": "Which repository should this go in?",
            "blocks": render_kickoff_question("Which repository?", DECLARED),
        },
        "container": {"message_ts": "1950.7", "thread_ts": thread},
        "actions": [element],
        "action_ts": "1960.1",
    }


def press(tmp_path, config, client, payload, create_issue=None):
    return inbound.handle_socket_action(
        payload,
        config,
        post_comment=lambda *a, **k: (True, ""),
        create_issue=create_issue or creator(),
        client_factory=lambda token: client,
    )


def env_created(client):
    """Every "Opened …" reply the bot posted — what "nothing was created" means
    from the channel's side."""
    return [post for post in client.posted if post["text"].startswith("Opened ")]


def state_of(tmp_path):
    return ChannelState.load(tmp_path / "state" / "channels" / "slack.json")


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")


# -- T2: the pending record (R3.1-R3.4) ---------------------------------------------


def test_a_question_is_written_read_back_and_claimed_once(tmp_path):
    """R3.1, R3.4: the answer-once rule is a pop, not a flag."""
    path = tmp_path / "slack.json"
    state = ChannelState()
    state.ask("1.1", "C123", "UHUMAN", "flaky teardown", DECLARED)
    state.save(path)

    reloaded = ChannelState.load(path)
    record = live(reloaded, "1.1")
    assert record["author"] == "UHUMAN"
    assert record["text"] == "flaky teardown"
    assert record["options"] == DECLARED
    assert reloaded.claim("1.1") is not None
    assert reloaded.claim("1.1") is None
    assert reloaded.pending_for("1.1") is None


def test_an_expired_question_reads_as_absent_without_writing(tmp_path):
    """R3.2: expiry is read as absence, so no read path has to write."""
    state = ChannelState()
    state.ask("1.1", "C123", "UHUMAN", "t", DECLARED)
    stale = datetime.now(timezone.utc) - timedelta(seconds=PENDING_TTL_SECONDS + 60)
    state.pending["1.1"]["asked"] = stale.isoformat().replace("+00:00", "Z")
    assert state.pending_for("1.1") is None
    assert "1.1" in state.pending  # the read did not sweep it
    state.ask("2.2", "C123", "UHUMAN", "t", DECLARED)  # the write did
    assert "1.1" not in state.pending

    # `claim` on an expired record answers None and removes it — it was never
    # answerable, and leaving it would only wait for the next write.
    state.ask("3.3", "C123", "UHUMAN", "t", DECLARED)
    state.pending["3.3"]["asked"] = stale.isoformat().replace("+00:00", "Z")
    assert state.claim("3.3") is None and "3.3" not in state.pending


def test_an_undateable_question_is_expired_not_eternal():
    """Fail-closed: a record the daemon cannot date is one it cannot honour."""
    state = ChannelState()
    state.ask("1.1", "C123", "UHUMAN", "t", DECLARED)
    state.pending["1.1"]["asked"] = "not a timestamp"
    assert state.pending_for("1.1") is None


def test_the_cap_drops_the_oldest_question(tmp_path):
    """R3.3: THREAD_CAP's rule — a burst of questions never buries a fresh one."""
    state = ChannelState()
    for index in range(PENDING_CAP + 5):
        state.ask(f"{index}.0", "C123", "UHUMAN", "t", DECLARED)
    assert len(state.pending) == PENDING_CAP
    assert "0.0" not in state.pending
    assert f"{PENDING_CAP + 4}.0" in state.pending


def test_restore_puts_a_claimed_question_back(tmp_path):
    """R3.5: the create failed, so the question stays answerable."""
    state = ChannelState()
    state.ask("1.1", "C123", "UHUMAN", "t", DECLARED)
    claimed = state.claim("1.1")
    assert claimed is not None
    state.restore("1.1", claimed)
    assert state.pending_for("1.1") == claimed


def test_a_pre_issue_349_state_file_loads_and_is_written_back_with_the_key(tmp_path):
    """NFR: no migration, no version — a question nobody asked is not pending."""
    path = tmp_path / "slack.json"
    path.write_text(
        '{"threads": {"1.1": {"workItem": "github:o/r#7", "channel": "C1"}},'
        ' "cursors": {}, "conversations": {}}',
        encoding="utf-8",
    )
    state = ChannelState.load(path)
    assert state.pending == {}
    assert state.work_item_for("1.1") == "github:o/r#7"
    state.save(path)
    assert '"pending"' in path.read_text(encoding="utf-8")


def test_a_malformed_options_list_contributes_nothing(tmp_path):
    """A record is parsed like any other input: a fault can only shrink the
    offered set, never widen it."""
    path = tmp_path / "slack.json"
    path.write_text(
        '{"pending": {"1.1": {"author": "U", "text": "t", "asked": "%s",'
        ' "options": "expertise-help/slim-gym"}}}'
        % datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        encoding="utf-8",
    )
    assert live(ChannelState.load(path), "1.1")["options"] == []


# -- T3: rendering and the payload read (R2.1-R2.4, R4.2, R5.1) ---------------------


def test_a_few_repositories_are_buttons(tmp_path):
    """R2.1: at most BUTTON_CHOICE_LIMIT is one tap, not a menu."""
    blocks = render_kickoff_question("Which?", DECLARED[:BUTTON_CHOICE_LIMIT])
    elements = blocks[1]["elements"]
    assert {element["type"] for element in elements} == {"button"}
    assert [element["value"] for element in elements] == DECLARED[:BUTTON_CHOICE_LIMIT]
    assert all(is_kickoff_repo_action(e["action_id"]) for e in elements)
    assert len({e["action_id"] for e in elements}) == len(elements)  # Slack: unique


def test_many_repositories_are_a_select_menu():
    """R2.2."""
    options = [f"octo/repo-{index}" for index in range(BUTTON_CHOICE_LIMIT + 1)]
    element = render_kickoff_question("Which?", options)[1]["elements"][0]
    assert element["type"] == "static_select"
    assert element["action_id"] == KICKOFF_REPO_ACTION
    assert [option["value"] for option in element["options"]] == options


def test_every_option_is_the_operators_own_declared_slug():
    """R2.4: the label and the value are the same declared string — nothing
    derived from the member's text is rendered at all (A8)."""
    for options in (DECLARED[:2], [f"octo/repo-{i}" for i in range(9)]):
        blocks = render_kickoff_question("Which?", options)
        rendered = str(blocks)
        for option in options:
            assert rendered.count(option) >= 2  # once as text, once as value


def test_more_options_than_slack_carries_are_capped_and_said_so():
    """R2.3: the first hundred in declaration order, and the prefix for the rest."""
    options = [f"octo/repo-{index}" for index in range(OPTION_LIMIT + 30)]
    blocks = render_kickoff_question("Which?", options)
    assert len(blocks[1]["elements"][0]["options"]) == OPTION_LIMIT
    assert f"Showing {OPTION_LIMIT} of {len(options)}" in blocks[0]["text"]["text"]
    assert "`<repo>: `" in blocks[0]["text"]["text"]


def test_no_options_renders_no_actions_block():
    assert len(render_kickoff_question("Which?", [])) == 1


def test_action_value_reads_both_widget_shapes():
    """R4.2: a static_select carries no top-level `value` at all."""
    assert action_value({"value": "octo/app"}) == "octo/app"
    assert action_value({"selected_option": {"value": "octo/app"}}) == "octo/app"
    assert action_value({"value": ""}) == ""
    assert action_value({"selected_option": {}}) == ""


def test_the_picker_needs_socket_and_the_grant(tmp_path):
    """R5.1 (decision-122 D1): the same two-part rule `interactive` applies."""
    socket = SlackChannelConfig.from_mapping(cli_config(tmp_path))
    assert socket.kickoff_picker
    poll = SlackChannelConfig.from_mapping(cli_config(tmp_path, mode="poll"))
    assert poll.kickoff_enabled and not poll.kickoff_picker
    no_grant = SlackChannelConfig.from_mapping(
        cli_config(tmp_path, publish=("work-item.reply",))
    )
    assert not no_grant.kickoff_picker


def test_the_press_line_names_the_picker_not_the_payloads_text():
    """R2.6 of issue-337, restated: the numbered buttons share one name."""
    assert BUTTON_NAMES[KICKOFF_REPO_ACTION] == "Repository"


# -- T4: the fork (R1.1-R1.5, R3.7, R5.1, R5.3) -------------------------------------


def test_a_message_with_no_target_is_asked_about(tmp_path):
    """R1.1: the common first-time case — asked, and nothing created."""
    client = FakeSlackClient()
    create_issue = creator()
    outcome, _ = run_kickoff(tmp_path, client, create_issue=create_issue)
    assert outcome == {"outcome": "asked", "options": len(DECLARED)}
    assert create_issue.calls == []
    asked = client.posted[-1]
    assert asked["thread_ts"] == "1900.1"
    assert "Which repository should this go in?" in asked["text"]
    assert [element["value"] for element in asked["blocks"][1]["elements"]] == DECLARED
    record = live(state_of(tmp_path), "1900.1")
    assert record["text"] == "flaky teardown in the batch runner"
    assert record["options"] == DECLARED
    assert state_of(tmp_path).work_item_for("1900.1") is None  # nothing bound


def test_an_ambiguous_prefix_offers_only_what_it_matched(tmp_path):
    """R1.2: the member half-answered it, so ask the narrow question."""
    client = FakeSlackClient()
    outcome, _ = run_kickoff(
        tmp_path, client, message=a_message("slim-gym: flaky teardown")
    )
    assert outcome == {"outcome": "asked", "options": 2}
    record = live(state_of(tmp_path), "1900.1")
    assert record["options"] == ["expertise-help/slim-gym", "other-org/slim-gym"]
    assert record["text"] == "flaky teardown"  # the prefix it read is stripped


def test_an_unknown_qualified_prefix_offers_the_whole_set(tmp_path):
    """R1.3."""
    client = FakeSlackClient()
    outcome, _ = run_kickoff(
        tmp_path, client, message=a_message("stranger/repo: flaky teardown")
    )
    assert outcome["outcome"] == "asked"
    assert "don't know a repository called `stranger/repo`" in client.posted[-1]["text"]
    assert live(state_of(tmp_path), "1900.1")["text"] == "flaky teardown"


def test_a_misconfigured_fallback_is_asked_about_too(tmp_path):
    """R1.3, the other arm: `kickoff.repo` pointing outside the declared set."""
    client = FakeSlackClient()
    outcome, _ = run_kickoff(tmp_path, client, kickoff_repo="stranger/repo")
    assert outcome["outcome"] == "asked"
    assert live(state_of(tmp_path), "1900.1")["text"] == (
        "flaky teardown in the batch runner"
    )


def test_an_empty_message_is_refused_not_asked(tmp_path):
    """R1.4: no pick puts words in a message that has none."""
    client = FakeSlackClient()
    outcome, _ = run_kickoff(
        tmp_path, client, message=a_message("expertise-help/agent-sims:")
    )
    assert outcome == {"outcome": "kickoff-empty-message"}
    assert "put the title after the prefix" in client.posted[-1]["text"]
    assert state_of(tmp_path).pending == {}


@pytest.mark.parametrize(
    "text, repo",
    [
        ("agent-sims: flaky teardown", ""),
        ("flaky teardown", "expertise-help/agent-sims"),
    ],
)
def test_a_message_that_resolves_is_never_asked_about(tmp_path, text, repo):
    """R1.5: someone who typed a prefix — or an operator who set a fallback —
    has already answered the question."""
    client = FakeSlackClient()
    create_issue = creator()
    outcome, _ = run_kickoff(
        tmp_path,
        client,
        message=a_message(text),
        create_issue=create_issue,
        kickoff_repo=repo,
    )
    assert outcome["outcome"] == "created"
    assert create_issue.calls[0]["repo"] == "expertise-help/agent-sims"
    assert state_of(tmp_path).pending == {}


def test_poll_mode_refuses_with_todays_text(tmp_path):
    """R5.1 (decision-122 D1): a question nobody can answer is worse than a
    refusal that says what to type."""
    client = FakeSlackClient()
    outcome, _ = run_kickoff(tmp_path, client, mode="poll")
    assert outcome == {"outcome": "kickoff-no-target"}
    assert "start your message with `<repo>: `" in client.posted[-1]["text"]
    assert client.posted[-1]["blocks"] is None
    assert state_of(tmp_path).pending == {}


def test_nothing_declared_refuses_rather_than_asking(tmp_path):
    """R5.3: a question with no options is not a question."""
    client = FakeSlackClient()
    outcome, _ = run_kickoff(tmp_path, client, declared=[])
    assert outcome == {"outcome": "kickoff-no-target"}
    assert "I know no repositories" in client.posted[-1]["text"]


def test_a_second_read_of_the_same_message_does_not_ask_twice(tmp_path):
    """R3.7: a poll cycle beside the listener, or a Slack retry."""
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    run_kickoff(tmp_path, client, config=config)
    outcome, _ = run_kickoff(tmp_path, client, config=config)
    assert outcome == {"outcome": "kickoff-already-asked"}
    assert len(client.posted) == 1


def test_a_question_that_could_not_be_posted_is_forgotten(tmp_path):
    """A record nobody can see must not suppress the next one."""
    client = FakeSlackClient(refuse_post="channel_not_found")
    outcome, _ = run_kickoff(tmp_path, client)
    assert outcome == {"outcome": "kickoff-ask-failed"}
    assert state_of(tmp_path).pending == {}


def test_asking_emits_counts_and_ids_but_no_text_or_repository(tmp_path):
    """NFR observability + A8: the event log carries no message and no slug."""
    events = []
    original = eventlog.emit
    try:
        eventlog.emit = lambda name, **fields: (
            events.append((name, fields)) or original(name, **fields)
        )
        run_kickoff(tmp_path, FakeSlackClient())
    finally:
        eventlog.emit = original
    asked = [fields for name, fields in events if name == "channel.kickoff_asked"]
    assert asked == [
        {
            "channel": "slack",
            "actor": "UHUMAN",
            "thread": "1900.1",
            "kind": "no-target",
            "count": len(DECLARED),
        }
    ]


# -- T5: the answer (R3.4, R3.5, R4.1-R4.5) -----------------------------------------


def test_a_pick_opens_the_work_item_the_question_was_holding(tmp_path):
    """R4.1, R4.3, R4.4: the same event, the same ledger, the same reply."""
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    run_kickoff(tmp_path, client, config=config)
    outcome = press(tmp_path, config, client, a_press("jchou2/devbox"))
    assert outcome["outcome"] == "created"
    assert outcome["workItem"] == "github:o/r#42"
    said = client.posted[-1]
    assert "Opened github:o/r#42" in said["text"]
    assert said["thread_ts"] == "1900.1"
    assert state_of(tmp_path).work_item_for("1900.1") == "github:o/r#42"
    conversation = state_of(tmp_path).conversation("github:o/r#42")
    assert conversation is not None and conversation["origin"] == "kickoff"
    assert state_of(tmp_path).pending == {}


def test_the_pick_reaches_the_ledger_as_the_declared_slug(tmp_path):
    """R4.3 + A1: what reaches `gh --repo` is the operator's own string."""
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    run_kickoff(tmp_path, client, config=config)
    create_issue = creator()
    outcome = inbound.process_kickoff_answer(
        InboundReply(
            channel="slack",
            work_item="",
            author="UHUMAN",
            text="jchou2/devbox",
            thread="1900.1",
            ts="1950.7",
            channel_id="C123",
        ),
        SlackChannelConfig.from_mapping(config),
        config,
        bot=make_channel(config, tmp_path, client),
        post_comment=lambda *a, **k: (True, ""),
        create_issue=create_issue,
    )
    assert outcome["outcome"] == "created"
    assert create_issue.calls[0]["repo"] == "jchou2/devbox"
    assert create_issue.calls[0]["labels"] == ["the-loop: auto-execute"]
    assert "flaky teardown in the batch runner" in (
        create_issue.calls[0]["title"] + create_issue.calls[0]["body"]
    )


def test_a_select_menu_pick_is_read_from_selected_option(tmp_path):
    """R4.2."""
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    run_kickoff(tmp_path, client, config=config)
    outcome = press(tmp_path, config, client, a_press("jchou2/devbox", select=True))
    assert outcome["outcome"] == "created"


def test_a_landed_press_is_reported_and_the_picker_removed(tmp_path):
    """R4.5."""
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    run_kickoff(tmp_path, client, config=config)
    press(tmp_path, config, client, a_press("jchou2/devbox"))
    channel, ts, text, blocks = client.updates[-1]
    assert (channel, ts) == ("C123", "1950.7")
    assert "✅ *Repository*" in text and "opened" in text
    assert not [
        element
        for block in blocks
        if block.get("type") == "actions"
        for element in block["elements"]
    ]


def test_a_failed_create_restores_the_question_and_keeps_the_picker(tmp_path):
    """R3.5 + R4.5: the question stays answerable beside the picker."""
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    run_kickoff(tmp_path, client, config=config)
    outcome = press(
        tmp_path,
        config,
        client,
        a_press("jchou2/devbox"),
        create_issue=creator(ok=False),
    )
    assert outcome["outcome"] == "create-failed"
    assert state_of(tmp_path).pending_for("1900.1") is not None
    _, _, text, blocks = client.updates[-1]
    assert "⚠️ *Repository*" in text
    assert [
        element
        for block in blocks
        if block.get("type") == "actions"
        for element in block["elements"]
    ]


def test_a_press_on_another_action_still_goes_the_old_way(tmp_path):
    """The routing sits above `process_reply` and touches nothing below it."""
    client = FakeSlackClient()
    config = cli_config(tmp_path, publish=("work-item.reply", "work-item.create"))
    outcome = press(
        tmp_path,
        config,
        client,
        a_press("approved", action="the-loop:approve", thread="1700.9"),
    )
    assert outcome["outcome"] == "unmapped"  # no binding — the pre-issue-349 answer


# -- T11: abuse cases A1-A10 ---------------------------------------------------------


def test_abuse_1_a_crafted_value_outside_the_offered_set_creates_nothing(tmp_path):
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    run_kickoff(tmp_path, client, config=config)
    for crafted in ("../../etc", "attacker/evil", "jchou2/devbox; rm -rf /", ""):
        outcome = press(tmp_path, config, client, a_press(crafted))
        assert outcome["outcome"] in ("undeclared-repository", "ignored")
    assert state_of(tmp_path).pending_for("1900.1") is not None


def test_abuse_2_a_declared_repository_never_offered_here_is_refused(tmp_path):
    """The record's own offered set is the bound, not the declared set alone."""
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    run_kickoff(tmp_path, client, config=config, message=a_message("slim-gym: t"))
    outcome = press(tmp_path, config, client, a_press("jchou2/devbox"))
    assert outcome == {"outcome": "undeclared-repository"}
    assert state_of(tmp_path).pending_for("1900.1") is not None


def test_abuse_3_an_unauthorized_presser_learns_nothing(tmp_path):
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    run_kickoff(tmp_path, client, config=config)
    before = len(client.posted)
    outcome = press(
        tmp_path, config, client, a_press("jchou2/devbox", author="UINTRUDER")
    )
    assert outcome == {"outcome": "unauthorized-actor"}
    assert len(client.posted) == before and client.updates == []
    assert state_of(tmp_path).pending_for("1900.1") is not None


def test_abuse_4_an_authorized_member_cannot_direct_anothers_message(tmp_path):
    """decision-122 D5: the issue is opened as the person who wrote it."""
    client = FakeSlackClient()
    config = cli_config(tmp_path, authorized=("UHUMAN", "UOTHER"))
    run_kickoff(tmp_path, client, config=config)
    outcome = press(tmp_path, config, client, a_press("jchou2/devbox", author="UOTHER"))
    assert outcome == {"outcome": "not-your-kickoff"}
    assert live(state_of(tmp_path), "1900.1")["author"] == "UHUMAN"


def test_abuse_5_an_unlisted_members_message_is_asked_nothing(tmp_path):
    """R2.6 of issue-341, preserved: the question sits BELOW the allow-list, and
    a question with options is a bigger disclosure than a refusal."""
    client = FakeSlackClient()
    outcome, _ = run_kickoff(tmp_path, client, message=a_message(author="UINTRUDER"))
    assert outcome == {"outcome": "unauthorized-actor"}
    assert client.posted == [] and state_of(tmp_path).pending == {}


def test_abuse_6_two_presses_of_one_question_open_one_issue(tmp_path):
    """The claim is inside the lock and the create outside it."""
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    run_kickoff(tmp_path, client, config=config)
    first = press(tmp_path, config, client, a_press("jchou2/devbox"))
    second = press(tmp_path, config, client, a_press("expertise-help/slim-gym"))
    assert first["outcome"] == "created"
    assert second == {"outcome": "no-pending-kickoff"}
    assert len([post for post in client.posted if "Opened" in post["text"]]) == 1


def test_abuse_7_an_expired_pick_names_no_repository(tmp_path):
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    run_kickoff(tmp_path, client, config=config)
    path = tmp_path / "state" / "channels" / "slack.json"
    state = ChannelState.load(path)
    stale = datetime.now(timezone.utc) - timedelta(seconds=PENDING_TTL_SECONDS + 60)
    state.pending["1900.1"]["asked"] = stale.isoformat().replace("+00:00", "Z")
    state.save(path)
    outcome = press(tmp_path, config, client, a_press("jchou2/devbox"))
    assert outcome == {"outcome": "no-pending-kickoff"}
    assert env_created(client) == []
    # The authorized member IS told, on the question itself (decision-120 D2's
    # narrowing) — and told nothing they could not already see: no repository
    # name, no other member, no config value.
    _, _, text, _ = client.updates[-1]
    assert "no longer open" in text
    for name in DECLARED:
        assert name not in text


def test_abuse_8_a_hostile_message_neither_styles_nor_sizes_the_question(tmp_path):
    hostile = "<!channel> " + "@here " * 200 + "`</section>`" + "x" * 4000
    client = FakeSlackClient()
    run_kickoff(tmp_path, client, message=a_message(hostile))
    asked = client.posted[-1]
    assert "@here" not in asked["text"] and "<!channel>" not in asked["text"]
    assert len(asked["text"]) < 500
    assert hostile not in str(asked["blocks"])
    # …but the held text is intact, because that is what the issue is made from
    assert live(state_of(tmp_path), "1900.1")["text"] == hostile


def test_abuse_9_an_unreadable_state_file_asks_rather_than_creates(tmp_path):
    """A corrupt file is empty state: nothing is pending, so a press answers
    nothing — never an issue created without an answer."""
    path = tmp_path / "state" / "channels" / "slack.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    outcome, _ = run_kickoff(tmp_path, client, config=config)
    assert outcome["outcome"] == "asked"
    path.write_text("{ not json", encoding="utf-8")
    assert press(tmp_path, config, client, a_press("jchou2/devbox")) == {
        "outcome": "no-pending-kickoff"
    }


# -- T14: `channels status` says whether it can ask (R5.2) --------------------------


def _status(tmp_path, monkeypatch, capsys, **kwargs):
    import argparse
    import json

    from the_loop.commands.channels_cmd import ChannelsCommand

    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    (tmp_path / "cli-config.yaml").write_text(
        json.dumps(cli_config(tmp_path, **kwargs)), encoding="utf-8"
    )
    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    assert ChannelsCommand().run(parser.parse_args(["status"])) == 0
    return capsys.readouterr().out


def test_status_says_it_asks(tmp_path, monkeypatch, capsys):
    out = _status(tmp_path, monkeypatch, capsys)
    assert "asks which repository when a message names none" in out


def test_status_says_why_it_cannot_ask_in_poll_mode(tmp_path, monkeypatch, capsys):
    out = _status(tmp_path, monkeypatch, capsys, mode="poll")
    assert "cannot ask which repository — read.mode is poll" in out
    assert "an unresolved message is refused" in out


def test_status_says_why_it_cannot_ask_with_nothing_declared(
    tmp_path, monkeypatch, capsys
):
    out = _status(tmp_path, monkeypatch, capsys, declared=[])
    assert "cannot ask which repository — nothing is declared" in out


# -- the authorized refusals answer on the question itself (decision-120 D2) --------


@pytest.mark.parametrize(
    "value, author, expect, phrase",
    [
        ("attacker/evil", "UHUMAN", "undeclared-repository", "not one of the"),
        ("jchou2/devbox", "UOTHER", "not-your-kickoff", "belongs to the member"),
    ],
)
def test_an_authorized_refusal_is_written_onto_the_question(
    tmp_path, value, author, expect, phrase
):
    """A member who taps and sees nothing happen is the failure this work item
    exists to end — so a refusal an authorized member earns is answered in
    place, with the picker left where it is."""
    client = FakeSlackClient()
    config = cli_config(tmp_path, authorized=("UHUMAN", "UOTHER"))
    run_kickoff(tmp_path, client, config=config)
    assert press(tmp_path, config, client, a_press(value, author=author)) == {
        "outcome": expect
    }
    _, _, text, blocks = client.updates[-1]
    assert "⚠️ *Repository*" in text and phrase in text
    assert [
        element
        for block in blocks
        if block.get("type") == "actions"
        for element in block["elements"]
    ], "a refused press keeps the picker — it is still answerable"
    assert live(state_of(tmp_path), "1900.1") is not None


def test_an_unauthorized_press_still_leaves_no_mark(tmp_path):
    """decision-111 D1 where it bites: below the allow-list, nothing at all."""
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    run_kickoff(tmp_path, client, config=config)
    before = (len(client.posted), len(client.reactions))
    assert press(
        tmp_path, config, client, a_press("jchou2/devbox", author="UINTRUDER")
    ) == {"outcome": "unauthorized-actor"}
    assert client.updates == []
    assert (len(client.posted), len(client.reactions)) == before


def test_an_accepted_press_is_acknowledged_on_the_question(tmp_path):
    """issue-325 R1.5: after the last refusal, before the record, on the message
    the press came from."""
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    run_kickoff(tmp_path, client, config=config)
    client.reactions.clear()
    press(tmp_path, config, client, a_press("jchou2/devbox"))
    assert [(channel, ts) for channel, ts, _ in client.reactions] == [
        ("C123", "1950.7"),
        ("C123", "1950.7"),
    ]


def test_a_revoked_grant_is_re_read_at_press_time(tmp_path):
    """The one gate a pending record could otherwise smuggle a member past: the
    question went out under a grant the operator has since taken away."""
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    run_kickoff(tmp_path, client, config=config)
    revoked = cli_config(tmp_path, publish=("work-item.reply",))
    assert press(tmp_path, revoked, client, a_press("jchou2/devbox")) == {
        "outcome": "unpublishable-event"
    }
    assert env_created(client) == []
    assert live(state_of(tmp_path), "1900.1") is not None


def test_leaving_socket_mode_revokes_the_answer_too(tmp_path):
    client = FakeSlackClient()
    config = cli_config(tmp_path)
    run_kickoff(tmp_path, client, config=config)
    assert press(
        tmp_path, cli_config(tmp_path, mode="poll"), client, a_press("jchou2/devbox")
    ) == {"outcome": "unpublishable-event"}
    assert env_created(client) == []
