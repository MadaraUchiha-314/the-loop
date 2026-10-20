"""Integration scenarios for collaboration-channel rooms behind a gateway (issue-505,
T2/T8 — R1.1, R1.2, R1.4, R2.2, R3.1, R4.1, R4.3, R7.2; abuse case 4): a real
GatewayClient attached to a real Dispatcher's channel store, publishing to a real gateway
app in-process, fed by signed Slack HTTP events.

Feature: a work item's collaboration channel routes every collaborator's message to it
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import time
from typing import Any, Iterator, List

import pytest

from gateway_support import GatewayHarness, Instance
from the_loop.gateway.adapters.ingest import Ingest
from the_loop.gateway.adapters.slack_http import build_slack_http_router
from the_loop.gateway.envelope import Delivery
from the_loop.workchannels import CollaborationChannelStore

SIGNING = "slack-signing-secret"
REF = "github:o/r#14"
SUBJECT = "loop-github-o-r-14"
ROOM = "C0123ABCD"


def _harness(tmp_path, monkeypatch) -> GatewayHarness:
    monkeypatch.setenv("SLACK_SIGNING_SECRET", SIGNING)
    harness = GatewayHarness(tmp_path, slack={"http": {"enabled": True}})
    harness.app.include_router(
        build_slack_http_router(Ingest(harness.state), harness.config)
    )
    return harness


@pytest.fixture()
def gw(tmp_path, monkeypatch) -> Iterator[GatewayHarness]:
    harness = _harness(tmp_path / "gw", monkeypatch)
    yield harness
    harness.close()


class Laptop:
    """laptop-a: registers U_OPERATOR, drives o/r#14, and records what it is handed."""

    def __init__(self, gw: GatewayHarness, root, monkeypatch):
        self.instance = Instance(gw, root, "laptop-a", actors=())
        self.client = self.instance.client
        self.client.block = dataclasses.replace(
            self.client.block, actors={"slack": ("U_OPERATOR",)}
        )
        self.channels: CollaborationChannelStore = (
            self.instance.dispatcher.channel_store
        )
        self.client.attach(
            self.instance.registry,
            control_store=self.instance.control,
            pipeline=self.instance.pipeline,
            channel_store=self.channels,
        )
        # what api/ingress.py wires for the hosted client
        monkeypatch.setattr(
            CollaborationChannelStore, "on_change", lambda: self.client.publish_rooms()
        )
        self.handed: List[Delivery] = []
        self.client._dispatch = lambda d: (self.handed.append(d), "delivered")[1]
        self.instance.register_session(REF)

    def poll(self) -> List[Delivery]:
        before = len(self.handed)
        self.client.step()
        return self.handed[before:]

    def stop(self) -> None:
        self.instance.stop()


@pytest.fixture()
def laptop(gw, tmp_path, monkeypatch) -> Iterator[Laptop]:
    instance = Laptop(gw, tmp_path / "a", monkeypatch)
    yield instance
    instance.stop()


def _post(gw: GatewayHarness, user: str, ts: str, channel: str = ROOM) -> None:
    body = json.dumps(
        {
            "event_id": f"Ev-{ts}",
            "team_id": "T1",
            "event": {
                "type": "app_mention",
                "channel": channel,
                "ts": ts,
                "user": user,
                "text": "<@UBOT> what is left?",
            },
        }
    ).encode()
    stamp = str(int(time.time()))
    sig = "v0=" + hmac.new(
        SIGNING.encode(), b"v0:" + stamp.encode() + b":" + body, hashlib.sha256
    ).hexdigest()
    answer = gw.client.post(
        "/slack/events",
        content=body,
        headers={
            "X-Slack-Signature": sig,
            "X-Slack-Request-Timestamp": stamp,
            "Content-Type": "application/json",
        },
    )
    assert answer.status_code == 200


def _routed(gw: GatewayHarness) -> List[Any]:
    return [(r.get("subject"), r.get("by")) for r in gw.events("subject.routed")]


