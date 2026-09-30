"""Unit tests for the fleet (issue-374, T1, T7, T8).

Probe states and their transitions, the cache and its interval, the bounded fan-out
with a hung member, the three resolvers (one, none, several, explicit `instance`),
member error translation, and the size / shape bounds on a member's answer — all
over an injected transport, so nothing here opens a socket.

Spec: docs/specs/issue-374/design.md §3.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List

import pytest

from the_loop.api.errors import Conflict, MemberUnavailable
from the_loop.instance import Member
from the_loop.manager import fleet as fleet_mod
from the_loop.manager.fleet import (
    LIVE,
    MAX_MEMBER_BODY,
    MISMATCHED,
    UNREACHABLE,
    Fleet,
    TransportError,
)

A = "http://a:1"
B = "http://b:1"


def _config(members, **manager):
    return {
        "instance": {
            "name": "hq",
            "role": "manager",
            "manager": {
                "instances": [{"name": n, "url": u} for n, u in members],
                "timeoutSeconds": manager.get("timeout", 1),
                "probeIntervalSeconds": manager.get("interval", 15),
            },
        }
    }


class FakeTransport:
    """A member per URL: `routes[url][path] -> (status, json-able) | callable`."""

    def __init__(self):
        self.routes: Dict[str, Dict[str, Any]] = {}
        self.calls: List[tuple] = []

    def member(self, url, name, role="worker", managed=(), version="1.0", standing=()):
        self.routes[url] = {
            "/api/v1/instance": (
                200,
                {
                    "name": name,
                    "role": role,
                    "scope": {"mode": "addressed", "workItems": []},
                    "managed": [
                        {"ref": ref, "sources": ["control"]} for ref in managed
                    ],
                    "sessionCount": 1,
                },
            ),
            "/api/v1/health": (200, {"status": "ok", "version": version}),
            "/api/v1/standing-sessions": (200, [{"name": n} for n in standing]),
        }
        return self

    def __call__(self, method, url, body, timeout):
        self.calls.append((method, url, body, timeout))
        base, _, rest = url.partition("/api/v1")
        path = "/api/v1" + rest.split("?", 1)[0]
        routes = self.routes.get(base)
        if routes is None:
            raise TransportError("connection refused")
        answer = routes.get(path)
        if answer is None:
            return 404, json.dumps({"detail": f"no route {path}"}).encode()
        if callable(answer):
            answer = answer(method, url, body, timeout)
        assert isinstance(answer, tuple)
        status, payload = answer
        if isinstance(payload, (bytes, bytearray)):
            return status, bytes(payload)
        return status, json.dumps(payload).encode()


@pytest.fixture
def quiet(monkeypatch):
    emitted = []
    monkeypatch.setattr(
        fleet_mod.eventlog, "emit", lambda *a, **k: emitted.append((a[0], k))
    )
    return emitted


def _fleet(transport, members, clock=None, **manager):
    config = _config(members, **manager)
    kwargs = {"transport": transport}
    if clock is not None:
        kwargs["clock"] = clock
    return Fleet(
        lambda: config,
        local_refs=lambda: ["github:octo/repo#1"],
        local_standing=lambda: ["pr-shepherd"],
        **kwargs,
    )


# -- the probe --------------------------------------------------------------------


def test_a_member_answering_to_its_name_is_live(quiet):
    transport = FakeTransport().member(A, "laptop-a", managed=["github:octo/repo#15"])
    fleet = _fleet(transport, [("laptop-a", A)])
    probe = fleet.probe(Member("laptop-a", A))
    assert probe.state == LIVE and probe.live
    assert probe.version == "1.0"
    row = probe.row()
    assert row["name"] == "laptop-a" and row["url"] == A and row["state"] == "live"
    assert (
        row["mode"] == "addressed"
        and row["managedCount"] == 1
        and row["sessionCount"] == 1
    )
    assert "detail" not in row
    # No transition from nothing to live is announced: it is the expected state.
    assert quiet == []


@pytest.mark.parametrize(
    "name, role, needle",
    [
        ("someone-else", "worker", "answers as someone-else"),
        ("", "worker", "(unnamed)"),
        ("laptop-a", "manager", "role 'manager'"),
    ],
)
def test_a_member_answering_as_another_name_or_a_manager_is_mismatched(
    quiet, name, role, needle
):
    """R6.1, abuse case 2: nothing is served from it or sent to it."""
    transport = FakeTransport().member(A, name, role=role)
    fleet = _fleet(transport, [("laptop-a", A)])
    probe = fleet.probe(Member("laptop-a", A))
    assert probe.state == MISMATCHED
    assert needle in probe.detail
    assert probe.row()["detail"] == probe.detail and probe.row()["managedCount"] == 0
    assert [e for e, k in quiet] == ["instance.mismatched"]
    assert quiet[0][1]["instance"] == "laptop-a"
    with pytest.raises(MemberUnavailable):
        fleet.call(Member("laptop-a", A), "GET", "/api/v1/work-items", expect=list)
    # Only the probe reached it: never the operation.
    assert all("/api/v1/instance" in url for _, url, _, _ in transport.calls)


def test_an_unreachable_member_is_unreachable_once_and_recovers_once(quiet):
    """R3.4: one event per transition."""
    transport = FakeTransport()
    now = [0.0]
    fleet = _fleet(transport, [("laptop-a", A)], clock=lambda: now[0], interval=5)
    member = Member("laptop-a", A)
    assert fleet.probe(member).state == UNREACHABLE
    now[0] += 10
    assert fleet.probe(member).state == UNREACHABLE
    assert [e for e, k in quiet] == ["instance.unreachable"]
    assert quiet[0][1]["level"] == "error"
    transport.member(A, "laptop-a")
    now[0] += 10
    assert fleet.probe(member).state == LIVE
    assert [e for e, k in quiet] == ["instance.unreachable", "instance.recovered"]


def test_the_probe_is_cached_for_the_interval(quiet):
    transport = FakeTransport().member(A, "laptop-a")
    now = [0.0]
    fleet = _fleet(transport, [("laptop-a", A)], clock=lambda: now[0], interval=15)
    member = Member("laptop-a", A)
    fleet.probe(member)
    calls = len(transport.calls)
    now[0] += 5
    fleet.probe(member)
    assert len(transport.calls) == calls
    now[0] += 11
    fleet.probe(member)
    assert len(transport.calls) > calls
    fleet.probe(member, fresh=True)
    assert len(transport.calls) > calls + 1


def test_a_member_with_no_role_field_probes_as_a_worker(quiet):
    """A 19.14.1 member carries no `role`; absent reads as worker (T10)."""
    transport = FakeTransport()
    transport.routes[A] = {
        "/api/v1/instance": (
            200,
            {
                "name": "laptop-a",
                "scope": {"mode": "open", "workItems": []},
                "managed": [],
            },
        ),
        "/api/v1/health": (200, {"version": "19.14.1"}),
    }
    fleet = _fleet(transport, [("laptop-a", A)])
    assert fleet.probe(Member("laptop-a", A)).live


def test_the_local_member_is_always_live_and_first(quiet):
    fleet = _fleet(FakeTransport(), [])
    assert fleet.local == Member("hq", "")
    assert fleet.probe(fleet.local).live
    assert fleet.is_local(fleet.local)


# -- one request, and its bounds -------------------------------------------------------


def test_a_members_error_is_the_managers_error(quiet):
    transport = FakeTransport().member(A, "laptop-a")
    transport.routes[A]["/api/v1/x400"] = (400, {"detail": "bad ref"})
    transport.routes[A]["/api/v1/x404"] = (404, {"detail": "no session"})
    transport.routes[A]["/api/v1/x409"] = (
        409,
        {"detail": "two", "candidates": ["p", "q"]},
    )
    transport.routes[A]["/api/v1/x500"] = (500, {"detail": "boom"})
    fleet = _fleet(transport, [("laptop-a", A)])
    member = Member("laptop-a", A)
    with pytest.raises(ValueError, match="bad ref"):
        fleet.call(member, "GET", "/api/v1/x400")
    with pytest.raises(LookupError, match="no session"):
        fleet.call(member, "GET", "/api/v1/x404")
    with pytest.raises(Conflict) as excinfo:
        fleet.call(member, "GET", "/api/v1/x409")
    assert excinfo.value.candidates == ("p", "q")
    with pytest.raises(MemberUnavailable, match="boom"):
        fleet.call(member, "GET", "/api/v1/x500")


@pytest.mark.parametrize(
    "payload, reason",
    [
        (b"x" * (MAX_MEMBER_BODY + 1), "body exceeds the bound"),
        (b"{not json", "not JSON"),
        (json.dumps({"a": 1}).encode(), "not a JSON list"),
    ],
)
def test_a_malformed_member_answer_is_dropped_and_the_rest_served(
    quiet, payload, reason
):
    """R6.4, abuse case 3: never crash, never hang, never pass the body on."""
    transport = FakeTransport().member(A, "laptop-a").member(B, "ci-box")
    transport.routes[A]["/api/v1/work-items"] = (200, payload)
    transport.routes[B]["/api/v1/work-items"] = (200, [{"ref": "github:octo/repo#2"}])
    fleet = _fleet(transport, [("laptop-a", A), ("ci-box", B)])
    with pytest.raises(MemberUnavailable):
        fleet.call(Member("laptop-a", A), "GET", "/api/v1/work-items", expect=list)
    malformed = [k for e, k in quiet if e == "instance.malformed"]
    assert (
        malformed
        and malformed[0]["instance"] == "laptop-a"
        and malformed[0]["reason"] == reason
    )
    answers, left_out = fleet.fan_out("GET", "/api/v1/work-items", expect=list)
    assert answers == {"ci-box": [{"ref": "github:octo/repo#2"}]}
    assert left_out == ["laptop-a"]


def test_nothing_of_the_caller_is_forwarded(quiet):
    """Abuse case 1: a request is built from the operation's arguments alone."""
    transport = FakeTransport().member(A, "laptop-a")
    transport.routes[A]["/api/v1/sessions/one"] = (200, {"ref": "github:octo/repo#2"})
    fleet = _fleet(transport, [("laptop-a", A)])
    fleet.call(
        Member("laptop-a", A),
        "GET",
        "/api/v1/sessions/one",
        query={"ref": "github:octo/repo#2", "instance": ""},
    )
    method, url, body, timeout = transport.calls[-1]
    assert url == A + "/api/v1/sessions/one?ref=github%3Aocto%2Frepo%232"
    assert body is None and timeout == 1


