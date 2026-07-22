"""Integration tests: live webhook traffic → the structured JSONL event log.

Feature: End-to-end observability of the-loop's CLI actions
Requirement: docs/specs/issue-50/requirements.md

Each test drives a real signed HTTP POST into a live receiver (the same
stub-harness stack as ``test_webhook_routing_integration``) and asserts on the
``events.jsonl`` trail the process leaves behind — the artifact a human (or a
coding agent running ``the-loop events``) uses to answer "which events
triggered this session, what was rejected, and what failed?".
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

from the_loop import eventlog
from the_loop.cli import main
from the_loop.harness import ClaudeCodeAdapter
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook import serve
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import Router

SECRET = "s3cret"
REF = "github:octo/repo#15"

STUB_TEMPLATE = """#!/usr/bin/env python3
import json, sys
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


@pytest.fixture()
def stack(tmp_path):
    """A live receiver + stub harness, with the event log configured the way
    `gh-webhook start` configures it — writing to a tmp events.jsonl."""
    log_path = tmp_path / "events.jsonl"
    eventlog.configure("gh-webhook", path=log_path)
    started = []

    def start(exit_code=0, register_session=True, **routing_overrides):
        binary = tmp_path / "claude"
        binary.write_text(STUB_TEMPLATE.format(exit_code=exit_code))
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
        registry = SessionRegistry(tmp_path / "sessions")
        if register_session:
            registry.register(
                Session(
                    work_item=WorkItemRef.parse(REF),
                    harness="claude",
                    harness_session_id="sess-1",
                    cwd=str(tmp_path),
                )
            )
        config = RoutingConfig(
            dispatch_timeout_seconds=30,
            spawn_workdir=str(tmp_path),
            **routing_overrides,
        )
        dispatcher = Dispatcher(
            registry=registry,
            adapters={"claude": ClaudeCodeAdapter(binary=str(binary))},
            config=config,
        )
        router = Router(
            events=["issue_comment"],
            deduper=dispatcher.deduper,
            auto_execute_label=config.auto_execute_label,
            authorized_users=["octocat"],
        )

        def on_event(event, payload, delivery_id):
            routed = router.route(event, payload, delivery_id)
            if routed is not None:
                dispatcher.handle(routed)

        httpd = serve(
            host="127.0.0.1", port=0, path="/gh-webhook", secret=SECRET,
            on_event=on_event,
        )
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        started.append((httpd, dispatcher))
        return httpd.server_address[1], registry

    def events(**filters):
        return list(eventlog.read_events(log_path, **filters))

    try:
        yield start, events, log_path
    finally:
        eventlog.reset()
        for httpd, dispatcher in started:
            httpd.shutdown()
            httpd.server_close()
            dispatcher.stop()


def post_webhook(port, event, payload, delivery_id, secret=SECRET):
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
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
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def issue_comment_payload(body, sender="octocat", number=15):
    return {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": number},
        "comment": {"body": body, "user": {"login": sender}},
        "sender": {"login": sender},
    }


def test_accepted_event_leaves_a_full_trail(stack):
    """
    Feature: End-to-end observability of the-loop's CLI actions
    Scenario: An accepted webhook event leaves a complete audit trail
        Given a running receiver with an active session for github:octo/repo#15
        When a signed issue_comment webhook is POSTed with delivery id d-1
        Then events.jsonl records webhook.received, routing.routed,
             dispatch.queued and dispatch.succeeded
        And every record carries the same delivery id d-1
        And the dispatch records name the work item and harness
    Requirement: docs/specs/issue-50/requirements.md#R1
    """
    start, events, _ = stack
    port, _ = start()
    assert post_webhook(port, "issue_comment", issue_comment_payload("hi"), "d-1") == 202
    assert wait_until(lambda: any(e["event"] == "dispatch.succeeded" for e in events()))
    trail = [e["event"] for e in events(delivery_id="d-1")]
    for expected in (
        "webhook.received",
        "routing.routed",
        "dispatch.queued",
        "dispatch.succeeded",
    ):
        assert expected in trail
    (succeeded,) = events(types=["dispatch.succeeded"])
    assert succeeded["work_item"] == REF
    assert succeeded["harness"] == "claude"
    assert succeeded["source"] == "gh-webhook"


