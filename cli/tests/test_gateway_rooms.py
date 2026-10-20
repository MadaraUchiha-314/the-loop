"""Unit tests for collaboration-channel rooms behind a gateway (issue-505, T1, T8, T10 —
R1.1–R1.6, R2.1–R2.4, R3.1–R3.3, R4.1–R4.5, R5.1–R5.4, R7.1, R7.2; abuse cases 1–5).
"""

from __future__ import annotations

import sqlite3
from typing import Iterator

import pytest

from the_loop.gateway.envelope import UNASSIGNED, Envelope
from the_loop.gateway.store import Refused, SqliteStore
from the_loop.sessions import WorkItemRef

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
    assert result.routed == [(first, SUBJECT), (second, SUBJECT)]
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


# -- resolution order (R2.1, R2.3, R2.4) ----------------------------------------------------


def _slack_event(channel: str, ts: str, thread: str = "") -> dict:
    event = {"type": "message", "channel": channel, "ts": ts, "user": "U_COLLAB"}
    if thread:
        event["thread_ts"] = thread
    return {"event_id": f"Ev-{ts}", "event": event}


@pytest.fixture()
def gw(tmp_path):
    from gateway_support import GatewayHarness

    harness = GatewayHarness(
        tmp_path, slack={"rooms": [{"channel": "C0STATIC", "workItem": "github:o/r#1"}]}
    )
    yield harness
    harness.close()


def _resolve(gw, payload):
    from the_loop.gateway.adapters.common import resolve_ref

    return resolve_ref("slack", "events_api", payload, gw.store, gw.config)


def test_a_top_level_message_in_a_published_room_resolves_to_its_work_item(gw):
    gw.store.publish_rooms("laptop-a", {"C0123ABCD": (REF, SLUG)})
    resolved = _resolve(gw, _slack_event("C0123ABCD", "1700.1"))
    assert resolved.subject == SUBJECT and resolved.work_item == REF


def test_a_thread_binding_beats_the_room(gw):
    gw.store.publish_rooms("laptop-a", {"C0123ABCD": (REF, SLUG)})
    gw.store.bind("slack", "C0123ABCD:1700.0", "github:o/r#2", "github-o-r-2")
    resolved = _resolve(gw, _slack_event("C0123ABCD", "1700.3", thread="1700.0"))
    assert resolved.work_item == "github:o/r#2"


def test_a_published_room_beats_the_static_room(gw):
    gw.store.publish_rooms("laptop-a", {"C0STATIC": (REF, SLUG)})
    assert _resolve(gw, _slack_event("C0STATIC", "1700.1")).work_item == REF


def test_without_a_room_resolution_is_unchanged(gw):
    assert _resolve(gw, _slack_event("C0STATIC", "1700.1")).work_item == "github:o/r#1"
    resolved = _resolve(gw, _slack_event("C0123ABCD", "1700.1"))
    assert resolved.subject == UNASSIGNED and resolved.held_key == "C0123ABCD:1700.1"


def test_a_slash_command_in_a_published_room_resolves(gw):
    from the_loop.gateway.adapters.common import resolve_ref

    gw.store.publish_rooms("laptop-a", {"C0123ABCD": (REF, SLUG)})
    resolved = resolve_ref(
        "slack", "slash_commands", {"channel_id": "C0123ABCD"}, gw.store, gw.config
    )
    assert resolved.work_item == REF


# -- PUT /api/v1/gateway/rooms (R5.1, R5.4, R7.1, R7.2; abuse 1, 5) ------------------------


def _put_rooms(gw, rooms, instance="laptop-a", peer="p"):
    return gw.client.put(
        "/api/v1/gateway/rooms",
        json={"instance": instance, "peer": peer, "rooms": rooms},
    )


def test_put_rooms_publishes_and_reports_routed_and_refused(gw):
    gw.store.claim(SUBJECT, "laptop-a", "driver")
    held(gw.store, 1, "C0123ABCD:1700.1")
    answer = _put_rooms(gw, {"C0123ABCD": REF})
    assert answer.status_code == 200
    assert answer.json() == {
        "instance": "laptop-a",
        "rooms": {"C0123ABCD": REF},
        "refused": [],
        "routed": 1,
    }
    (record,) = gw.events("gateway.rooms")
    assert record["instance"] == "laptop-a" and record["rooms"] == 1
    assert record["routed"] == 1
    assert [r["by"] for r in gw.events("subject.routed")] == ["room"]