# -- fan-out ------------------------------------------------------------------------------


def test_fan_out_is_the_union_of_the_live_members_and_names_the_rest(quiet):
    transport = FakeTransport().member(A, "laptop-a").member(B, "ci-box")
    transport.routes[A]["/api/v1/sessions"] = (200, [{"ref": "r1"}])
    transport.routes[B]["/api/v1/sessions"] = (200, [{"ref": "r2"}])
    fleet = _fleet(
        transport, [("laptop-a", A), ("ci-box", B), ("cloud-1", "http://c:1")]
    )
    answers, left_out = fleet.fan_out("GET", "/api/v1/sessions", expect=list)
    assert answers == {"laptop-a": [{"ref": "r1"}], "ci-box": [{"ref": "r2"}]}
    assert left_out == ["cloud-1"]
    assert [e for e, k in quiet if e == "aggregate.partial"]


def test_a_hung_member_costs_at_most_the_timeout_and_is_bounded(quiet):
    """Abuse case 4, T7: one hung member does not hold the others."""
    transport = FakeTransport().member(A, "laptop-a").member(B, "ci-box")
    release = threading.Event()

    def hang(method, url, body, timeout):
        release.wait(timeout=10)
        return 200, []

    transport.routes[A]["/api/v1/work-items"] = hang
    transport.routes[B]["/api/v1/work-items"] = (200, [{"ref": "r2"}])
    fleet = _fleet(transport, [("laptop-a", A), ("ci-box", B)], timeout=1)
    started = time.monotonic()
    answers, left_out = fleet.fan_out("GET", "/api/v1/work-items", expect=list)
    elapsed = time.monotonic() - started
    release.set()
    assert answers == {"ci-box": [{"ref": "r2"}]}
    assert left_out == ["laptop-a"]
    assert elapsed < 4
    assert fleet.probe(Member("laptop-a", A)).state == UNREACHABLE


