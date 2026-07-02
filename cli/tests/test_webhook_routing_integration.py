"""Integration tests: signed webhook POST → router → dispatcher → harness CLI.

Every test here drives a *real* signed HTTP POST into a live receiver and
asserts on what a stub harness CLI was actually invoked with (argv, cwd,
timing) — i.e. "was the harness triggered, and how", not just the pure
routing functions (those are in ``test_routing.py``).

Feature: Webhook event routing
Requirement: docs/specs/issue-15/requirements.md#R3
"""

import hashlib
import hmac
import json
import stat
import threading
import time
import urllib.error
import urllib.request

import pytest

from the_loop.harness import ClaudeCodeAdapter
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook import serve
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import Router

SECRET = "s3cret"
REF = "github:octo/repo#15"
ROUTED_EVENTS = ["issue_comment", "pull_request_review_comment"]

# A fake harness CLI: records each invocation's argv/cwd and start/end wall
# times (so tests can prove serialization vs. parallelism), optionally sleeps
# to simulate an in-flight run, and optionally exits non-zero to simulate a
# harness error. Behaviour is baked into the script so distinct stubs don't
# collide over env vars.
STUB_TEMPLATE = """#!/usr/bin/env python3
import json, os, sys, time
start = time.time()
time.sleep({delay})
end = time.time()
with open(os.environ["STUB_RECORD"], "a") as f:
    f.write(json.dumps(
        {{"argv": sys.argv[1:], "cwd": os.getcwd(), "start": start, "end": end}}
    ) + "\\n")
if {exit_code}:
    sys.stderr.write("stub harness error\\n")
    sys.exit({exit_code})
print(json.dumps({{"session_id": "spawned-1", "result": "ok"}}))
"""


