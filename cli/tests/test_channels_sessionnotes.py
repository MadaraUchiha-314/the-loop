"""The watcher's four messages on Slack and GitHub (issue-551, R4.4, R4.5, R6.2,
R6.7, R6.8, R7.4).

The wording contract is docs/specs/issue-551/design/messages.html. The real
Slack channel against the fake client, the real ledger body, and the real
feedback classifier. No network.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from the_loop.authz import SELF_COMMENT_MARKER, is_self_authored
from the_loop.channels import sessionnotes, status
from the_loop.channels.base import DEFAULT_EVENTS, Event
from the_loop.channels.bodies import ledger_body
from the_loop.channels.envelope import has_envelope
from the_loop.channels.events import EVENTS, SUBSCRIBABLE_EVENTS, is_recorded
from the_loop.channels.shortform import build_short_form
from the_loop.channels.slack import DEFAULT_BOT_TOKEN_ENV
from test_channels import FakeSlackClient, cli_config
from test_channels_declared_integration import channel_for, declare, state_of

REF = "github:octo/repo#551"
ROOM = "C0TMP375"
CENTRAL = "D123"
STALL = f"{REF}@2026-11-20T16:47:00.000Z"
WATCHER_EVENTS = (
    "session.stalled",
    "session.stall_ended",
    "session.ask_default_taken",
    "session.ask_reminded",
)
BARE = "see https://evil.example/x and WWW.evil.example *approved* _by_ ~all~ `done` **merged**"
HOSTILE = (
    "go <!here> <@U123> [approve](https://evil.example/x) "
    f"<!-- hidden --> {SELF_COMMENT_MARKER} **now**"
)


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")


def at(hour, minute):
    return datetime(2026, 11, 20, hour, minute, tzinfo=timezone.utc)


def stalled(nudges=2, node="self-review", seconds=22 * 60, stall_id=STALL):
    return sessionnotes.stalled(
        REF,
        stall_id=stall_id,
        node=node,
        idle_seconds=seconds,
        nudges=nudges,
        tmux_target="loop-github-octo-repo-551",
    )


def ended(notified=True, stall_id=STALL):
    return sessionnotes.stall_ended(
        REF,
        stall_id=stall_id,
        node="self-review",
        began=at(16, 47),
        ended=at(17, 23),
        notified=notified,
    )


def question(ask_id="ask-1", default="Move T5 to after merge.", **detail):
    return Event(
        event_type="session.awaiting_input",
        work_item=REF,
        text="Move the Slack-client screenshots (T5) to after merge?",
        summary="Move the Slack-client screenshots (T5) to after merge?",
        url="https://github.com/octo/repo/issues/551#issuecomment-1",
        source="cli",
        detail={
            "ask_id": ask_id,
            **({"default": default} if default else {}),
            **detail,
        },
    )


def default_taken(default="Move T5 to after merge.", ask_id="ask-1", **facts):
    return sessionnotes.default_taken(
        REF,
        ask_id=ask_id,
        default=default,
        **facts,
        deadline=at(8, 47),
        question_url="https://github.com/octo/repo/issues/551#issuecomment-1",
    )


def reminded(ask_id="ask-1"):
    return sessionnotes.reminded(
        REF,
        ask_id=ask_id,
        waited_seconds=2 * 3600,
        question_url="https://github.com/octo/repo/issues/551#issuecomment-1",
    )


def room(tmp_path, **slack):
    """A Slack channel whose conversation for REF is a declared room."""
    config = cli_config(tmp_path, **slack)
    declare(config, work_item=REF, target=ROOM)
    client = FakeSlackClient()
    return config, client, channel_for(config, client)


def central(tmp_path, **slack):
    config = cli_config(tmp_path, **slack)
    client = FakeSlackClient()
    return config, client, channel_for(config, client)


def memory(config):
    return state_of(config).delivery_for(REF)


# -- the catalog ------------------------------------------------------------------


def test_the_four_events_are_in_the_catalog_and_recorded():
    for name in WATCHER_EVENTS:
        assert name in EVENTS and name in SUBSCRIBABLE_EVENTS
        assert is_recorded(name)
        # The description explains the event in its own words: no work item id.
        assert EVENTS[name].description and "issue-" not in EVENTS[name].description


def test_the_stall_notice_joins_the_default_subscription(tmp_path):
    assert DEFAULT_EVENTS == ("session.awaiting_input", "session.stalled")
    _, _, bot = central(tmp_path)
    for name in WATCHER_EVENTS:
        assert bot.subscribes(name), name


def test_a_follow_up_is_heard_only_with_the_event_it_follows(tmp_path):
    _, _, asks_only = central(tmp_path, subscribe=["session.awaiting_input"])
    assert asks_only.subscribes("session.ask_default_taken")
    assert asks_only.subscribes("session.ask_reminded")
    assert not asks_only.subscribes("session.stalled")
    assert not asks_only.subscribes("session.stall_ended")
    _, _, stalls_only = central(tmp_path, subscribe=["session.stalled"])
    assert stalls_only.subscribes("session.stall_ended")
    assert not stalls_only.subscribes("session.ask_reminded")


def test_the_status_reaction_follows_the_stall_and_the_default():
    assert status.state_for(stalled()) == status.BLOCKED
    assert status.STATUS_EMOJI[status.BLOCKED] == "octagonal_sign"
    assert status.state_for(ended()) == status.WORKING
    assert status.state_for(default_taken()) == status.WORKING
    assert status.state_for(reminded()) == ""


# -- the wording, on GitHub ---------------------------------------------------------


def comment(event):
    """The ledger's comment, without its trailing marker and envelope."""
    body = ledger_body(event, {})
    assert body.count(SELF_COMMENT_MARKER) == 1 and has_envelope(body)
    return body.partition("\n\n🤖 _the-loop, autonomous comment_")[0]


