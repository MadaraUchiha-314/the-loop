"""Unit tests for the SQLite store (issue-496, T1 — R2.1, R2.6, R2.8, R3.2, R3.4, R3.6,
R4.1, R4.3, R4.4, R5.3, R5.5, R5.7, R9.2, R11.1; abuse cases 4, 5, 6, 8).
"""

from __future__ import annotations

from typing import Any, Dict, Iterator

import threading
import time

import pytest

from the_loop.gateway import store as store_mod
from the_loop.gateway.envelope import Envelope
from the_loop.gateway.store import Refused, SqliteStore


@pytest.fixture()
def store(tmp_path) -> Iterator[SqliteStore]:
    s = SqliteStore(tmp_path / "gateway.db", retention_days=7, max_attempts=3)
    yield s
    s.close()


def ev(
    n: int = 1, *, subject="loop-github-o-r-14", provider="github", **over
) -> Envelope:
    base: Dict[str, Any] = dict(
        subject=subject,
        provider=provider,
        source="webhook",
        delivery_id=f"d-{n}",
        kind="issue_comment",
        payload={"n": n},
        work_item="github:o/r#14",
        actor="octocat",
    )
    base.update(over)
    return Envelope(**base)


# -- append (R2.1, R2.6, R4.1) ----------------------------------------------------------------


def test_append_writes_one_delivery_per_consumer_and_none_elsewhere(store):
    result = store.append(ev(1), ["laptop-a", "laptop-b"])
    assert result.inserted and result.consumers == ("laptop-a", "laptop-b")
    assert len(result.seqs) == 2
    assert [d.event.id for d in store.fetch("laptop-a", 0, 10).deliveries] == [
        result.event_id
    ]
    assert [d.event.id for d in store.fetch("laptop-b", 0, 10).deliveries] == [
        result.event_id
    ]
    assert store.fetch("laptop-c", 0, 10).deliveries == []


def test_append_is_idempotent_on_the_dedup_key(store):
    first = store.append(ev(1, dedup_key="gh-comment-1"), ["laptop-a"])
    again = store.append(
        ev(99, source="poll", delivery_id="poll-comment-1", dedup_key="gh-comment-1"),
        ["laptop-a"],
    )
    assert first.inserted and not again.inserted
    assert again.event_id == first.event_id and again.consumers == ()
    assert len(store.fetch("laptop-a", 0, 10).deliveries) == 1


def test_the_default_dedup_key_is_provider_and_delivery_id(store):
    store.append(ev(1), ["a"])
    assert not store.append(ev(1), ["a"]).inserted
    assert store.append(ev(1, provider="jira"), ["a"]).inserted


def test_an_event_with_no_consumer_is_held_not_delivered(store):
    result = store.append(ev(1), [])
    assert result.held and result.consumers == () and result.inserted
    assert store.fetch("laptop-a", 0, 10).deliveries == []


def test_the_payload_is_stored_verbatim_and_returned_decoded(store):
    raw = b'{"text": "hello",  "user": "U1"}'
    store.append(ev(1, payload=raw, headers={"x-github-event": "issue_comment"}), ["a"])
    (d,) = store.fetch("a", 0, 10).deliveries
    assert d.event.payload == {"text": "hello", "user": "U1"}
    assert d.event.headers == {"x-github-event": "issue_comment"}
    assert d.event.subject == "loop-github-o-r-14" and d.subject == d.event.subject


# -- fetch (R3.2, R3.6) ---------------------------------------------------------------------


def test_fetch_returns_only_this_queue_in_seq_order_after_committed(store):
    for n in range(1, 6):
        store.append(ev(n), ["a"] if n != 3 else ["b"])
    first = store.fetch("a", 0, 2)
    assert [d.event.payload["n"] for d in first.deliveries] == [1, 2]
    assert all(d.attempt == 1 for d in first.deliveries)
    commit = store.commit("a", [(d.seq, "delivered") for d in first.deliveries])
    assert not isinstance(commit, Refused)
    second = store.fetch("a", commit.committed, 10)
    assert [d.event.payload["n"] for d in second.deliveries] == [4, 5]
    assert second.committed == commit.committed


def test_the_cursor_is_a_hint_and_the_server_reads_from_committed(store):
    store.append(ev(1), ["a"])
    store.append(ev(2), ["a"])
    got = store.fetch("a", 0, 10)
    store.commit("a", [(got.deliveries[0].seq, "delivered")])
    # a client with no memory sends 0 and still gets only the uncommitted one
    again = store.fetch("a", 0, 10)
    assert [d.event.payload["n"] for d in again.deliveries] == [2]
    assert again.deliveries[0].attempt == 2
    assert again.redelivered == [
        (again.deliveries[0].seq, again.deliveries[0].event.id, 2)
    ]


