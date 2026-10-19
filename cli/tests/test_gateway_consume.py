"""Unit tests for the consumer API (issue-496, T1 — R3.2, R3.3, R3.4, R4.2, R4.3, R5.3,
R5.5, R5.7, R6.3, R9.2; abuse cases 4, 5, 8)."""

from __future__ import annotations

import pytest

from the_loop.gateway.store import peer_fingerprint

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
            "peer": "p",
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
    assert body["error"] == "duplicate-instance" and body["holder"] == peer_fingerprint(
        "p1"
    )
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
            "peer": "p",
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
    assert refused.json()["error"] == "duplicate-instance" and refused.json()[
        "holder"
    ] == peer_fingerprint("p1")
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
    assert (
        row["instance"] == "a"
        and row["peerFingerprint"] == peer_fingerprint("p1")
        and row["leaseLive"] is True
    )
    assert row["actors"] == {"slack": ["U1"]} and row["backlog"] == 1


def test_a_long_poll_returns_at_once_when_the_gateway_is_stopping(gw):
    """
    Feature: the gateway is one process that follows its own config
      Scenario: a long-poll returns at once when the gateway is stopping
        Given a fetch holding a long-poll on an empty queue
        When the shutdown path marks the state stopping and wakes the store
        Then the fetch returns within a second with no deliveries, and a fetch after
             that does not block at all

    Requirement: docs/specs/issue-496/requirements.md#requirement-8 (R8.5)
    """
    import threading
    import time

    done: dict = {}

    def poll():
        started = time.monotonic()
        response = gw.fetch("laptop-a", peer="p1", lease=60, wait=5)
        done["elapsed"] = time.monotonic() - started
        done["status"] = response.status_code
        done["deliveries"] = response.json()["deliveries"]

    thread = threading.Thread(target=poll)
    thread.start()
    time.sleep(0.3)
    gw.state.stopping.set()
    gw.store.wake_all()
    thread.join(timeout=3)
    assert not thread.is_alive() and done["status"] == 200
    assert done["deliveries"] == [] and done["elapsed"] < 1.5
    started = time.monotonic()
    assert gw.fetch("laptop-a", peer="p1", lease=60, wait=5).status_code == 200
    assert time.monotonic() - started < 0.5


def test_an_actor_registration_routes_the_events_held_for_that_actor(gw):
    """
    Feature: many instances, one queue each
      Scenario: an actor registration routes the events held for that actor
        Given a comment by octocat that arrived before any instance registered octocat
              (held on its subject, no claim, no actor)
        When laptop-a registers octocat
        Then the held event is on laptop-a's queue, subject.routed says by actor, the
             registration answers routed 1, and a second registration routes nothing

    Requirement: docs/specs/issue-496/requirements.md#requirement-2 (R2.2)
                 (self-review R4)
    """
    gw.append(1, consumers=[], actor="octocat")
    gw.append(2, consumers=[], actor="hubot")
    assert gw.fetch("laptop-a", peer="p1", lease=60).json()["deliveries"] == []
    answer = gw.register("laptop-a", {"github": ["octocat"]}, peer="p1")
    assert answer.status_code == 200 and answer.json()["routed"] == 1
    assert gw.events("subject.routed")[-1]["by"] == "actor"
    (delivery,) = gw.fetch("laptop-a", peer="p1").json()["deliveries"]
    assert delivery["event"]["deliveryId"] == "d-1"
    assert (
        gw.register("laptop-a", {"github": ["octocat"]}, peer="p1").json()["routed"]
        == 0
    )
    assert gw.store.queue("laptop-a").backlog == 1  # hubot's stays held