def test_the_stall_notice_comment_is_pinned():
    assert comment(stalled()) == (
        "🤖 **the-loop** — **the session is idle**\n\n"
        "The session for this work item stopped at `self-review` 22 minutes ago"
        " with work still to do. the-loop nudged it twice and it did not resume.\n\n"
        "Any comment from an authorized user wakes it. To look first:"
        f" `the-loop sessions attach --work-item {REF} --read-only`."
    )


@pytest.mark.parametrize(
    "nudges, words",
    [
        (0, "the-loop could not nudge it."),
        (1, "the-loop nudged it once and it did not resume."),
        (3, "the-loop nudged it 3 times and it did not resume."),
    ],
)
def test_the_stall_notice_counts_its_nudges_in_words(nudges, words):
    assert words in stalled(nudges=nudges).text


def test_a_stall_with_no_node_names_none():
    event = stalled(nudges=0, node="")
    assert "stopped 22 minutes ago" in event.text
    assert "**#551 is idle**. The session" in event.summary
    assert "and the-loop could not nudge it" in event.summary


def test_a_node_that_is_not_a_node_id_is_left_out():
    event = stalled(node="x` <!here> [a](http://b)")
    assert "<!here>" not in event.text + event.summary
    assert event.detail["node"] == ""


def test_the_resolved_comment_is_pinned():
    assert comment(ended()) == (
        "🤖 **the-loop** — **the session was idle, and is working again**\n\n"
        "Idle at `self-review` from 16:47 UTC to 17:23 UTC (36 minutes)."
    )


def test_the_default_taken_comment_is_pinned():
    assert comment(default_taken()) == (
        "🤖 **the-loop** — **default taken**\n\n"
        "Nobody answered [the question above]"
        "(https://github.com/octo/repo/issues/551#issuecomment-1) by 08:47 UTC,"
        " so the session is going ahead with its stated default:"
        " “Move T5 to after merge.”\n\n"
        "This is not an approval of anything. An answer now still reaches the session."
    )


def test_the_default_taken_comment_for_a_session_that_was_not_told_is_pinned():
    """Requirement: R6.2"""
    event = default_taken(delivered=False)
    assert comment(event) == (
        "🤖 **the-loop** — **default taken**\n\n"
        "Nobody answered [the question above]"
        "(https://github.com/octo/repo/issues/551#issuecomment-1) by 08:47 UTC,"
        " so the default applies: “Move T5 to after merge.”\n\n"
        "The session has not been told: it is paused, or its terminal did not"
        " take the message. Reply here, or attach to the session, to tell it.\n\n"
        "This is not an approval of anything."
    )
    assert event.detail["delivered"] == ""
    assert default_taken().detail["delivered"] == "true"


def test_the_reminder_comment_is_pinned():
    assert comment(reminded()) == (
        "🤖 **the-loop** — **still waiting**\n\n"
        "The session has waited 2 hours for an answer to [this question]"
        "(https://github.com/octo/repo/issues/551#issuecomment-1). It has no"
        " default, so the work item does not move until an authorized user answers."
    )


