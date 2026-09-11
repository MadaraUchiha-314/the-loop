"""Integration scenarios for issue-349: the whole shape of "the-loop asks which
repository" through the transports as they are actually composed —
``handle_socket_event`` for the message, ``handle_socket_action`` for the pick, and
``poll_once`` for the mode that cannot receive one.

Only the process boundaries are faked: the Slack SDK client (injected factory) and
the two GitHub writers (``create_issue`` / ``post_comment`` injection points the
pipeline already exposes). Everything between them is the real modules.

Spec: docs/specs/issue-349/{requirements,design,testing-plan}.md — row T8.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from the_loop.channels import inbound
from the_loop.channels.slack import (
    DEFAULT_BOT_TOKEN_ENV,
    KICKOFF_REPO_ACTION,
    kickoff_cursor_key,
)
from the_loop.channels.state import PENDING_TTL_SECONDS, ChannelState

DECLARED = ["expertise-help/slim-gym", "jchou2/devbox", "octo/app"]


class FakeSlackClient:
    def __init__(self):
        self.posted = []
        self.reactions = []
        self.updates = []
        self.history = []
        self.replies = {}

    def chat_postMessage(self, *, channel, text, thread_ts=None, blocks=None):
        self.posted.append(
            {"channel": channel, "text": text, "thread_ts": thread_ts, "blocks": blocks}
        )
        return {"ok": True, "channel": channel, "ts": f"1700.{len(self.posted):06d}"}

    def chat_update(self, *, channel, ts, text, blocks=None):
        self.updates.append((channel, ts, text, blocks))
        return {"ok": True, "channel": channel, "ts": ts}

    def chat_getPermalink(self, *, channel, message_ts):
        return {"ok": True, "permalink": f"https://slack/{channel}/{message_ts}"}

    def conversations_history(self, *, channel, oldest=None, limit=100):
        return {"ok": True, "messages": list(self.history)}

    def conversations_replies(self, *, channel, ts, oldest=None, limit=200):
        return {"ok": True, "messages": list(self.replies.get(ts, []))}

    def auth_test(self):
        return {"ok": True, "user_id": "UBOT"}

    def reactions_add(self, *, channel, name, timestamp):
        self.reactions.append((channel, timestamp, name))
        return {"ok": True}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A Socket-Mode channel with three declared repositories and no fallback —
    the shape issue-349 exists for."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")

    class Env:
        def __init__(self):
            self.client = FakeSlackClient()
            self.created = []
            self.comments = []
            self.tmp_path = tmp_path
            self.mode = "socket"

        @property
        def config(self):
            return {
                "state": {"root": str(tmp_path / "state")},
                "repositories": list(DECLARED),
                "routing": {
                    "authorizedUsers": [{"github": "gh-UHUMAN", "slack": "UHUMAN"}]
                },
                "channels": {
                    "slack": {
                        "enabled": True,
                        "channel": "C123",
                        "publish": ["work-item.reply", "work-item.create"],
                        "read": {"mode": self.mode},
                        "kickoff": {"repo": "", "labels": []},
                    }
                },
            }

        @property
        def state_path(self):
            return tmp_path / "state" / "channels" / "slack.json"

        def state(self):
            return ChannelState.load(self.state_path)

        def create_issue(self, repo, title, body, labels, gh_binary="gh"):
            self.created.append({"repo": repo, "title": title, "body": body})
            number = len(self.created)
            return (
                True,
                "",
                f"github:{repo}#{number}",
                f"https://github.com/{repo}/issues/{number}",
            )

        def post_comment(self, *args, **kwargs):
            self.comments.append((args, kwargs))
            return True, ""

        def message(self, text, ts="1900.1", user="UHUMAN"):
            """A top-level message, through the Socket Mode event handler."""
            return inbound.handle_socket_event(
                {"ts": ts, "channel": "C123", "user": user, "text": text},
                self.config,
                post_comment=self.post_comment,
                create_issue=self.create_issue,
                client_factory=lambda token: self.client,
            )

        def pick(self, value, *, thread="1900.1", user="UHUMAN", message_ts="1950.7"):
            """A press on the picker, through the Socket Mode action handler."""
            return inbound.handle_socket_action(
                {
                    "type": "block_actions",
                    "user": {"id": user},
                    "channel": {"id": "C123"},
                    "message": {
                        "ts": message_ts,
                        "thread_ts": thread,
                        "text": "Which repository should this go in?",
                        "blocks": self.client.posted[-1]["blocks"],
                    },
                    "container": {"message_ts": message_ts, "thread_ts": thread},
                    "actions": [
                        {"action_id": f"{KICKOFF_REPO_ACTION}:0", "value": value}
                    ],
                },
                self.config,
                post_comment=self.post_comment,
                create_issue=self.create_issue,
                client_factory=lambda token: self.client,
            )

        def reply(self, text, *, thread="1900.1", ts="2000.1"):
            return inbound.handle_socket_event(
                {
                    "ts": ts,
                    "thread_ts": thread,
                    "channel": "C123",
                    "user": "UHUMAN",
                    "text": text,
                },
                self.config,
                post_comment=self.post_comment,
                client_factory=lambda token: self.client,
            )

    return Env()


def test_a_prefixless_message_is_asked_about_and_the_pick_opens_it(env):
    """
    Feature: a Slack kickoff asks which repository instead of refusing
    Scenario: a member who has never used the-loop files from their phone
        Given a Socket Mode channel with three declared repositories and no
        kickoff fallback
        When a member posts a top-level message that names no repository
        Then the-loop asks which repository, offering the three as pickable
        options, and creates nothing
        And when the member picks one, the issue is opened in exactly that
        repository from exactly the text they wrote, the thread is bound to it,
        and a reply in that thread now reaches the work item
    Requirement: github issue #349 (R1.1, R2.1, R3.4, R4.1, R4.3, R4.4)
    """
    asked = env.message("flaky teardown in the batch runner")
    assert asked == {"outcome": "asked", "options": 3}
    assert env.created == []
    question = env.client.posted[-1]
    assert question["thread_ts"] == "1900.1"
    assert [element["value"] for element in question["blocks"][1]["elements"]] == (
        DECLARED
    )
    assert env.state().work_item_for("1900.1") is None

    opened = env.pick("jchou2/devbox")
    assert opened["outcome"] == "created"
    assert env.created == [
        {
            "repo": "jchou2/devbox",
            "title": "flaky teardown in the batch runner",
            "body": env.created[0]["body"],
        }
    ]
    assert env.state().work_item_for("1900.1") == "github:jchou2/devbox#1"
    assert "✅ *Repository*" in env.client.updates[-1][2]

    # The thread is the work item's conversation now, exactly as a prefixed
    # kickoff's would be: a reply reaches it rather than being dropped.
    assert env.reply("looks like a fixture leak")["outcome"] == "processed"


def test_a_prefix_that_resolves_still_goes_straight_through(env):
    """
    Feature: a Slack kickoff asks which repository instead of refusing
    Scenario: a member who already knows the prefix is not asked again
        Given the same channel
        When a member posts a message starting with a declared repository's slug
        Then the issue is opened immediately in that repository, no question is
        asked, and nothing is left pending
    Requirement: github issue #349 (R1.5)
    """
    assert env.message("devbox: flaky teardown")["outcome"] == "created"
    assert env.created[0]["repo"] == "jchou2/devbox"
    assert env.created[0]["title"] == "flaky teardown"
    assert env.state().pending == {}
    assert all("Which repository" not in post["text"] for post in env.client.posted)


def test_a_second_press_of_one_question_opens_one_issue(env):
    """
    Feature: a pending kickoff is answered exactly once
    Scenario: a member double-taps, or Slack redelivers the press
        Given a message the-loop has asked about
        When the picker is pressed twice
        Then exactly one issue exists and the second press is told there is
        nothing pending
    Requirement: github issue #349 (R3.4; abuse case A6)
    """
    env.message("flaky teardown")
    assert env.pick("octo/app")["outcome"] == "created"
    assert env.pick("jchou2/devbox") == {"outcome": "no-pending-kickoff"}
    assert len(env.created) == 1


def test_an_expired_question_opens_nothing(env):
    """
    Feature: a pending kickoff expires
    Scenario: nobody answers for a day
        Given a message the-loop asked about more than PENDING_TTL_SECONDS ago
        When the picker is finally pressed
        Then nothing is created and the press is told there is nothing pending
    Requirement: github issue #349 (R3.2; abuse case A7)
    """
    env.message("flaky teardown")
    state = env.state()
    stale = datetime.now(timezone.utc) - timedelta(seconds=PENDING_TTL_SECONDS + 60)
    state.pending["1900.1"]["asked"] = stale.isoformat().replace("+00:00", "Z")
    state.save(env.state_path)
    assert env.pick("octo/app") == {"outcome": "no-pending-kickoff"}
    assert env.created == []


def test_the_same_message_in_poll_mode_is_refused_instead(env):
    """
    Feature: the question is only asked where a press can be received
    Scenario: the operator runs the channel in poll mode
        Given the same channel with read.mode poll
        When the same prefix-less top-level message arrives through the poll
        read
        Then it is refused with the text that names the declared repositories,
        nothing is held pending, and the member is told what to type
    Requirement: github issue #349 (R5.1; decision-122 D1)
    """
    env.mode = "poll"
    # Baseline the kickoff cursor the way a first read does, then let the poll
    # cycle see one new top-level message.
    state = ChannelState()
    state.advance(kickoff_cursor_key("C123"), "1800.0")
    state.save(env.state_path)
    env.client.history = [{"ts": "1900.1", "user": "UHUMAN", "text": "flaky teardown"}]

    summary = inbound.poll_once(
        env.config,
        client_factory=lambda token: env.client,
        post_comment=env.post_comment,
        create_issue=env.create_issue,
    )
    assert summary["created"] == 0 and summary["dropped"] == 1
    assert env.created == [] and env.state().pending == {}
    refusal = env.client.posted[-1]
    assert "start your message with `<repo>: `" in refusal["text"]
    assert refusal["blocks"] is None
    for name in DECLARED:
        assert f"`{name}`" in refusal["text"]
