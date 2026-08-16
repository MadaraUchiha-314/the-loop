"""Integration tests: `GET /api/v1/stream` against a live server (issue-239, T3/T8/T9).

Three of the four decisions in `design.md` are only provable by *observing a stream*:
the `api.request` exclusion, `Last-Event-ID` replay, and the `maxSubscribers` refusal.
Each is a plausible-looking implementation away from being silently wrong, so each gets
a scenario here rather than a unit test over a helper.

**A real server on a loopback port, not `TestClient`.** Starlette's `TestClient` runs the
app and collects the *whole* response body before returning, so against an endless
`text/event-stream` it never returns at all — the first draft of this file hung, and the
testing plan was replanned on the strength of it. Nothing short of a socket proves this
feature: what is asserted here is that headers arrive *before* the body, that frames
arrive one at a time while the connection stays open, and that a second connection is
refused while the first is still held. A buffering client cannot observe any of them.

**Never abandon `iter_text()` on a connection a test still needs.** Breaking out of that
generator closes the response, the server sees a disconnect, and the subscriber is
released — so a later assertion about capacity sees a slot that should have been taken.
Tests that must hold a connection open sleep instead of reading; `_frames` is only for
connections the test is finished with.

Each test boots uvicorn on an ephemeral port against its own state root, so no two share
an event log, a subscriber count or a port.
"""

import contextlib
import json
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest

from the_loop.api.app import create_app
from the_loop.api.stream import TICK_SECONDS
from the_loop.state import layout_from_config

uvicorn = pytest.importorskip("uvicorn", reason="the service extra is not installed")

REF = "github:octo/repo#7"
OTHER = "github:octo/repo#8"


# -- a server, and a way to read frames off it ----------------------------------


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextlib.contextmanager
def _serving(config):
    """Boot the app on a loopback port for the duration of the block.

    ``uvicorn.Server.run`` in a thread rather than a subprocess: the test wants the
    app built from *this* config object, and a subprocess would need it written to
    a file first. ``should_exit`` is uvicorn's own cooperative stop, so an open
    stream connection is cancelled the way a real shutdown cancels one.

    The event log is **configured**, exactly as :func:`the_loop.api.serve.main`
    does. Without it ``eventlog.emit`` is a module-level no-op, so nothing would be
    appended — and the two tests that matter most here (the ``api.request``
    exclusion, and the instrumentation) would pass against an empty file while
    proving nothing at all.
    """
    from the_loop import eventlog

    log = _log_path(config)
    log.parent.mkdir(parents=True, exist_ok=True)
    eventlog.configure("service", path=log)
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(config), host="127.0.0.1", port=port, log_level="warning"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started, "uvicorn did not come up"
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=15)
    try:
        yield client
    finally:
        client.close()
        server.should_exit = True
        thread.join(timeout=10)
        eventlog.reset()


def _config(tmp_path, **stream):
    """A config for one test's own state root.

    ``keepAliveSeconds`` defaults to 1 here, not to the shipped 15: these tests read
    the stream chunk by chunk, and a chunk only arrives when there is something to
    send. At the shipped interval an assertion about *absence* would block for
    fifteen seconds before it could conclude anything.
    """
    config = {"state": {"root": str(tmp_path / ".the-loop")}}
    stream.setdefault("keepAliveSeconds", 1)
    config["service"] = {"stream": stream}
    return config


def _log_path(config) -> Path:
    return Path(layout_from_config(config).event_log)


def _append(config, *records):
    """Append records the way another process would — the poller, or the harness."""
    path = _log_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")


def _frames(response, count, timeout=10.0):
    """Read until ``count`` non-comment frames have arrived, or the timeout passes.

    Parses the SSE wire format by hand rather than through a library: the framing
    *is* part of the contract under test (``id:``, ``event:``, exactly one
    ``data:`` line), so a parser that tolerated a different shape would hide the
    only thing worth asserting.
    """
    frames = []
    buffer = ""
    deadline = time.monotonic() + timeout
    for chunk in response.iter_text():
        buffer += chunk
        while "\n\n" in buffer:
            block, _, buffer = buffer.partition("\n\n")
            parsed = _parse(block)
            if parsed is not None:
                frames.append(parsed)
        if len(frames) >= count or time.monotonic() > deadline:
            break
    return frames