def test_rejections_are_recorded_with_reasons(stack):
    """
    Feature: End-to-end observability of the-loop's CLI actions
    Scenario: Rejected events are recorded with a machine-readable reason
        Given a running receiver with an active session
        When a POST arrives with an invalid HMAC signature
        And an authorized POST arrives for an event type that is not enabled
        And a POST arrives from an unauthorized actor
        Then events.jsonl records webhook.rejected reason=invalid-signature
        And routing.dropped reason=disabled-event for the disabled type
        And routing.dropped reason=unauthorized-actor naming the actor
    Requirement: docs/specs/issue-50/requirements.md#R2
    """
    start, events, _ = stack
    port, _ = start()
    assert (
        post_webhook(
            port, "issue_comment", issue_comment_payload("x"), "d-bad",
            secret="wrong",
        )
        == 401
    )
    assert post_webhook(port, "issues", issue_comment_payload("y"), "d-off") == 202
    assert (
        post_webhook(
            port,
            "issue_comment",
            issue_comment_payload("z", sender="mallory"),
            "d-mal",
        )
        == 202
    )
    assert wait_until(
        lambda: len(events(types=["webhook.rejected", "routing.dropped"])) >= 3
    )
    (rejected,) = events(types=["webhook.rejected"])
    assert rejected["reason"] == "invalid-signature"
    assert rejected["delivery_id"] == "d-bad"
    reasons = {e["delivery_id"]: e["reason"] for e in events(types=["routing.dropped"])}
    assert reasons["d-off"] == "disabled-event"
    assert reasons["d-mal"] == "unauthorized-actor"
    (unauthorized,) = events(types=["routing.dropped"], delivery_id="d-mal")
    assert unauthorized["actor"] == "mallory"


def test_failed_dispatch_is_recorded_as_retryable(stack):
    """
    Feature: End-to-end observability of the-loop's CLI actions
    Scenario: A failed harness dispatch is recorded with its retry semantics
        Given a running receiver whose harness CLI exits non-zero
        When a signed issue_comment webhook is POSTed
        Then events.jsonl records dispatch.failed at level error
        And the record carries the harness error and will_retry=true
             (the delivery id was released for GitHub redelivery)
    Requirement: docs/specs/issue-50/requirements.md#R3
    """
    start, events, _ = stack
    port, _ = start(exit_code=3)
    assert post_webhook(port, "issue_comment", issue_comment_payload("go"), "d-f") == 202
    assert wait_until(lambda: events(types=["dispatch.failed"]))
    (failed,) = events(types=["dispatch.failed"])
    assert failed["level"] == "error"
    assert failed["work_item"] == REF
    assert failed["will_retry"] is True
    assert failed["error"]


def test_spawn_and_session_lifecycle_are_recorded(stack):
    """
    Feature: End-to-end observability of the-loop's CLI actions
    Scenario: What triggered a session is answerable from the log alone
        Given a receiver with spawnOnUnmatched: always and an empty registry
        When a signed issue_comment webhook for issue 15 is POSTed
        Then events.jsonl records session.spawned for github:octo/repo#15
        And the record names the triggering gh_event and delivery id
        And session.registered is recorded for the new session
    Requirement: docs/specs/issue-50/requirements.md#R1
    """
    start, events, _ = stack
    port, _ = start(register_session=False, spawn_on_unmatched="always")
    assert post_webhook(port, "issue_comment", issue_comment_payload("new"), "d-s") == 202
    assert wait_until(lambda: events(types=["session.spawned"]))
    (spawned,) = events(types=["session.spawned"])
    assert spawned["work_item"] == REF
    assert spawned["gh_event"] == "issue_comment"
    assert spawned["delivery_id"] == "d-s"
    assert spawned["harness_session_id"] == "spawned-1"
    assert events(types=["session.registered"], work_item=REF)


def test_events_command_reads_the_live_trail(stack, capsys):
    """
    Feature: End-to-end observability of the-loop's CLI actions
    Scenario: `the-loop events` answers questions about a work item's history
        Given a receiver that processed an event for github:octo/repo#15
        When `the-loop events --file <log> --work-item github:octo/repo#15` runs
        Then it prints that item's dispatch trail
        And `--format json` emits machine-readable records for agents
    Requirement: docs/specs/issue-50/requirements.md#R4
    """
    start, events, log_path = stack
    port, _ = start()
    assert post_webhook(port, "issue_comment", issue_comment_payload("q"), "d-q") == 202
    assert wait_until(lambda: events(types=["dispatch.succeeded"]))
    assert main(["events", "--file", str(log_path), "--work-item", REF]) == 0
    out = capsys.readouterr().out
    assert "dispatch.succeeded" in out
    assert (
        main(["events", "--file", str(log_path), "--format", "json", "--type",
              "dispatch.*"])
        == 0
    )
    records = json.loads(capsys.readouterr().out)
    assert {r["event"] for r in records} >= {"dispatch.queued", "dispatch.succeeded"}