def test_a_refetched_delivery_carries_attempt_plus_one_and_is_dead_lettered_at_max(
    store,
):
    store.append(ev(1), ["a"])
    attempts = []
    for _ in range(3):
        got = store.fetch("a", 0, 10)
        attempts.append(got.deliveries[0].attempt)
        store.commit("a", [(got.deliveries[0].seq, "failed")])
    assert attempts == [1, 2, 3]
    fourth = store.fetch("a", 0, 10)
    assert fourth.deliveries == []
    (dead,) = fourth.dead_lettered
    assert dead.attempts == 3 and dead.instance == "a"
    # dead-lettering commits the row: the queue advances past it
    assert fourth.committed == dead.seq


def test_the_fetch_is_an_index_range_read_on_the_queue(store):
    for n in range(1, 4):
        store.append(ev(n), [f"i{n % 2}"])
    plan = store.query_plan("i1")
    assert "deliveries_queue" in plan, plan
    assert "SCAN" not in plan.replace("SEARCH", ""), plan


# -- commit (R3.4, R3.5; abuse case 5) ---------------------------------------------------------


def test_commit_advances_committed_only_contiguously(store):
    for n in range(1, 4):
        store.append(ev(n), ["a"])
    got = store.fetch("a", 0, 10)
    s1, s2, s3 = (d.seq for d in got.deliveries)
    result = store.commit("a", [(s2, "delivered"), (s3, "spawned")])
    assert not isinstance(result, Refused)
    assert result.committed == 0  # s1 is still pending
    result = store.commit("a", [(s1, "dropped:awaiting-start")])
    assert not isinstance(result, Refused)
    assert result.committed == s3
    assert store.committed("a") == s3


def test_a_commit_for_a_delivery_never_fetched_is_refused_and_nothing_applied(store):
    """
    Feature: the commit is honest (requirements §Security, abuse case 5)
      Scenario: a commit for a delivery never fetched is refused
        Given a delivery routed to laptop-a but not yet fetched
        When laptop-b, or laptop-a itself, commits that seq
        Then the store refuses with commit-undelivered and applies nothing
    """
    store.append(ev(1), ["a"])
    store.append(ev(2), ["a"])
    got = store.fetch("a", 0, 1)
    fetched = got.deliveries[0].seq
    unfetched = fetched + 1
    refused = store.commit("a", [(fetched, "delivered"), (unfetched, "delivered")])
    assert isinstance(refused, Refused) and refused.reason == "commit-undelivered"
    assert store.committed("a") == 0  # the valid half was not applied either
    other = store.commit("b", [(fetched, "delivered")])
    assert isinstance(other, Refused) and other.reason == "commit-undelivered"
    nonsense = store.commit("a", [(fetched, "done")])
    assert isinstance(nonsense, Refused)


def test_failed_leaves_the_row_pending_and_recommit_is_idempotent(store):
    store.append(ev(1), ["a"])
    (d,) = store.fetch("a", 0, 10).deliveries
    result = store.commit("a", [(d.seq, "failed")])
    assert not isinstance(result, Refused) and result.pending == (d.seq,)
    assert store.committed("a") == 0
    assert store.commit("a", [(d.seq, "delivered")]).committed == d.seq  # type: ignore[union-attr]
    again = store.commit("a", [(d.seq, "delivered")])
    assert not isinstance(again, Refused) and again.applied == ()


# -- durability (R11.1) ---------------------------------------------------------------------


def test_offsets_survive_a_reopen(tmp_path):
    path = tmp_path / "gateway.db"
    s = SqliteStore(path)
    s.append(ev(1), ["a"])
    s.append(ev(2), ["a"])
    got = s.fetch("a", 0, 1)
    s.commit("a", [(got.deliveries[0].seq, "delivered")])
    s.close()
    s2 = SqliteStore(path)
    assert s2.committed("a") == got.deliveries[0].seq
    assert [d.event.payload["n"] for d in s2.fetch("a", 0, 10).deliveries] == [2]
    assert s2.schema_version() == store_mod.SCHEMA_VERSION
    s2.close()


# -- the long-poll wake-up (R3.3) -----------------------------------------------------------


def test_append_wakes_a_waiter_on_that_queue_only(store):
    woke = {}

    def waiter(name):
        woke[name] = store.wait(name, timeout=2.0)

    threads = [threading.Thread(target=waiter, args=(n,)) for n in ("a", "b")]
    for t in threads:
        t.start()
    time.sleep(0.05)
    started = time.monotonic()
    store.append(ev(1), ["a"])
    threads[0].join()
    assert woke["a"] is True and time.monotonic() - started < 1.0
    threads[1].join()
    assert woke["b"] is False  # timed out: nothing was routed to b