# -- the resolvers ------------------------------------------------------------------------


def test_by_instance_resolves_own_registered_and_unknown_names(quiet):
    transport = FakeTransport().member(A, "laptop-a")
    fleet = _fleet(transport, [("laptop-a", A)])
    assert fleet.by_instance("") == fleet.local
    assert fleet.by_instance("hq") == fleet.local
    assert fleet.by_instance("laptop-a") == Member("laptop-a", A)
    with pytest.raises(LookupError):
        fleet.by_instance("nobody")
    assert transport.calls == []  # abuse case 6: nothing sent anywhere


def test_by_ref_routes_to_the_one_instance_that_manages_it(quiet):
    transport = (
        FakeTransport()
        .member(A, "laptop-a", managed=["github:octo/repo#15"])
        .member(B, "ci-box", managed=["github:octo/repo#16"])
    )
    fleet = _fleet(transport, [("laptop-a", A), ("ci-box", B)])
    assert fleet.by_ref("github:octo/repo#15") == Member("laptop-a", A)
    assert fleet.by_ref("github:octo/repo#16") == Member("ci-box", B)
    assert fleet.by_ref("github:octo/repo#1") == fleet.local
    with pytest.raises(LookupError):
        fleet.by_ref("github:octo/repo#99")
    assert fleet.by_ref("github:octo/repo#99", instance="ci-box") == Member("ci-box", B)