def test_a_stale_peer_under_a_live_name_can_neither_commit_nor_touch_its_claims(gw):
    """
    Feature: one start, one instance (abuse case 4, R4.3)
      Scenario: a stale peer under a live name can neither commit nor touch its claims
        Given laptop-a polls as peer p1 with a delivery fetched and a driver claim
        When peer p2 commits that seq, releases the claim or claims another subject
             under the name laptop-a
        Then each is 409 duplicate-instance naming p1, nothing is applied, and p1's
             own commit and release go through
    """
    gw.append(1, consumers=["laptop-a"])
    (delivery,) = gw.fetch("laptop-a", peer="p1", lease=60).json()["deliveries"]
    assert (
        gw.client.put(
            "/api/v1/gateway/claims",
            json={
                "instance": "laptop-a",
                "peer": "p1",
                "subject": "loop-github-o-r-14",
                "role": "driver",
            },
        ).status_code
        == 200
    )
    stale_commit = gw.client.post(
        "/api/v1/gateway/commit",
        json={
            "instance": "laptop-a",
            "peer": "p2",
            "commit": [{"seq": delivery["seq"], "outcome": "delivered"}],
        },
    )
    assert stale_commit.status_code == 409 and stale_commit.json()[
        "holder"
    ] == peer_fingerprint("p1")
    assert gw.store.committed("laptop-a") == 0
    stale_release = gw.client.request(
        "DELETE",
        "/api/v1/gateway/claims",
        json={
            "instance": "laptop-a",
            "peer": "p2",
            "subject": "loop-github-o-r-14",
            "role": "driver",
        },
    )
    assert stale_release.status_code == 409
    assert {c.instance for c in gw.store.claimants("loop-github-o-r-14")} == {
        "laptop-a"
    }
    stale_claim = gw.client.put(
        "/api/v1/gateway/claims",
        json={
            "instance": "laptop-a",
            "peer": "p2",
            "subject": "loop-github-o-r-77",
            "role": "driver",
        },
    )
    assert stale_claim.status_code == 409 and not gw.store.claimants(
        "loop-github-o-r-77"
    )
    assert [e["reason"] for e in gw.events("gateway.refused")] == [
        "duplicate-instance"
    ] * 3
    own = gw.client.post(
        "/api/v1/gateway/commit",
        json={
            "instance": "laptop-a",
            "peer": "p1",
            "commit": [{"seq": delivery["seq"], "outcome": "delivered"}],
        },
    )
    assert own.status_code == 200 and gw.store.committed("laptop-a") == delivery["seq"]
    assert (
        gw.client.request(
            "DELETE",
            "/api/v1/gateway/claims",
            json={
                "instance": "laptop-a",
                "peer": "p1",
                "subject": "loop-github-o-r-14",
                "role": "driver",
            },
        ).json()["released"]
        == 1
    )


def test_a_long_poll_whose_lease_lapsed_mid_wait_reads_nothing_of_the_new_holders(gw):
    """
    Feature: one start, one instance (R4.3)
      Scenario: a long-poll whose lease lapsed mid-wait reads nothing of the new holder's
        Given peer p1 long-polling laptop-a's empty queue on a one-second lease
        When its lease lapses, peer p2 takes the name, and an event is appended
        Then p1's woken fetch is 409 duplicate-instance naming p2, and p2's next fetch
             carries the delivery (critic C1)
    """
    import threading
    import time

    outcome: dict = {}

    def poll():
        outcome["response"] = gw.fetch("laptop-a", peer="p1", lease=1, wait=5)

    thread = threading.Thread(target=poll)
    thread.start()
    time.sleep(1.3)  # p1's one-second lease has lapsed
    assert gw.fetch("laptop-a", peer="p2", lease=60).status_code == 200
    gw.append(1, consumers=["laptop-a"])
    thread.join(timeout=5)
    assert not thread.is_alive()
    response = outcome["response"]
    assert response.status_code == 409 and response.json()[
        "holder"
    ] == peer_fingerprint("p2"), response.json()
    (delivery,) = gw.fetch("laptop-a", peer="p2").json()["deliveries"]
    assert delivery["event"]["deliveryId"] == "d-1"


def test_a_binding_routes_what_was_held_on_the_pull_requests_own_subject(gw):
    """
    Feature: many instances, one queue each (R5.7)
      Scenario: a binding routes what was held on the pull request's own subject
        Given a PR event held on loop-github-o-r-77 (no claim, no actor) and laptop-a
              driving the ticket o/r#14
        When the binding o/r#77 → o/r#14 is published
        Then the held event is routed onto laptop-a's queue, subject.routed says by
             binding, and a sha key (no subject of its own) still binds without error
             (critic C3)
    """
    gw.append(
        1,
        subject="loop-github-o-r-77",
        work_item="github:o/r#77",
        consumers=[],
        actor="",
    )
    gw.store.claim("loop-github-o-r-14", "laptop-a", "driver")
    assert gw.fetch("laptop-a", peer="p1", lease=60).json()["deliveries"] == []
    answer = gw.bind("github:o/r#14", "github", "o/r#77")
    assert answer.status_code == 200 and answer.json()["routed"] == 1
    assert gw.events("subject.routed")[-1]["by"] == "binding"
    (delivery,) = gw.fetch("laptop-a", peer="p1").json()["deliveries"]
    assert delivery["event"]["deliveryId"] == "d-1"
    assert gw.bind("github:o/r#14", "github", "o/r@abc123").status_code == 200