def wait_until(predicate, timeout=5.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class ServerFactory:
    """Builds live receivers wired to a stub-harness dispatcher.

    Call it (``**routing_overrides``) to start a server → ``(port, registry,
    calls)``; ``make_stub(delay=, exit_code=)`` writes a stub harness CLI. The
    stub's invocations are shared via ``calls()``. Servers are torn down by the
    fixture.
    """

    def __init__(self, tmp_path, record):
        self._tmp_path = tmp_path
        self._record = record
        self.started = []

    def make_stub(self, delay: float = 0.0, exit_code: int = 0) -> str:
        binary = self._tmp_path / "claude"
        binary.write_text(STUB_TEMPLATE.format(delay=delay, exit_code=exit_code))
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
        return str(binary)

    def calls(self) -> list:
        if not self._record.exists():
            return []
        lines = self._record.read_text().strip().splitlines()
        return [json.loads(line) for line in lines]

    def __call__(self, binary=None, registry=None, **routing_overrides):
        binary = binary or self.make_stub()
        registry = registry or SessionRegistry(self._tmp_path / "sessions")
        config = RoutingConfig(
            dispatch_timeout_seconds=30,
            spawn_workdir=str(self._tmp_path),
            **routing_overrides,
        )
        dispatcher = Dispatcher(
            registry=registry,
            adapters={"claude": ClaudeCodeAdapter(binary=binary)},
            config=config,
        )
        router = Router(events=ROUTED_EVENTS, deduper=dispatcher.deduper)

        def on_event(event, payload, delivery_id):
            routed = router.route(event, payload, delivery_id)
            if routed is not None:
                dispatcher.handle(routed)

        httpd = serve(
            host="127.0.0.1",
            port=0,
            path="/gh-webhook",
            secret=SECRET,
            on_event=on_event,
        )
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.started.append((httpd, dispatcher))
        return httpd.server_address[1], registry, self.calls


@pytest.fixture()
def server_factory(tmp_path, monkeypatch):
    record = tmp_path / "record.jsonl"
    monkeypatch.setenv("STUB_RECORD", str(record))
    factory = ServerFactory(tmp_path, record)
    try:
        yield factory
    finally:
        for httpd, dispatcher in factory.started:
            httpd.shutdown()
            httpd.server_close()
            dispatcher.stop()


def post_webhook(port, event, payload, delivery_id):
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/gh-webhook",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": event,
            "X-GitHub-Delivery": delivery_id,
            "X-Hub-Signature-256": signature,
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status


def issue_comment_payload(body, number=15):
    return {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": number},
        "comment": {"body": body},
        "sender": {"login": "octocat"},
    }


def register(registry, tmp_path, ref=REF, session_id="sess-1"):
    registry.register(
        Session(
            work_item=WorkItemRef.parse(ref),
            harness="claude",
            harness_session_id=session_id,
            cwd=str(tmp_path),
        )
    )


def prompt_of(call):
    argv = call["argv"]
    return argv[argv.index("-p") + 1]


def test_idle_session_is_resumed_on_event(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: An idle registered session is resumed when its event arrives
        Given a running receiver and a session registered for github:octo/repo#15
        And the harness is not currently doing any work for that item
        When a signed issue_comment webhook for issue 15 is POSTed
        Then the harness CLI is invoked with --resume and the session id
        And the prompt embeds the comment body as untrusted data
        And the registry records the processed delivery id
    Requirement: docs/specs/issue-15/requirements.md#R3 (R3.2, R4.2, R5.1)
    """
    port, registry, calls = server_factory()
    register(registry, tmp_path)
    assert (
        post_webhook(
            port, "issue_comment", issue_comment_payload("CI is red, please fix"), "d-1"
        )
        == 202
    )

    def delivery_recorded():
        found = registry.find_by_work_item(REF)
        return found is not None and "d-1" in found.recent_deliveries

    assert wait_until(delivery_recorded)
    (call,) = calls()
    argv = call["argv"]
    assert argv[argv.index("--resume") + 1] == "sess-1"
    assert "CI is red, please fix" in prompt_of(call)
    assert "UNTRUSTED" in prompt_of(call)
    assert call["cwd"] == str(tmp_path)  # resumed in the session's own directory


def test_unmatched_event_is_dropped_by_default(server_factory):
    """
    Feature: Webhook event routing
    Scenario: An event with no registered work item is dropped
        Given a running receiver with an empty registry (spawnOnUnmatched: never)
        When a signed issue_comment webhook is POSTed
        Then the receiver acknowledges with 202
        And no harness CLI invocation happens
    Requirement: docs/specs/issue-15/requirements.md#R3 (R3.3)
    """
    port, _, calls = server_factory()
    assert (
        post_webhook(port, "issue_comment", issue_comment_payload("anyone?"), "d-2")
        == 202
    )
    time.sleep(0.3)  # give a would-be dispatch time to (wrongly) happen
    assert calls() == []


def test_unmatched_event_spawns_session_when_configured(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: An event with no work item spawns a session when configured
        Given a running receiver with spawnOnUnmatched: always and an empty registry
        When a signed issue_comment webhook for issue 15 is POSTed
        Then the harness CLI is invoked WITHOUT --resume (a fresh session)
        And the new session is registered with the harness-assigned id
    Requirement: docs/specs/issue-15/requirements.md#R3 (R3.3, R4.4)
    """
    port, registry, calls = server_factory(spawn_on_unmatched="always")
    assert (
        post_webhook(port, "issue_comment", issue_comment_payload("new work"), "d-3")
        == 202
    )
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)
    (call,) = calls()
    assert "--resume" not in call["argv"]  # spawned, not resumed
    session = registry.find_by_work_item(REF)
    assert session is not None and session.harness_session_id == "spawned-1"


def test_busy_session_queues_second_event_and_preserves_order(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: A second event for a busy session waits and runs after the first
        Given a session whose harness takes ~0.3s per event
        When two issue_comment webhooks for the same item arrive back-to-back
        Then the harness is invoked twice, in arrival order
        And the second invocation only starts after the first finishes
    Requirement: docs/specs/issue-15/requirements.md#R3 (R5.2)
    """
    binary = server_factory.make_stub(delay=0.3)
    port, registry, calls = server_factory(binary=binary)
    register(registry, tmp_path)
    assert (
        post_webhook(port, "issue_comment", issue_comment_payload("first"), "b-1")
        == 202
    )
    assert (
        post_webhook(port, "issue_comment", issue_comment_payload("second"), "b-2")
        == 202
    )
    assert wait_until(lambda: len(calls()) == 2, timeout=8.0)
    first, second = calls()  # record is append-order = dispatch order
    assert "first" in prompt_of(first) and "second" in prompt_of(second)
    # Serialized: the second run did not start until the first had ended.
    assert second["start"] >= first["end"] - 0.01


def test_events_for_different_items_run_in_parallel(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: Events for different work items dispatch concurrently
        Given two sessions registered for two different work items
        And a harness that takes ~0.3s per event
        When an event arrives for each, back-to-back
        Then both harness runs overlap in time (multiple sessions per executor)
    Requirement: docs/specs/issue-15/requirements.md#R3 (R5.1, R5.3)
    """
    binary = server_factory.make_stub(delay=0.3)
    port, registry, calls = server_factory(binary=binary)
    register(registry, tmp_path, ref="github:octo/repo#15", session_id="s15")
    register(registry, tmp_path, ref="github:octo/repo#16", session_id="s16")
    assert (
        post_webhook(
            port, "issue_comment", issue_comment_payload("a", number=15), "p-1"
        )
        == 202
    )
    assert (
        post_webhook(
            port, "issue_comment", issue_comment_payload("b", number=16), "p-2"
        )
        == 202
    )
    assert wait_until(lambda: len(calls()) == 2, timeout=8.0)
    a, b = calls()
    # Overlap: each starts before the other ends → they ran concurrently.
    assert a["start"] < b["end"] and b["start"] < a["end"]


def test_duplicate_delivery_is_processed_at_most_once(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: A redelivered webhook does not double-trigger the session
        Given a session registered for github:octo/repo#15
        When the same delivery id is POSTed twice
        Then the harness CLI is invoked exactly once
    Requirement: docs/specs/issue-15/requirements.md#R3 (R3.4)
    """
    port, registry, calls = server_factory()
    register(registry, tmp_path)
    payload = issue_comment_payload("one event, two deliveries")
    assert post_webhook(port, "issue_comment", payload, "dup-9") == 202
    assert post_webhook(port, "issue_comment", payload, "dup-9") == 202
    assert wait_until(lambda: len(calls()) >= 1)
    time.sleep(0.3)
    assert len(calls()) == 1


def test_harness_error_is_isolated_and_redelivery_retries(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: A failed harness run is logged and the delivery can be retried
        Given a harness that exits non-zero (an error)
        When an event is POSTed and the harness fails
        Then the delivery id is NOT recorded (so GitHub can redeliver)
        And re-POSTing the same delivery triggers the harness again
        And the receiver stays alive throughout (still returns 202)
    Requirement: docs/specs/issue-15/requirements.md#R3 (error handling)
    """
    binary = server_factory.make_stub(exit_code=1)
    port, registry, calls = server_factory(binary=binary)
    register(registry, tmp_path)
    assert (
        post_webhook(port, "issue_comment", issue_comment_payload("boom"), "e-1") == 202
    )
    assert wait_until(lambda: len(calls()) == 1)
    # Failure is isolated: the delivery is not marked processed...
    time.sleep(0.2)
    found = registry.find_by_work_item(REF)
    assert found is not None and "e-1" not in found.recent_deliveries
    # ...so a redelivery of the same id is retried, not deduped away.
    assert (
        post_webhook(port, "issue_comment", issue_comment_payload("boom"), "e-1") == 202
    )
    assert wait_until(lambda: len(calls()) == 2)


def test_invalid_signature_is_rejected_before_routing(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: An event with a bad HMAC signature never reaches the harness
        Given a receiver with a configured secret and a registered session
        When a POST arrives with an incorrect X-Hub-Signature-256
        Then the receiver responds 401 and the harness is never invoked
    Requirement: docs/specs/issue-15/requirements.md#R3 (security)
    """
    port, registry, calls = server_factory()
    register(registry, tmp_path)
    body = json.dumps(issue_comment_payload("forged")).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/gh-webhook",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "issue_comment",
            "X-GitHub-Delivery": "x-1",
            "X-Hub-Signature-256": "sha256=deadbeef",
        },
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request, timeout=10)
    assert exc.value.code == 401
    time.sleep(0.2)
    assert calls() == []


def test_disabled_event_type_is_not_routed(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: An event type outside the configured list is ignored
        Given a receiver routing only issue_comment / pull_request_review_comment
        When a signed pull_request webhook arrives
        Then the harness is never invoked
    Requirement: docs/specs/issue-15/requirements.md#R3 (R3.5)
    """
    port, registry, calls = server_factory()
    register(registry, tmp_path)
    payload = {
        "action": "synchronize",
        "repository": {"full_name": "octo/repo"},
        "pull_request": {"number": 15, "head": {"ref": "main"}, "body": ""},
    }
    assert post_webhook(port, "pull_request", payload, "f-1") == 202
    time.sleep(0.3)
    assert calls() == []


def test_gh_webhook_start_accepts_route_flag():
    """
    Feature: Webhook event routing
    Scenario: Routing is opt-in on the receiver command
        Given the gh-webhook start command
        When parsed with --route or --no-route
        Then the flag round-trips (config routing.enabled is the default)
    Requirement: docs/specs/issue-15/requirements.md#R3
    """
    from the_loop.cli import build_parser

    parser = build_parser()
    assert parser.parse_args(["gh-webhook", "start", "--route"]).route is True
    assert parser.parse_args(["gh-webhook", "start", "--no-route"]).route is False
