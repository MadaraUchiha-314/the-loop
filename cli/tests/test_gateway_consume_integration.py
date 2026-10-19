"""Integration scenarios for the consumer API (issue-496, T2/T7 — R3.3, R2.2, R5.2,
R5.3, non-functional Latency and Scalability).

Feature: instances pull their own queue from the gateway
"""

from __future__ import annotations

import threading
import time

import pytest

from gateway_support import GatewayHarness


@pytest.fixture()
def gw(tmp_path):
    harness = GatewayHarness(tmp_path)
    yield harness
    harness.close()


def test_a_long_poll_returns_within_a_second_of_an_append(gw):
    """
    Feature: instances pull their own queue from the gateway
      Scenario: a long-poll returns within a second of an append
        Given laptop-a's queue is empty and it fetches with wait=5
        When an event is appended to a subject laptop-a consumes 200 ms later
        Then the fetch answers with that delivery well under a second after the append

    Requirement: docs/specs/issue-496/requirements.md#requirement-3 (R3.3);
                 non-functional Latency
    """
    gw.store.claim("loop-github-o-r-14", "laptop-a", "driver")
    result = {}

    def poll():
        started = time.monotonic()
        result["body"] = gw.fetch("laptop-a", wait=5).json()
        result["took"] = time.monotonic() - started

    thread = threading.Thread(target=poll)
    thread.start()
    time.sleep(0.2)
    appended_at = time.monotonic()
    gw.append(1, consumers=["laptop-a"])
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert [d["event"]["payload"]["n"] for d in result["body"]["deliveries"]] == [1]
    assert time.monotonic() - appended_at < 1.0, result["took"]


def test_an_empty_long_poll_gives_up_at_wait(gw):
    """
    Feature: instances pull their own queue from the gateway
      Scenario: an empty long-poll answers empty when wait elapses
        Given nothing is routed to laptop-b
        When it fetches with wait=0.3
        Then the answer is empty and arrives after about 0.3 s, not at once and not later

    Requirement: docs/specs/issue-496/requirements.md#requirement-3 (R3.3)
    """
    started = time.monotonic()
    body = gw.fetch("laptop-b", wait=0.3).json()
    took = time.monotonic() - started
    assert body["deliveries"] == [] and 0.25 <= took < 2.0


def test_a_fetch_by_one_of_fifty_instances_reads_only_its_own_queue(gw):
    """
    Feature: instances pull their own queue from the gateway
      Scenario: a fetch by one of fifty instances reads only its own queue
        Given fifty instances each with a backlog of three, and one of them with ten
        When the one fetches
        Then it receives exactly its ten, the fetch's query plan is an index range on
             deliveries(instance, seq), and no other queue is touched

    Requirement: docs/specs/issue-496/requirements.md non-functional Scalability (R4.1)
    """
    for i in range(50):
        for n in range(3):
            gw.append(i * 10 + n, consumers=[f"inst-{i}"], delivery_id=f"d-{i}-{n}")
    for n in range(7):
        gw.append(900 + n, consumers=["inst-7"], delivery_id=f"extra-{n}")
    body = gw.fetch("inst-7", max=16).json()
    assert len(body["deliveries"]) == 10
    assert all(
        d["event"]["deliveryId"].startswith(("d-7-", "extra-"))
        for d in body["deliveries"]
    )
    plan = gw.store.query_plan("inst-7")
    assert "deliveries_queue" in plan and "SCAN deliveries" not in plan, plan
    # the other queues are untouched: first attempt everywhere
    other = gw.fetch("inst-8").json()["deliveries"]
    assert len(other) == 3 and all(d["attempt"] == 1 for d in other)


def test_an_event_with_no_consumer_waits_on_unassigned_until_a_claim_routes_it(gw):
    """
    Feature: instances pull their own queue from the gateway
      Scenario: an event with no consumer waits on unassigned until a claim routes it
        Given an event on a subject nobody claims and no actor registered
        When it is appended
        Then it is held (no queue has it, subjects lists it as held)
        And when laptop-a claims the subject the event appears on laptop-a's queue only

    Requirement: docs/specs/issue-496/requirements.md#requirement-2 (R2.2), R5.2, R5.3
    """
    held = gw.append(1, consumers=[])
    assert held.held
    assert gw.fetch("laptop-a").json()["deliveries"] == []
    (row,) = gw.client.get("/api/v1/gateway/subjects").json()["subjects"]
    assert row["held"] == 1 and row["claimants"] == []
    assert gw.claim("laptop-a", "loop-github-o-r-14").json()["routed"] == 1
    assert gw.claim("laptop-b", "loop-github-o-r-14", "reviewer").json()["routed"] == 0
    assert [d["event"]["id"] for d in gw.fetch("laptop-a").json()["deliveries"]] == [
        held.event_id
    ]
    assert gw.fetch("laptop-b").json()["deliveries"] == []
    (row,) = gw.client.get("/api/v1/gateway/subjects").json()["subjects"]
    assert row["held"] == 0 and {c["instance"] for c in row["claimants"]} == {
        "laptop-a",
        "laptop-b",
    }
