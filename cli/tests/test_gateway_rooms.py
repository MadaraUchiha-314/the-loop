"""Unit tests for collaboration-channel rooms behind a gateway (issue-505, T1, T8, T10 —
R1.1–R1.6, R2.1–R2.4, R3.1–R3.3, R4.1–R4.5, R5.1–R5.4, R7.1, R7.2; abuse cases 1–5).
"""

from __future__ import annotations

import sqlite3
from typing import Iterator

import pytest

from the_loop.gateway.envelope import UNASSIGNED, Envelope
from the_loop.gateway.store import Refused, SqliteStore

REF = "github:o/r#14"
SLUG = "github-o-r-14"
SUBJECT = f"loop-{SLUG}"


@pytest.fixture()
def store(tmp_path) -> Iterator[SqliteStore]:
    s = SqliteStore(tmp_path / "gateway.db", retention_days=7, max_attempts=3)
    yield s
    s.close()


def held(store: SqliteStore, n: int, key: str, actor: str = "U_COLLAB") -> int:
    env = Envelope(
        subject=UNASSIGNED,
        provider="slack",
        source="socket",
        delivery_id=f"s-{n}",
        kind="events_api",
        payload={"n": n},
        work_item=None,
        actor=actor,
    )
    return store.append(env, [], held_key=key).event_id


def subject_of(store: SqliteStore, event_id: int) -> str:
    conn = sqlite3.connect(str(store.path))
    try:
        return conn.execute(
            "SELECT subject FROM events WHERE id = ?", (event_id,)
        ).fetchone()[0]
    finally:
        conn.close()


# -- the store: publish, resolve, retract (R3, R4, R5) ------------------------------------


def test_publish_rooms_records_and_resolves_a_room(store):
    result = store.publish_rooms("laptop-a", {"C0123ABCD": (REF, SLUG)}, peer="p")
    assert not isinstance(result, Refused)
    assert result.rooms == ("C0123ABCD",) and result.refused == ()
    assert store.resolve_room("C0123ABCD") == (REF, SLUG)
    assert store.resolve_room("C0OTHER") is None
    assert store.rooms_of("laptop-a") == [("C0123ABCD", REF)]


def test_publishing_drains_the_rooms_held_events_in_order(store):
    store.claim(SUBJECT, "laptop-a", "driver")
    first = held(store, 1, "C0123ABCD:1700.1")
    second = held(store, 2, "C0123ABCD:1700.2")
    other = held(store, 3, "C0OTHER:1700.3")
    result = store.publish_rooms("laptop-a", {"C0123ABCD": (REF, SLUG)})
    assert result.routed == [first, second]
    deliveries = store.fetch("laptop-a", 0, 10).deliveries
    assert [d.event.id for d in deliveries] == [first, second]
    assert all(
        d.event.subject == SUBJECT and d.event.work_item == REF for d in deliveries
    )
    assert subject_of(store, other) == UNASSIGNED


def test_a_drained_event_waits_on_the_subject_until_a_claim(store):
    event = held(store, 1, "C0123ABCD:1700.1", actor="U_NOBODY")
    assert store.publish_rooms("laptop-a", {"C0123ABCD": (REF, SLUG)}).routed == []
    assert subject_of(store, event) == SUBJECT
    assert store.claim(SUBJECT, "laptop-a", "driver") == [event]


def test_the_drain_matches_the_channel_exactly_not_as_a_pattern(store):
    store.claim(SUBJECT, "laptop-a", "driver")
    # `_` is a LIKE wildcard; a channel id may contain one
    lookalike = held(store, 1, "C0_ABXY:1700.1")
    store.publish_rooms("laptop-a", {"C0_AB": (REF, SLUG)})
    assert subject_of(store, lookalike) == UNASSIGNED


def test_an_already_routed_event_is_not_routed_again(store):
    store.claim(SUBJECT, "laptop-a", "driver")
    held(store, 1, "C0123ABCD:1700.1")
    assert len(store.publish_rooms("laptop-a", {"C0123ABCD": (REF, SLUG)}).routed) == 1
    store.publish_rooms("laptop-a", {})
    assert store.publish_rooms("laptop-a", {"C0123ABCD": (REF, SLUG)}).routed == []
    assert len(store.fetch("laptop-a", 0, 10).deliveries) == 1


