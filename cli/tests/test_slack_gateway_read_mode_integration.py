"""Integration scenarios for issue-503 (T2): an instance in ``read.mode: gateway``
handles the Slack envelopes its gateway client delivers, and renders the buttons a
press through the gateway can answer.

Feature: a gateway consumer that never opens Socket Mode keeps every interactive feature
"""

from __future__ import annotations

from test_channels_buttons import (
    FakeSlackClient,
    _bind,
    _wire,
    a_press,
    buttons,
    cli_config,
)
from the_loop.channels.base import OutboundEvent
from the_loop.channels.slack import SlackBotChannel, SlackChannelConfig
from the_loop.core import lifecycle
from the_loop.gateway.client_dispatch import Pipeline
from the_loop.gateway.envelope import Delivery, Envelope

GRANTS = ["work-item.reply", "gate.feedback", "control.command"]


def gateway_config(tmp_path, *, gateway=True):
    config = cli_config(tmp_path, read={"mode": "gateway"}, publish=list(GRANTS))
    if gateway:
        config["gateway"] = {"url": "https://gateway.example"}
    return config


def a_delivery(kind, payload):
    return Delivery(
        seq=1,
        attempt=1,
        event=Envelope(
            subject="slack:C123",
            provider="slack",
            source="socket",
            delivery_id="env-503",
            kind=kind,
            payload=payload,
        ),
    )


def test_an_approval_press_reaches_a_gateway_mode_instance(tmp_path, monkeypatch):
    """
    Feature: a gateway consumer that never opens Socket Mode keeps every interactive feature
      Scenario: a button pressed in Slack reaches a gateway-mode instance and is handled
        Given an instance with a gateway block and channels.slack.read.mode: gateway
          And a bound thread carrying the phase-selection checklist
        When the gateway client delivers the member's Execute press
        Then the press is recorded on the ledger and the pressed message is rewritten
          And the instance hosts no Slack listener of its own

    Requirement: docs/specs/issue-503/requirements.md#requirement-1 (R1.2, R1.4), R2.2
    """
    records = []
    _wire(monkeypatch, records)
    config = gateway_config(tmp_path)
    client = FakeSlackClient()
    _, thread, _ = _bind(tmp_path, monkeypatch, client, config)
    seen = []

    def dispatch(kind, payload, cli):
        from the_loop.channels import inbound

        outcome = inbound.handle_socket_action(
            dict(payload), cli, client_factory=lambda token: client
        )
        seen.append(outcome)
        return "handled:block-actions"

    pipeline = Pipeline(
        router=None, dispatcher=None, cli_config=config, slack_dispatch=dispatch
    )
    assert (
        pipeline.dispatch(a_delivery("interactive", a_press(thread=thread)))
        == "delivered"
    )
    assert seen and seen[0]["outcome"] == "processed"
    assert len(records) == 1 and "the-loop execute" in records[0][1]
    assert len(client.updates) == 1
    assert lifecycle.enabled_services(config)["slack-listener"] is False


def test_the_real_classifier_routes_a_gateway_press(tmp_path, monkeypatch):
    """
    Feature: a gateway consumer that never opens Socket Mode keeps every interactive feature
      Scenario: the gateway client's Slack path classifies a press without checking the read mode
        Given an instance in read.mode: gateway
        When an interactive block_actions envelope is delivered through the pipeline
        Then the one shared classifier hands it to the press handler

    Requirement: docs/specs/issue-503/requirements.md#requirement-1 (R1.4)
    """
    calls = []
    monkeypatch.setattr(
        "the_loop.channels.inbound.handle_socket_action",
        lambda payload, cli: calls.append((payload["type"], cli["gateway"]["url"])),
    )
    pipeline = Pipeline(
        router=None, dispatcher=None, cli_config=gateway_config(tmp_path)
    )
    out = pipeline.dispatch(a_delivery("interactive", a_press()))
    assert out == "delivered"
    assert calls == [("block_actions", "https://gateway.example")]


def test_a_gateway_mode_instance_renders_the_approve_pair(tmp_path, monkeypatch):
    """
    Feature: a gateway consumer that never opens Socket Mode keeps every interactive feature
      Scenario: a gateway-mode instance renders Approve / Request changes on an approval notification
        Given an instance in read.mode: gateway with the gate.feedback grant
        When a phase-approval-pending event is posted to its Slack channel
        Then the message carries the Approve and Request changes buttons
          And without the gateway block the same event carries neither

    Requirement: docs/specs/issue-503/requirements.md#requirement-2 (R2.2), R3.1
    """
    monkeypatch.setenv("THE_LOOP_SLACK_BOT_TOKEN", "xoxb-test")
    event = OutboundEvent(
        event_type="phase-approval-pending",
        work_item="github:o/r#7",
        text="requirements.md is ready for review",
        url="https://github.com/o/r/issues/7#c2",
        detail={},
    )

    def posted(config):
        client = FakeSlackClient()
        SlackBotChannel(
            SlackChannelConfig.from_mapping(config),
            tmp_path / "state" / "channels" / "slack.json",
            client_factory=lambda token: client,
        ).post(event)
        return [action for action, _ in buttons(client.posted[-1]["blocks"])]

    with_block = posted(gateway_config(tmp_path))
    assert "the-loop:approve" in with_block and "the-loop:changes" in with_block
    without = posted(gateway_config(tmp_path, gateway=False))
    assert "the-loop:approve" not in without and "the-loop:changes" not in without
