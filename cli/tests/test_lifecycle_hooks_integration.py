"""Lifecycle hooks through the real seams (issue-344): a CLI config file on disk, a
module file beside it, ``eventlog.configure_from_file`` — the call every daemon and
every one-shot command makes — and ``eventlog.emit`` as the instrumentation calls it.

Nothing here is mocked between the config file and the hook. The conftest stubs
``configure_from_file`` for hermeticity; these tests call the real one, captured at
import, against a config whose ``eventLog.path`` is under ``tmp_path``.
"""

from __future__ import annotations

import http.server
import json
import threading
from pathlib import Path
from typing import Any, Dict, List

import pytest

from the_loop import eventlog
from the_loop import lifecycle_hooks as lh
from the_loop.graph import extensions

REAL_CONFIGURE_FROM_FILE = eventlog.configure_from_file

TELEMETRY = """
import json
from the_loop.graph import HookResult, hook


@hook("x-telemetry")
def telemetry(event):
    with open(event.params["out"], "a") as handle:
        handle.write(json.dumps({"event": event.event, "work_item": event.work_item}) + "\\n")
    return HookResult.ok("x-telemetry")
"""

EVIL = """
import pathlib
pathlib.Path(__file__).with_suffix(".ran").write_text("ran")
from the_loop.graph import hook


@hook("x-evil")
def evil(event):
    return None
"""


@pytest.fixture(autouse=True)
def _clean():
    extensions.clear_module_cache()
    lh.reset()
    yield
    lh.reset()
    extensions.clear_module_cache()


def _instance(tmp_path: Path, monkeypatch, hooks: str) -> Path:
    """An operator's config directory: the config file and a `hooks/` folder beside it."""
    home = tmp_path / "op"
    (home / "hooks").mkdir(parents=True)
    (home / "hooks" / "telemetry.py").write_text(TELEMETRY)
    path = home / "cli-config.yaml"
    path.write_text(
        f'version: "0.9.0"\neventLog:\n  path: {home / "events.jsonl"}\n' + hooks
    )
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    return home


def _seen(path: Path) -> List[Dict[str, Any]]:
    return (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.is_file()
        else []
    )


def test_work_start_and_finish_reach_a_declared_hook(tmp_path, monkeypatch):
    """
    Feature: an enterprise sends its own telemetry on work start and work finish
      Scenario: the CLI config attaches a hook to the events the daemon records
        Given a CLI config declaring hooks.modules with a module beside it
        And hooks.lifecycle attaching x-telemetry to session.spawned and work_item.*
        When the daemon's entry point configures the event log from that file
        And it records session.spawned and, later, work_item.ended for a work item
        Then the hook received both records with the work item
        And the log records hooks.loaded once, and no hooks.failed

    Requirement: docs/specs/issue-344/requirements.md R1.4, R2.1, R2.2, R4.1, R6.3
    """
    out = tmp_path / "telemetry.jsonl"
    home = _instance(
        tmp_path,
        monkeypatch,
        "hooks:\n  modules:\n    - path: hooks/telemetry.py\n  lifecycle:\n"
        f"    - hook: x-telemetry\n      on: [session.spawned, work_item.*]\n      with: {{out: {out}}}\n",
    )
    REAL_CONFIGURE_FROM_FILE("gh-webhook")
    eventlog.emit("session.spawned", work_item="github:o/r#1", session="loop-o-r-1")
    eventlog.emit("graph.advanced", work_item="github:o/r#1", node="design")
    eventlog.emit("work_item.ended", work_item="github:o/r#1", reason="pr-merged")
    assert lh.drain(5.0)
    assert _seen(out) == [
        {"event": "session.spawned", "work_item": "github:o/r#1"},
        {"event": "work_item.ended", "work_item": "github:o/r#1"},
    ]
    events = [r["event"] for r in eventlog.read_events(home / "events.jsonl")]
    assert events.count("hooks.loaded") == 1 and "hooks.failed" not in events


