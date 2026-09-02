"""Integration scenarios for the event bus (issue-309): the ask as one record, the
comment mirror, the gate and control grants, the kickoff, the completion event and
the Approve button — through the real modules, with the Slack SDK client, the
GitHub writers and session delivery faked at their injection points."""

from __future__ import annotations

import pytest

from the_loop.authz import is_self_authored
from the_loop.channels import envelope as env
from the_loop.channels import inbound
from the_loop.channels.slack import DEFAULT_BOT_TOKEN_ENV
from the_loop.channels.state import ChannelState
from the_loop.control import ControlConfig, parse_command
from the_loop.core import sessions as core_sessions
from the_loop.graphlink import comments_from
from the_loop.webhook.router import Router, RoutedEvent

OPERATOR = "octocat"  # the login the-loop's own credential posts as


def _etype(body):
    parsed = env.parse(body)
    assert parsed is not None
    return parsed.type


class FakeSlackClient:
    def __init__(self):
        self.posted = []
        self.replies = {}
        self.history = []

    def chat_postMessage(self, *, channel, text, thread_ts=None, blocks=None):
        self.posted.append(
            {"channel": channel, "text": text, "thread_ts": thread_ts, "blocks": blocks}
        )
        return {"ok": True, "channel": channel, "ts": f"1700.{len(self.posted):06d}"}

    def conversations_replies(self, *, channel, ts, oldest=None, limit=200):
        return {"ok": True, "messages": list(self.replies.get(ts, []))}

    def conversations_history(self, *, channel, oldest=None, limit=100):
        return {"ok": True, "messages": list(self.history)}

    def auth_test(self):
        return {"ok": True, "user_id": "UBOT"}


def cli_config(tmp_path, **slack):
    section = {"enabled": True, "channel": "C123", **slack}
    return {
        "state": {"root": str(tmp_path / "state")},
        "routing": {
            "authorizedUsers": [{"github": OPERATOR, "slack": "UHUMAN", "name": "Octo"}]
        },
        "channels": {"ledger": "github", "slack": section},
    }


@pytest.fixture
def slack(monkeypatch):
    client = FakeSlackClient()
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    monkeypatch.setattr("the_loop.channels.slack.build_client", lambda token: client)
    return client


def _ledger_writer(monkeypatch, sink):
    """Every ledger write lands in ``sink`` — the pipeline's writer and the ask's."""

    def write(item, body, gh_binary="gh"):
        sink.append((item.ref, body))
        return True, "", f"https://gh/c/{len(sink)}"

    monkeypatch.setattr("the_loop.comments.post_issue_comment_with_url", write)
    monkeypatch.setattr(core_sessions, "post_issue_comment_with_url", write)


def _bound_thread(tmp_path, config, slack, ref="github:o/r#7"):
    """A thread the-loop started for ``ref`` — the ask, through the bus."""
    result = core_sessions.ask_session(ref, "A or B?", config=config)
    assert result["asked"] is True
    bound = ChannelState.load(
        tmp_path / "state" / "channels" / "slack.json"
    ).thread_for(ref)
    assert bound is not None
    return bound[1]


def test_an_asked_question_is_one_ledger_comment_and_one_slack_post(
    tmp_path, monkeypatch, slack
):
    """Scenario: An asked question is one ledger comment and one Slack post

    Given a Slack channel subscribed to session.awaiting_input
    When the agent runs `the-loop ask`
    Then the ledger records the question once — marked, enveloped — before Slack
    And the Slack post carries the record's link as a button
    And the record is one the ledger's ingress will never re-publish

    Requirement: docs/specs/issue-309/requirements.md R1.3, R1.4, R3.3, R3.7
    """
    records = []
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (
            records.append((item.ref, body)) or (True, "", "https://gh/c/1")
        ),
    )
    config = cli_config(tmp_path)
    result = core_sessions.ask_session("github:o/r#7", "A or B?", config=config)

    assert result["asked"] is True and result["commentUrl"] == "https://gh/c/1"
    assert len(records) == 1
    ref, body = records[0]
    assert ref == "github:o/r#7" and is_self_authored(body)
    assert _etype(body) == "session.awaiting_input"
    assert len(slack.posted) == 1
    buttons = slack.posted[0]["blocks"][-1]["elements"]
    assert buttons[0]["url"] == "https://gh/c/1"
    from the_loop.channels.publishers import publish_comment

    assert publish_comment("agent", ref, OPERATOR, body, "", config) is False