def _parse(block):
    """One SSE block -> ``{"id", "event", "data"}``; ``None`` for a comment or a
    bare ``retry:`` directive."""
    frame = {}
    for line in block.splitlines():
        if not line or line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        frame[field.strip()] = value.strip()
    if "event" not in frame:
        return None
    return {
        "id": frame.get("id"),
        "event": frame["event"],
        "data": json.loads(frame["data"]),
    }


# -- delivery, filtering, framing -----------------------------------------------


def test_an_appended_event_reaches_an_open_subscriber(tmp_path):
    """
    Feature: the control plane learns without asking
      Scenario: an event is appended while a subscriber is connected
        Given an open stream connection
        When another process appends a graph event to the event log
        Then the subscriber receives it as a `log` frame carrying a cursor

    Requirement: docs/specs/issue-239/requirements.md R1.1, R1.2
    """
    config = _config(tmp_path)
    with _serving(config) as client:
        with client.stream("GET", "/api/v1/stream") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers.get("cache-control") == "no-cache"
            # A buffering proxy in front would turn this into a very slow poll.
            assert response.headers.get("x-accel-buffering") == "no"

            time.sleep(TICK_SECONDS * 2)
            _append(config, {"event": "graph.advanced", "work_item": REF, "node": "x"})

            (frame,) = _frames(response, 1)
            assert frame["event"] == "log"
            assert frame["data"]["event"] == "graph.advanced"
            assert frame["data"]["work_item"] == REF
            assert int(frame["id"]) > 0


def test_a_work_item_filter_excludes_another_items_events(tmp_path):
    """
    Feature: a subscriber sees only what it asked for
      Scenario: two work items are active and the subscriber filters to one
        Given a stream opened with workItem=<one ref>
        When events for both refs are appended
        Then only the filtered ref's event arrives

    Requirement: docs/specs/issue-239/requirements.md R1.3
    """
    config = _config(tmp_path)
    with _serving(config) as client:
        with client.stream(
            "GET", "/api/v1/stream", params={"workItem": REF}
        ) as response:
            time.sleep(TICK_SECONDS * 2)
            _append(
                config,
                {"event": "graph.advanced", "work_item": OTHER},
                {"event": "graph.advanced", "work_item": REF},
            )
            (frame,) = _frames(response, 1)
            assert frame["data"]["work_item"] == REF


def test_the_control_planes_own_api_requests_never_reach_the_stream(tmp_path):
    """
    Feature: the stream cannot feed itself
      Scenario: the control plane refreshes while streaming
        Given an open stream connection
        When the client calls other API routes, each of which emits api.request
        Then no frame is delivered for them, and a real event still arrives

    Requirement: docs/specs/issue-239/design.md §Trade-offs

    The failure guarded against is not a wrong frame, it is a system that never
    idles: a refresh emits api.request, which would wake a refresh, which emits
    more. Invisible in review and obvious in production, so it is asserted end to
    end against the real router rather than against the tailer alone.
    """
    from the_loop import eventlog

    config = _config(tmp_path)
    with _serving(config) as client:
        with client.stream("GET", "/api/v1/stream") as response:
            time.sleep(TICK_SECONDS * 2)
            for _ in range(5):
                assert client.get("/api/v1/work-items").status_code == 200
            _append(config, {"event": "graph.advanced", "work_item": REF})

            frames = _frames(response, 1)
            assert [f["data"]["event"] for f in frames] == ["graph.advanced"]

        # The exclusion is only meaningful if the records were really written:
        # without this the test would pass against an empty log.
        written = [r["event"] for r in eventlog.read_events(_log_path(config))]
        assert written.count("api.request") >= 5, written


def test_a_reconnect_with_last_event_id_replays_exactly_the_missed_records(tmp_path):
    """
    Feature: a dropped connection loses nothing
      Scenario: a subscriber reconnects quoting the last frame it saw
        Given a subscriber that received one event and disconnected
        And two further events appended while it was away
        When it reconnects with Last-Event-ID set to that frame's id
        Then it receives exactly the two it missed, and not the one it had

    Requirement: docs/specs/issue-239/requirements.md R1.5
    """
    config = _config(tmp_path)
    with _serving(config) as client:
        with client.stream("GET", "/api/v1/stream") as response:
            time.sleep(TICK_SECONDS * 2)
            _append(config, {"event": "graph.advanced", "work_item": REF, "n": 1})
            (first,) = _frames(response, 1)
        cursor = first["id"]

        _append(
            config,
            {"event": "graph.advanced", "work_item": REF, "n": 2},
            {"event": "graph.advanced", "work_item": REF, "n": 3},
        )

        with client.stream(
            "GET", "/api/v1/stream", headers={"Last-Event-ID": cursor}
        ) as response:
            frames = _frames(response, 2)
            assert [f["data"]["n"] for f in frames] == [2, 3]


