"""The two message shortcuts and the decision modal, end to end (issue-389 R6).
Spec: docs/specs/issue-389/testing-plan.md T2.

Feature: a message shortcut is exactly the typed mention
Requirement: docs/specs/issue-389/requirements.md#R6
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from the_loop.channels import inbound, once
from the_loop.channels import slack as slack_mod
from test_channels_dm_integration import (  # noqa: F401
    listener_env,
    run_listener,
)
from test_channels_mentions_integration import (  # noqa: F401
    BOT,
    ROOM,
    Client,
    Sink,
    _thread_client,
    _token,
    config_for,
    declare,
    envelope_of,
    send,
)


@pytest.fixture(autouse=True)
def _fresh_ring():
    once.reset()
    yield
    once.reset()


class ModalClient(Client):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.views = []  # (trigger_id, view)

    def views_open(self, *, trigger_id, view):
        self.views.append((trigger_id, view))
        return {"ok": True, "view": {"id": "V1"}}


def action(
    callback,
    *,
    user="UHUMAN",
    channel=ROOM,
    ts="1800.2",
    thread="1800.1",
    text="the message",
    trigger="t-1",
):
    payload = {
        "type": "message_action",
        "callback_id": callback,
        "trigger_id": trigger,
        "user": {"id": user},
        "channel": {"id": channel},
        "message": {"ts": ts, "text": text},
    }
    if thread:
        payload["message"]["thread_ts"] = thread
    return payload


def shortcut(config, sink, client, payload):
    return inbound.handle_message_action(
        payload,
        config,
        post_comment=sink.post_comment,
        deliver=sink.deliver,
        client_factory=lambda token: client,
    )


def submission(
    config,
    sink,
    client,
    *,
    metadata,
    text="we ship",
    kind="tech",
    rationale="",
    user="UHUMAN",
    view_id="V1",
):
    values: dict = {"decision": {"text": {"value": text}}}
    if kind:
        values["kind"] = {"select": {"selected_option": {"value": kind}}}
    if rationale:
        values["rationale"] = {"text": {"value": rationale}}
    payload = {
        "type": "view_submission",
        "user": {"id": user},
        "view": {
            "id": view_id,
            "callback_id": "the-loop:record-decision",
            "private_metadata": metadata,
            "state": {"values": values},
        },
    }
    return inbound.handle_view_submission(
        payload,
        config,
        post_comment=sink.post_comment,
        deliver=sink.deliver,
        client_factory=lambda token: client,
    )


def test_the_context_shortcut_is_the_typed_mention(tmp_path):
    """
    Scenario: the context shortcut is the typed mention
      Given a thread in #389's room
      When an authorized member uses "Add to the-loop as context" on a message in it
      Then the outcome is byte for byte the typed `@the-loop record-context` on that thread
      And the member is answered ephemerally with the record's link
    """
    # Two installs with the same thread: a snapshot notes what it recorded, so
    # the second act on ONE install would rightly find nothing new.
    typed_config = config_for(tmp_path / "typed")
    declare(typed_config)
    typed_sink, typed_client = Sink(), _thread_client()
    typed = send(
        typed_config,
        typed_sink,
        typed_client,
        addressed=True,
        text=f"<@{BOT}> record-context",
        thread="1800.1",
        ts="1800.4",
    )
    tapped_config = config_for(tmp_path / "tapped")
    declare(tapped_config)
    tapped_sink, tapped_client = Sink(), _thread_client()
    tapped = shortcut(
        tapped_config, tapped_sink, tapped_client, action("the-loop:record-context")
    )
    assert typed["outcome"] == tapped["outcome"] == "processed"
    assert typed_sink.recorded[0][1] == tapped_sink.recorded[0][1]
    assert typed_sink.delivered[0]["text"] == tapped_sink.delivered[0]["text"]
    assert (
        tapped_client.ephemeral[-1][1] == "UHUMAN"
        and "issuecomment-1" in tapped_client.ephemeral[-1][2]
    )


def test_the_decision_shortcut_opens_the_modal_and_the_submission_is_the_typed_mention(
    tmp_path,
):
    """
    Scenario: the decision shortcut opens the modal and the submission is the typed mention
      When an authorized member uses "Record a decision" on a message
      Then a modal opens on the payload's trigger, pre-filled from the message, carrying the message's coordinates
      When they submit it with a kind and a rationale
      Then the outcome is the typed `@the-loop record-decision tech: … — why: …` on that message
    """
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), ModalClient()
    opened = shortcut(
        config,
        sink,
        client,
        action("the-loop:record-decision", text="keep poll mode", thread=""),
    )
    assert opened == {"outcome": "modal-opened"}
    trigger, view = client.views[0]
    assert (
        trigger == "t-1"
        and view["blocks"][0]["element"]["initial_value"] == "keep poll mode"
    )
    metadata = json.loads(view["private_metadata"])
    assert metadata == {"channel": ROOM, "ts": "1800.2", "thread_ts": "1800.2"}
    submitted = submission(
        config,
        sink,
        client,
        metadata=view["private_metadata"],
        text="keep poll mode",
        kind="tech",
        rationale="cheap",
    )
    assert (
        submitted["outcome"] == "processed"
        and submitted["event"] == "decision.recorded"
    )
    body = sink.recorded[0][1]
    assert "kind: tech" in body and "cheap" in body and "> keep poll mode" in body
    assert envelope_of(body).actor["slack"] == "UHUMAN"
    typed_sink, typed_client = Sink(), Client()
    send(
        config,
        typed_sink,
        typed_client,
        addressed=True,
        text=f"<@{BOT}> record-decision tech: keep poll mode — why: cheap",
        ts="1800.2",
    )
    assert typed_sink.delivered[0]["text"] == sink.delivered[0]["text"]
    assert (
        typed_sink.delivered[0]["detail"]["kind"] == sink.delivered[0]["detail"]["kind"]
    )


def test_a_shortcut_acts_once_per_trigger(tmp_path):
    """
    Scenario: a shortcut acts once per trigger
    """
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), _thread_client()
    first = shortcut(
        config, sink, client, action("the-loop:record-context", trigger="t-9")
    )
    again = shortcut(
        config, sink, client, action("the-loop:record-context", trigger="t-9")
    )
    assert first["outcome"] == "processed" and again == {"outcome": "duplicate"}
    assert len(sink.recorded) == 1
    sink2, client2 = Sink(), ModalClient()
    shortcut(config, sink2, client2, action("the-loop:record-decision", trigger="t-10"))
    metadata = client2.views[0][1]["private_metadata"]
    once_ = submission(config, sink2, client2, metadata=metadata, view_id="V7")
    twice = submission(config, sink2, client2, metadata=metadata, view_id="V7")
    assert once_["outcome"] == "processed" and twice == {"outcome": "duplicate"}


def test_a_collaborator_gets_the_context_shortcut_but_not_the_decision_modal(tmp_path):
    from test_channels_mentions_integration import _collaborator

    config = config_for(tmp_path)
    declare(config)
    _collaborator(config)
    sink, client = Sink(), ModalClient()
    refused = shortcut(
        config, sink, client, action("the-loop:record-decision", user="UCOLLAB")
    )
    assert refused == {"outcome": "unauthorized-act"} and client.views == []
    assert "authorized user" in client.ephemeral[-1][2]
    client.replies = _thread_client().replies
    ok = shortcut(
        config,
        sink,
        client,
        action("the-loop:record-context", user="UCOLLAB", trigger="t-2"),
    )
    assert ok["outcome"] == "processed"


def test_a_failed_modal_open_tells_the_member(tmp_path):
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), Client()  # no views_open on this fake

    outcome = shortcut(config, sink, client, action("the-loop:record-decision"))
    assert outcome == {"outcome": "modal-failed"}
    assert "record-decision" in client.ephemeral[-1][2]


def test_the_listener_routes_mentions_shortcuts_and_submissions(
    listener_env,  # noqa: F811 — the fixture, imported above
    monkeypatch,
):
    """
    Scenario: the listener routes app_mention, message_action and view_submission
      Given a connected Socket Mode listener
      When Slack delivers an app_mention, a message, a message_action and a view_submission
      Then each is acknowledged first and handed to its handler, the mention as addressed
    """
    seen = []
    monkeypatch.setattr(
        inbound,
        "handle_socket_event",
        lambda event, cfg, addressed=False: seen.append(
            ("event", event["type"], addressed)
        ),
    )
    monkeypatch.setattr(
        inbound,
        "handle_message_action",
        lambda payload, cfg: seen.append(("shortcut", payload["callback_id"])),
    )
    monkeypatch.setattr(
        inbound,
        "handle_view_submission",
        lambda payload, cfg: seen.append(("view", payload["view"]["callback_id"])),
    )
    monkeypatch.setattr(slack_mod, "catch_up", lambda cfg: {})
    stop = threading.Event()
    thread, client, _ = run_listener(listener_env, stop)
    try:
        client.deliver(
            "events_api", {"event": {"type": "app_mention", "text": "<@UBOT> hi"}}
        )
        client.deliver("events_api", {"event": {"type": "message", "text": "hi"}})
        client.deliver(
            "interactive",
            {"type": "message_action", "callback_id": "the-loop:record-context"},
        )
        client.deliver(
            "interactive",
            {
                "type": "view_submission",
                "view": {"callback_id": "the-loop:record-decision"},
            },
        )
    finally:
        stop.set()
        thread.join(timeout=5)
    assert len(client.acks) == 4
    assert seen == [
        ("event", "app_mention", True),
        ("event", "message", False),
        ("shortcut", "the-loop:record-context"),
        ("view", "the-loop:record-decision"),
    ]


# -- the recorded payload shapes (testing plan § Verification environment) ----------

FIXTURES = Path(__file__).parent / "fixtures" / "slack"


def _fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_the_recorded_payload_shapes_are_handled_as_the_typed_mention(tmp_path):
    """
    Scenario: Slack's own payload shapes drive the three handlers
      Given the app_mention, message_action and view_submission payloads as Slack sends them
      When each is handed to its handler with the room declared
      Then the mention records the thread as context, the shortcut does the same
      And the submission records the decision with its kind and rationale
    """
    config = config_for(tmp_path)
    declare(config)
    mention_sink, mention_client = Sink(), _thread_client()
    mentioned = inbound.handle_socket_event(
        _fixture("app_mention")["payload"]["event"],
        config,
        post_comment=mention_sink.post_comment,
        deliver=mention_sink.deliver,
        client_factory=lambda token: mention_client,
        addressed=True,
    )
    assert mentioned["outcome"] == "processed" and mentioned["event"] == "context.added"

    tapped_config = config_for(tmp_path / "tapped")
    declare(tapped_config)
    tapped_sink, tapped_client = Sink(), _thread_client()
    tapped = shortcut(
        tapped_config, tapped_sink, tapped_client, _fixture("message_action")["payload"]
    )
    assert tapped["outcome"] == "processed" and tapped["event"] == "context.added"
    assert tapped_sink.recorded[0][1] == mention_sink.recorded[0][1]

    submitted_sink, submitted_client = Sink(), _thread_client()
    submitted = inbound.handle_view_submission(
        _fixture("view_submission")["payload"],
        config,
        post_comment=submitted_sink.post_comment,
        deliver=submitted_sink.deliver,
        client_factory=lambda token: submitted_client,
    )
    assert submitted["outcome"] == "processed"
    assert submitted["event"] == "decision.recorded"
    body = submitted_sink.recorded[0][1]
    assert "> keep poll mode" in body and "kind: tech" in body and "it is cheap" in body
    assert envelope_of(body).actor["slack"] == "UHUMAN"


def test_the_listener_routes_the_recorded_payload_shapes(
    listener_env,  # noqa: F811 — the fixture, imported above
    monkeypatch,
):
    seen = []
    monkeypatch.setattr(
        inbound,
        "handle_socket_event",
        lambda event, cfg, addressed=False: seen.append((event["type"], addressed)),
    )
    monkeypatch.setattr(
        inbound,
        "handle_message_action",
        lambda payload, cfg: seen.append((payload["type"], payload["callback_id"])),
    )
    monkeypatch.setattr(
        inbound,
        "handle_view_submission",
        lambda payload, cfg: seen.append(
            (payload["type"], payload["view"]["callback_id"])
        ),
    )
    monkeypatch.setattr(slack_mod, "catch_up", lambda cfg: {})
    stop = threading.Event()
    thread, client, _ = run_listener(listener_env, stop)
    try:
        for name in ("app_mention", "message_action", "view_submission"):
            envelope = _fixture(name)
            client.deliver(envelope["type"], envelope["payload"])
    finally:
        stop.set()
        thread.join(timeout=5)
    assert len(client.acks) == 3
    assert seen == [
        ("app_mention", True),
        ("message_action", "the-loop:record-context"),
        ("view_submission", "the-loop:record-decision"),
    ]


# -- self-review round 1 (finding 7): what a shortcut says back ---------------------


class RefusingSink(Sink):
    def post_comment(self, item, body, **kwargs) -> tuple:
        return False, "boom: the ledger refused", ""


def test_a_shortcut_where_nothing_is_bound_says_nothing(tmp_path):
    """A8: no room, no binding → silence, whoever tapped."""
    config = config_for(tmp_path)  # nothing declared
    sink, client = Sink(), _thread_client()
    outcome = shortcut(
        config, sink, client, action("the-loop:record-context", channel="C0NOBODY")
    )
    assert outcome["outcome"] == "unmapped"
    assert client.ephemeral == [] and sink.recorded == []


def test_a_shortcut_whose_record_failed_says_so(tmp_path):
    config = config_for(tmp_path)
    declare(config)
    sink, client = RefusingSink(), _thread_client()
    outcome = shortcut(config, sink, client, action("the-loop:record-context"))
    assert outcome["outcome"] == "processed" and outcome["mirrored"] is False
    assert client.ephemeral[-1][2].startswith("Could not record: boom")


def test_the_decision_modal_is_not_offered_without_the_grant(tmp_path):
    config = config_for(tmp_path, publish=["work-item.reply", "context.added"])
    declare(config)
    sink, client = Sink(), ModalClient()
    outcome = shortcut(config, sink, client, action("the-loop:record-decision"))
    assert outcome["outcome"] == "unpublishable-event"
    assert client.views == []
    assert "decision.recorded" in client.ephemeral[-1][2]


def test_a_decision_shortcut_on_a_standing_thread_is_refused_before_the_form(tmp_path):
    """Round 2, finding 3: no modal whose submission would be `no-ticket`."""
    from test_channels_mentions_integration import DM, bot_for

    config = config_for(tmp_path, channel=DM)
    sink, client = Sink(), ModalClient()
    bot_for(config, client).bind("1800.1", "standing:review", DM, origin="start")
    outcome = shortcut(
        config, sink, client, action("the-loop:record-decision", channel=DM)
    )
    assert outcome["outcome"] == "no-ticket" and client.views == []
    assert len(client.ephemeral) == 1 and "standing session" in client.ephemeral[0][2]


def test_a_refused_shortcut_is_told_once(tmp_path):
    """Round 2, finding 3: the pipeline's ephemeral is the only one."""
    from test_channels_mentions_integration import DM, bot_for

    config = config_for(tmp_path, channel=DM)
    sink, client = Sink(), _thread_client()
    bot_for(config, client).bind("1800.1", "standing:review", DM, origin="start")
    outcome = shortcut(
        config, sink, client, action("the-loop:record-context", channel=DM)
    )
    assert outcome["outcome"] == "no-ticket"
    assert len(client.ephemeral) == 1


def test_a_shortcut_with_nothing_new_is_told_once(tmp_path):
    """Round 3, finding 2."""
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), _thread_client()
    first = shortcut(config, sink, client, action("the-loop:record-context"))
    assert first["outcome"] == "processed"
    told = len(client.ephemeral)
    again = shortcut(
        config, sink, client, action("the-loop:record-context", trigger="t-2")
    )
    assert again["outcome"] == "nothing-new"
    assert len(client.ephemeral) == told + 1
    assert "Nothing new" in client.ephemeral[-1][2]