# -- the wording, on Slack ----------------------------------------------------------


def test_the_stall_notice_short_form_is_pinned():
    assert build_short_form(stalled()).text == (
        "🛑 *#551 is idle* at `self-review`. The session stopped 22 min ago with"
        " work still to do, and 2 nudges did not restart it.\n"
        "Reply here or comment on the work item to wake it, or attach:"
        " `tmux attach -t loop-github-octo-repo-551`"
    )


def test_the_resolved_short_form_is_pinned():
    assert build_short_form(ended()).text == (
        "✅ ~#551 is idle at `self-review`~ — working again since 17:23 UTC,"
        " after 36 min idle."
    )


def test_the_default_taken_line_is_pinned():
    assert build_short_form(default_taken()).text == (
        "⚙️ No answer by 08:47 UTC, so the session went ahead with:"
        " _“Move T5 to after merge.”_ Reply to overrule."
    )


def test_the_default_taken_line_for_a_session_that_was_not_told_is_pinned():
    """Requirement: R6.2"""
    assert build_short_form(default_taken(delivered=False)).text == (
        "⚙️ No answer by 08:47 UTC, so the default applies:"
        " _“Move T5 to after merge.”_ The session has not been told (it is"
        " paused, or its terminal is gone). Reply here to tell it."
    )


def test_the_reminder_short_form_is_pinned():
    assert build_short_form(reminded()).text == (
        "⏳ #551 has been waiting on this question for 2 h. The session does"
        " nothing until someone answers."
    )


# -- the stall notice in Slack ------------------------------------------------------


def test_the_stall_notice_is_one_short_message_with_a_mention_and_the_reaction(
    tmp_path,
):
    config, client, bot = room(tmp_path)
    bot.post(Event(event_type="comment.human", work_item=REF, text="hello"))
    before = len(client.posted)

    bot.post(stalled())

    (notice,) = client.posted[before:]
    assert (notice["channel"], notice["thread_ts"]) == (ROOM, None)
    # T9: the fallback is the short form, and names the state in words.
    assert notice["text"] == notice["blocks"][0]["text"]["text"]
    assert "<@UHUMAN>" in notice["text"]
    assert "*#551 is idle* at `self-review`" in notice["text"]
    assert "the session is idle" not in notice["text"]  # the comment's wording
    ts = f"1700.{len(client.posted):06d}"
    assert client.reactions[-1] == (ROOM, ts, "octagonal_sign")
    held = memory(config)
    assert held["gateTs"][f"stall:{STALL}"] == ts
    assert held["gateMessage"][f"stall:{STALL}"]["channel"] == ROOM


def test_a_second_stall_at_the_same_node_is_a_new_notice(tmp_path):
    _, client, bot = room(tmp_path)
    bot.post(stalled())
    later = f"{REF}@2026-11-20T19:00:00.000Z"
    bot.post(stalled(stall_id=later))
    notices = [p for p in client.posted if "is idle" in p["text"]]
    assert len(notices) == 2


def test_the_stall_notice_in_the_central_channel_is_a_reply_in_the_item_thread(
    tmp_path,
):
    config, client, bot = central(tmp_path)
    bot.post(stalled())
    root, notice = client.posted
    assert notice["thread_ts"] == "1700.000001" and notice["channel"] == CENTRAL
    assert "*#551 is idle*" in notice["text"]
    # In the central channel the status message is the work item's thread root.
    assert client.reactions[-1] == (CENTRAL, "1700.000001", "octagonal_sign")


def test_the_end_of_a_stall_edits_the_notice_and_posts_nothing(tmp_path):
    config, client, bot = room(tmp_path)
    bot.post(stalled())
    posted = len(client.posted)
    ts = f"1700.{posted:06d}"

    result = bot.post(ended())

    assert result.ok and len(client.posted) == posted
    ((channel, edited, text, blocks),) = client.updates
    assert (channel, edited) == (ROOM, ts)
    assert text == (
        "✅ ~#551 is idle at `self-review`~ — working again since 17:23 UTC,"
        " after 36 min idle."
    )
    assert blocks[0]["text"]["text"] == text
    assert client.reactions[-1] == (ROOM, ts, "gear")
    assert (ROOM, ts, "octagonal_sign") in client.removed
    assert f"stall:{STALL}" not in memory(config)["gateTs"]

    bot.post(ended())  # a replay finds nothing to edit
    assert len(client.updates) == 1 and len(client.posted) == posted