def test_an_idle_stream_is_kept_alive(tmp_path):
    """
    Feature: an idle connection is not reaped, and can be told from a dead one
      Scenario: nothing happens on a connected stream
        Given a stream configured to keep alive every second
        When nothing is appended
        Then the connection carries keep-alive comments

    Requirement: docs/specs/issue-239/requirements.md R1.4
    """
    config = _config(tmp_path, keepAliveSeconds=1)
    with _serving(config) as client:
        with client.stream("GET", "/api/v1/stream") as response:
            seen = ""
            deadline = time.monotonic() + 8
            for chunk in response.iter_text():
                seen += chunk
                if ": keep-alive" in seen or time.monotonic() > deadline:
                    break
            assert ": keep-alive" in seen


def test_the_retry_directive_sets_the_browsers_reconnect_delay(tmp_path):
    """``EventSource`` reconnects on its own; without ``retry:`` it picks its own
    interval, which has been as low as half a second."""
    from the_loop.api.stream import RETRY_MS

    with _serving(_config(tmp_path)) as client:
        with client.stream("GET", "/api/v1/stream") as response:
            seen = ""
            deadline = time.monotonic() + 8
            for chunk in response.iter_text():
                seen += chunk
                if "retry:" in seen or time.monotonic() > deadline:
                    break
            assert f"retry: {RETRY_MS}" in seen


# -- capacity and the REST surface (T8) -----------------------------------------


def test_the_rest_surface_still_answers_with_the_stream_at_capacity(tmp_path):
    """
    Feature: watching a work item does not slow down working one
      Scenario: every allowed stream connection is open and idle
        Given maxSubscribers connections held open
        When the CLI calls /api/v1/health and /api/v1/work-items
        Then both answer normally

    Requirement: docs/specs/issue-239/requirements.md R5.1

    The mechanism is that the route is ``async def``: a synchronous generator would
    hold an anyio threadpool slot for the life of each connection. This asserts the
    property, not the mechanism, so a refactor back to ``def`` fails here.
    """
    config = _config(tmp_path, maxSubscribers=2)
    with _serving(config) as client:
        with client.stream("GET", "/api/v1/stream") as one:
            assert one.status_code == 200
            time.sleep(TICK_SECONDS)
            with client.stream("GET", "/api/v1/stream") as two:
                assert two.status_code == 200
                assert client.get("/api/v1/health").status_code == 200
                assert client.get("/api/v1/work-items").status_code == 200


def test_abuse_a_connection_beyond_the_maximum_is_refused(tmp_path):
    """
    Feature: an open dashboard cannot starve the service
      Scenario: more connections are opened than the configuration allows
        Given maxSubscribers is 1 and one connection is open
        When a second is opened
        Then it is refused with 503 and a Retry-After, not accepted and degraded

    Requirement: docs/specs/issue-239/requirements.md R5.2 (abuse case 1)
    """
    config = _config(tmp_path, maxSubscribers=1)
    with _serving(config) as client:
        with client.stream("GET", "/api/v1/stream") as one:
            assert one.status_code == 200
            # Sleep, do not read: reading and breaking out would close this
            # connection and free the very slot the next line asserts is taken.
            time.sleep(TICK_SECONDS * 2)
            refused = client.get("/api/v1/stream")
            assert refused.status_code == 503
            assert refused.headers.get("retry-after")
            assert "maxSubscribers" in refused.json()["detail"]


def test_a_disconnect_releases_the_slot(tmp_path):
    """
    Feature: a closed tab frees its capacity
      Scenario: the only allowed connection is opened and closed
        Given maxSubscribers is 1
        When the first connection closes and another opens
        Then the second is accepted

    Requirement: docs/specs/issue-239/requirements.md R5.4
    """
    config = _config(tmp_path, maxSubscribers=1)
    with _serving(config) as client:
        with client.stream("GET", "/api/v1/stream") as response:
            assert response.status_code == 200
            time.sleep(TICK_SECONDS * 2)

        # The unsubscribe happens as the server finishes the cancelled generator,
        # which is not synchronous with the client's close.
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            with client.stream("GET", "/api/v1/stream") as again:
                if again.status_code == 200:
                    return
            time.sleep(0.2)
        pytest.fail("the slot was never released")