def test_a_checkout_module_nobody_declared_never_runs(tmp_path, monkeypatch):
    """
    Feature: only the operator's CLI config can put code in the-loop's process
      Scenario: a repository checkout carries a hook module the config never names
        Given a checkout with .the-loop/hooks/evil.py that leaves a mark when imported
        And the operator's CLI config declares no hooks block
        When the entry point configures the event log and records an event
        Then the module was never imported and no runtime was installed

    Requirement: docs/specs/issue-344/requirements.md R2.3 (abuse case A1)
    """
    checkout = tmp_path / "checkout"
    (checkout / ".the-loop" / "hooks").mkdir(parents=True)
    (checkout / ".the-loop" / "hooks" / "evil.py").write_text(EVIL)
    _instance(tmp_path, monkeypatch, "")
    monkeypatch.chdir(checkout)
    REAL_CONFIGURE_FROM_FILE("gh-webhook")
    eventlog.emit("session.spawned", work_item="github:o/r#1")
    assert lh.active() is None and lh.drain(1.0)
    assert not (checkout / ".the-loop" / "hooks" / "evil.ran").exists()


def test_forward_event_end_to_end_with_the_token_from_the_environment(
    tmp_path, monkeypatch
):
    """
    Feature: the commonest telemetry need takes no Python
      Scenario: forward-event ships the record to an HTTP endpoint with a bearer token
        Given a CLI config attaching the shipped forward-event to work_item.* with a tokenEnv
        And the named environment variable set in the daemon's environment
        When the entry point configures the event log and records work_item.ended
        Then the endpoint received the record as JSON with the bearer token
        And the token appears nowhere in the config or the log

    Requirement: docs/specs/issue-344/requirements.md R5.2, R5.4 (abuse case A6)
    """
    received: List[Dict[str, Any]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            received.append(
                {"auth": self.headers.get("Authorization"), "body": json.loads(body)}
            )
            self.send_response(202)
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/events"
        monkeypatch.setenv("TEST_LOOP_TOKEN", "placeholder-token")
        home = _instance(
            tmp_path,
            monkeypatch,
            f"hooks:\n  lifecycle:\n    - hook: forward-event\n      on: work_item.*\n"
            f"      with: {{url: {url}, tokenEnv: TEST_LOOP_TOKEN}}\n",
        )
        REAL_CONFIGURE_FROM_FILE("poll")
        eventlog.emit("work_item.ended", work_item="github:o/r#1", reason="pr-merged")
        assert lh.drain(5.0)
    finally:
        httpd.shutdown()
        httpd.server_close()
    (req,) = received
    assert req["auth"] == "Bearer placeholder-token"
    assert (
        req["body"]["event"] == "work_item.ended"
        and req["body"]["work_item"] == "github:o/r#1"
    )
    assert req["body"]["source"] == "poll"
    assert "placeholder-token" not in (home / "cli-config.yaml").read_text()
    assert "placeholder-token" not in (home / "events.jsonl").read_text()


def test_a_broken_declaration_fails_the_entry_point(tmp_path, monkeypatch):
    """
    Feature: nothing degrades to "no hooks"
      Scenario: the config names a module that does not exist
        Given a CLI config whose hooks.modules names hooks/absent.py
        When an entry point configures the event log from it
        Then it fails naming the module, and no runtime is installed

    Requirement: docs/specs/issue-344/requirements.md R6.2 (abuse case A8)
    """
    _instance(
        tmp_path,
        monkeypatch,
        "hooks:\n  modules:\n    - path: hooks/absent.py\n  lifecycle:\n    - hook: x-telemetry\n      on: '*'\n",
    )
    with pytest.raises(lh.HooksConfigError, match="hooks/absent.py"):
        REAL_CONFIGURE_FROM_FILE("cli")
    assert lh.active() is None