# -- the lease per name, by peer (R4.3; abuse case 4) -----------------------------------------


def test_the_lease_refuses_a_second_peer_under_a_live_name_and_admits_the_same_peer(
    store,
):
    """
    Feature: one queue, one poller (requirements §Security, abuse case 4)
      Scenario: a second peer under the same instance name is refused while the first polls
        Given laptop-a polled as peer p1 within the lease window
        When peer p2 fetches as laptop-a
        Then it is refused with duplicate-instance naming the holder
        And p1 restarting (same persisted peer id) is admitted at once
    """
    first = store.touch("laptop-a", "p1", lease_s=30)
    assert not isinstance(first, Refused) and first.expires_in > 0
    second = store.touch("laptop-a", "p2", lease_s=30)
    assert isinstance(second, Refused) and second.reason == "duplicate-instance"
    assert second.holder == "p1"
    assert not isinstance(store.touch("laptop-a", "p1", lease_s=30), Refused)


def test_an_expired_lease_admits_a_new_peer(store):
    store.touch("laptop-a", "p1", lease_s=0)
    time.sleep(0.01)
    assert not isinstance(store.touch("laptop-a", "p2", lease_s=30), Refused)
    (row,) = store.instances()
    assert row.peer == "p2" and row.lease_live()


# -- claims route held events (R2.2, R5.3) -------------------------------------------------------


def test_a_claim_routes_the_events_held_on_that_subject(store):
    held = store.append(ev(1), [])
    assert held.held
    routed = store.claim("loop-github-o-r-14", "laptop-a", "driver")
    assert routed == [held.event_id]
    (d,) = store.fetch("laptop-a", 0, 10).deliveries
    assert d.event.id == held.event_id
    # a second claim on the same subject does not re-route what was delivered
    assert store.claim("loop-github-o-r-14", "laptop-b", "reviewer") == []
    assert store.fetch("laptop-b", 0, 10).deliveries == []
    claims = store.claimants("loop-github-o-r-14")
    assert [(c.instance, c.role) for c in claims] == [
        ("laptop-a", "driver"),
        ("laptop-b", "reviewer"),
    ]
    assert store.release("loop-github-o-r-14", "laptop-a") == 1
    assert [c.instance for c in store.claimants("loop-github-o-r-14")] == ["laptop-b"]


def test_every_claim_is_listed_with_its_instance_and_time(store):
    """
    Feature: steering is visible (requirements §Security, abuse case 8)
      Scenario: every claim is listed with its instance and time
    """
    store.claim("loop-x-1", "laptop-a", "driver")
    store.claim("loop-x-1", "laptop-b", "reviewer")
    (row,) = store.subjects()
    listed = {(c.instance, c.role) for c in row.claimants}
    assert listed == {("laptop-a", "driver"), ("laptop-b", "reviewer")}
    assert all(c.since.endswith("Z") for c in row.claimants)


# -- actors (R5.5; abuse case 8) --------------------------------------------------------------


def test_a_duplicate_actor_registration_is_refused_while_the_holder_is_live(store):
    """
    Feature: one start, one instance (requirements §Security, abuse case 8)
      Scenario: a duplicate actor registration is refused
        Given laptop-a registered github:octocat and its lease is live
        When laptop-b registers github:octocat
        Then it is refused with duplicate-actor naming laptop-a, and nothing is applied
    """
    store.touch("laptop-a", "p1", lease_s=60)
    assert (
        store.register_actors("laptop-a", {"github": ["octocat"], "slack": ["U1"]})
        is None
    )
    refused = store.register_actors("laptop-b", {"github": ["octocat"], "jira": ["j1"]})
    assert isinstance(refused, Refused) and refused.reason == "duplicate-actor"
    assert refused.holder == "laptop-a"
    assert store.instance_for_actor("jira", "j1") is None  # nothing applied
    assert store.instance_for_actor("github", "octocat") == "laptop-a"
    assert store.actors_of("laptop-a") == {"github": ("octocat",), "slack": ("U1",)}


def test_an_actor_of_an_expired_instance_is_taken_over_and_a_registration_replaces(
    store,
):
    store.touch("laptop-a", "p1", lease_s=0)
    store.register_actors("laptop-a", {"github": ["octocat"]})
    time.sleep(0.01)
    assert store.register_actors("laptop-b", {"github": ["octocat"]}) is None
    assert store.instance_for_actor("github", "octocat") == "laptop-b"
    store.register_actors("laptop-b", {"github": ["hubot"]})  # replaces the set
    assert store.instance_for_actor("github", "octocat") is None
    assert store.instance_for_actor("github", "hubot") == "laptop-b"


