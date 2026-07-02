"""Integration tests: signed webhook POST → router → dispatcher → harness CLI.

Feature: Webhook event routing
Requirement: docs/specs/issue-15/requirements.md#R3
"""

import hashlib
import hmac
import json
import stat
import threading
import time
import urllib.request

import pytest

from the_loop.harness import ClaudeCodeAdapter
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook import serve
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import Router

SECRET = "s3cret"
REF = "github:octo/repo#15"

STUB_SOURCE = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["STUB_RECORD"], "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}) + "\\n")
print(json.dumps({"session_id": "sess-1", "result": "ok"}))
"""


def wait_until(predicate, timeout=5.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture()
def routed_server(tmp_path, monkeypatch):
    """A live receiver wired to a dispatcher whose harness CLI is a stub."""
    binary = tmp_path / "claude"
    binary.write_text(STUB_SOURCE)
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    record = tmp_path / "record.jsonl"
    monkeypatch.setenv("STUB_RECORD", str(record))

    registry = SessionRegistry(tmp_path / "sessions")
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": ClaudeCodeAdapter(binary=str(binary))},
        config=RoutingConfig(dispatch_timeout_seconds=30),
    )
    router = Router(events=["issue_comment", "pull_request_review_comment"])

    def on_event(event, payload, delivery_id):
        routed = router.route(event, payload, delivery_id)
        if routed is not None:
            dispatcher.handle(routed)

    httpd = serve(
        host="127.0.0.1", port=0, path="/gh-webhook", secret=SECRET, on_event=on_event
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    def calls():
        if not record.exists():
            return []
        return [
            json.loads(line) for line in record.read_text().strip().splitlines()
        ]

    try:
        yield httpd.server_address[1], registry, calls
    finally:
        httpd.shutdown()
        httpd.server_close()
        dispatcher.stop()


def post_webhook(port, event, payload, delivery_id):
    body = json.dumps(payload).encode()
    signature = (
        "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    )
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


def issue_comment_payload(body):
    return {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15},
        "comment": {"body": body},
        "sender": {"login": "octocat"},
    }


def test_review_comment_resumes_registered_session(routed_server, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: A PR comment resumes the registered session
        Given a running receiver with routing enabled
        And a session registered for github:octo/repo#15
        When a signed issue_comment webhook for issue 15 is POSTed
        Then the harness CLI is invoked with --resume and the session id
        And the prompt embeds the comment body as untrusted data
        And the registry records the processed delivery id
    Requirement: docs/specs/issue-15/requirements.md#R3 (R3.2, R4.2, R5.1)
    """
    port, registry, calls = routed_server
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(tmp_path),
        )
    )
    status = post_webhook(
        port, "issue_comment", issue_comment_payload("CI is red, please fix"), "d-1"
    )
    assert status == 202

    def delivery_recorded():
        found = registry.find_by_work_item(REF)
        return found is not None and "d-1" in found.recent_deliveries

    assert wait_until(delivery_recorded)  # dispatch completed AND was recorded
    (call,) = calls()
    argv = call["argv"]
    assert argv[argv.index("--resume") + 1] == "sess-1"
    prompt = argv[argv.index("-p") + 1]
    assert "CI is red, please fix" in prompt
    assert "UNTRUSTED" in prompt


def test_unmatched_event_is_dropped_by_default(routed_server):
    """
    Feature: Webhook event routing
    Scenario: An event with no registered session is dropped
        Given a running receiver with routing enabled and an empty registry
        When a signed issue_comment webhook is POSTed
        Then the receiver acknowledges with 202
        And no harness CLI invocation happens (spawnOnUnmatched: never)
    Requirement: docs/specs/issue-15/requirements.md#R3 (R3.3)
    """
    port, _, calls = routed_server
    assert post_webhook(
        port, "issue_comment", issue_comment_payload("anyone there?"), "d-2"
    ) == 202
    time.sleep(0.3)  # give a would-be dispatch time to (wrongly) happen
    assert calls() == []


def test_duplicate_delivery_is_processed_at_most_once(routed_server, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: A redelivered webhook does not double-trigger the session
        Given a session registered for github:octo/repo#15
        When the same delivery id is POSTed twice
        Then the harness CLI is invoked exactly once
    Requirement: docs/specs/issue-15/requirements.md#R3 (R3.4)
    """
    port, registry, calls = routed_server
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(tmp_path),
        )
    )
    payload = issue_comment_payload("one event, two deliveries")
    assert post_webhook(port, "issue_comment", payload, "dup-9") == 202
    assert post_webhook(port, "issue_comment", payload, "dup-9") == 202
    assert wait_until(lambda: len(calls()) >= 1)
    time.sleep(0.3)
    assert len(calls()) == 1


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
