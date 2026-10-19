"""Unit tests for the consumer API (issue-496, T1 — R3.2, R3.3, R3.4, R4.2, R4.3, R5.3,
R5.5, R5.7, R6.3, R9.2; abuse cases 4, 5, 8)."""

from __future__ import annotations

import pytest

from gateway_support import GatewayHarness


@pytest.fixture()
def gw(tmp_path):
    harness = GatewayHarness(tmp_path)
    yield harness
    harness.close()


def test_fetch_returns_this_queue_with_cursor_committed_and_lease(gw):
    gw.append(1, consumers=["laptop-a"])
    gw.append(2, consumers=["laptop-b"])
    response = gw.fetch("laptop-a")
    assert response.status_code == 200
    body = response.json()
    assert [d["event"]["payload"]["n"] for d in body["deliveries"]] == [1]
    delivery = body["deliveries"][0]
    assert delivery["subject"] == "loop-github-o-r-14" and delivery["attempt"] == 1
    assert body["cursor"] == delivery["seq"] and body["committed"] == 0
    assert 0 < body["lease"]["expiresIn"] <= 60


def test_the_commit_rides_on_the_next_fetch_and_the_offset_advances(gw):
    gw.append(1, consumers=["a"])
    gw.append(2, consumers=["a"])
    first = gw.fetch("a", max=1).json()
    seq = first["deliveries"][0]["seq"]
    second = gw.fetch(
        "a", cursor=first["committed"], commit=[{"seq": seq, "outcome": "delivered"}]
    ).json()
    assert second["committed"] == seq
    assert [d["event"]["payload"]["n"] for d in second["deliveries"]] == [2]
    committed = gw.events("subject.committed")
    assert (
        committed
        and committed[0]["seq"] == seq
        and committed[0]["outcome"] == "delivered"
    )


def test_explicit_commit_for_a_stop(gw):
    gw.append(1, consumers=["a"])
    seq = gw.fetch("a").json()["deliveries"][0]["seq"]
    response = gw.client.post(
        "/api/v1/gateway/commit",
        json={
            "instance": "a",
            "commit": [{"seq": seq, "outcome": "dropped:session-paused"}],
        },
    )
    assert response.status_code == 200 and response.json()["committed"] == seq


def test_max_and_wait_are_clamped_to_the_gateways_bounds(gw):
    for n in range(1, 20):
        gw.append(n, consumers=["a"])
    body = gw.fetch("a", max=500).json()
    assert len(body["deliveries"]) == 16  # consume.maxBatch in the harness config
    # wait is clamped to maxWaitSeconds (5): an empty long-poll with wait=0 answers at once
    assert gw.fetch("b", wait=0).json()["deliveries"] == []


def test_a_commit_for_a_delivery_never_fetched_is_409_and_nothing_is_fetched(gw):
    """
    Feature: the commit is honest (abuse case 5)
      Scenario: a commit for a delivery never fetched is refused
    """
    gw.append(1, consumers=["a"])
    gw.append(2, consumers=["a"])
    response = gw.fetch("a", commit=[{"seq": 999, "outcome": "delivered"}])
    assert response.status_code == 409
    assert response.json()["error"] == "commit-undelivered"
    assert gw.events("gateway.refused")[0]["reason"] == "commit-undelivered"
    # and the queue was not read: both are still first-attempt
    assert all(d["attempt"] == 1 for d in gw.fetch("a").json()["deliveries"])


def test_a_second_peer_under_a_live_name_is_409_naming_the_holder(gw):
    """
    Feature: one queue, one poller (abuse case 4)
      Scenario: a second peer under the same instance name is refused while the first polls
    """
    assert gw.fetch("laptop-a", peer="p1", lease=30).status_code == 200
    refused = gw.fetch("laptop-a", peer="p2", lease=30)
    assert refused.status_code == 409
    body = refused.json()
    assert body["error"] == "duplicate-instance" and body["holder"] == "p1"
    assert gw.fetch("laptop-a", peer="p1").status_code == 200
    record = gw.events("gateway.refused")[0]
    assert record["reason"] == "duplicate-instance" and record["peer"] == "p2"


def test_claims_route_held_events_and_are_recorded(gw):
    held = gw.append(1, consumers=[])
    response = gw.claim("laptop-a", "loop-github-o-r-14", "driver")
    assert response.status_code == 200 and response.json()["routed"] == 1
    assert gw.fetch("laptop-a").json()["deliveries"][0]["event"]["id"] == held.event_id
    claimed = gw.events("gateway.claimed")[0]
    assert claimed["instance"] == "laptop-a" and claimed["role"] == "driver"
    routed = gw.events("subject.routed")[0]
    assert routed["to"] == ["laptop-a"] and routed["by"] == "claim"
    assert (
        gw.client.put(
            "/api/v1/gateway/claims",
            json={"instance": "x", "subject": "s", "role": "owner"},
        ).status_code
        == 400
    )
    released = gw.client.request(
        "DELETE",
        "/api/v1/gateway/claims",
        json={
            "instance": "laptop-a",
            "subject": "loop-github-o-r-14",
            "role": "driver",
        },
    )
    assert released.status_code == 200 and released.json()["released"] == 1
    assert gw.events("gateway.released")