def test_a_stall_nobody_was_told_about_ends_in_silence(tmp_path):
    _, client, bot = room(tmp_path)
    bot.post(Event(event_type="comment.human", work_item=REF, text="hello"))
    posted, reactions = len(client.posted), list(client.reactions)

    assert bot.post(ended(notified=False)).ok

    assert len(client.posted) == posted and client.updates == []
    assert client.reactions == reactions


# -- the question in Slack ----------------------------------------------------------


def test_default_taken_edits_the_question_and_removes_its_button(tmp_path):
    config, client, bot = room(tmp_path, read={"mode": "socket"})
    bot.post(question())
    asked = client.posted[-1]
    ts = f"1700.{len(client.posted):06d}"
    posted = len(client.posted)
    assert memory(config)["gateTs"]["ask:ask-1"] == ts

    bot.post(default_taken())

    assert len(client.posted) == posted
    ((channel, edited, text, blocks),) = client.updates
    assert (channel, edited) == (ROOM, ts)
    assert text == (
        asked["text"] + "\n⚙️ No answer by 08:47 UTC, so the session went ahead"
        " with: _“Move T5 to after merge.”_ Reply to overrule."
    )
    assert blocks[0]["text"]["text"] == asked["text"]
    assert blocks[1]["type"] == "context"
    buttons = [e for b in blocks if b["type"] == "actions" for e in b["elements"]]
    assert [b["action_id"].rpartition(":")[2] for b in buttons] == ["open"]
    assert client.reactions[-1][2] == "gear"
    assert "ask:ask-1" not in memory(config)["gateTs"]


def test_default_taken_for_a_question_slack_never_showed_posts_nothing(tmp_path):
    _, client, bot = room(tmp_path)
    bot.post(default_taken())
    assert client.posted == [] and client.updates == []


def test_the_reminder_is_a_thread_reply_under_the_question_with_a_mention(tmp_path):
    _, client, bot = room(tmp_path)
    bot.post(question(default=""))
    ts = f"1700.{len(client.posted):06d}"

    bot.post(reminded())

    reminder = client.posted[-1]
    assert (reminder["channel"], reminder["thread_ts"]) == (ROOM, ts)
    assert "<@UHUMAN>" in reminder["text"]
    assert "#551 has been waiting on this question for 2 h" in reminder["text"]
    assert reminder["text"] == reminder["blocks"][0]["text"]["text"]
    assert len([p for p in client.posted if "has been waiting" in p["text"]]) == 1


def second_question(ask_id="ask-2"):
    return Event(
        event_type="session.awaiting_input",
        work_item=REF,
        text="And the second one?",
        summary="And the second one?",
        source="cli",
        detail={"ask_id": ask_id},
    )


def test_each_open_question_keeps_its_own_message(tmp_path):
    """Two questions are open at once: the first one's default edits the first
    message and leaves the second remembered.

    Requirement: R6.2, R6.7
    """
    config, client, bot = room(tmp_path, read={"mode": "socket"})
    bot.post(question(ask_id="ask-1"))
    first = f"1700.{len(client.posted):06d}"
    bot.post(second_question())
    second = f"1700.{len(client.posted):06d}"
    assert memory(config)["gateTs"]["ask:ask-1"] == first

    bot.post(default_taken(ask_id="ask-1"))

    ((channel, edited, text, _),) = client.updates
    assert (channel, edited) == (ROOM, first)
    assert "No answer by 08:47 UTC" in text
    held = memory(config)
    assert [k for k in held["gateTs"] if k.startswith("ask:")] == ["ask:ask-2"]
    assert held["gateTs"]["ask:ask-2"] == second
    assert [k for k in held["gateMessage"] if k.startswith("ask:")] == ["ask:ask-2"]


def test_a_reminder_for_an_older_question_threads_under_that_question(tmp_path):
    """Requirement: R6.8"""
    _, client, bot = room(tmp_path)
    bot.post(question(ask_id="ask-1", default=""))
    first = f"1700.{len(client.posted):06d}"
    bot.post(second_question())

    bot.post(reminded(ask_id="ask-1"))

    assert client.posted[-1]["thread_ts"] == first