def test_a_collaborators_top_level_message_in_a_declared_room_reaches_the_work_item(
    gw, laptop
):
    """
    Feature: a work item's collaboration channel routes every collaborator's message to it
      Scenario: a collaborator's top-level message in a declared room reaches the work item
        Given laptop-a registers only Slack user U_OPERATOR and drives o/r#14
        And laptop-a declares slack@C0123ABCD as o/r#14's collaboration channel
        When U_COLLAB, registered by no instance, posts a top-level mention in C0123ABCD
        Then the gateway routes it to loop-github-o-r-14 by claim
        And laptop-a is handed the raw event, author and all, for its own pipeline to judge

    Requirement: docs/specs/issue-505/requirements.md#requirement-2 (R2.2), R1.1, R1.2,
                 R6.1, R7.2
    """
    laptop.poll()  # registers actors, the claim and the (empty) set of rooms
    laptop.channels.add(REF, f"slack@{ROOM}", actor="octocat")  # hook → PUT /rooms
    assert gw.store.resolve_room(ROOM) == (REF, "github-o-r-14")
    (rooms,) = [r for r in gw.events("gateway.rooms") if r["rooms"] == 1]
    assert rooms["instance"] == "laptop-a"

    _post(gw, "U_COLLAB", "1700.1")

    assert _routed(gw)[-1] == (SUBJECT, "claim")
    (delivery,) = laptop.poll()
    assert delivery.event.subject == SUBJECT and delivery.event.work_item == REF
    # abuse case 4: the gateway judged nothing; the instance gets the author to check
    assert delivery.event.payload["event"]["user"] == "U_COLLAB"


def test_messages_held_before_the_room_was_published_are_routed_when_it_is(gw, laptop):
    """
    Feature: a work item's collaboration channel routes every collaborator's message to it
      Scenario: messages held before the room was published are routed when it is
        Given laptop-a drives o/r#14 and has declared no collaboration channel
        And U_COLLAB has posted two top-level mentions in C0123ABCD, both held
        When laptop-a declares slack@C0123ABCD on o/r#14
        Then both held messages are routed to loop-github-o-r-14, in the order they arrived

    Requirement: docs/specs/issue-505/requirements.md#requirement-3 (R3.1)
    """
    laptop.poll()
    _post(gw, "U_COLLAB", "1700.1")
    _post(gw, "U_COLLAB", "1700.2")
    assert [by for _, by in _routed(gw)] == ["hold", "hold"]
    assert laptop.poll() == []

    laptop.channels.add(REF, f"slack@{ROOM}", actor="octocat")

    handed = laptop.poll()
    assert [d.event.payload["event"]["ts"] for d in handed] == ["1700.1", "1700.2"]
    assert all(d.event.subject == SUBJECT for d in handed)
    assert [by for _, by in _routed(gw)[-2:]] == ["room", "room"]


def test_clearing_the_declaration_retracts_the_room(gw, laptop):
    """
    Feature: a work item's collaboration channel routes every collaborator's message to it
      Scenario: clearing the declaration retracts the room
        Given laptop-a has declared slack@C0123ABCD on o/r#14
        When o/r#14 ends and its declarations are cleared
        Then the gateway no longer resolves C0123ABCD to o/r#14
        And a later top-level message there from U_COLLAB is held on unassigned

    Requirement: docs/specs/issue-505/requirements.md#requirement-4 (R4.1), R4.3
    """
    laptop.poll()
    laptop.channels.add(REF, f"slack@{ROOM}", actor="octocat")
    assert gw.store.resolve_room(ROOM) is not None

    laptop.channels.clear(REF)  # what Dispatcher.complete_work_item does

    assert gw.store.resolve_room(ROOM) is None
    _post(gw, "U_COLLAB", "1700.9")
    assert _routed(gw)[-1] == ("unassigned", "hold")
    assert laptop.poll() == []


def test_a_gateway_that_lost_its_store_gets_the_rooms_back_on_re_registration(
    gw, laptop, tmp_path, monkeypatch
):
    """
    Feature: a work item's collaboration channel routes every collaborator's message to it
      Scenario: a gateway that lost its store gets the rooms back on re-registration
        Given laptop-a has declared slack@C0123ABCD on o/r#14
        When the gateway restarts on an empty store and laptop-a reconnects
        Then laptop-a's registration publishes the room again
        And a top-level message from U_COLLAB in C0123ABCD routes to loop-github-o-r-14

    Requirement: docs/specs/issue-505/requirements.md#requirement-1 (R1.4)
    """
    laptop.poll()
    laptop.channels.add(REF, f"slack@{ROOM}", actor="octocat")

    fresh = _harness(tmp_path / "gw-new", monkeypatch)
    try:
        laptop.client._transport = lambda m, p, b, t: Instance._call(fresh, m, p, b)
        laptop.client.registered = False  # what the outage the restart caused sets
        laptop.poll()

        assert fresh.store.resolve_room(ROOM) == (REF, "github-o-r-14")
        _post(fresh, "U_COLLAB", "1700.4")
        assert _routed(fresh)[-1] == (SUBJECT, "claim")
        (delivery,) = laptop.poll()
        assert delivery.event.payload["event"]["user"] == "U_COLLAB"
    finally:
        fresh.close()
