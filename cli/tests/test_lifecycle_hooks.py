"""Lifecycle hooks — the declaration, the loader, the dispatch, the shipped forwarder
and the event-log seam (issue-344).

Every test writes the module it declares under ``tmp_path`` and builds a runtime
against it; nothing reaches the network except a local ``http.server`` the forwarder
tests start on an ephemeral port. Asynchronous tests wait on ``drain()`` — the
outcome — never on a sleep (decision-091).

The negatives are the point: a lifecycle hook runs inside the-loop's process, so what
it may NOT do is what the design is — stop the-loop, feed the system, move the graph,
load from outside the config directory, or silently not run.
"""

from __future__ import annotations

import http.server
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from the_loop import eventlog
from the_loop import lifecycle_hooks as lh
from the_loop.graph import extensions


REAL_CONFIGURE_FROM_FILE = eventlog.configure_from_file

#: A hook that appends what it saw to the file its params name — the side channel
#: a test reads, because the module runs under a synthetic name on another thread.
SEEN_MODULE = """
import json
from the_loop.graph import HookResult, hook


@hook("x-seen")
def seen(event):
    with open(event.params["out"], "a") as handle:
        handle.write(json.dumps({
            "event": event.event, "tag": event.params.get("tag"),
            "fields": dict(event.fields), "work_item": event.work_item,
            "instance": event.instance,
        }) + "\\n")
    return HookResult.ok("x-seen")
"""

RAISING_MODULE = """
from the_loop.graph import hook


@hook("x-boom")
def boom(event):
    raise RuntimeError("boom")
"""

BLOCKING_MODULE = """
from the_loop.graph import HookResult, Message, hook


@hook("x-veto")
def veto(event):
    return HookResult.blocked("x-veto", [Message(text="no")], outcome="changes-requested")


@hook("x-approve")
def approve(event):
    return HookResult.ok("x-approve", outcome="approved")


@hook("x-chatty")
def chatty(event):
    return HookResult(status="pass", hook="x-chatty", messages=[Message(text="chatty")])
"""

EMITTING_MODULE = """
import json
from the_loop import eventlog
from the_loop.graph import HookResult, hook


@hook("x-emits")
def emits(event):
    with open(event.params["out"], "a") as handle:
        handle.write(event.event + "\\n")
    eventlog.emit("session.closed", work_item="github:o/r#1")
    return None
"""


@pytest.fixture(autouse=True)
def _clean():
    extensions.clear_module_cache()
    lh.reset()
    yield
    lh.reset()
    extensions.clear_module_cache()


