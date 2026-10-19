"""Unit tests for the instance's gateway client (issue-496, T1 — R3.1, R3.3, R3.4,
R3.7, R4.2, R4.3, R5.3, R5.5, R14.4), against the real consume API in-process."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pytest

from gateway_support import GatewayHarness
from the_loop.gateway import client as client_mod
from the_loop.gateway.client import GatewayClient
from the_loop.gateway.envelope import Delivery


class Transport:
    """Routes the client's requests into the harness app; can be made to fail."""

    def __init__(self, harness: GatewayHarness):
        self.harness = harness
        self.down = False
        self.calls: List[Tuple[str, str, Optional[Dict[str, Any]]]] = []

    def __call__(self, method, path, body, timeout):
        self.calls.append((method, path, dict(body) if body else None))
        if self.down:
            raise OSError("connection refused")
        response = self.harness.client.request(method, path, json=body)
        return response.status_code, (response.json() if response.content else None)


def _cli_config(tmp_path: Path, **gateway) -> Dict[str, Any]:
    block = {
        "url": "http://127.0.0.1:8790",
        "pollIntervalSeconds": 5,
        "longPollSeconds": 0,
    }
    block.update(gateway)
    return {
        "state": {"root": str(tmp_path / ".the-loop")},
        "instance": {"name": "laptop-a"},
        "gateway": block,
    }


@pytest.fixture()
def gw(tmp_path) -> Iterator[GatewayHarness]:
    harness = GatewayHarness(tmp_path)
    yield harness
    harness.close()


def _client(
    gw, tmp_path, *, dispatch=None, claims=None, sleeps=None, **gateway
) -> Tuple[GatewayClient, Transport]:
    transport = Transport(gw)
    sleeps = sleeps if sleeps is not None else []
    client = GatewayClient(
        _cli_config(tmp_path, **gateway),
        threading.Event(),
        dispatch=dispatch,
        claims=claims,
        transport=transport,
        sleep=sleeps.append,
        rng=lambda: 0.5,
    )
    return client, transport


def test_the_client_registers_actors_and_claims_before_its_first_fetch(gw, tmp_path):
    client, transport = _client(
        gw,
        tmp_path,
        claims=lambda: [("loop-github-o-r-14", "driver")],
        actors={"github": ["octocat"]},
    )
    assert client.step() is True  # empty plain poll → sleep the interval
    paths = [(m, p) for m, p, _ in transport.calls]
    assert paths[:3] == [
        ("PUT", "/api/v1/gateway/actors"),
        ("PUT", "/api/v1/gateway/claims"),
        ("POST", "/api/v1/gateway/fetch"),
    ]
    assert gw.store.instance_for_actor("github", "octocat") == "laptop-a"
    assert [c.instance for c in gw.store.claimants("loop-github-o-r-14")] == [
        "laptop-a"
    ]
    assert client.state == "connected" and gw.events("gateway.connected")


def test_pending_commits_ride_the_next_fetch_with_the_servers_committed_as_cursor(
    gw, tmp_path
):
    seen: List[str] = []
    client, transport = _client(
        gw, tmp_path, dispatch=lambda d: seen.append(d.event.delivery_id) or "spawned"
    )
    gw.append(1, consumers=["laptop-a"])
    gw.append(2, consumers=["laptop-a"])
    assert client.step() is False  # two deliveries dispatched: no interval sleep
    assert seen == ["d-1", "d-2"]
    fetch_bodies = [
        b for m, p, b in transport.calls if p.endswith("/fetch") and b is not None
    ]
    assert fetch_bodies[0]["commit"] == [] and fetch_bodies[0]["cursor"] == 0
    client.step()
    fetch_bodies = [
        b for m, p, b in transport.calls if p.endswith("/fetch") and b is not None
    ]
    assert [c["outcome"] for c in fetch_bodies[1]["commit"]] == ["spawned", "spawned"]
    assert (
        fetch_bodies[1]["cursor"] == 0
    )  # the server's committed before the commit was applied
    assert client.committed == fetch_bodies[1]["commit"][-1]["seq"]
    assert gw.store.committed("laptop-a") == client.committed
    assert len(gw.events("subject.committed")) == 2