def test_a_set_without_a_room_retracts_it_and_a_move_swaps_it(store):
    store.publish_rooms("laptop-a", {"C0OLD": (REF, SLUG)})
    store.publish_rooms("laptop-a", {"C0NEW": (REF, SLUG)})
    assert store.resolve_room("C0OLD") is None
    assert store.resolve_room("C0NEW") == (REF, SLUG)
    store.publish_rooms("laptop-a", {})
    assert store.resolve_room("C0NEW") is None and store.rooms_of("laptop-a") == []


def test_abuse_a_live_holders_room_is_kept_and_the_rest_applied(store):
    store.touch("laptop-a", "pa", lease_s=60)
    store.publish_rooms("laptop-a", {"C0SHARED": (REF, SLUG)}, peer="pa")
    result = store.publish_rooms(
        "laptop-b",
        {"C0SHARED": ("github:o/r#99", "github-o-r-99"), "C0MINE": (REF, SLUG)},
        peer="pb",
    )
    assert result.refused == (("C0SHARED", "laptop-a"),)
    assert result.rooms == ("C0MINE",)
    assert store.resolve_room("C0SHARED") == (REF, SLUG)
    assert store.rooms_of("laptop-b") == [("C0MINE", REF)]


def test_an_expired_holders_room_is_taken_over(store):
    store.publish_rooms("laptop-a", {"C0SHARED": (REF, SLUG)})  # no lease: lapsed
    result = store.publish_rooms(
        "laptop-b", {"C0SHARED": ("github:o/r#99", "github-o-r-99")}
    )
    assert result.refused == () and result.rooms == ("C0SHARED",)
    assert store.resolve_room("C0SHARED") == ("github:o/r#99", "github-o-r-99")
    assert store.rooms_of("laptop-a") == []


def test_abuse_a_publication_never_retracts_another_instances_room(store):
    store.publish_rooms("laptop-a", {"C0A": (REF, SLUG)})
    store.publish_rooms("laptop-b", {})
    assert store.resolve_room("C0A") == (REF, SLUG)


def test_abuse_a_second_peer_under_a_live_name_is_refused_and_nothing_applied(store):
    store.touch("laptop-a", "pa", lease_s=60)
    store.publish_rooms("laptop-a", {"C0A": (REF, SLUG)}, peer="pa")
    refused = store.publish_rooms("laptop-a", {}, peer="intruder")
    assert isinstance(refused, Refused) and refused.reason == "duplicate-instance"
    assert store.resolve_room("C0A") == (REF, SLUG)


def test_pruning_a_lapsed_instance_drops_its_rooms(store):
    store.publish_rooms("laptop-a", {"C0A": (REF, SLUG)})
    pruned, _ = store._prune(now_s=10**12, cutoff="9999-12-31T00:00:00Z")
    assert "laptop-a" in pruned
    assert store.resolve_room("C0A") is None


def test_the_instances_view_lists_rooms(store):
    store.publish_rooms("laptop-a", {"C0A": (REF, SLUG)})
    (row,) = [i for i in store.instances() if i.instance == "laptop-a"]
    assert store.rooms_of(row.instance) == [("C0A", REF)]


def test_migration_a_store_without_the_rooms_table_gains_it(tmp_path):
    path = tmp_path / "gateway.db"
    old = SqliteStore(path)
    old.bind("slack", "C1:1700.1", REF, SLUG)
    old.close()
    conn = sqlite3.connect(str(path))
    conn.execute("DROP TABLE rooms")  # the 20.4.0 schema had none
    conn.commit()
    conn.close()
    reopened = SqliteStore(path)
    try:
        assert reopened.resolve("slack", "C1:1700.1") == REF
        reopened.publish_rooms("laptop-a", {"C0A": (REF, SLUG)})
        assert reopened.resolve_room("C0A") == (REF, SLUG)
    finally:
        reopened.close()


def test_bind_keeps_routing_held_events_after_the_refactor(store):
    store.claim(SUBJECT, "laptop-a", "driver")
    event = held(store, 1, "C1:1700.1")
    assert store.bind("slack", "C1:1700.1", REF, SLUG) == [event]