# -- refusals (T9) ---------------------------------------------------------------


def test_abuse_a_malformed_cursor_is_refused_rather_than_ignored(tmp_path):
    """
    Feature: a bad cursor is a caller error, not a silent full replay
      Scenario: Last-Event-ID is not a byte offset
        Given a stream request whose Last-Event-ID is unparseable
        When the service handles it
        Then it answers 400 naming the header, and streams nothing

    Requirement: docs/specs/issue-239/requirements.md R1.5 (abuse case 3)
    """
    with _serving(_config(tmp_path)) as client:
        for bad in ("nonsense", "-1", "1e5", ""):
            response = client.get("/api/v1/stream", headers={"Last-Event-ID": bad})
            assert response.status_code == 400, bad
            assert "Last-Event-ID" in response.json()["detail"]


def test_abuse_a_malformed_filter_is_refused_rather_than_streaming_everything(tmp_path):
    """
    Feature: an unparseable filter never widens to "everything"
      Scenario: the workItem parameter is not a work-item ref
        Given a stream request with workItem=not-a-ref
        When the service handles it
        Then it answers 400 and no connection is opened

    Requirement: docs/specs/issue-239/requirements.md R1.3 (abuse case 3)

    The direction is the point: failing open here would turn a typo into a
    subscription to every work item on the workstation.
    """
    with _serving(_config(tmp_path)) as client:
        for param in ("workItem", "transcript"):
            response = client.get("/api/v1/stream", params={param: "not-a-ref"})
            assert response.status_code == 400, param
            assert "not-a-ref" in response.json()["detail"]


def test_abuse_replay_from_far_behind_is_bounded_and_the_client_is_told(tmp_path):
    """
    Feature: replay cannot be used to read unbounded history
      Scenario: a client resumes from an offset far behind the end of the log
        Given an event log larger than the replay window
        When a client connects with Last-Event-ID 0
        Then it is told to resynchronise instead of being served the history

    Requirement: docs/specs/issue-239/requirements.md R1.5 (abuse case 4)
    """
    config = _config(tmp_path)
    filler = {"event": "session.spawned", "work_item": REF, "pad": "x" * 900}
    _append(config, *[filler] * 400)  # comfortably past REPLAY_BYTES
    with _serving(config) as client:
        with client.stream(
            "GET", "/api/v1/stream", headers={"Last-Event-ID": "0"}
        ) as response:
            (frame,) = _frames(response, 1)
            assert frame["event"] == "desync"
            assert frame["data"]["reason"] == "replay-window"


def test_a_disabled_stream_answers_404(tmp_path):
    """
    Feature: a deployment can narrow itself to REST-only
      Scenario: service.stream.enabled is false
        Given a service with the stream disabled
        When a client connects
        Then it receives 404 and can fall back to polling

    Requirement: docs/specs/issue-239/requirements.md R1.1, R4.1

    Also the stand-in for "a service older than this feature", which answers 404
    for the same route for the same practical reason (testing plan T13).
    """
    with _serving(_config(tmp_path, enabled=False)) as client:
        response = client.get("/api/v1/stream")
        assert response.status_code == 404
        assert "stream" in response.json()["detail"]


# -- observability ---------------------------------------------------------------


def test_the_stream_is_instrumented_like_everything_else(tmp_path):
    """
    Feature: the event log answers "who was watching, and what was refused?"
      Scenario: a connection is opened, a second refused, and the first closed
        Given a service with one allowed connection
        When one client connects, a second is refused, and the first leaves
        Then each is recorded under a type registered in EVENT_TYPES

    Requirement: docs/specs/issue-239/requirements.md §Non-functional (observability)

    The catalog assertion is the one that keeps working: an emission whose type
    nobody registered is invisible to `the-loop events` and to the observability
    reference, which is the bar every other surface here meets.
    """
    from the_loop import eventlog

    config = _config(tmp_path, maxSubscribers=1)
    path = _log_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)

    with _serving(config) as client:
        with client.stream("GET", "/api/v1/stream") as one:
            assert one.status_code == 200
            time.sleep(TICK_SECONDS * 2)
            assert client.get("/api/v1/stream").status_code == 503
        time.sleep(1.5)
        seen = {r["event"] for r in eventlog.read_events(path)}

    for event in ("stream.subscribed", "stream.refused", "stream.disconnected"):
        assert event in seen, f"{event} was never emitted; saw {sorted(seen)}"
        assert event in eventlog.EVENT_TYPES, "an emitted type must be in the catalog"
