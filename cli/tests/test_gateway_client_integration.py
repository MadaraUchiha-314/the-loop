"""Integration scenarios for the instance side of the gateway (issue-496, T2/T8 —
R3.4, R3.6, R3.7, R5.6, R10.2, R12.2; abuse case 3): a real GatewayClient driving a
real Dispatcher with the fake tmux runner, fed by a real gateway app in-process.

Feature: every event reaches its consumers raw; the instance judges
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
from conftest import FakeTmux, StubInteractiveAdapter

from gateway_support import GatewayHarness
from the_loop.control import ControlConfig
from the_loop.gateway.client import GatewayClient
from the_loop.gateway.client_dispatch import Pipeline
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import Router

FIXTURES = Path(__file__).parent / "fixtures" / "github"
AUTO_LABEL = "the-loop: auto-execute"
REF = "github:o/r#14"


def wait_until(predicate, timeout=5.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class Instance:
    """One instance: its registry, dispatcher, router, pipeline and gateway client."""

    def __init__(self, gw: GatewayHarness, root: Path, name: str, **routing):
        self.root = root
        self.tmux = FakeTmux()
        self.registry = SessionRegistry(root / "sessions")
        config = RoutingConfig(
            dispatch_timeout_seconds=30,
            spawn_workdir=str(root),
            portable_dir=str(root / "portable"),
            **{
                "control": ControlConfig(require_start_command=False),
                "auto_execute_labels": [AUTO_LABEL],
                "authorized_users": ["octocat"],
                **routing,
            },
        )
        self.dispatcher = Dispatcher(
            registry=self.registry,
            adapters={"claude": StubInteractiveAdapter()},
            config=config,
            tmux_runner=self.tmux,
        )
        self.router = Router(
            events=[
                "issues",
                "issue_comment",
                "pull_request",
                "pull_request_review_comment",
            ],
            deduper=self.dispatcher.deduper,
            auto_execute_labels=config.auto_execute_labels,
            authorized_users=["octocat"],
            collaborators=self.dispatcher.collaborator_store,
            repositories=None,
        )
        self.cli_config: Dict[str, Any] = {
            "state": {"root": str(root / ".the-loop")},
            "instance": {"name": name},
            "gateway": {
                "url": "http://127.0.0.1:8790",
                "pollIntervalSeconds": 1,
                "longPollSeconds": 0,
                "actors": {"github": ["octocat"]},
            },
        }
        self.pipeline = Pipeline(
            router=self.router, dispatcher=self.dispatcher, cli_config=self.cli_config
        )
        self.client = GatewayClient(
            self.cli_config,
            threading.Event(),
            dispatch=self.pipeline.dispatch,
            claims=self.claims,
            transport=lambda m, p, b, t: self._call(gw, m, p, b),
            sleep=lambda s: None,
            rng=lambda: 0.5,
        )

    @staticmethod
    def _call(gw, method, path, body):
        response = gw.client.request(method, path, json=body)
        return response.status_code, (response.json() if response.content else None)

    def claims(self) -> List[Any]:
        return [
            (f"loop-{s.work_item.slug}", "driver")
            for s in self.registry.list_sessions()
            if s.is_live
        ]

    def register_session(self, ref: str = REF) -> None:
        item = WorkItemRef.parse(ref)
        self.registry.register(
            Session(
                work_item=item,
                harness="claude",
                harness_session_id="sess-1",
                cwd=str(self.root),
                tmux_target=f"loop-{item.slug}",
            )
        )

    def stop(self) -> None:
        self.dispatcher.stop()


@pytest.fixture()
def gw(tmp_path) -> Iterator[GatewayHarness]:
    harness = GatewayHarness(tmp_path)
    yield harness
    harness.close()


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_an_issue_comment_through_the_gateway_spawns_on_the_instance_with_the_gateway_event_id(
    gw, tmp_path
):
    """
    Feature: every event reaches its consumers raw; the instance judges
      Scenario: an issue comment through the gateway spawns on the instance with the
                gateway event id in its dispatch record
        Given laptop-a registered github:octocat and spawns on a labelled, unmatched item
        When the gateway stores octocat's labelled issue event and laptop-a polls
        Then the instance's dispatcher spawns a session for o/r#14, the client commits
             the delivery as spawned, and the dispatch.* records carry gateway_event_id

    Requirement: docs/specs/issue-496/requirements.md#requirement-1 (R1.3), R2.1, R3.4,
                 R5.5, R10.2, R12.2
    """
    laptop = Instance(gw, tmp_path / "a", "laptop-a", spawn_on_unmatched="labeled")
    try:
        assert laptop.client.step() is True  # registers actors, fetches nothing
        appended = gw.append(
            1,
            consumers=["laptop-a"],
            kind="issues",
            payload=_fixture("issues.labeled.json"),
            delivery_id="lbl-1",
        )
        laptop.client.step()
        assert wait_until(lambda: laptop.registry.find_by_work_item(REF) is not None)
        ((ref, prompt, _cwd, resume),) = laptop.tmux.spawns
        assert ref == REF and resume is False and "/the-loop:work-on" in prompt
        assert wait_until(
            lambda: laptop.client.resolve_deferred() or not laptop.client.deferred
        )
        laptop.client.step()  # the commit rides this fetch
        committed = gw.events("subject.committed")
        assert committed and committed[-1]["outcome"] == "spawned"
        assert gw.store.committed("laptop-a") > 0
        dispatch_records = [
            r
            for r in gw.events()
            if r["event"].startswith("dispatch.") and r.get("delivery_id") == "lbl-1"
        ]
        assert dispatch_records and all(
            r.get("gateway_event_id") == appended.event_id for r in dispatch_records
        )
    finally:
        laptop.stop()


def test_a_crash_between_dispatch_and_commit_redelivers_once_and_the_dispatcher_drops_the_duplicate(
    gw, tmp_path
):
    """
    Feature: every event reaches its consumers raw; the instance judges
      Scenario: a crash between dispatch and commit redelivers once and the dispatcher
                drops the duplicate
        Given laptop-a with a live session for o/r#14 receives a comment and delivers it
        When the client dies before its next fetch (its pending commit is lost) and a
             new client under the same peer fetches
        Then the delivery comes back with attempt 2, the dispatcher's dedup drops it as a
             duplicate, the pane saw the comment once, and the redelivery is committed

    Requirement: docs/specs/issue-496/requirements.md#requirement-3 (R3.6, R3.7)
    """
    laptop = Instance(gw, tmp_path / "a", "laptop-a")
    try:
        laptop.register_session()
        laptop.client.step()
        payload = _fixture("issue_comment.created.json")
        payload["comment"]["body"] = "CI is red, please fix"
        gw.append(1, consumers=["laptop-a"], payload=payload, delivery_id="d-1")
        laptop.client.step()
        assert wait_until(lambda: len(laptop.tmux.delivers) == 1)
        assert wait_until(
            lambda: laptop.client.resolve_deferred() >= 1 or not laptop.client.deferred
        )
        # the crash: a fresh client with the same peer, the pending commit never sent
        reborn = GatewayClient(
            laptop.cli_config,
            threading.Event(),
            dispatch=laptop.pipeline.dispatch,
            claims=laptop.claims,
            transport=laptop.client._transport,
            sleep=lambda s: None,
            rng=lambda: 0.5,
        )
        assert reborn.peer == laptop.client.peer
        reborn.step()
        redelivered = gw.events("subject.redelivered")
        assert redelivered and redelivered[-1]["attempt"] == 2
        reborn.step()
        assert gw.store.committed("laptop-a") > 0
        time.sleep(0.2)
        assert len(laptop.tmux.delivers) == 1
        dropped = [
            r
            for r in gw.events("routing.dropped")
            if r.get("reason") == "duplicate-delivery"
        ]
        assert dropped and dropped[-1]["delivery_id"] == "d-1"
        committed = gw.events("subject.committed")
        assert committed[-1]["outcome"] == "dropped:not-routed"
    finally:
        laptop.stop()


def test_an_injected_start_keyword_from_an_unauthorized_actor_is_dropped_on_the_instance(
    gw, tmp_path
):
    """
    Feature: every event reaches its consumers raw; the instance judges
      Scenario: an injected start keyword from an unauthorized actor is dropped on the instance
        Given laptop-a spawns on labelled items and only octocat is authorized
        When a comment by mallory saying "the-loop start" reaches laptop-a's queue
        Then the router drops it as unauthorized-actor, nothing spawns or is delivered,
             and the queue commits it as dropped

    Requirement: docs/specs/issue-496/requirements.md §Security considerations, abuse case 3
    """
    laptop = Instance(gw, tmp_path / "a", "laptop-a", spawn_on_unmatched="labeled")
    try:
        payload = _fixture("issue_comment.created.json")
        payload["comment"]["user"]["login"] = "mallory"
        payload["sender"]["login"] = "mallory"
        payload["comment"]["body"] = "the-loop start"
        gw.append(1, consumers=["laptop-a"], payload=payload, delivery_id="evil-1")
        laptop.client.step()
        laptop.client.step()
        assert laptop.tmux.spawns == [] and laptop.tmux.delivers == []
        dropped = gw.events("routing.dropped")
        assert dropped and dropped[-1]["reason"] == "unauthorized-actor"
        assert gw.events("subject.committed")[-1]["outcome"] == "dropped:not-routed"
    finally:
        laptop.stop()


def test_a_jira_comment_through_the_gateway_rings_the_instances_doorbell_unchanged(
    gw, tmp_path
):
    """
    Feature: every event reaches its consumers raw; the instance judges
      Scenario: a Jira comment through the gateway rings the instance's doorbell unchanged
    Requirement: docs/specs/issue-496/requirements.md#requirement-5 (R5.1, R5.6)
    """
    rung: List[Any] = []

    class Doorbell:
        def ring(self, bell):
            rung.append((bell.event, bell.issue_key, bell.comment_id))
            return "delivered:comment" if bell.comment_id else "ignored:event"

    laptop = Instance(gw, tmp_path / "a", "laptop-a")
    try:
        laptop.pipeline.doorbell = Doorbell()
        doc = {
            "webhookEvent": "comment_created",
            "issue": {"key": "PROJ-7", "self": "https://acme.atlassian.net/x"},
            "comment": {"id": "42", "author": {"accountId": "j1"}},
        }
        gw.append(
            1,
            consumers=["laptop-a"],
            provider="jira",
            kind="comment_created",
            payload=doc,
            work_item="jira:acme.atlassian.net/PROJ-7",
            subject="loop-jira-acme.atlassian.net-PROJ-7",
        )
        gw.append(
            2,
            consumers=["laptop-a"],
            provider="jira",
            kind="jira:issue_updated",
            payload={"webhookEvent": "jira:issue_updated", "issue": {"key": "PROJ-7"}},
            work_item="jira:acme.atlassian.net/PROJ-7",
            subject="loop-jira-acme.atlassian.net-PROJ-7",
        )
        laptop.client.step()
        laptop.client.step()
        assert rung == [
            ("comment_created", "PROJ-7", "42"),
            ("jira:issue_updated", "PROJ-7", ""),
        ]
        outcomes = [r["outcome"] for r in gw.events("subject.committed")]
        assert outcomes == ["delivered", "dropped:event"]
    finally:
        laptop.stop()


def test_a_slack_envelope_from_the_queue_goes_through_the_one_classifier(gw, tmp_path):
    """
    Feature: one classifier, two transports
      Scenario: a Slack delivery is classified by slack.dispatch_envelope on the instance
    Requirement: docs/specs/issue-496/requirements.md#requirement-5 (R5.6)
    """
    seen: List[Any] = []
    laptop = Instance(gw, tmp_path / "a", "laptop-a")
    try:
        laptop.pipeline._slack_dispatch = lambda kind, payload, cfg: (
            seen.append((kind, payload["event"]["type"])) or "handled:message"
        )
        gw.append(
            1,
            consumers=["laptop-a"],
            provider="slack",
            source="socket",
            kind="events_api",
            payload={"event": {"type": "message", "text": "approved"}},
        )
        laptop.client.step()
        laptop.client.step()
        assert seen == [("events_api", "message")]
        assert gw.events("subject.committed")[-1]["outcome"] == "delivered"
    finally:
        laptop.stop()