def test_the_remembered_questions_of_a_work_item_are_capped(tmp_path):
    """Questions that were answered are never edited, so they would be kept
    for ever: past the cap the oldest is forgotten.

    Requirement: R6.2
    """
    from the_loop.channels.slack import REMEMBERED_ASKS_CAP

    config, _, bot = room(tmp_path)
    count = REMEMBERED_ASKS_CAP + 2
    for n in range(count):
        bot.post(second_question(ask_id=f"ask-{n}"))
    kept = [f"ask:ask-{n}" for n in range(2, count)]
    held = memory(config)
    assert [k for k in held["gateTs"] if k.startswith("ask:")] == kept
    assert [k for k in held["gateMessage"] if k.startswith("ask:")] == kept


# -- abuse cases --------------------------------------------------------------------


def test_abuse_a_default_with_markup_is_inert_in_the_github_comment():
    body = ledger_body(default_taken(default=HOSTILE), {})
    quoted = body.partition("stated default: “")[2].partition("”\n\nThis is not")[0]
    assert "\n" not in quoted
    assert "<!here>" not in quoted and "<@U123>" not in quoted
    assert "<!--" not in quoted and "hidden" not in quoted
    assert "@U123" not in quoted and "@​U123" in quoted
    assert "\\[approve\\](https:\u200b//evil.example/x)" in quoted
    assert "\\*\\*now\\*\\*" in quoted
    assert body.count(SELF_COMMENT_MARKER) == 1


def test_abuse_a_bare_address_in_a_default_is_no_link_on_github():
    """
    Feature: A question can carry a default and a deadline
    Scenario: the default answer holds a bare web address
      Then neither `https://…` nor `www.…` is left in a form GitHub links

    Requirement: docs/specs/issue-551/requirements.md#security-considerations
    """
    body = ledger_body(default_taken(default=BARE), {})
    quoted = body.partition("stated default: “")[2].partition("”\n\nThis is not")[0]
    assert "://" not in quoted and "www." not in quoted.lower()
    assert "https:\u200b//evil.example/x" in quoted
    assert "WWW\u200b.evil.example" in quoted


def test_abuse_a_default_with_markup_is_inert_in_slack(tmp_path):
    _, client, bot = room(tmp_path)
    bot.post(question(default=HOSTILE))
    bot.post(default_taken(default=HOSTILE))
    ((_, _, text, blocks),) = client.updates
    line = blocks[1]["elements"][0]["text"]
    for drawn in (text, line):
        assert "<!here>" not in drawn and "<@U123>" not in drawn
        assert "<!--" not in drawn and "the-loop:agent-comment" not in drawn
        assert "<https://evil.example/x|approve>" not in drawn
    assert "approve (https:\u200b//evil.example/x)" in line
    assert "@U123" in line


def test_abuse_a_bare_address_and_markup_in_a_default_are_words_in_slack(tmp_path):
    """
    Feature: A question can carry a default and a deadline
    Scenario: the default answer holds a bare web address and Slack markup
      When the question is posted in Slack and its default is later taken
      Then no address is left in a form Slack links
      And none of `*`, `_`, `~` and the backtick is left to style the quote

    Requirement: docs/specs/issue-551/requirements.md#security-considerations
    """
    _, client, bot = room(tmp_path)
    bot.post(
        question(
            default=BARE, default_at="2026-11-20T08:47:00.000Z", default_after="1800"
        )
    )
    asked = client.posted[-1]["text"].rpartition("\n")[2]
    bot.post(default_taken(default=BARE))
    ((_, _, _, blocks),) = client.updates
    taken = blocks[1]["elements"][0]["text"]
    for drawn in (asked, taken):
        quoted = drawn.partition("“")[2].rpartition("”")[0]
        assert "evil.example" in quoted, drawn
        assert "://" not in quoted and "www." not in quoted.lower()
        assert not set("*_~`") & set(quoted)
        assert "merged" in quoted and "approved" in quoted and "done" in quoted