def test_an_agents_comment_reaches_slack_and_a_humans_only_when_subscribed(
    tmp_path, monkeypatch, slack
):
    """Scenario: An agent's comment reaches the Slack thread and a human's reaches
    it only when subscribed

    Given a bound thread and a Slack channel subscribed to comment.agent alone
    When the webhook router sees the agent's own marked comment on the work item
    Then it is dropped at ingress as before AND posted into the bound Slack thread
    When the router sees an authorized human's comment
    Then it is routed as before and NOT posted to Slack
    When the channel also subscribes to comment.human
    Then the human's comment reaches the thread too
    And a bus record (enveloped) is never re-published

    Requirement: docs/specs/issue-309/requirements.md R6.1, R3.7 (A10)
    """
    from the_loop.authz import mark_self_authored
    from the_loop.channels.publishers import comment_publisher

    _ledger_writer(monkeypatch, [])
    config = cli_config(tmp_path, subscribe=["session.awaiting_input", "comment.agent"])
    _bound_thread(tmp_path, config, slack)
    assert len(slack.posted) == 1

    def comment(body, author=OPERATOR):
        return {
            "action": "created",
            "repository": {"full_name": "o/r"},
            "issue": {"number": 7, "html_url": "https://gh/o/r/issues/7"},
            "comment": {
                "body": body,
                "user": {"login": author},
                "html_url": "https://gh/o/r/issues/7#c9",
            },
        }

    holder = {"config": config}
    router = Router(
        events=[],
        authorized_users=[OPERATOR],
        publisher=comment_publisher(lambda: holder["config"]),
    )

    agent = router.route(
        "issue_comment", comment(mark_self_authored("## Summary")), "d1"
    )
    assert agent is None  # dropped at ingress, exactly as before
    assert len(slack.posted) == 2
    assert slack.posted[1]["thread_ts"] == slack.posted[0]["thread_ts"]
    assert "## Summary" in slack.posted[1]["text"]

    human = router.route("issue_comment", comment("looks good"), "d2")
    assert isinstance(human, RoutedEvent)
    assert len(slack.posted) == 2  # not subscribed to comment.human

    holder["config"] = cli_config(
        tmp_path, subscribe=["session.awaiting_input", "comment.agent", "comment.human"]
    )
    assert router.route("issue_comment", comment("ship it"), "d3") is not None
    assert len(slack.posted) == 3 and "ship it" in slack.posted[2]["text"]
    assert "@octocat" in slack.posted[2]["blocks"][0]["text"]["text"]

    record = env.stamp(
        mark_self_authored("> yes"), env.Envelope("work-item.reply", "slack")
    )
    assert router.route("issue_comment", comment(record), "d4") is None
    assert len(slack.posted) == 3  # A10: the bus's own record is never echoed

    assert router.route("issue_comment", comment("hi", author="stranger"), "d5") is None
    assert len(slack.posted) == 3  # an unauthorized stranger is relayed nowhere