# -- bindings route held events (R5.7, R5.8) -------------------------------------------------


def test_a_binding_routes_held_events_to_the_subjects_claimants(store):
    held = store.append(
        ev(1, subject="unassigned", work_item=None, provider="github"),
        [],
        held_key="o/r#77",
    )
    store.claim("loop-github-o-r-14", "laptop-a", "driver")
    routed = store.bind("github", "o/r#77", "github:o/r#14", "github-o-r-14")
    assert routed == [held.event_id]
    assert store.resolve("github", "o/r#77") == "github:o/r#14"
    (d,) = store.fetch("laptop-a", 0, 10).deliveries
    assert (
        d.event.subject == "loop-github-o-r-14" and d.event.work_item == "github:o/r#14"
    )


def test_a_binding_with_no_claimant_routes_by_actor_else_keeps_holding(store):
    store.touch("laptop-b", "p", lease_s=60)
    store.register_actors("laptop-b", {"slack": ["U9"]})
    by_actor = store.append(
        ev(1, subject="unassigned", provider="slack", actor="U9", work_item=None),
        [],
        held_key="C1:1700.1",
    )
    nobody = store.append(
        ev(2, subject="unassigned", provider="slack", actor="U0", work_item=None),
        [],
        held_key="C1:1700.1",
    )
    routed = store.bind("slack", "C1:1700.1", "github:o/r#14", "github-o-r-14")
    assert routed == [by_actor.event_id]
    (d,) = store.fetch("laptop-b", 0, 10).deliveries
    assert d.event.id == by_actor.event_id
    (row,) = [r for r in store.subjects() if r.subject == "loop-github-o-r-14"]
    assert row.held == 1  # U0's event waits under its new subject
    assert store.claim("loop-github-o-r-14", "laptop-a", "driver") == [nobody.event_id]


# -- views (R9.2) -----------------------------------------------------------------------------


def test_subjects_queues_and_instances_report_depth_and_oldest_age(store):
    store.append(ev(1), ["a"])
    store.append(ev(2), ["a"])
    store.append(ev(3, subject="loop-other-1", work_item="github:o/r#1"), ["b"])
    got = store.fetch("a", 0, 1)
    store.commit("a", [(got.deliveries[0].seq, "delivered")])
    subjects = {r.subject: r for r in store.subjects()}
    assert subjects["loop-github-o-r-14"].pending == 1
    assert subjects["loop-github-o-r-14"].events == 2
    assert subjects["loop-github-o-r-14"].oldest_pending_at is not None
    queues = {q.instance: q for q in store.queues()}
    assert queues["a"].backlog == 1 and queues["a"].committed == got.deliveries[0].seq
    assert queues["b"].backlog == 1 and queues["b"].committed == 0
    instances = {i.instance: i for i in store.instances()}
    assert instances["a"].last_fetch_at is not None and instances["a"].backlog == 1
    assert instances["b"].last_fetch_at is None


# -- retention (R2.8; abuse case 6) -------------------------------------------------------------


def test_retention_expires_committed_then_pending_then_held(tmp_path):
    """
    Feature: bounded growth (requirements §Security, abuse case 6)
      Scenario: retention expires committed rows
        Given committed, pending and held rows older than retention
        When expire runs
        Then committed rows are deleted silently, pending and held ones are expired and
             reported, and an event with no delivery left is deleted with its key retired
    """
    store = SqliteStore(tmp_path / "gw.db", retention_days=1, dedup_window=10)
    store.append(ev(1), ["a"])  # will be committed
    store.append(ev(2), ["a"])  # stays pending
    store.append(ev(3), [])  # held
    got = store.fetch("a", 0, 1)
    store.commit("a", [(got.deliveries[0].seq, "delivered")])
    later = time.time() + 2 * 86_400
    result = store.expire(now=later)
    assert result.deleted_deliveries == 2  # the committed row and the pending row
    assert sorted(e[1] for e in result.expired) == [2, 3]
    assert {e[2] for e in result.expired} == {"a", ""}
    assert result.deleted_events == 3
    assert store.fetch("a", 0, 10).deliveries == []
    # a late redelivery of the expired event is still recognised (dedup window)
    assert not store.append(ev(1), ["a"]).inserted
    store.close()


def test_retention_keeps_fresh_rows(store):
    store.append(ev(1), ["a"])
    store.fetch("a", 0, 10)
    result = store.expire()
    assert result.expired == () and result.deleted_events == 0
    assert len(store.fetch("a", 0, 10).deliveries) == 1
