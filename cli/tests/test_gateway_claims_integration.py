"""Integration scenarios for routing by claim, actor and binding across instances
(issue-496, T2 — R2.8, R3.2, R3.9, R4.1, R4.4, R4.5, R5.3, R5.4, R5.5, R5.7, R5.8, R12.4,
R12.8): two real instances (registry, dispatcher, pipeline, client) against one gateway.

Feature: many instances, one queue each
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Iterator

import pytest

from gateway_support import GatewayHarness, Instance
from the_loop.gateway.adapters.ingest import Ingest
from the_loop.gateway.client import GatewayClient

FIXTURES = Path(__file__).parent / "fixtures" / "github"
TICKET = "github:o/r#14"
PR = "github:o/r#77"


def wait_until(predicate, timeout=5.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture()
def gw(tmp_path) -> Iterator[GatewayHarness]:
    harness = GatewayHarness(tmp_path)
    harness.ingest = Ingest(harness.state)
    yield harness
    harness.close()


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _ingest(gw, kind: str, payload: dict, delivery: str):
    return gw.ingest.accept(
        "github", "webhook", kind, delivery, {}, json.dumps(payload).encode()
    )


def _queue(gw, instance: str):
    """What is pending on an instance's queue, read through the store so no lease is
    touched (the instance's own client holds the name)."""
    return [d.event.delivery_id for d in gw.store.fetch(instance, 0, 64).deliveries]


def test_a_driver_and_a_reviewer_on_two_instances_each_receive_their_own_queue(
    gw, tmp_path
):
    """
    Feature: many instances, one queue each
      Scenario: a driver and a reviewer on two instances each receive their own queue
        Given laptop-a drives ticket o/r#14 (a registered session publishes a driver claim)
        And laptop-b reviews pull request o/r#77 (its control record says review, so its
            session publishes a reviewer claim) and the PR is bound to the ticket
        When a review comment lands on the PR and a comment lands on the ticket
        Then the PR comment reaches both queues and the ticket comment the driver's only,
             and nothing in the gateway makes one wait for the other

    Requirement: docs/specs/issue-496/requirements.md#requirement-4 (R4.1, R4.5), R5.3,
                 R5.4, R12.8
    """
    a = Instance(gw, tmp_path / "a", "laptop-a")
    b = Instance(gw, tmp_path / "b", "laptop-b", actors=[])
    try:
        a.client.step()
        b.client.step()
        a.register_session(TICKET)  # → PUT /claims driver on loop-github-o-r-14
        b.control.record(PR, "review", actor="reviewer")
        b.register_session(PR)  # → PUT /claims reviewer on loop-github-o-r-77
        a.registry.link_pull_request(TICKET, PR)  # → POST /bindings o/r#77 → #14
        claims = {
            (c.instance, c.role) for c in gw.store.claimants("loop-github-o-r-14")
        }
        assert claims == {("laptop-a", "driver")}
        claims = {
            (c.instance, c.role) for c in gw.store.claimants("loop-github-o-r-77")
        }
        assert claims == {("laptop-b", "reviewer")}
        assert gw.store.resolve("github", "o/r#77") == TICKET
        review = {
            "action": "created",
            "pull_request": {"number": 77, "user": {"login": "octocat"}},
            "comment": {
                "id": 9001,
                "body": "nit: rename",
                "user": {"login": "reviewer"},
            },
            "repository": {"full_name": "o/r"},
            "sender": {"login": "reviewer"},
        }
        assert _ingest(
            gw, "pull_request_review_comment", review, "rev-1"
        ).consumers == ("laptop-b", "laptop-a")
        ticket = _fixture("issue_comment.created.json")
        ticket["comment"]["body"] = "status?"
        assert _ingest(gw, "issue_comment", ticket, "tick-1").consumers == ("laptop-a",)
        assert _queue(gw, "laptop-b") == ["rev-1"]
        assert _queue(gw, "laptop-a") == ["rev-1", "tick-1"]
    finally:
        a.stop()
        b.stop()


def test_a_start_by_a_registered_actor_lands_on_that_actors_instance_only(gw, tmp_path):
    """
    Feature: many instances, one queue each
      Scenario: a start by a registered actor lands on that actor's instance only
        Given laptop-a works for octocat and laptop-b for hubot, no claim on o/r#14
        When octocat labels o/r#14
        Then the event is on laptop-a's queue alone, routed by actor, and laptop-a's
             dispatcher spawns for it

    Requirement: docs/specs/issue-496/requirements.md#requirement-5 (R5.5), R4.1
    """
    a = Instance(gw, tmp_path / "a", "laptop-a", spawn_on_unmatched="labeled")
    b = Instance(gw, tmp_path / "b", "laptop-b", actors=["hubot"])
    try:
        a.client.step()
        b.client.step()
        result = _ingest(gw, "issues", _fixture("issues.labeled.json"), "lbl-1")
        assert result.consumers == ("laptop-a",)
        assert gw.events("subject.routed")[-1]["by"] == "actor"
        assert _queue(gw, "laptop-b") == []
        a.client.step()
        assert wait_until(lambda: a.registry.find_by_work_item(TICKET) is not None)
        assert a.tmux.spawns and b.tmux.spawns == []
        # the spawned session published its claim: later events route by claim
        assert wait_until(
            lambda: (
                {c.instance for c in gw.store.claimants("loop-github-o-r-14")}
                == {"laptop-a"}
            )
        )
    finally:
        a.stop()
        b.stop()


def test_a_pull_request_event_with_no_binding_is_routed_by_actor_and_the_instance_publishes_the_binding(
    gw, tmp_path
):
    """
    Feature: many instances, one queue each
      Scenario: a pull request event with no binding is routed by actor and the instance
                publishes the binding
        Given laptop-a drives o/r#14 and the gateway knows no pull request for it
        When octocat opens o/r#77 with "Closes #14" in its body
        Then the gateway routes it by actor to laptop-a, whose router infers the linkage
             and publishes the binding, so the next PR event is routed by claim

    Requirement: docs/specs/issue-496/requirements.md#requirement-5 (R5.7, R5.8)
    """
    a = Instance(gw, tmp_path / "a", "laptop-a")
    try:
        a.client.step()
        a.register_session(TICKET)
        opened = _fixture("pull_request.opened.json")
        first = _ingest(gw, "pull_request", opened, "pr-open-1")
        assert (
            first.consumers == ("laptop-a",)
            and gw.events("subject.routed")[-1]["by"] == "actor"
        )
        a.client.step()
        assert wait_until(lambda: gw.store.resolve("github", "o/r#77") == TICKET)
        again: dict = dict(opened, action="synchronize")
        again["pull_request"] = dict(
            opened["pull_request"], updated_at="2026-10-18T16:00:00Z"
        )
        second = _ingest(gw, "pull_request", again, "pr-sync-1")
        assert (
            second.consumers == ("laptop-a",)
            and gw.events("subject.routed")[-1]["by"] == "claim"
        )
    finally:
        a.stop()


def test_a_stopped_instance_finds_its_backlog_in_order(gw, tmp_path):
    """
    Feature: many instances, one queue each
      Scenario: a stopped instance finds its backlog in order
        Given laptop-a drives o/r#14, polled once, then stopped
        When three comments arrive while it is down and it starts again as the same peer
        Then the three are delivered in order, once, and committed

    Requirement: docs/specs/issue-496/requirements.md#requirement-4 (R4.4), R2.8, R3.2,
                 R3.9, R12.4
    """
    a = Instance(gw, tmp_path / "a", "laptop-a")
    try:
        a.register_session(TICKET)
        a.client.step()
        a.client.flush()
        for n in (1, 2, 3):
            comment = _fixture("issue_comment.created.json")
            comment["comment"] = {
                "id": 7000 + n,
                "body": f"reply {n}",
                "user": {"login": "octocat"},
            }
            _ingest(gw, "issue_comment", comment, f"while-down-{n}")
        reborn = GatewayClient(
            a.cli_config,
            threading.Event(),
            dispatch=a.pipeline.dispatch,
            transport=a.client._transport,
            sleep=lambda s: None,
            rng=lambda: 0.5,
        )
        reborn.attach(a.registry, control_store=a.control, pipeline=a.pipeline)
        assert reborn.peer == a.client.peer
        reborn.step()
        # three deliveries through one session's FIFO; under --dispatch-lag each of the
        # dispatcher's follow-up writes is slowed, so the budget is generous on purpose
        assert wait_until(lambda: len(a.tmux.delivers) == 3, timeout=30)
        import re

        orders = []
        for _, prompt in a.tmux.delivers:
            match = re.search(r"reply (\d)", prompt)
            assert match is not None, prompt[:200]
            orders.append(match.group(1))
        assert orders == ["1", "2", "3"]
        assert wait_until(lambda: not reborn.deferred or reborn.resolve_deferred() >= 0)
        assert wait_until(
            lambda: reborn.resolve_deferred() >= 0 and not reborn.deferred, timeout=30
        )
        reborn.step()
        assert wait_until(lambda: gw.store.queue("laptop-a").backlog == 0, timeout=30)
        assert not gw.events("subject.redelivered")
    finally:
        a.stop()


def test_the_same_instance_resuming_after_a_stop_receives_what_was_routed_to_it_meanwhile(
    gw, tmp_path
):
    """
    Feature: many instances, one queue each
      Scenario: the same instance resuming after a stop receives what was routed to it meanwhile
        Given laptop-a's claim is on the gateway and laptop-a is down
        When a claim it never subscribed to per subject is covered by a new binding and
             events arrive on it
        Then they are on laptop-a's one queue when it resumes: the instance never
             subscribes per subject

    Requirement: docs/specs/issue-496/requirements.md#requirement-3 (R3.9), R4.4
    """
    a = Instance(gw, tmp_path / "a", "laptop-a")
    try:
        a.register_session(TICKET)
        a.client.step()
        # while down: a PR event nobody bound is held; a binding published by another
        # path (here, the API) routes it onto laptop-a's queue through its ticket claim
        held = _ingest(
            gw,
            "pull_request_review",
            {
                "action": "submitted",
                "pull_request": {"number": 78},
                "review": {"id": 1, "user": {"login": "nobody"}},
                "repository": {"full_name": "o/r"},
                "sender": {"login": "nobody"},
            },
            "held-1",
        )
        assert held.held
        assert (
            gw.bind(TICKET, "github", "o/r#78").json()["routed"] == 0
        )  # held under its own subject, not a key
        gw.store.claim(
            "loop-github-o-r-78", "laptop-a", "driver"
        )  # the ticket's driver takes the PR too
        assert _queue(gw, "laptop-a") == ["held-1"]
    finally:
        a.stop()