def _config_dir(tmp_path: Path, body: str = SEEN_MODULE, name: str = "mine.py") -> Path:
    (tmp_path / "hooks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "hooks" / name).write_text(body)
    return tmp_path


def _declaration(**block: Any) -> lh.Declaration:
    return lh.read_declaration({"hooks": block})


def _runtime(root: Path, capacity: int = 1024, **block: Any) -> lh.LifecycleHooks:
    return lh.LifecycleHooks(_declaration(**block), root, "inst", capacity).load()


def _record(event: str, **fields: Any) -> Dict[str, Any]:
    out = {
        "ts": "2026-09-12T00:00:00.000Z",
        "source": "t",
        "event": event,
        "level": "info",
        "pid": 1,
    }
    out.update(fields)
    return out


def _lines(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _log(tmp_path: Path) -> Path:
    path = tmp_path / "events.jsonl"
    eventlog.configure("t", path=path)
    return path


def _events(path: Path, *types: str) -> List[Dict[str, Any]]:
    return list(eventlog.read_events(path, types=list(types)))


# -- declaration ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "config", [{}, {"hooks": {}}, {"hooks": None}, "not a mapping"]
)
def test_declaration_absent_block_is_empty(config):
    assert lh.read_declaration(config).empty


def test_declaration_reads_a_bare_yaml_on_key():
    """YAML 1.1 parses an unquoted `on:` key as True; the declaration must not care."""
    parsed = _declaration(lifecycle=[{"hook": "x-a", True: "graph.advanced"}])
    assert parsed.attachments[0].patterns == ("graph.advanced",)


def test_declaration_on_accepts_a_string_or_a_list():
    one = _declaration(lifecycle=[{"hook": "x-a", "on": "session.spawned"}])
    many = _declaration(
        lifecycle=[{"hook": "x-a", "on": ["session.spawned", "graph.*"]}]
    )
    assert one.attachments[0].events == ("session.spawned",)
    assert "graph.advanced" in many.attachments[0].events
    assert many.attachments[0].patterns == ("session.spawned", "graph.*")


@pytest.mark.parametrize(
    "block, fragment",
    [
        ([], "must be a mapping"),
        ({"lifecycle": {"hook": "x-a"}}, "must be a list"),
        ({"lifecycle": ["x-a"]}, "must be a mapping of `hook`, `on`"),
        ({"lifecycle": [{"on": "session.spawned"}]}, "needs a `hook`"),
        ({"lifecycle": [{"hook": "x-a"}]}, "needs `on`"),
        ({"lifecycle": [{"hook": "x-a", "on": ""}]}, "needs `on`"),
        (
            {"lifecycle": [{"hook": "x-a", "on": ["session.spawned", " "]}]},
            "empty `on`",
        ),
        (
            {"lifecycle": [{"hook": "x-a", "on": "session.spawned", "with": 3}]},
            "`with` that is not a mapping",
        ),
        ({"modules": ["hooks/mine.py"]}, "never a bare string"),
        ({"modules": [{"path": "a.py", "module": "b"}]}, "exactly one of"),
        ({"attach": []}, "unknown key"),
    ],
)
def test_declaration_refuses_malformed_shapes(block, fragment):
    with pytest.raises(lh.HooksConfigError, match=fragment):
        lh.read_declaration({"hooks": block})


def test_declaration_refuses_a_name_neither_x_nor_shipped():
    with pytest.raises(lh.HooksConfigError, match="forward-event") as excinfo:
        _declaration(lifecycle=[{"hook": "licence-header", "on": "graph.*"}])
    assert "x-<something>" in str(excinfo.value)


def test_declaration_expands_patterns_against_the_catalog_at_parse():
    everything = _declaration(lifecycle=[{"hook": "x-a", "on": "*"}]).attachments[0]
    assert set(everything.events) == set(lh.attach_points())
    assert everything.events == tuple(sorted(everything.events))
    graph = _declaration(lifecycle=[{"hook": "x-a", "on": "graph.*"}]).attachments[0]
    assert graph.events and all(e.startswith("graph.") for e in graph.events)
    twice = _declaration(
        lifecycle=[{"hook": "x-a", "on": ["graph.*", "graph.advanced"]}]
    )
    assert twice.attachments[0].events.count("graph.advanced") == 1


def test_a_pattern_matching_nothing_fails_the_load():
    """A8: a typo in a telemetry declaration surfaces at load, not on the day it is missed."""
    with pytest.raises(
        lh.HooksConfigError, match="'sessoin.spawned' matches no event type"
    ):
        _declaration(lifecycle=[{"hook": "x-a", "on": "sessoin.spawned"}])


@pytest.mark.parametrize("pattern", ["hooks.failed", "hooks.*", "hooks.dropped"])
def test_hooks_events_are_never_attach_points(pattern):
    """A4: the hook system's own domain is not in the universe, so it cannot be named."""
    assert not any(name.startswith("hooks.") for name in lh.attach_points())
    with pytest.raises(lh.HooksConfigError, match="matches no event type"):
        _declaration(lifecycle=[{"hook": "x-a", "on": pattern}])
    assert (
        "hooks.failed" in eventlog.EVENT_TYPES
    )  # catalogued, deliberately unattachable


@pytest.mark.parametrize(
    "params, fragment",
    [
        ({}, "needs `with: {url"),
        ({"url": "file:///etc/passwd"}, "must be http or https"),
        ({"url": "ftp://x/y"}, "must be http or https"),
        ({"url": "telemetry.example/x"}, "must be http or https"),
        ({"url": "https://x/y", "tokenEnv": 3}, "`tokenEnv` must be the NAME"),
        ({"url": "https://x/y", "tokenEnv": ""}, "`tokenEnv` must be the NAME"),
        ({"url": "https://x/y", "headers": ["a"]}, "`headers` must be a mapping"),
        ({"url": "https://x/y", "headers": {"a": 1}}, "`headers` must be a mapping"),
        ({"url": "https://x/y", "timeoutSeconds": 0}, "positive number"),
        ({"url": "https://x/y", "timeoutSeconds": True}, "positive number"),
    ],
)
def test_forward_event_refuses_bad_params_at_load(params, fragment):
    """A7 among them: only http/https leave the process, checked before any import."""
    with pytest.raises(lh.HooksConfigError, match=fragment):
        _declaration(
            lifecycle=[{"hook": "forward-event", "on": "work_item.*", "with": params}]
        )


def test_forward_event_refuses_a_non_http_url_at_load():
    with pytest.raises(lh.HooksConfigError, match="never a file"):
        lh.validate_forward({"url": "file:///tmp/x"})


def test_digest_changes_with_the_declaration():
    a = _declaration(lifecycle=[{"hook": "x-a", "on": "graph.*"}])
    b = _declaration(lifecycle=[{"hook": "x-a", "on": "graph.*", "with": {"k": 1}}])
    assert (
        a.digest() != b.digest()
        and a.digest()
        == _declaration(lifecycle=[{"hook": "x-a", "on": "graph.*"}]).digest()
    )


# -- loading ---------------------------------------------------------------------


def test_load_resolves_a_path_against_the_config_directory(tmp_path):
    root = _config_dir(tmp_path)
    rt = _runtime(
        root,
        modules=[{"path": "hooks/mine.py"}],
        lifecycle=[{"hook": "x-seen", "on": "session.*"}],
    )
    assert "x-seen" in rt.table
    assert "session.spawned" in rt.events and all(
        e.startswith("session.") for e in rt.events
    )


def test_a_path_escaping_the_config_directory_is_refused(tmp_path):
    """A2: absolute, ``..`` and a symlink out are the same defect with the same answer."""
    root = _config_dir(tmp_path / "cfg")
    outside = tmp_path / "outside.py"
    outside.write_text(SEEN_MODULE)
    (root / "hooks" / "link.py").symlink_to(outside)
    for raw in (str(outside), "../outside.py", "hooks/link.py"):
        with pytest.raises(lh.HooksConfigError, match="the CLI config's directory"):
            _runtime(
                root, modules=[{"path": raw}], lifecycle=[{"hook": "x-seen", "on": "*"}]
            )


@pytest.mark.parametrize(
    "body, fragment",
    [
        (None, "does not exist"),
        ("raise RuntimeError('boom')\n", "could not be loaded: RuntimeError: boom"),
        ("X = 1\n", "registered no hooks"),
        (
            "from the_loop.graph import hook\n@hook('licence')\ndef f(e): ...\n",
            "must be named x-",
        ),
    ],
)
def test_a_missing_raising_empty_or_misnamed_module_fails_naming_it(
    tmp_path, body, fragment
):
    root = tmp_path
    if body is not None:
        _config_dir(root, body)
    with pytest.raises(lh.HooksConfigError, match=fragment) as excinfo:
        _runtime(
            root,
            modules=[{"path": "hooks/mine.py"}],
            lifecycle=[{"hook": "x-seen", "on": "*"}],
        )
    assert "hooks/mine.py" in str(excinfo.value) or "hooks.modules" in str(
        excinfo.value
    )


def test_a_duplicate_name_across_modules_is_refused(tmp_path):
    root = _config_dir(tmp_path)
    _config_dir(root, SEEN_MODULE, "other.py")
    with pytest.raises(
        lh.HooksConfigError, match="two `hooks.modules` register 'x-seen'"
    ):
        _runtime(
            root,
            modules=[{"path": "hooks/mine.py"}, {"path": "hooks/other.py"}],
            lifecycle=[{"hook": "x-seen", "on": "*"}],
        )


def test_an_attachment_to_an_unregistered_hook_fails(tmp_path):
    root = _config_dir(tmp_path)
    with pytest.raises(
        lh.HooksConfigError, match="'x-other', which no declared module registered"
    ):
        _runtime(
            root,
            modules=[{"path": "hooks/mine.py"}],
            lifecycle=[{"hook": "x-other", "on": "*"}],
        )


def test_a_shipped_hook_needs_no_module(tmp_path):
    rt = _runtime(
        tmp_path,
        lifecycle=[
            {
                "hook": "forward-event",
                "on": "work_item.*",
                "with": {"url": "https://x/y"},
            }
        ],
    )
    assert rt.table == {} and rt.index["work_item.ended"][0].fn is lh.forward_event


def test_a_registered_but_unattached_hook_is_warned(tmp_path, caplog):
    root = _config_dir(tmp_path, BLOCKING_MODULE)
    with caplog.at_level("WARNING", logger="the-loop.hooks"):
        _runtime(
            root,
            modules=[{"path": "hooks/mine.py"}],
            lifecycle=[{"hook": "x-veto", "on": "*"}],
        )
    assert "x-approve, x-chatty" in caplog.text and "will never run" in caplog.text


# -- dispatch ---------------------------------------------------------------------


def test_dispatch_delivers_in_declaration_order_with_params_and_fields(tmp_path):
    root = _config_dir(tmp_path)
    out = tmp_path / "seen.jsonl"
    rt = _runtime(
        root,
        modules=[{"path": "hooks/mine.py"}],
        lifecycle=[
            {
                "hook": "x-seen",
                "on": "session.spawned",
                "with": {"out": str(out), "tag": "a"},
            },
            {
                "hook": "x-seen",
                "on": "session.*",
                "with": {"out": str(out), "tag": "b"},
            },
        ],
    )
    record = _record("session.spawned", work_item="github:o/r#1", session="loop-1")
    assert rt.dispatch(record) is True
    assert rt.drain(5.0)
    seen = _lines(out)
    assert [s["tag"] for s in seen] == ["a", "b"]
    assert seen[0]["fields"] == {"work_item": "github:o/r#1", "session": "loop-1"}
    assert seen[0]["work_item"] == "github:o/r#1" and seen[0]["instance"] == "inst"
    assert record == _record(
        "session.spawned", work_item="github:o/r#1", session="loop-1"
    )


def test_dispatch_ignores_unmatched_and_own_domain_records(tmp_path):
    root = _config_dir(tmp_path)
    rt = _runtime(
        root,
        modules=[{"path": "hooks/mine.py"}],
        lifecycle=[
            {"hook": "x-seen", "on": "session.*", "with": {"out": str(tmp_path / "o")}}
        ],
    )
    assert rt.dispatch(_record("graph.advanced")) is False
    assert rt.dispatch(_record("hooks.failed")) is False
    assert rt.drain(1.0) and not (tmp_path / "o").exists()


def test_a_hook_that_emits_does_not_recurse(tmp_path):
    """A4: a record emitted on the worker thread is written, never re-dispatched."""
    log = _log(tmp_path)
    root = _config_dir(tmp_path, EMITTING_MODULE)
    out = tmp_path / "seen.txt"
    rt = _runtime(
        root,
        modules=[{"path": "hooks/mine.py"}],
        lifecycle=[{"hook": "x-emits", "on": "session.*", "with": {"out": str(out)}}],
    )
    eventlog.add_sink(rt.dispatch)
    eventlog.emit("session.spawned")
    assert rt.drain(5.0)
    assert out.read_text().splitlines() == ["session.spawned"]
    assert [e["event"] for e in _events(log)] == ["session.spawned", "session.closed"]


def test_a_raising_hook_is_recorded_and_the_next_one_runs(tmp_path):
    """A3: the raise is one hooks.failed; the hook after it still runs."""
    log = _log(tmp_path)
    _config_dir(tmp_path, RAISING_MODULE, "boom.py")
    root = _config_dir(tmp_path)
    out = tmp_path / "seen.jsonl"
    rt = _runtime(
        root,
        modules=[{"path": "hooks/boom.py"}, {"path": "hooks/mine.py"}],
        lifecycle=[
            {"hook": "x-boom", "on": "graph.completed"},
            {"hook": "x-seen", "on": "graph.completed", "with": {"out": str(out)}},
        ],
    )
    rt.dispatch(_record("graph.completed", work_item="github:o/r#1"))
    assert rt.drain(5.0)
    failed = _events(log, "hooks.failed")
    assert len(failed) == 1 and failed[0]["level"] == "warning"
    assert failed[0]["hook"] == "x-boom" and failed[0]["on"] == "graph.completed"
    assert failed[0]["error"] == "RuntimeError: boom"
    assert [s["event"] for s in _lines(out)] == ["graph.completed"]


def test_a_blocking_result_is_a_failure_not_a_veto(tmp_path):
    """A3/A5: `block` is recorded as a failure; nothing is stopped and no outcome is read."""
    log = _log(tmp_path)
    root = _config_dir(tmp_path, BLOCKING_MODULE)
    rt = _runtime(
        root,
        modules=[{"path": "hooks/mine.py"}],
        lifecycle=[{"hook": "x-veto", "on": "graph.advanced"}],
    )
    rt.dispatch(_record("graph.advanced"))
    assert rt.drain(5.0)
    failed = _events(log, "hooks.failed")
    assert (
        len(failed) == 1
        and failed[0]["error"] == "no"
        and failed[0]["hook"] == "x-veto"
    )


def test_an_outcome_a_lifecycle_hook_declares_is_ignored(tmp_path):
    """A5: no HookContext, no chain, nothing reads `outcome` — a pass with one is just a pass."""
    log = _log(tmp_path)
    root = _config_dir(tmp_path, BLOCKING_MODULE)
    rt = _runtime(
        root,
        modules=[{"path": "hooks/mine.py"}],
        lifecycle=[{"hook": "x-approve", "on": "graph.advanced"}],
    )
    rt.dispatch(_record("graph.advanced"))
    assert rt.drain(5.0)
    assert _events(log, "hooks.*") == []


def test_messages_on_a_passing_result_become_no_event(tmp_path, caplog):
    log = _log(tmp_path)
    root = _config_dir(tmp_path, BLOCKING_MODULE)
    rt = _runtime(
        root,
        modules=[{"path": "hooks/mine.py"}],
        lifecycle=[{"hook": "x-chatty", "on": "graph.advanced"}],
    )
    with caplog.at_level("DEBUG", logger="the-loop.hooks"):
        rt.dispatch(_record("graph.advanced"))
        assert rt.drain(5.0)
    assert _events(log, "hooks.*") == [] and "chatty" in caplog.text


def _gated(monkeypatch, name: str = "test-gate"):
    """A shipped-table hook a test controls: blocks until ``gate`` is set."""
    gate, entered = threading.Event(), threading.Event()
    seen: List[str] = []

    def fn(event):
        entered.set()
        gate.wait(10)
        seen.append(event.event)
        return None

    monkeypatch.setitem(lh.SHIPPED, name, lh.ShippedHook(fn, lambda p: None))
    return gate, entered, seen


def test_overflow_drops_for_hooks_only_and_says_so_once(tmp_path, monkeypatch):
    """A9: a full queue drops for hooks, never for the log, and announces one episode."""
    log = _log(tmp_path)
    gate, entered, seen = _gated(monkeypatch)
    rt = _runtime(
        tmp_path, capacity=2, lifecycle=[{"hook": "test-gate", "on": "poll.cycle"}]
    )
    eventlog.add_sink(rt.dispatch)
    eventlog.emit("poll.cycle", n=1)
    assert entered.wait(5)  # the worker holds record 1; the queue is empty
    for n in (2, 3):
        eventlog.emit("poll.cycle", n=n)  # fills the two slots
    eventlog.emit("poll.cycle", n=4)  # dropped: the first of the episode
    eventlog.emit("poll.cycle", n=5)  # dropped: same episode, no second announcement
    gate.set()
    assert rt.drain(5.0)
    assert rt.dropped == 2 and seen == ["poll.cycle"] * 3
    cycles = _events(log, "poll.cycle")
    assert [c["n"] for c in cycles] == [1, 2, 3, 4, 5]  # the log lost nothing
    dropped = _events(log, "hooks.dropped")
    assert (
        len(dropped) == 1
        and dropped[0]["capacity"] == 2
        and dropped[0]["on"] == "poll.cycle"
    )
    eventlog.emit(
        "poll.cycle", n=6
    )  # the queue accepts again: a new episode may announce
    assert rt.drain(5.0) and seen[-1] == "poll.cycle" and len(seen) == 4


def test_a_hung_hook_stalls_only_the_worker(tmp_path, monkeypatch):
    """A3: the emitter never waits; drain reports the truth and gives up on time."""
    gate, entered, seen = _gated(monkeypatch)
    rt = _runtime(tmp_path, lifecycle=[{"hook": "test-gate", "on": "poll.cycle"}])
    started = time.monotonic()
    rt.dispatch(_record("poll.cycle"))
    rt.dispatch(_record("poll.cycle"))
    assert time.monotonic() - started < 1.0
    assert entered.wait(5) and rt.drain(0.2) is False
    gate.set()
    assert rt.drain(5.0) and seen == ["poll.cycle", "poll.cycle"]


# -- process-wide install ----------------------------------------------------------


def _cli_config(tmp_path: Path, **block: Any) -> Dict[str, Any]:
    return {"version": "0.9.0", "instance": {"name": "west"}, "hooks": block}


def test_install_is_idempotent_and_reset_forgets(tmp_path):
    _config_dir(tmp_path)
    config = _cli_config(
        tmp_path,
        modules=[{"path": "hooks/mine.py"}],
        lifecycle=[{"hook": "x-seen", "on": "*", "with": {"out": str(tmp_path / "o")}}],
    )
    first = lh.install(config, tmp_path / "cli-config.yaml")
    assert first is not None and lh.active() is first and first.instance == "west"
    assert lh.install(config, tmp_path / "cli-config.yaml") is first
    changed = dict(
        config,
        hooks=dict(config["hooks"], lifecycle=[{"hook": "x-seen", "on": "graph.*"}]),
    )
    second = lh.install(changed, tmp_path / "cli-config.yaml")
    assert second is not None
    assert (
        second is not first
        and lh.active() is second
        and eventlog._sinks == [second.dispatch]
    )
    lh.reset()
    assert lh.active() is None and eventlog._sinks == []


def test_install_with_an_empty_block_registers_nothing(tmp_path):
    assert lh.install({"version": "0.9.0"}, tmp_path / "cli-config.yaml") is None
    assert lh.active() is None and eventlog._sinks == [] and lh.drain(0.1) is True


# -- forward-event ------------------------------------------------------------------


class _Server:
    def __init__(self, status: int = 200) -> None:
        self.requests: List[Dict[str, Any]] = []
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 — http.server's name
                length = int(self.headers.get("Content-Length") or 0)
                server.requests.append(
                    {
                        "path": self.path,
                        "headers": dict(self.headers),
                        "body": self.rfile.read(length),
                    }
                )
                self.send_response(status)
                self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:  # silence
                pass

        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/loop"

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    srv = _Server()
    yield srv
    srv.close()


def _event(**params: Any) -> lh.LifecycleEvent:
    return lh.LifecycleEvent.from_record(
        _record("work_item.ended", work_item="github:o/r#1", reason="pr-merged"),
        params,
        "west",
    )


def test_forward_event_posts_the_record_with_headers_and_bearer(server, monkeypatch):
    monkeypatch.setenv("TEST_LOOP_TOKEN", "placeholder-token")
    result = lh.forward_event(
        _event(
            url=server.url, tokenEnv="TEST_LOOP_TOKEN", headers={"X-Source": "the-loop"}
        )
    )
    assert result.status == "pass" and result.data == {"status": 200}
    (req,) = server.requests
    assert req["path"] == "/loop"
    assert req["headers"]["Authorization"] == "Bearer placeholder-token"
    assert req["headers"]["Content-Type"] == "application/json"
    assert req["headers"]["X-Source"] == "the-loop"
    assert json.loads(req["body"]) == _record(
        "work_item.ended", work_item="github:o/r#1", reason="pr-merged"
    )


def test_forward_event_reads_the_token_at_call_time_and_sends_nothing_when_unset(
    server, monkeypatch
):
    """A6: an unset variable fails closed — nothing is sent, unauthenticated least of all."""
    monkeypatch.delenv("TEST_LOOP_TOKEN", raising=False)
    result = lh.forward_event(_event(url=server.url, tokenEnv="TEST_LOOP_TOKEN"))
    assert result.status == "block" and "TEST_LOOP_TOKEN is unset" in result.render()
    assert server.requests == []
    monkeypatch.setenv("TEST_LOOP_TOKEN", "later")  # set after load, read at call
    assert (
        lh.forward_event(_event(url=server.url, tokenEnv="TEST_LOOP_TOKEN")).status
        == "pass"
    )
    assert server.requests[0]["headers"]["Authorization"] == "Bearer later"


def test_forward_event_without_a_token_sends_no_authorization(server):
    assert lh.forward_event(_event(url=server.url)).status == "pass"
    assert "Authorization" not in server.requests[0]["headers"]


def test_forward_event_fails_on_non_2xx_and_refused_connections_without_retry(
    monkeypatch,
):
    srv = _Server(status=500)
    try:
        result = lh.forward_event(_event(url=srv.url))
        assert result.status == "block" and "HTTP 500" in result.render()
        assert len(srv.requests) == 1
        dead = srv.url
    finally:
        srv.close()
    refused = lh.forward_event(_event(url=dead, timeoutSeconds=1))
    assert refused.status == "block" and "URLError" in refused.render()


def test_the_failure_event_names_the_variable_not_the_value(tmp_path, monkeypatch):
    """A6: through the runtime, a failure carries the variable name and never a token."""
    log = _log(tmp_path)
    srv = _Server(status=503)
    try:
        monkeypatch.setenv("TEST_LOOP_TOKEN", "s3cret-value")
        rt = _runtime(
            tmp_path,
            lifecycle=[
                {
                    "hook": "forward-event",
                    "on": "work_item.ended",
                    "with": {"url": srv.url, "tokenEnv": "TEST_LOOP_TOKEN"},
                }
            ],
        )
        rt.dispatch(_record("work_item.ended"))
        assert rt.drain(5.0)
        monkeypatch.delenv("TEST_LOOP_TOKEN")
        rt.dispatch(_record("work_item.ended"))
        assert rt.drain(5.0)
    finally:
        srv.close()
    failed = _events(log, "hooks.failed")
    assert len(failed) == 2 and all(f["hook"] == "forward-event" for f in failed)
    assert (
        "HTTP 503" in failed[0]["error"]
        and "TEST_LOOP_TOKEN is unset" in failed[1]["error"]
    )
    assert "s3cret-value" not in log.read_text()


# -- the event-log seam ---------------------------------------------------------------


def test_seam_emit_reaches_sinks_even_when_the_log_is_disabled(tmp_path):
    eventlog.configure("t", path=tmp_path / "events.jsonl", enabled=False)
    seen: List[Dict[str, Any]] = []
    eventlog.add_sink(seen.append)
    eventlog.emit("poll.cycle", n=1, skipped=None)
    assert [(s["event"], s["source"], s["n"]) for s in seen] == [("poll.cycle", "t", 1)]
    assert "skipped" not in seen[0] and not (tmp_path / "events.jsonl").exists()


def test_seam_a_raising_sink_never_propagates(tmp_path, caplog):
    log = _log(tmp_path)

    def bad(record):
        raise RuntimeError("sink broke")

    eventlog.add_sink(bad)
    with caplog.at_level("WARNING"):
        eventlog.emit("poll.cycle")
        eventlog.emit("poll.cycle")
    assert len(_events(log, "poll.cycle")) == 2 and caplog.text.count("sink broke") == 1


def _config_file(tmp_path: Path, monkeypatch, hooks: str) -> Path:
    path = tmp_path / "cli-config.yaml"
    path.write_text(
        f'version: "0.9.0"\neventLog:\n  path: {tmp_path / "events.jsonl"}\n{hooks}'
    )
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    return path


def test_seam_configure_from_file_installs_the_hooks_block(tmp_path, monkeypatch):
    _config_dir(tmp_path)
    out = tmp_path / "seen.jsonl"
    _config_file(
        tmp_path,
        monkeypatch,
        "hooks:\n  modules:\n    - path: hooks/mine.py\n  lifecycle:\n"
        f"    - hook: x-seen\n      on: session.spawned\n      with: {{out: {out}}}\n",
    )
    REAL_CONFIGURE_FROM_FILE("cli")
    installed = lh.active()
    assert installed is not None and installed.root == tmp_path.resolve()
    eventlog.emit("session.spawned", work_item="github:o/r#1")
    assert lh.drain(5.0)
    assert [s["work_item"] for s in _lines(out)] == ["github:o/r#1"]
    loaded = _events(tmp_path / "events.jsonl", "hooks.loaded")
    assert (
        loaded
        and loaded[0]["modules"] == 1
        and loaded[0]["attachments"] == 1
        and loaded[0]["events"] == 1
    )


def test_seam_a_broken_declaration_fails_configure_from_file(tmp_path, monkeypatch):
    """A8: the entry point refuses to run rather than running without the hooks it was told to run."""
    _config_file(
        tmp_path,
        monkeypatch,
        "hooks:\n  modules:\n    - path: hooks/absent.py\n  lifecycle:\n    - hook: x-seen\n      on: '*'\n",
    )
    with pytest.raises(lh.HooksConfigError, match="hooks/absent.py"):
        REAL_CONFIGURE_FROM_FILE("cli")
    assert lh.active() is None


def test_seam_reset_clears_sinks_and_runtime(tmp_path):
    _log(tmp_path)
    rt = _runtime(
        tmp_path,
        lifecycle=[
            {
                "hook": "forward-event",
                "on": "work_item.*",
                "with": {"url": "https://x/y"},
            }
        ],
    )
    eventlog.add_sink(rt.dispatch)
    eventlog.reset()
    assert eventlog._sinks == [] and lh.active() is None and eventlog._log is None
