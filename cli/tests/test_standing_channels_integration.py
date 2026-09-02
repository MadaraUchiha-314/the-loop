"""A standing session's Slack thread, end to end (issue-277, T2/T8).

The announcement post binds a thread to `standing:<name>`, and an authorized member's
reply in that thread is pasted into the session's terminal — through the *existing*
inbound pipeline, minus the mirror step, because there is no ticket to mirror onto.

Only the process boundaries are faked: the Slack SDK client (injected factory), the
GitHub comment writer, and tmux.
"""

from __future__ import annotations

import pytest

from the_loop.channels import inbound
from the_loop.channels.slack import DEFAULT_BOT_TOKEN_ENV, SlackChannelConfig
from the_loop.channels.state import ChannelState
from the_loop.core import standing as core_standing
from the_loop.harness.base import HarnessAdapter
from the_loop.runner import SESSION_ABSENT, SESSION_LIVE, TmuxResult
from the_loop.standing import standing_ref
from the_loop.state import layout_from_config
from the_loop.trust import TrustResult


class FakeSlackClient:
    def __init__(self):
        self.posted = []
        self.replies = {}

    def chat_postMessage(self, *, channel, text, thread_ts=None, blocks=None):
        ts = f"1700.{len(self.posted) + 1:06d}"
        self.posted.append(
            {"channel": channel, "text": text, "thread_ts": thread_ts, "ts": ts}
        )
        return {"ok": True, "channel": channel, "ts": ts}

    def conversations_replies(self, *, channel, ts, oldest=None, limit=200):
        return {"ok": True, "messages": list(self.replies.get(ts, []))}

    def auth_test(self):
        return {"ok": True, "user_id": "UBOT"}


class _Adapter(HarnessAdapter):
    name = "claude"
    default_binary = "claude-stub"

    def is_available(self):
        return True

    def prepare_environment(self, cwd, root=None):
        return TrustResult()

    def interactive_argv(self, prompt, session_id):
        return ["--session-id", session_id, prompt]

    def interactive_resume_argv(self, prompt, session_id):
        return ["--resume", session_id, prompt]


class _Tmux:
    def __init__(self):
        self.state = {}
        self.delivered = []

    def session_state(self, target):
        return self.state.get(target, SESSION_ABSENT)

    def has_session(self, target):
        return target in self.state

    def has_live_session(self, target):
        return self.state.get(target) == SESSION_LIVE

    def survived(self, target, delay, sleeper=None):
        return self.has_live_session(target)

    def spawn_in(
        self, target, adapter, prompt, cwd, session_id, timeout=None, resume=False
    ):
        self.state[target] = SESSION_LIVE
        return TmuxResult(ok=True)

    def deliver_to(self, target, prompt, timeout=None):
        self.delivered.append((target, prompt))
        return TmuxResult(ok=True)

    def kill_target(self, target, timeout=None):
        self.state.pop(target, None)
        return TmuxResult(ok=True)

    def terminate_harness_in(self, target, label, grace=5.0, **kwargs):
        return TmuxResult(ok=True)


@pytest.fixture
def tmux(monkeypatch):
    server = _Tmux()
    monkeypatch.setattr(core_standing, "TmuxRunner", lambda **kwargs: server)
    monkeypatch.setattr(
        core_standing, "build_adapters", lambda **kwargs: {"claude": _Adapter()}
    )
    return server


def _config(tmp_path, *, channel="", slack_channel="C123", authorized=("UHUMAN",)):
    return {
        "state": {"root": str(tmp_path / "state")},
        "routing": {
            "defaultHarness": "claude",
            "spawnWorkdir": str(tmp_path),
            # Identity in one place (issue-309): Slack member ids on person entries.
            "authorizedUsers": [{"slack": member} for member in authorized],
        },
        "standingSessions": {
            "enabled": True,
            "sessions": [
                {"name": "supervisor", "slack": {"enabled": True, "channel": channel}}
            ],
        },
        "channels": {
            "slack": {
                "enabled": True,
                "channel": slack_channel,
            }
        },
    }


@pytest.fixture
def slack(monkeypatch):
    client = FakeSlackClient()
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)
    return client


def _reply(client, thread, *, user="UHUMAN", text="what is stuck?", ts="1700.9"):
    client.replies[thread] = [
        {"ts": ts, "user": user, "text": text},
    ]