def test_put_rooms_reports_a_live_holders_room_as_refused(gw):
    gw.store.touch("laptop-b", "pb", lease_s=60)
    gw.store.publish_rooms("laptop-b", {"C0SHARED": (REF, SLUG)}, peer="pb")
    answer = _put_rooms(gw, {"C0SHARED": "github:o/r#99", "C0MINE": REF})
    assert answer.status_code == 200
    body = answer.json()
    assert body["rooms"] == {"C0MINE": REF}
    assert body["refused"] == [{"channel": "C0SHARED", "holder": "laptop-b"}]
    (refusal,) = gw.events("gateway.refused")
    assert refusal["reason"] == "duplicate-room" and refusal["holder"] == "laptop-b"
    assert refusal["channel"] == "C0SHARED"


def test_the_instances_view_reports_each_instances_rooms(gw):
    _put_rooms(gw, {"C0123ABCD": REF})
    (row,) = [
        r
        for r in gw.client.get("/api/v1/gateway/instances").json()["instances"]
        if r["instance"] == "laptop-a"
    ]
    assert row["rooms"] == [{"channel": "C0123ABCD", "workItem": REF}]


def test_abuse_an_instance_off_the_allow_list_is_refused(tmp_path):
    from gateway_support import GatewayHarness

    gw = GatewayHarness(tmp_path, instances=["laptop-a"])
    try:
        answer = _put_rooms(gw, {"C0123ABCD": REF}, instance="intruder")
        assert answer.status_code == 409
        assert answer.json()["error"] == "unknown-instance"
        assert gw.store.resolve_room("C0123ABCD") is None
    finally:
        gw.close()


def test_abuse_a_second_peer_under_a_live_name_gets_409(gw):
    gw.store.touch("laptop-a", "p", lease_s=60)
    assert _put_rooms(gw, {"C0123ABCD": REF}, peer="intruder").status_code == 409
    assert gw.store.resolve_room("C0123ABCD") is None


@pytest.mark.parametrize(
    "rooms",
    [
        {"not-a-channel": REF},
        {"C0123ABCD:1700.1": REF},
        {"C0123ABCD": "not a ref"},
        {"C0123ABCD": "x" * 600},
        {f"C{n:08d}": REF for n in range(257)},
    ],
    ids=["name", "thread-key", "bad-ref", "long-ref", "too-many"],
)
def test_abuse_a_malformed_publication_is_422_and_stores_nothing(gw, rooms):
    assert _put_rooms(gw, rooms).status_code == 422
    assert gw.store.rooms_of("laptop-a") == []


# -- the instance: the store hook (R1.2) ------------------------------------------------------


@pytest.fixture()
def channels(tmp_path, monkeypatch):
    from the_loop.workchannels import CollaborationChannelStore

    calls: list = []
    monkeypatch.setattr(CollaborationChannelStore, "on_change", lambda: calls.append(1))
    return CollaborationChannelStore(tmp_path / "portable"), calls


def test_on_change_fires_after_a_changing_add_remove_and_clear(channels):
    store, calls = channels
    store.add(REF, "slack@C0123ABCD", actor="op")
    assert len(calls) == 1
    store.add(REF, "slack@C0123ABCD", actor="op")  # unchanged
    assert len(calls) == 1
    store.remove(REF, "slack@C0123ABCD")
    assert len(calls) == 2
    store.remove(REF, "slack@C0123ABCD")  # nothing to remove
    assert len(calls) == 2
    store.add(REF, "slack@C0OTHER", actor="op")
    store.clear(REF)
    assert len(calls) == 4
    store.clear(REF)  # nothing to clear
    assert len(calls) == 4


def test_on_change_failing_never_fails_the_declaration(tmp_path, monkeypatch):
    from the_loop.workchannels import CollaborationChannelStore

    def boom() -> None:
        raise RuntimeError("gateway down")

    monkeypatch.setattr(CollaborationChannelStore, "on_change", boom)
    store = CollaborationChannelStore(tmp_path / "portable")
    changed, _ = store.add(REF, "slack@C0123ABCD", actor="op")
    assert changed and store.targets() == {"C0123ABCD": REF}


# -- the instance: the client publishes rooms (R1.1–R1.6, R4.1, R4.2) ------------------------


class _Transport:
    def __init__(self, harness):
        self.harness = harness
        self.down = False
        self.status: "int | None" = None
        self.calls: list = []

    def __call__(self, method, path, body, timeout):
        self.calls.append((method, path, dict(body) if body else None))
        if self.down:
            raise OSError("connection refused")
        if self.status is not None and path.endswith("/rooms"):
            return self.status, {"error": "boom"}
        response = self.harness.client.request(method, path, json=body)
        return response.status_code, (response.json() if response.content else None)