def test_the_interval_is_slept_after_an_empty_plain_poll_and_never_after_a_long_poll(
    gw, tmp_path
):
    sleeps: List[float] = []
    client, _ = _client(
        gw, tmp_path, sleeps=sleeps, longPollSeconds=0, pollIntervalSeconds=7
    )
    assert client.step() is True
    client2, _ = _client(gw, tmp_path, longPollSeconds=1)
    gw.config  # the harness clamps wait to 5 s; 1 s here
    assert client2.step() is False  # the long-poll already waited


def test_a_failed_dispatch_leaves_the_delivery_pending_and_it_comes_back_with_attempt_two(
    gw, tmp_path
):
    attempts: List[int] = []

    def flaky(delivery: Delivery) -> str:
        attempts.append(delivery.attempt)
        if delivery.attempt == 1:
            raise RuntimeError("boom")
        return "delivered"

    client, _ = _client(gw, tmp_path, dispatch=flaky)
    gw.append(1, consumers=["laptop-a"])
    client.step()
    client.step()
    assert attempts == [1, 2]
    client.step()
    assert gw.store.committed("laptop-a") > 0
    assert gw.events("subject.redelivered")


def test_stop_flushes_the_pending_commits(gw, tmp_path):
    client, transport = _client(gw, tmp_path)
    gw.append(1, consumers=["laptop-a"])
    client.step()
    assert gw.store.committed("laptop-a") == 0
    assert client.flush() is True
    assert gw.store.committed("laptop-a") > 0
    assert any(p.endswith("/commit") for _, p, _ in transport.calls)


def test_the_peer_id_is_persisted_and_the_same_instance_restarting_is_not_refused(
    gw, tmp_path
):
    first, _ = _client(gw, tmp_path)
    first.step()
    assert (
        json.loads(
            (tmp_path / ".the-loop" / "local" / client_mod.PEER_FILE).read_text()
        )["peer"]
        == first.peer
    )
    again, _ = _client(gw, tmp_path)
    assert again.peer == first.peer
    assert again.step() is True and again.state == "connected"


def test_a_second_peer_under_the_name_is_refused_and_retried_on_the_backoff_schedule(
    gw, tmp_path
):
    """
    Feature: one queue, one poller (abuse case 4)
      Scenario: a second peer under the same instance name is refused while the first polls
    """
    first, _ = _client(gw, tmp_path)
    first.step()
    other_root = tmp_path / "other"
    other_root.mkdir()
    transport = Transport(gw)
    second = GatewayClient(
        _cli_config(other_root),
        threading.Event(),
        transport=transport,
        sleep=lambda s: None,
        rng=lambda: 0.5,
    )
    assert second.peer != first.peer
    assert second.step() is False
    assert second.state == "refused" and second.refused_by == first.peer
    assert second.last_error == "duplicate-instance"
    refusals = [
        r for r in gw.events("gateway.refused") if r["reason"] == "duplicate-instance"
    ]
    assert refusals and refusals[-1]["holder"] == first.peer
    waits = [second._backoff() for _ in range(8)]
    assert waits[0] == 1.0 and waits[-1] == 60.0 and waits == sorted(waits)
    assert first.step() is True  # the holder keeps polling


def test_an_outage_is_recorded_once_and_recovery_re_registers(gw, tmp_path):
    client, transport = _client(gw, tmp_path, actors={"slack": ["U1"]})
    client.step()
    transport.down = True
    for _ in range(3):
        assert client.step() is False
    assert client.state == "unreachable" and len(gw.events("gateway.unreachable")) == 1
    transport.down = False
    before = len(transport.calls)
    client.step()
    assert client.state == "connected" and len(gw.events("gateway.connected")) == 2
    after_recovery = [
        p for _, p, _ in transport.calls[before:] if p.endswith("/actors")
    ]
    assert after_recovery == ["/api/v1/gateway/actors"]  # registered again, first thing