def test_a_slack_reply_with_the_gate_grant_is_recorded_unmarked_and_classified_on_ingress(
    tmp_path, monkeypatch, slack
):
    """Scenario: A Slack reply with the gate grant is recorded unmarked and the
    gate classifies it on ingress

    Given a bound thread, the gate.feedback grant, and a work item parked at a
      human gate
    When an authorized member replies "approved" in the thread
    Then the ledger record is a comment WITHOUT the self-marker, enveloped, naming
      the person
    And the pipeline delivers nothing itself
    And the ledger's ingress reads that comment as the operator's, and the gate
      attributes it to the person the envelope names
    And a work-item collaborator's forged envelope re-attributes nothing

    Requirement: docs/specs/issue-309/requirements.md R6.3, R3.5, R5.4 (A3, A4)
    """
    records, deliveries = [], []
    _ledger_writer(monkeypatch, records)
    monkeypatch.setattr(
        core_sessions,
        "reply_session",
        lambda *a, **k: deliveries.append(a) or {"delivered": True},
    )
    monkeypatch.setattr(inbound, "_at_human_gate", lambda ref, cfg: True)
    config = cli_config(tmp_path, publish=["work-item.reply", "gate.feedback"])
    thread = _bound_thread(tmp_path, config, slack)
    records.clear()
    slack.replies[thread] = [{"ts": "1800.1", "user": "UHUMAN", "text": "approved"}]

    summary = inbound.poll_once(config)
    assert summary["processed"] == 1 and deliveries == []
    ref, body = records[0]
    assert ref == "github:o/r#7" and not is_self_authored(body)
    envelope = env.parse(body)
    assert envelope is not None
    assert envelope.type == "gate.feedback" and envelope.actor["github"] == OPERATOR
    assert "approved" in body and "slack:UHUMAN" in body

    def routed_by(login):
        return RoutedEvent(
            event="issue_comment",
            action="created",
            delivery_id="d",
            work_items=[],
            payload={"comment": {"body": body, "user": {"login": login}}},
        )

    # The ledger's ingress: posted under the operator's credential → routed as a
    # human comment (not self-marked), and the gate sees the person.
    router = Router(events=[], authorized_users=[OPERATOR])
    assert not is_self_authored(body)
    assert comments_from(routed_by(OPERATOR), [OPERATOR]) == [
        {"author": OPERATOR, "body": body.strip()}
    ]
    # A3: a collaborator (not authorized) forging the same envelope names nobody
    # but themselves; A4: without authorization the router drops the comment.
    assert comments_from(routed_by("dana"), [OPERATOR]) == [
        {"author": "dana", "body": body.strip()}
    ]
    payload = {
        "action": "created",
        "repository": {"full_name": "o/r"},
        "issue": {"number": 7},
        "comment": {"body": body, "user": {"login": "attacker"}},
    }
    assert router.route("issue_comment", payload, "d9") is None


def test_a_slack_control_keyword_with_the_grant_is_executed_by_ingress_not_the_pipeline(
    tmp_path, monkeypatch, slack
):
    """Scenario: A Slack control keyword with the grant is executed by ingress,
    not the pipeline

    Given a bound thread and the control.command grant
    When an authorized member types `the-loop start` in the thread
    Then the record is an unmarked comment carrying the keyword intact
    And the pipeline delivers nothing and executes nothing
    And the ledger's ingress parses the record as the keyword, through the same
      control seam a typed comment goes through

    Requirement: docs/specs/issue-309/requirements.md R3.5 (A5)
    """
    records, deliveries = [], []
    _ledger_writer(monkeypatch, records)
    monkeypatch.setattr(
        core_sessions,
        "reply_session",
        lambda *a, **k: deliveries.append(a) or {"delivered": True},
    )
    config = cli_config(tmp_path, publish=["work-item.reply", "control.command"])
    thread = _bound_thread(tmp_path, config, slack)
    records.clear()
    slack.replies[thread] = [
        {"ts": "1800.1", "user": "UHUMAN", "text": "the-loop start"}
    ]

    assert inbound.poll_once(config)["processed"] == 1
    assert deliveries == []
    body = records[0][1]
    assert not is_self_authored(body)
    assert parse_command(body, ControlConfig()).command == "start"
    assert _etype(body) == "control.command"


def test_without_a_grant_a_reply_is_session_input_and_nothing_more(
    tmp_path, monkeypatch, slack
):
    """Scenario: Without a grant a reply is session input and nothing more

    Given a bound thread, the default grant, and a work item parked at a gate
    When an authorized member replies "approved"
    Then the message is dropped as unpublishable-event — never recorded unmarked,
      never delivered as prose
    And an ordinary reply on a work item that is not at a gate is mirrored and
      delivered exactly as before

    Requirement: docs/specs/issue-309/requirements.md R2.2, R2.3
    """
    records, deliveries = [], []
    _ledger_writer(monkeypatch, records)
    monkeypatch.setattr(
        core_sessions,
        "reply_session",
        lambda *a, **k: deliveries.append(a) or {"delivered": True},
    )
    config = cli_config(tmp_path)
    thread = _bound_thread(tmp_path, config, slack)
    records.clear()

    monkeypatch.setattr(inbound, "_at_human_gate", lambda ref, cfg: True)
    slack.replies[thread] = [{"ts": "1800.1", "user": "UHUMAN", "text": "approved"}]
    summary = inbound.poll_once(config)
    assert summary["dropped"] == 1 and records == [] and deliveries == []

    monkeypatch.setattr(inbound, "_at_human_gate", lambda ref, cfg: False)
    slack.replies[thread] = [{"ts": "1800.2", "user": "UHUMAN", "text": "go with A"}]
    summary = inbound.poll_once(config)
    assert summary["processed"] == 1 and summary["delivered"] == 1
    assert is_self_authored(records[0][1])
    assert _etype(records[0][1]) == "work-item.reply"