def _gateway_client(gw, tmp_path, channel_store=None):
    import threading

    from the_loop.gateway.client import GatewayClient

    transport = _Transport(gw)
    client = GatewayClient(
        {
            "state": {"root": str(tmp_path / ".the-loop")},
            "instance": {"name": "laptop-a"},
            "gateway": {
                "url": "http://gw",
                "pollIntervalSeconds": 5,
                "longPollSeconds": 0,
            },
        },
        threading.Event(),
        transport=transport,
        sleep=lambda _: None,
        rng=lambda: 0.5,
    )

    class _Registry:
        publisher = None

        def list_sessions(self):
            return []

    if channel_store is not None:
        client.attach(_Registry(), channel_store=channel_store)
    return client, transport


def _rooms_calls(transport):
    return [body for _, path, body in transport.calls if path.endswith("/rooms")]


@pytest.fixture()
def declared(tmp_path):
    from the_loop.workchannels import CollaborationChannelStore

    return CollaborationChannelStore(tmp_path / "portable")


def test_register_publishes_every_declared_room(gw, tmp_path, declared):
    declared.add(REF, "slack@C0123ABCD", actor="op")
    client, transport = _gateway_client(gw, tmp_path, declared)
    client.step()
    assert _rooms_calls(transport)[0]["rooms"] == {"C0123ABCD": REF}
    assert gw.store.resolve_room("C0123ABCD") == (REF, SLUG)
    assert client.document(probe=False)["rooms"] == {"C0123ABCD": REF}


def test_a_contested_channel_is_not_published(gw, tmp_path, declared):
    declared.add(REF, "slack@C0123ABCD", actor="op")
    # a second record naming the same channel (hand-edited): declared by none
    declared._write(WorkItemRef.parse("github:o/r#99"), declared.list(REF))
    client, transport = _gateway_client(gw, tmp_path, declared)
    client.step()
    assert _rooms_calls(transport)[0]["rooms"] == {}


def test_the_reconcile_publishes_only_a_changed_set_after_the_interval(
    gw, tmp_path, declared
):
    client, transport = _gateway_client(gw, tmp_path, declared)
    client.step()  # registers: one publish of {}
    assert len(_rooms_calls(transport)) == 1
    declared.add(REF, "slack@C0123ABCD", actor="op")  # another process: no hook here
    client.step()
    assert len(_rooms_calls(transport)) == 1  # the interval has not passed
    client._rooms_at -= 31
    client.step()
    assert _rooms_calls(transport)[-1]["rooms"] == {"C0123ABCD": REF}
    client._rooms_at -= 31
    client.step()
    assert len(_rooms_calls(transport)) == 2  # unchanged: no call


def test_register_publishes_the_full_set_even_when_unchanged(gw, tmp_path, declared):
    declared.add(REF, "slack@C0123ABCD", actor="op")
    client, transport = _gateway_client(gw, tmp_path, declared)
    client.step()
    client.registered = False  # an outage
    client.step()
    assert len(_rooms_calls(transport)) == 2


def test_a_failed_publish_is_logged_and_retried(gw, tmp_path, declared, caplog):
    client, transport = _gateway_client(gw, tmp_path, declared)
    client.step()
    declared.add(REF, "slack@C0123ABCD", actor="op")
    transport.status = 500
    assert client.publish_rooms() is False
    assert "rooms not published" in caplog.text
    transport.status = None
    transport.down = True
    assert client.publish_rooms() is False
    transport.down = False
    assert client.publish_rooms() is True
    assert gw.store.resolve_room("C0123ABCD") == (REF, SLUG)


def test_retraction_reaches_the_gateway(gw, tmp_path, declared):
    declared.add(REF, "slack@C0OLD", actor="op")
    client, _ = _gateway_client(gw, tmp_path, declared)
    client.step()
    declared.add(REF, "slack@C0NEW", actor="op")  # moves the room
    client.publish_rooms()
    assert gw.store.resolve_room("C0OLD") is None
    assert gw.store.resolve_room("C0NEW") == (REF, SLUG)
    declared.clear(REF)
    client.publish_rooms()
    assert gw.store.resolve_room("C0NEW") is None