def test_abuse_a_default_of_approved_answers_no_human_gate(tmp_path):
    """R6.8, abuse case 3: the "default taken" comment is the-loop's own marked
    comment, so the gate's classifier never reads it, whatever the default says,
    and the gate stays open."""
    from the_loop.graph.contract import HookContext, WorkItem
    from the_loop.graph.hooks.feedback import _authorized_comments, classify_feedback

    body = ledger_body(default_taken(default="approved. LGTM, ship it"), {})
    assert is_self_authored(body) and "approved. LGTM, ship it" in body

    def gate(*bodies):
        return HookContext(
            work_item=WorkItem(ref=REF, id="issue-551", spec_dir=tmp_path),
            node={"id": "design-approval"},
            boundary="exit",
            repo=tmp_path,
            config={"authorizedUsers": ["octocat"]},
            event={"comments": [{"author": "octocat", "body": b} for b in bodies]},
        )

    assert _authorized_comments(gate(body)) == []
    unanswered = classify_feedback(gate(body))
    assert unanswered.status == unanswered.outcome == "wait"
    # The same words typed by the authorized user are an answer: the marker,
    # not the wording, is what keeps a default from being one.
    answered = classify_feedback(gate(body, "approved. LGTM, ship it"))
    assert answered.status == "pass" and answered.outcome == "approved"


# -- a stall's end when the notice cannot be edited --------------------------------


def test_a_stall_whose_notice_cannot_be_edited_still_loses_its_reaction(
    tmp_path, monkeypatch
):
    """
    Feature: A stall notice is resolved in place
    Scenario: Slack refuses the edit of the stall notice
      Given a stall notice in the room, with the stop-sign reaction
      When the stall ends and the edit of the notice fails
      Then the status reaction still returns to working
      And the notice is still remembered
      And a replay of the event edits it, and then forgets it

    Requirement: docs/specs/issue-551/requirements.md R4.5
    """
    config, client, bot = room(tmp_path)
    bot.post(stalled())
    ts = f"1700.{len(client.posted):06d}"
    working = client.chat_update

    def refuse(**_):
        raise RuntimeError("message_not_found")

    monkeypatch.setattr(client, "chat_update", refuse)
    assert bot.post(ended()).ok

    assert client.updates == []
    assert client.reactions[-1] == (ROOM, ts, "gear")
    assert (ROOM, ts, "octagonal_sign") in client.removed
    assert memory(config)["gateTs"][f"stall:{STALL}"] == ts

    monkeypatch.setattr(client, "chat_update", working)
    assert bot.post(ended()).ok
    assert len(client.updates) == 1
    assert f"stall:{STALL}" not in memory(config)["gateTs"]


def test_a_stall_notice_with_no_channel_left_still_loses_its_reaction(
    tmp_path, monkeypatch
):
    """
    Feature: A stall notice is resolved in place
    Scenario: the notice is remembered but where it was posted is not
      When the stall ends
      Then nothing is edited and the status reaction returns to working

    Requirement: docs/specs/issue-551/requirements.md R4.5
    """
    from the_loop.channels.state import ChannelState

    config, client, bot = room(tmp_path)
    bot.post(stalled())
    ts = f"1700.{len(client.posted):06d}"
    with ChannelState.locked(bot.state_path, bot.stores) as state:
        state.remember_delivery(REF, gateMessage={f"stall:{STALL}": {"channel": ""}})
        state.save(bot.state_path)
    monkeypatch.setattr(ChannelState, "conversation_for", lambda self, ref: None)

    assert bot.post(ended()).ok

    assert client.updates == []
    assert (ROOM, ts, "octagonal_sign") in client.removed


# -- an explicit subscription that predates the stall notice ------------------------


def test_status_warns_when_questions_are_heard_and_stalls_are_not(tmp_path, capsys):
    """
    Feature: A stall reaches a person
    Scenario: the operator's config lists its subscription and leaves out the stall
      Given a Slack channel that subscribes to session.awaiting_input by name
      When the-loop channels status is printed
      Then one line says a stalled session will not be announced, and what to add
      And a channel on the default subscription, or one that names both, gets no line

    Requirement: docs/specs/issue-551/requirements.md R4.4
    """
    from the_loop.commands import channels_cmd

    def status(**slack):
        channels_cmd._status(cli_config(tmp_path, **slack))  # noqa: SLF001
        return capsys.readouterr().out

    warned = status(subscribe=["session.awaiting_input", "comment.agent"])
    assert "[!] session.stalled is not subscribed" in warned
    assert "add session.stalled" in warned
    both = status(subscribe=["session.awaiting_input", "session.stalled"])
    assert "session.stalled is not subscribed" not in both
    assert "session.stalled is not subscribed" not in status()
    neither = status(subscribe=["comment.agent"])
    assert "session.stalled is not subscribed" not in neither