def test_a_top_level_dm_becomes_a_labelled_issue_bound_to_its_thread(
    tmp_path, monkeypatch, slack
):
    """Scenario: A top-level DM becomes a labelled issue bound to its thread

    Given the work-item.create grant, a kickoff repo and labels
    When the first read baselines the channel
    Then nothing earlier is turned into a work item
    When an authorized member posts a new top-level message
    Then an issue is created in the configured repo with the configured labels
    And the thread is bound to the new ref and told the link
    And a stranger's message, a bot's, and a message with no repo configured
      create nothing

    Requirement: docs/specs/issue-309/requirements.md R6.5, R3.6 (A1, A6, A7)
    """
    created = []

    def create(repo, title, body, labels, gh_binary="gh"):
        created.append((repo, title, labels))
        return True, "", "github:o/r#42", "https://gh/o/r/issues/42"

    monkeypatch.setattr("the_loop.comments.create_issue", create)
    config = cli_config(
        tmp_path,
        publish=["work-item.reply", "work-item.create"],
        kickoff={"repo": "o/r", "labels": ["the-loop: auto-execute"]},
    )
    slack.history = [{"ts": "1600.1", "user": "UHUMAN", "text": "old backlog item"}]
    assert inbound.poll_once(config)["created"] == 0
    assert created == []  # first sight baselines

    slack.history.append(
        {"ts": "1600.2", "user": "UHUMAN", "text": "Ship it\n\ndetails"}
    )
    slack.history.append({"ts": "1600.3", "user": "USTRANGER", "text": "me too"})
    slack.history.append(
        {"ts": "1600.4", "user": "UBOT", "bot_id": "B1", "text": "bot"}
    )
    summary = inbound.poll_once(config)
    assert summary["created"] == 1 and summary["dropped"] == 2
    assert created == [("o/r", "Ship it", ["the-loop: auto-execute"])]
    state = ChannelState.load(tmp_path / "state" / "channels" / "slack.json")
    assert state.work_item_for("1600.2") == "github:o/r#42"
    assert slack.posted[-1]["thread_ts"] == "1600.2"
    assert "github:o/r#42" in slack.posted[-1]["text"]
    assert inbound.poll_once(config)["created"] == 0  # cursor advanced

    no_repo = cli_config(tmp_path, publish=["work-item.reply", "work-item.create"])
    slack.history.append({"ts": "1600.5", "user": "UHUMAN", "text": "another"})
    assert inbound.poll_once(no_repo)["created"] == 0 and len(created) == 1