def test_abuse_an_unreadable_directory_retracts_nothing(
    gw, tmp_path, declared, monkeypatch
):
    declared.add(REF, "slack@C0123ABCD", actor="op")
    client, transport = _gateway_client(gw, tmp_path, declared)
    client.step()
    real_iterdir = type(declared.root).iterdir

    def unreadable(path):
        if path == declared.root:
            raise PermissionError("denied")
        return real_iterdir(path)

    monkeypatch.setattr(type(declared.root), "iterdir", unreadable)
    assert client.publish_rooms(force=True) is False
    assert len(_rooms_calls(transport)) == 1
    assert gw.store.resolve_room("C0123ABCD") == (REF, SLUG)


def test_abuse_a_corrupt_record_retracts_nothing(gw, tmp_path, declared):
    """Critic C3: the record reader swallows a corrupt file; the snapshot must not."""
    declared.add(REF, "slack@C0123ABCD", actor="op")
    client, transport = _gateway_client(gw, tmp_path, declared)
    client.step()
    (record,) = [p for p in declared.root.glob("*.json") if p.name != "index.json"]
    record.write_text("{not json", encoding="utf-8")
    assert client.publish_rooms(force=True) is False
    assert len(_rooms_calls(transport)) == 1
    assert gw.store.resolve_room("C0123ABCD") == (REF, SLUG)


def test_a_client_without_a_channel_store_publishes_no_rooms(gw, tmp_path):
    client, transport = _gateway_client(gw, tmp_path)
    client.step()
    assert _rooms_calls(transport) == []


def test_the_drain_leaves_an_event_a_thread_binding_already_claimed(store):
    """Critic C1: a bound thread keeps its work item (R2.4), even unclaimed."""
    event = held(store, 1, "C0123ABCD:1700.0", actor="U_NOBODY")
    store.bind("slack", "C0123ABCD:1700.0", "github:o/r#2", "github-o-r-2")
    assert subject_of(store, event) == "loop-github-o-r-2"  # held there, no claimant
    store.claim(SUBJECT, "laptop-b", "driver")
    store.publish_rooms("laptop-b", {"C0123ABCD": (REF, SLUG)})
    assert subject_of(store, event) == "loop-github-o-r-2"
    assert store.fetch("laptop-b", 0, 10).deliveries == []


def test_a_room_published_between_resolve_and_append_still_routes_the_event(
    gw, monkeypatch
):
    """Critic C2: the ingest resolves, then appends in another transaction."""
    import json

    import the_loop.gateway.adapters.ingest as ingest_mod

    gw.store.claim(SUBJECT, "laptop-a", "driver")
    real_resolve = ingest_mod.resolve_ref

    def resolve_then_publish(*args, **kwargs):
        resolved = real_resolve(*args, **kwargs)  # unassigned: no room yet
        gw.store.publish_rooms("laptop-a", {"C0123ABCD": (REF, SLUG)})
        return resolved

    monkeypatch.setattr(ingest_mod, "resolve_ref", resolve_then_publish)
    payload = _slack_event("C0123ABCD", "1700.7")
    ingest_mod.Ingest(gw.state).accept(
        "slack", "socket", "events_api", "d-race", {}, json.dumps(payload).encode()
    )
    (delivery,) = gw.store.fetch("laptop-a", 0, 10).deliveries
    assert delivery.event.subject == SUBJECT and delivery.event.work_item == REF


def test_a_refused_room_is_taken_on_a_later_reconcile_once_the_holder_lets_go(
    gw, tmp_path, declared, caplog
):
    """Critic C4: a refused room is retried, and its warning is not repeated."""
    gw.store.touch("laptop-b", "pb", lease_s=60)
    gw.store.publish_rooms("laptop-b", {"C0123ABCD": (REF, SLUG)}, peer="pb")
    declared.add(REF, "slack@C0123ABCD", actor="op")
    client, transport = _gateway_client(gw, tmp_path, declared)
    client.step()
    assert gw.store.rooms_of("laptop-a") == []
    assert caplog.text.count("held by instance laptop-b") == 1
    client.publish_rooms()  # still held: retried, warned once
    assert len(_rooms_calls(transport)) == 2
    assert caplog.text.count("held by instance laptop-b") == 1
    gw.store.publish_rooms("laptop-b", {}, peer="pb")  # the holder retracts
    client.publish_rooms()
    assert gw.store.rooms_of("laptop-a") == [("C0123ABCD", REF)]
    client.publish_rooms()  # accepted now: no further call
    assert len(_rooms_calls(transport)) == 3
