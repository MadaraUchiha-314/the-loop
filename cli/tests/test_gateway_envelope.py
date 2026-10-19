"""Unit tests for the stored event's shape and the gateway's event families
(issue-496, T1 — R6.2, R10.1, R10.2).
"""

from __future__ import annotations

from typing import Any, Dict

import json

from the_loop import eventlog
from the_loop.gateway import envelope as env


def _envelope(**over) -> env.Envelope:
    base: Dict[str, Any] = dict(
        subject="loop-github-o-r-14",
        provider="slack",
        source="socket",
        delivery_id="Ev0ABC",
        kind="message",
        payload={"text": "hello", "user": "U1"},
        work_item="github:o/r#14",
        headers={"x-slack-request-timestamp": "1"},
        received_at="2026-10-18T14:02:11.120Z",
    )
    base.update(over)
    return env.Envelope(**base)


def test_the_envelope_carries_exactly_the_ten_fields_of_r6_2():
    data = _envelope(id=42).to_json()
    assert set(data) == {
        "id",
        "subject",
        "provider",
        "source",
        "deliveryId",
        "receivedAt",
        "workItem",
        "kind",
        "headers",
        "payload",
        "attempt",
    }
    assert data["payload"] == {"text": "hello", "user": "U1"}
    assert data["attempt"] == 1


def test_the_envelope_and_delivery_round_trip_through_json():
    original = _envelope(id=7, attempt=2)
    again = env.Envelope.from_json(json.loads(json.dumps(original.to_json())))
    assert again == env.Envelope(**{**original.__dict__, "actor": None})
    delivery = env.Delivery(seq=17, attempt=3, event=original)
    data = json.loads(json.dumps(delivery.to_json()))
    assert (
        data["event"]["attempt"] == 3
    )  # the delivery's attempt is what the client sees
    assert data["subject"] == original.subject
    back = env.Delivery.from_json(data)
    assert back.seq == 17 and back.attempt == 3 and back.event.id == 7


def test_headers_keep_only_the_allow_list_lower_cased():
    kept = env.Envelope.filter_headers(
        {
            "X-GitHub-Event": "issue_comment",
            "X-GitHub-Delivery": "d-1",
            "Authorization": "Bearer nope",
            "Cookie": "a=b",
            "X-Hub-Signature-256": "sha256=…",
        }
    )
    assert kept == {"x-github-event": "issue_comment", "x-github-delivery": "d-1"}


def test_the_subject_is_named_after_the_tmux_slug():
    assert env.subject_for_slug("github-o-r-14") == "loop-github-o-r-14"
    assert env.UNASSIGNED == "unassigned"


def test_outcomes_are_the_four_words_plus_a_dropped_reason():
    assert env.is_outcome("delivered")
    assert env.is_outcome("spawned")
    assert env.is_outcome("failed")
    assert env.is_outcome("dropped:awaiting-start")
    assert env.is_outcome("dead-lettered")
    assert not env.is_outcome("done")


def test_payload_bytes_are_verbatim_when_the_adapter_had_bytes():
    raw = b'{"a": 1,  "b":2}'
    assert _envelope(payload=raw).payload_bytes() == raw
    assert json.loads(_envelope().payload_bytes()) == {"text": "hello", "user": "U1"}


# -- the event families (R10.1) ------------------------------------------------------------


def test_the_two_families_are_in_the_catalogue():
    gateway = {
        "started",
        "stopped",
        "received",
        "dropped",
        "refused",
        "reloaded",
        "claimed",
        "released",
        "registered",
        "unreachable",
        "connected",
    }
    subject = {
        "appended",
        "routed",
        "committed",
        "redelivered",
        "dead-lettered",
        "expired",
    }
    for name in gateway:
        assert f"gateway.{name}" in eventlog.EVENT_TYPES, name
    for name in subject:
        assert f"subject.{name}" in eventlog.EVENT_TYPES, name


# -- context fields ride every record on the thread (R10.2) -----------------------------------


def test_context_fields_are_added_to_every_record_emitted_within(tmp_path):
    log = eventlog.EventLog(tmp_path / "events.jsonl", source="test")
    with eventlog.context(gateway_event_id=42, delivery_id="outer"):
        log.emit("dispatch.queued", work_item="github:o/r#1")
        with eventlog.context(delivery_id="inner"):
            log.emit("dispatch.succeeded")
        log.emit("dispatch.dropped", gateway_event_id=43)  # explicit wins
    log.emit("dispatch.failed")
    rows = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text().splitlines()
    ]
    assert rows[0]["gateway_event_id"] == 42 and rows[0]["delivery_id"] == "outer"
    assert rows[1]["gateway_event_id"] == 42 and rows[1]["delivery_id"] == "inner"
    assert rows[2]["gateway_event_id"] == 43
    assert "gateway_event_id" not in rows[3]


def test_context_is_per_thread(tmp_path):
    import threading

    log = eventlog.EventLog(tmp_path / "events.jsonl", source="test")
    seen = {}

    def other():
        log.emit("dispatch.queued")
        seen["done"] = True

    with eventlog.context(gateway_event_id=1):
        thread = threading.Thread(target=other)
        thread.start()
        thread.join()
    row = json.loads((tmp_path / "events.jsonl").read_text().splitlines()[0])
    assert seen["done"] and "gateway_event_id" not in row