def test_an_ambiguous_ref_is_refused_not_sent_twice(quiet):
    """R2.4, abuse case 5."""
    transport = (
        FakeTransport()
        .member(A, "laptop-a", managed=["github:octo/repo#15"])
        .member(B, "ci-box", managed=["github:octo/repo#15"])
    )
    fleet = _fleet(transport, [("laptop-a", A), ("ci-box", B)])
    with pytest.raises(Conflict) as excinfo:
        fleet.by_ref("github:octo/repo#15")
    assert excinfo.value.candidates == ("laptop-a", "ci-box")
    assert fleet.by_ref("github:octo/repo#15", instance="laptop-a") == Member(
        "laptop-a", A
    )


def test_by_standing_name_routes_and_refuses_ambiguity(quiet):
    transport = (
        FakeTransport()
        .member(A, "laptop-a", standing=["nightly"])
        .member(B, "ci-box", standing=["nightly", "other"])
    )
    fleet = _fleet(transport, [("laptop-a", A), ("ci-box", B)])
    assert fleet.by_standing_name("other") == Member("ci-box", B)
    assert fleet.by_standing_name("pr-shepherd") == fleet.local
    with pytest.raises(Conflict):
        fleet.by_standing_name("nightly")
    with pytest.raises(LookupError):
        fleet.by_standing_name("nobody")


def test_rows_and_from_config(quiet):
    transport = FakeTransport().member(A, "laptop-a")
    fleet = Fleet.from_config(
        _config([("laptop-a", A), ("cloud-1", "http://c:1")]), transport=transport
    )
    rows = fleet.rows()
    assert [(r["name"], r["state"]) for r in rows] == [
        ("laptop-a", "live"),
        ("cloud-1", "unreachable"),
    ]
    assert rows[1]["detail"] == "connection refused"
    assert fleet.own_name == "hq"


# -- the real transport: no redirects -----------------------------------------------


def test_the_transport_never_follows_a_redirect():
    """Security review (Low): a member's 3xx is its answer, never a new address."""
    import http.server
    import threading

    from the_loop.manager.fleet import urllib_transport

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — stdlib naming
            if self.path.startswith("/api/v1/instance"):
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:1/api/v1/instance")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, format, *args):  # noqa: A002 — stdlib signature
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        status, body = urllib_transport(
            "GET", f"http://127.0.0.1:{port}/api/v1/instance", None, 3
        )
        assert status == 302
        status, body = urllib_transport("GET", f"http://127.0.0.1:{port}/x", None, 3)
        assert status == 200 and json.loads(body) == {"ok": True}
    finally:
        server.shutdown()


def test_by_ref_re_probes_once_before_answering_nobody(quiet):
    """Self-review: a cached probe may predate the member taking the work item."""
    transport = FakeTransport().member(A, "laptop-a", managed=[])
    now = [0.0]
    fleet = _fleet(transport, [("laptop-a", A)], clock=lambda: now[0], interval=60)
    fleet.probe(Member("laptop-a", A))  # cached: manages nothing
    transport.member(
        A, "laptop-a", managed=["github:octo/repo#15"]
    )  # then it takes #15
    assert fleet.by_ref("github:octo/repo#15") == Member("laptop-a", A)
    with pytest.raises(LookupError):
        fleet.by_ref("github:octo/repo#99")


def test_a_member_answering_an_http_error_is_mismatched_not_a_raised_probe(quiet):
    """Self-review round 2: any other app at the address is 'not this instance'."""
    transport = FakeTransport()
    transport.routes[A] = {
        "/api/v1/health": (200, {"version": "x"})
    }  # no /instance route → 404
    fleet = _fleet(transport, [("laptop-a", A)])
    rows = fleet.rows()  # must not raise
    assert rows[0]["state"] == MISMATCHED
    assert "does not answer as a the-loop instance" in rows[0]["detail"]


def test_a_one_shot_fleet_announces_nothing(quiet):
    """Self-review round 2: `status` must not record a transition on every run."""
    fleet = Fleet.from_config(
        _config([("cloud-1", "http://c:1")]), transport=FakeTransport()
    )
    fleet.rows()
    fleet.rows()
    assert quiet == []