def test_the_complete_node_announces_work_item_complete_with_a_link(
    tmp_path, monkeypatch, slack
):
    """Scenario: The complete node announces work-item-complete with a link

    Given a Slack channel subscribed to work-item-complete and phase-approval-pending
    When the outer loop's complete node fires its notify hook
    Then the event reaches Slack with the work item's link, roles or no roles
    When an approval node's notify names its artifact
    Then the Slack message carries an excerpt of that artifact

    Requirement: docs/specs/issue-309/requirements.md R6.4, R4.4, R6.2
    """
    from the_loop.graph.contract import HookContext, WorkItem
    from the_loop.graph.hooks.sideeffects import notify
    from the_loop.graph.model import load_graph, shipped_graph_path

    graph = load_graph(shipped_graph_path("pdlc-work-item-loop"))
    complete = graph.nodes["complete"]
    assert any(
        getattr(h, "hook", h) == "notify"
        or (isinstance(h, dict) and h.get("hook") == "notify")
        for h in complete.entry
    ) or "notify" in str(complete.entry)

    spec = tmp_path / "specs" / "issue-7"
    spec.mkdir(parents=True)
    (spec / "requirements.md").write_text(
        "---\ntype: requirements\n---\n\n# Requirements: x\n\n## R1\n\nthe thing\n"
    )
    config = cli_config(
        tmp_path, subscribe=["work-item-complete", "phase-approval-pending"]
    )

    def ctx(event, artifact=None):
        return HookContext(
            work_item=WorkItem(id="issue-7", ref="github:o/r#7", spec_dir=spec),
            node={"id": "complete"},
            boundary="entry",
            repo=tmp_path,
            config=config,  # no notifications.events roles at all
            params={"event": event, **({"artifact": artifact} if artifact else {})},
        )

    done = notify(ctx("work-item-complete"))
    assert done.status == "pass" and done.data["delivered"] is True
    post = slack.posted[-1]
    assert "Done" in post["blocks"][0]["text"]["text"]
    assert post["blocks"][-1]["elements"][0]["url"] == "https://github.com/o/r/issues/7"

    gate = notify(ctx("phase-approval-pending", artifact="requirements.md"))
    assert gate.status == "pass"
    text = " ".join(
        b["text"]["text"] for b in slack.posted[-1]["blocks"] if "text" in b
    )
    assert "the thing" in text and "type: requirements" not in text


def test_an_approve_button_press_enters_the_pipeline_as_that_members_reply(
    tmp_path, monkeypatch, slack
):
    """Scenario: An Approve button press enters the pipeline as that member's reply

    Given Socket Mode with the gate.feedback grant and a bound thread at a gate
    When an authorized member presses Approve
    Then the record is an unmarked gate.feedback comment saying "approved"
    When an unauthorized member presses it
    Then nothing is recorded
    When a crafted action carries an unknown value
    Then it is judged as plain text through the same pipeline

    Requirement: docs/specs/issue-309/requirements.md R4.3 (A9)
    """
    records = []
    _ledger_writer(monkeypatch, records)
    monkeypatch.setattr(inbound, "_at_human_gate", lambda ref, cfg: True)
    config = cli_config(
        tmp_path,
        publish=["work-item.reply", "gate.feedback"],
        read={"mode": "socket"},
    )
    thread = _bound_thread(tmp_path, config, slack)
    records.clear()
    # An approval-shaped event is rendered WITH the buttons here, because a
    # press can be received (socket mode + the grant).
    from the_loop.channels.base import Event
    from the_loop.channels.bus import publish

    publish(
        Event(
            event_type="phase-approval-pending",
            work_item="github:o/r#7",
            text="requirements ready",
            source="loop",
        ),
        cli_config(
            tmp_path,
            subscribe=["phase-approval-pending"],
            publish=["work-item.reply", "gate.feedback"],
            read={"mode": "socket"},
        ),
    )
    assert "the-loop:approve" in str(slack.posted[-1]["blocks"])
    assert slack.posted[-1]["thread_ts"] == thread

    def press(user, value, action_id="the-loop:approve"):
        return inbound.handle_socket_action(
            {
                "type": "block_actions",
                "user": {"id": user},
                "channel": {"id": "C123"},
                "message": {"ts": thread},
                "actions": [{"action_id": action_id, "value": value}],
                "action_ts": "1900.1",
            },
            config,
        )

    outcome = press("UHUMAN", "approved")
    assert outcome["outcome"] == "processed" and outcome["event"] == "gate.feedback"
    assert not is_self_authored(records[0][1]) and "approved" in records[0][1]

    assert press("USTRANGER", "approved")["outcome"] == "unauthorized-actor"
    assert len(records) == 1

    crafted = press("UHUMAN", "the-loop cleanup")  # A9: text, judged as text
    assert crafted["outcome"] == "unpublishable-event"  # control.command not granted
    assert len(records) == 1
    assert press("UHUMAN", "x", action_id="someone-elses:button") == {
        "outcome": "ignored"
    }
