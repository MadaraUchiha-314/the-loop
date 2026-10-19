"""Integration scenarios for the gateway's poller (issue-496, T2 — R1.5, R1.6, R7.1,
R7.3, R7.4, R3.4).

Feature: the gateway polls the providers the instance used to poll
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re

import pytest

from gateway_support import GatewayHarness
from ghfakes import FakeGitHubClient
from the_loop.ghapi import GhComment, GhItem
from the_loop.gateway.adapters.github import build_github_router
from the_loop.gateway.adapters.ingest import Ingest
from the_loop.gateway.adapters.poll import PollAdapter, build_github_providers

SECRET = "gw-test-secret"


def _item(number: int, *, is_pr: bool = False, title: str = "A ticket") -> GhItem:
    kind = "pull" if is_pr else "issues"
    return GhItem(
        number=number,
        title=title,
        labels=["the-loop: auto-execute"],
        updated_at="2026-10-18T14:00:00Z",
        url=f"https://github.com/o/r/{kind}/{number}",
        is_pr=is_pr,
        author="octocat",
    )


def _comment(cid: str, body: str = "the-loop start") -> GhComment:
    return GhComment(
        id=cid,
        body=body,
        author="octocat",
        created_at="2026-10-18T14:02:11Z",
        url=f"https://github.com/o/r/issues/14#issuecomment-{cid}",
    )


@pytest.fixture()
def gw(tmp_path, monkeypatch):
    monkeypatch.setenv("THE_LOOP_GH_WEBHOOK_SECRET", SECRET)
    harness = GatewayHarness(
        tmp_path,
        github={
            "webhook": {"enabled": True},
            "poll": {
                "enabled": True,
                "intervalSeconds": 60,
                "sources": [
                    {"repository": "o/r", "labels": ["the-loop: auto-execute"]}
                ],
            },
        },
    )
    harness.ingest = Ingest(harness.state)
    harness.app.include_router(build_github_router(harness.ingest, harness.config))
    harness.api = FakeGitHubClient()
    harness.api.issues[("o", "r")] = [_item(14)]
    harness.api.comments[("o", "r", 14)] = [_comment("6257")]
    (provider,) = build_github_providers(harness.config, api=harness.api)
    harness.poll = PollAdapter(provider, harness.ingest, interval_s=60)
    yield harness
    harness.close()


def test_the_gateway_poller_produces_the_same_delivery_ids_the_instance_poller_produces(
    gw,
):
    """
    Feature: the gateway polls the providers the instance used to poll
      Scenario: the gateway poller produces the same delivery ids the instance poller produces
        Given o/r#14 is labelled and carries one comment, and laptop-a registered octocat
        When the gateway polls once, and again after a new comment
        Then laptop-a's queue holds a presence event `poll-presence-<ref>-<uuid>` and
             then a comment event `poll-comment-6258`, webhook-shaped, by the provider's
             own builders — and the comment is not offered again on the next cycle

    Requirement: docs/specs/issue-496/requirements.md#requirement-1 (R1.5), R7.1
    """
    gw.fetch("laptop-a", peer="p1", lease=60)
    gw.register("laptop-a", {"github": ["octocat"]}, peer="p1")
    cycle = gw.poll.poll_once()
    assert cycle.items == 1 and cycle.stored == 1 and not cycle.errors
    gw.api.comments[("o", "r", 14)].append(_comment("6258", "status?"))
    again = gw.poll.poll_once()
    assert again.stored == 1 and again.duplicates == 0
    deliveries = gw.fetch("laptop-a", peer="p1").json()["deliveries"]
    ids = [d["event"]["deliveryId"] for d in deliveries]
    assert re.fullmatch(r"poll-presence-github:o/r#14-[0-9a-f-]{36}", ids[0]), ids
    assert ids[1] == "poll-comment-6258"
    presence, comment = (d["event"] for d in deliveries)
    assert presence["kind"] == "issues" and presence["payload"]["action"] == "labeled"
    assert presence["source"] == "poll" and presence["subject"] == "loop-github-o-r-14"
    assert comment["kind"] == "issue_comment"
    assert comment["payload"]["comment"]["id"] == "6258"
    assert comment["payload"]["comment"]["body"] == "status?"
    # third cycle: the comment is seen; presence is pending, so not offered twice
    third = gw.poll.poll_once()
    assert third.stored == 0 and third.duplicates == 0


def test_a_new_gateway_baselines_an_items_existing_thread_at_first_sight(gw):
    """
    Feature: the gateway polls the providers the instance used to poll
      Scenario: a new gateway baselines an item's existing thread at first sight
        Given o/r#14 has been armed for a while and carries three comments, and laptop-a
              drives it
        When a gateway with an empty store polls it for the first time
        Then the three comments are marked seen and not stored (the presence alone is
             offered), the cycle reports them as baselined, and the next comment is
             stored once — matching the instance poller's first-sight baseline, so a
             migration never replays a thread's history as prompts

    Requirement: docs/specs/issue-496/requirements.md#requirement-1 (R1.5), R7.1
                 (found answering the author's migration question on the PR)
    """
    gw.api.comments[("o", "r", 14)] = [
        _comment("1", "the-loop start"),
        _comment("2", "status?"),
        _comment("3", "ship it"),
    ]
    gw.store.claim("loop-github-o-r-14", "laptop-a", "driver")
    cycle = gw.poll.poll_once()
    assert cycle.stored == 1 and cycle.baselined == 3 and cycle.duplicates == 0
    assert all(gw.store.poll_seen("github:o/r#14", cid) for cid in ("1", "2", "3"))
    (presence,) = gw.fetch("laptop-a").json()["deliveries"]
    assert presence["event"]["deliveryId"].startswith("poll-presence-")
    gw.api.comments[("o", "r", 14)].append(_comment("4", "and now?"))
    again = gw.poll.poll_once()
    assert again.stored == 1 and again.baselined == 0
    ids = [d["event"]["deliveryId"] for d in gw.fetch("laptop-a").json()["deliveries"]]
    assert ids[-1] == "poll-comment-4" and "poll-comment-1" not in ids


def test_a_webhook_and_a_poll_of_the_same_comment_store_one_row(gw):
    """
    Feature: the gateway polls the providers the instance used to poll
      Scenario: a webhook and a poll of the same comment store one row
        Given comment 6257 arrived by webhook
        When the poller lists the same comment
        Then the store holds one event for it (dedup key gh-comment-6257) and the
             poller still marks it seen, so the poll is the reconciliation path (R7.4)

    Requirement: docs/specs/issue-496/requirements.md#requirement-7 (R7.3, R7.4)
    """
    gw.store.claim("loop-github-o-r-14", "laptop-a", "driver")
    gw.store.set_poll_state("github:o/r#14", "spawned")  # no presence in this scenario
    body = json.dumps(
        {
            "action": "created",
            "issue": {"number": 14},
            "comment": {
                "id": 6257,
                "body": "the-loop start",
                "user": {"login": "octocat"},
            },
            "repository": {"full_name": "o/r"},
            "sender": {"login": "octocat"},
        }
    ).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    response = gw.client.post(
        "/gh-webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "issue_comment",
            "X-GitHub-Delivery": "d-1",
        },
    )
    assert response.status_code == 202
    cycle = gw.poll.poll_once()
    assert cycle.duplicates == 1 and cycle.stored == 0
    (row,) = gw.client.get("/api/v1/gateway/subjects").json()["subjects"]
    assert row["events"] == 1
    assert gw.store.poll_seen("github:o/r#14", "6257")
    deliveries = gw.fetch("laptop-a").json()["deliveries"]
    assert [d["event"]["deliveryId"] for d in deliveries] == ["d-1"]


def test_the_commit_outcome_drives_the_presence_ledger(gw):
    """
    Feature: the gateway polls the providers the instance used to poll
      Scenario: an instance's commit outcome ends or keeps the presence offering
        Given a presence delivery on laptop-a's queue
        When laptop-a commits it as dropped:awaiting-start, the next cycle offers presence
             again; when it commits as spawned, no cycle offers it any more

    Requirement: docs/specs/issue-496/requirements.md#requirement-3 (R3.4), R1.5
    """
    gw.fetch("laptop-a", peer="p1", lease=60)
    gw.register("laptop-a", {"github": ["octocat"]}, peer="p1")
    gw.poll.poll_once()
    (presence,) = gw.fetch("laptop-a", peer="p1").json()["deliveries"]
    assert presence["event"]["deliveryId"].startswith("poll-presence-")
    gw.fetch(
        "laptop-a",
        peer="p1",
        commit=[{"seq": presence["seq"], "outcome": "dropped:awaiting-start"}],
    )
    assert gw.store.poll_state("github:o/r#14") == "awaiting-start"
    assert gw.poll.poll_once().stored == 1  # presence offered again
    (presence,) = gw.fetch("laptop-a", peer="p1").json()["deliveries"]
    gw.fetch(
        "laptop-a", peer="p1", commit=[{"seq": presence["seq"], "outcome": "spawned"}]
    )
    assert gw.store.poll_state("github:o/r#14") == "spawned"
    assert gw.poll.poll_once().stored == 0


def test_a_vanished_item_is_closed_once_by_the_providers_closure_event(gw):
    """
    Feature: the gateway polls the providers the instance used to poll
      Scenario: a work item that left the listing is stored as a webhook-shaped closure
        Given o/r#14 was polled and then closed on GitHub
        When the next cycle lists nothing
        Then one `issues.closed` event reaches the subject's claimant and the ledger
             marks the ref closed, so a later cycle stores nothing more

    Requirement: docs/specs/issue-496/requirements.md#requirement-1 (R1.5)
    """
    gw.store.claim("loop-github-o-r-14", "laptop-a", "driver")
    gw.poll.poll_once()
    gw.api.issues[("o", "r")] = []
    gw.api.states[("o", "r", 14)] = {
        "state": "closed",
        "title": "A ticket",
        "is_pr": False,
        "merged": False,
    }
    cycle = gw.poll.poll_once()
    assert cycle.stored == 1 and not cycle.errors
    closure = gw.fetch("laptop-a").json()["deliveries"][-1]["event"]
    assert closure["kind"] == "issues" and closure["payload"]["action"] == "closed"
    assert closure["deliveryId"].startswith("poll-close-")
    assert gw.store.poll_state("github:o/r#14") == "closed"
    assert gw.poll.poll_once().stored == 0


def test_a_held_presence_is_offered_once_until_someone_consumes_it(gw):
    """
    Feature: the gateway polls the providers the instance used to poll
      Scenario: a held presence is offered once until someone consumes it
        Given an armed item whose author no instance registered and no claim on it
        When the poller runs three cycles
        Then one presence is held (the existing comment is baselined), not one per
             cycle; a later claim routes exactly one presence onto the claimant's queue

    Requirement: docs/specs/issue-496/requirements.md#requirement-1 (R1.5), R2.2
                 (self-review R1)
    """
    assert gw.poll.poll_once().stored == 1  # the presence, held
    assert gw.poll.poll_once().stored == 0
    assert gw.poll.poll_once().stored == 0
    (row,) = [s for s in gw.store.subjects() if s.subject == "loop-github-o-r-14"]
    assert row.held == 1 and row.events == 1
    gw.store.claim("loop-github-o-r-14", "laptop-a", "driver")
    deliveries = gw.fetch("laptop-a", peer="p1").json()["deliveries"]
    presences = [
        d for d in deliveries if d["event"]["deliveryId"].startswith("poll-presence-")
    ]
    assert len(presences) == 1 and len(deliveries) == 1