def test_a_duplicate_actor_is_refused_and_the_client_keeps_retrying(gw, tmp_path):
    gw.fetch("laptop-b", peer="pb", lease=60)
    gw.register("laptop-b", {"github": ["octocat"]}, peer="pb")
    client, transport = _client(gw, tmp_path, actors={"github": ["octocat"]})
    assert client.step() is False
    assert (
        client.state == "refused"
        and client.last_error == "duplicate-actor"
        and client.refused_by == "laptop-b"
    )
    assert not any(p.endswith("/fetch") for _, p, _ in transport.calls)


def test_the_document_describes_the_client_for_the_dashboard(gw, tmp_path):
    client, _ = _client(gw, tmp_path, claims=lambda: [("loop-x", "reviewer")])
    doc = client.document()
    assert doc["state"] == "off" and doc["configured"] and doc["instance"] == "laptop-a"
    client.step()
    doc = client.document()
    assert doc["state"] == "connected" and doc["health"]["ok"] is True
    assert doc["queue"]["instance"] == "laptop-a" and doc["claims"] == [
        {"subject": "loop-x", "role": "reviewer"}
    ]
    assert doc["mode"] == {"pollIntervalSeconds": 5, "longPollSeconds": 0}


def test_run_loops_until_stopped_and_flushes(gw, tmp_path):
    sleeps: List[float] = []
    client, _ = _client(gw, tmp_path, sleeps=sleeps)
    gw.append(1, consumers=["laptop-a"])
    stop = client.stop_event

    def stop_after_two_fetches():
        while client.fetches < 2:
            pass
        stop.set()

    threading.Thread(target=stop_after_two_fetches, daemon=True).start()
    assert client.run() == 0
    assert client.state == "off" and gw.store.committed("laptop-a") > 0


def test_a_config_without_a_gateway_block_is_refused():
    with pytest.raises(ValueError):
        GatewayClient({"instance": {"name": "x"}}, threading.Event())


def test_a_delivery_whose_dispatch_is_in_flight_is_not_fetched_again(gw, tmp_path):
    """
    Feature: the gateway client consumes one queue
      Scenario: a delivery whose dispatch is in flight is not fetched again
        Given a dispatch that answers Deferred while a resume is spawning
        When the client polls again before it settles
        Then the cursor runs past the held delivery, it is dispatched once, nothing is
             redelivered, and once the dispatch settles the outcome is committed

    Requirement: docs/specs/issue-496/requirements.md#requirement-3 (R3.4), R12.4
    """
    from the_loop.gateway.client_dispatch import Deferred

    seen: List[str] = []
    settled: Dict[str, Optional[str]] = {"outcome": None}

    def dispatch(delivery: Delivery):
        seen.append(delivery.event.delivery_id)
        return Deferred(delivery.event.delivery_id, lambda: settled["outcome"], 0.0)

    client, transport = _client(gw, tmp_path, dispatch=dispatch)
    gw.append(1, consumers=["laptop-a"])
    client.step()
    client.step()
    client.step()
    assert seen == ["d-1"] and client.deferred == 1
    fetch_bodies = [
        b for m, p, b in transport.calls if p.endswith("/fetch") and b is not None
    ]
    assert [b["cursor"] for b in fetch_bodies] == [0, 1, 1]
    assert not gw.events("subject.redelivered")
    assert gw.store.queue("laptop-a").backlog == 1
    settled["outcome"] = "spawned"
    client.step()
    assert client.deferred == 0 and gw.store.queue("laptop-a").backlog == 0
    assert gw.store.committed("laptop-a") == 1
    fourth = [
        b for m, p, b in transport.calls if p.endswith("/fetch") and b is not None
    ][3]
    # settled: it rides as a commit, and the cursor is back on the server's committed
    assert (
        fourth["commit"] == [{"seq": 1, "outcome": "spawned"}] and fourth["cursor"] == 0
    )
    assert not gw.events("subject.redelivered")