def test_a_slack_thread_reply_reaches_a_standing_session_and_no_ticket(
    tmp_path, tmux, slack, monkeypatch
):
    """
    Feature: standing sessions
      Scenario: a Slack thread reply reaches a standing session and no ticket
        Given a standing session announced in Slack, with its thread bound to it
        When an authorized member replies in that thread
        Then the reply is pasted into the session's tmux pane
        And nothing is posted on any work item
        And the skipped mirror is recorded rather than silent

    Requirement: docs/specs/issue-277/requirements.md R4.1, R4.2, R4.3
    """
    config = _config(tmp_path)
    posted_comments = []
    monkeypatch.setattr(
        "the_loop.comments.post_issue_comment",
        lambda *args, **kwargs: posted_comments.append(args) or (True, ""),
    )

    core_standing.start_standing(config=config)

    # The root names the session's ref and is bound to it; the announcement is
    # its first reply (issue-312).
    assert len(slack.posted) == 2
    thread = slack.posted[0]["ts"]
    assert slack.posted[1]["thread_ts"] == thread
    state = ChannelState.load(
        __import__("pathlib").Path(layout_from_config(config).channels_dir)
        / "slack.json"
    )
    assert state.work_item_for(thread) == standing_ref("supervisor")

    _reply(slack, thread)
    summary = inbound.poll_once(config)

    assert summary["processed"] == 1 and summary["delivered"] == 1
    target, prompt = tmux.delivered[0]
    assert target == "loop-standing-supervisor"
    assert "what is stuck?" in prompt
    assert posted_comments == []  # no ticket was touched — there is none


def test_the_skipped_mirror_is_recorded(tmp_path, tmux, slack, monkeypatch):
    config = _config(tmp_path)
    events = []
    monkeypatch.setattr(
        "the_loop.eventlog.emit",
        lambda event_type, **fields: events.append((event_type, fields)),
    )
    core_standing.start_standing(config=config)
    _reply(slack, slack.posted[0]["ts"])

    inbound.poll_once(config)

    skipped = [fields for name, fields in events if name == "channel.mirror_skipped"]
    assert skipped and skipped[0]["reason"] == "standing-session"
    assert not [name for name, _ in events if name == "channel.mirrored"]


def test_an_unauthorized_member_never_reaches_a_standing_session(tmp_path, tmux, slack):
    """
    Feature: standing sessions
      Scenario: an unauthorized Slack member never reaches a standing session
        Given a standing session with a bound Slack thread
        When a member outside channels.slack.authorizedUsers replies in it
        Then the reply is dropped before either standing branch runs

    Requirement: docs/specs/issue-277/requirements.md R4.4
    """
    config = _config(tmp_path)
    core_standing.start_standing(config=config)
    _reply(slack, slack.posted[0]["ts"], user="UINTRUDER")

    summary = inbound.poll_once(config)

    assert summary["dropped"] == 1 and summary["delivered"] == 0
    assert tmux.delivered == []


def test_the_bot_never_talks_to_the_session_it_announced(tmp_path, tmux, slack):
    config = _config(tmp_path)
    core_standing.start_standing(config=config)
    thread = slack.posted[0]["ts"]
    slack.replies[thread] = [{"ts": "1700.9", "user": "UBOT", "text": "hello"}]

    inbound.poll_once(config)

    assert tmux.delivered == []


def test_a_session_can_name_its_own_channel(tmp_path, tmux, slack):
    config = _config(tmp_path, channel="C-OPS")
    core_standing.start_standing(config=config)
    assert slack.posted[0]["channel"] == "C-OPS"
    # …while every other Slack setting stays centrally declared.
    assert SlackChannelConfig.from_mapping(config).channel == "C123"


def test_a_restart_keeps_talking_in_the_same_thread(tmp_path, tmux, slack):
    config = _config(tmp_path)
    core_standing.start_standing(config=config)
    core_standing.stop_standing(config=config)
    core_standing.start_standing(config=config)
    assert len(slack.posted) == 2  # the root and the announcement, once


def test_a_slack_failure_never_stops_the_session_starting(tmp_path, tmux, monkeypatch):
    class _Broken(FakeSlackClient):
        def chat_postMessage(self, **kwargs):
            raise RuntimeError("channel_not_found")

    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: _Broken())
    events = []
    monkeypatch.setattr(
        "the_loop.eventlog.emit",
        lambda event_type, **fields: events.append(event_type),
    )

    report = core_standing.start_standing(config=_config(tmp_path))

    assert report["sessions"][0]["outcome"] == "started"
    assert "standing.announce_failed" in events


def test_a_disabled_channels_block_announces_nothing(tmp_path, tmux, slack):
    config = _config(tmp_path)
    config["channels"]["slack"]["enabled"] = False
    report = core_standing.start_standing(config=config)
    assert report["sessions"][0]["outcome"] == "started"
    assert slack.posted == []