def test_a_duplicate_actor_registration_is_409(gw):
    """
    Feature: one start, one instance (abuse case 8)
      Scenario: a duplicate actor registration is refused
    """
    assert gw.fetch("laptop-a", peer="p1", lease=60).status_code == 200
    assert (
        gw.register("laptop-a", {"github": ["octocat"]}, peer="p1").status_code == 200
    )
    refused = gw.register("laptop-b", {"github": ["octocat"], "slack": ["U1"]})
    assert refused.status_code == 409
    assert (
        refused.json()["error"] == "duplicate-actor"
        and refused.json()["holder"] == "laptop-a"
    )
    assert gw.events("gateway.registered")[0]["actors"] == {"github": 1}
    assert gw.events("gateway.refused")[-1]["reason"] == "duplicate-actor"


def test_a_second_peer_under_a_live_name_cannot_replace_the_registration(gw):
    """
    Feature: one start, one instance (R4.3)
      Scenario: a second peer under a live name cannot replace the registration
        Given laptop-a polls as peer p1 with octocat registered
        When a second peer registers under the name laptop-a with other actors
        Then it is 409 duplicate-instance naming the holder, octocat still routes to
             laptop-a, and the same peer may re-register at any time
    """
    assert gw.fetch("laptop-a", peer="p1", lease=60).status_code == 200
    assert (
        gw.register("laptop-a", {"github": ["octocat"]}, peer="p1").status_code == 200
    )
    refused = gw.register("laptop-a", {"github": ["hubot"]}, peer="p2")
    assert refused.status_code == 409
    assert (
        refused.json()["error"] == "duplicate-instance"
        and refused.json()["holder"] == "p1"
    )
    assert gw.store.actors_of("laptop-a") == {"github": ("octocat",)}
    assert gw.store.instance_for_actor("github", "hubot") is None
    assert gw.events("gateway.refused")[-1]["reason"] == "duplicate-instance"
    assert (
        gw.register("laptop-a", {"github": ["octocat", "hubot"]}, peer="p1").status_code
        == 200
    )
    assert gw.store.actors_of("laptop-a") == {"github": ("hubot", "octocat")}


def test_bindings_route_held_events_and_a_bad_ref_is_400(gw):
    gw.append(1, subject="unassigned", work_item=None, consumers=[])
    gw.store.claim("loop-github-o-r-14", "laptop-a", "driver")
    # the held event has no held_key here, so the binding routes nothing; the shape is tested
    response = gw.bind("github:o/r#14", "github", "o/r#77")
    assert response.status_code == 200 and response.json()["routed"] == 0
    assert gw.store.resolve("github", "o/r#77") == "github:o/r#14"
    assert gw.bind("nonsense", "github", "k").status_code == 400


def test_the_allow_list_refuses_an_unknown_name(tmp_path):
    gw = GatewayHarness(tmp_path, instances=["laptop-a"])
    try:
        assert gw.fetch("laptop-a").status_code == 200
        refused = gw.fetch("laptop-z")
        assert (
            refused.status_code == 409 and refused.json()["error"] == "unknown-instance"
        )
        assert gw.claim("laptop-z", "s").status_code == 409
        assert gw.register("laptop-z", {}).status_code == 409
    finally:
        gw.close()


def test_the_views_report_health_subjects_queues_and_instances(gw):
    gw.append(1, consumers=["a"])
    gw.append(2, subject="loop-x-1", work_item="github:o/r#1", consumers=[])
    gw.fetch("a", peer="p1")
    gw.register("a", {"slack": ["U1"]}, peer="p1")
    health = gw.client.get("/api/v1/gateway/health").json()
    assert health["ok"] is True and health["store"]["queues"] == {"a": 1}
    assert health["store"]["held"] == 1 and health["store"]["events"] == 2
    subjects = gw.client.get("/api/v1/gateway/subjects").json()["subjects"]
    assert {s["subject"] for s in subjects} == {"loop-github-o-r-14", "loop-x-1"}
    queues = gw.client.get("/api/v1/gateway/queues").json()["queues"]
    assert queues == [
        {
            "instance": "a",
            "committed": 0,
            "backlog": 1,
            "oldestPendingAt": queues[0]["oldestPendingAt"],
            "dead": 0,
        }
    ]
    (row,) = gw.client.get("/api/v1/gateway/instances").json()["instances"]
    assert row["instance"] == "a" and row["peer"] == "p1" and row["leaseLive"] is True
    assert row["actors"] == {"slack": ["U1"]} and row["backlog"] == 1
