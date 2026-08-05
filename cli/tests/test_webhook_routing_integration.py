"""Integration tests: signed webhook POST → router → dispatcher → tmux session.

Every test here drives a *real* signed HTTP POST into a live receiver and
asserts on what the tmux runner was actually asked to do — spawn a session, or
paste a prompt into a live one — i.e. "was the harness triggered, and how", not
just the pure routing functions (those are in ``test_routing.py``). The
observable seam is an injected FakeTmux (issue-156): ``tmux.delivers`` carries
each delivered prompt, ``tmux.spawns`` each spawned session, so prompt-content
assertions read the full text (a stub tmux binary only sees argv — the pasted
buffer travels via a deleted tempfile; that end-to-end path is
``test_tmux_runner_integration.py``).

Feature: Webhook event routing
Requirement: docs/specs/issue-15/requirements.md#R3
"""

import hashlib
import hmac
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from conftest import FakeTmux, StubInteractiveAdapter
from the_loop.control import ControlConfig
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook import serve
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import Router

SECRET = "s3cret"
REF = "github:octo/repo#15"
ROUTED_EVENTS = ["issue_comment", "pull_request_review_comment"]


def wait_until(predicate, timeout=5.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class ServerFactory:
    """Builds live receivers wired to a FakeTmux-backed dispatcher.

    Call it (``**routing_overrides``) to start a server → ``(port, registry,
    tmux)``. Pass ``tmux=FakeTmux(delay=…)`` (or a knob-tweaked instance) to
    shape delivery behaviour; its ``delivers``/``spawns`` record what the
    harness sessions were actually asked to do. Servers are torn down by the
    fixture.
    """

    def __init__(self, tmp_path):
        self._tmp_path = tmp_path
        self.started = []

    def __call__(self, tmux=None, registry=None, events=None, **routing_overrides):
        tmux = tmux if tmux is not None else FakeTmux()
        registry = registry or SessionRegistry(self._tmp_path / "sessions")
        config = RoutingConfig(
            dispatch_timeout_seconds=30,
            spawn_workdir=str(self._tmp_path),
            # Pre-issue-106 spawn behaviour (the start gate has its own tests).
            **{
                "control": ControlConfig(require_start_command=False),
                **routing_overrides,
            },
        )
        dispatcher = Dispatcher(
            registry=registry,
            adapters={"claude": StubInteractiveAdapter()},
            config=config,
            tmux_runner=tmux,
        )
        router = Router(
            events=ROUTED_EVENTS if events is None else events,
            deduper=dispatcher.deduper,
            auto_execute_label=config.auto_execute_label,
            authorized_users=["octocat"],  # the acting user in these fixtures
        )

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
        return httpd.server_address[1], registry, tmux


@pytest.fixture()
def server_factory(tmp_path):
    factory = ServerFactory(tmp_path)
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
    item = WorkItemRef.parse(ref)
    registry.register(
        Session(
            work_item=item,
            harness="claude",
            harness_session_id=session_id,
            cwd=str(tmp_path),
            tmux_target=f"loop-{item.slug}",
        )
    )


def test_idle_session_is_resumed_on_event(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: An idle registered session is resumed when its event arrives
        Given a running receiver and a session registered for github:octo/repo#15
        And the harness is not currently doing any work for that item
        When a signed issue_comment webhook for issue 15 is POSTed
        Then the prompt is delivered into that session's tmux session
        And the prompt embeds the comment body as untrusted data
        And the registry records the processed delivery id
    Requirement: docs/specs/issue-15/requirements.md#R3 (R3.2, R4.2, R5.1)
    """
    port, registry, tmux = server_factory()
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
    ((ref, prompt),) = tmux.delivers
    assert ref == REF
    assert "CI is red, please fix" in prompt
    assert "UNTRUSTED" in prompt
    assert tmux.spawns == []  # delivered into the existing session, not a new one


def test_unmatched_event_is_dropped_by_default(server_factory):
    """
    Feature: Webhook event routing
    Scenario: An event with no registered work item is dropped
        Given a running receiver with an empty registry (spawnOnUnmatched: never)
        When a signed issue_comment webhook is POSTed
        Then the receiver acknowledges with 202
        And nothing is delivered to or spawned in tmux
    Requirement: docs/specs/issue-15/requirements.md#R3 (R3.3)
    """
    port, _, tmux = server_factory()
    assert (
        post_webhook(port, "issue_comment", issue_comment_payload("anyone?"), "d-2")
        == 202
    )
    time.sleep(0.3)  # give a would-be dispatch time to (wrongly) happen
    assert tmux.delivers == [] and tmux.spawns == []


def test_unmatched_event_spawns_session_when_configured(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: An event with no work item spawns a session when configured
        Given a running receiver with spawnOnUnmatched: always and an empty registry
        When a signed issue_comment webhook for issue 15 is POSTed
        Then a fresh tmux session is spawned (not a resume of an old conversation)
        And the new session is registered with a pre-assigned harness id
    Requirement: docs/specs/issue-15/requirements.md#R3 (R3.3, R4.4)
    """
    port, registry, tmux = server_factory(spawn_on_unmatched="always")
    assert (
        post_webhook(port, "issue_comment", issue_comment_payload("new work"), "d-3")
        == 202
    )
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)
    ((ref, _, cwd, resume),) = tmux.spawns
    assert ref == REF
    assert resume is False  # spawned fresh, not resumed
    assert cwd == str(tmp_path)  # spawned in the configured workdir
    session = registry.find_by_work_item(REF)
    assert session is not None and session.harness_session_id  # pre-assigned uuid
    assert session.tmux_target == "loop-github-octo-repo-15"


def test_busy_session_queues_second_event_and_preserves_order(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: A second event for a busy session waits and runs after the first
        Given a session whose tmux delivery takes ~0.2s per event
        When two issue_comment webhooks for the same item arrive back-to-back
        Then the prompts are delivered twice, in arrival order
        And the deliveries never overlap (one at a time per session)
    Requirement: docs/specs/issue-15/requirements.md#R3 (R5.2)
    """
    port, registry, tmux = server_factory(tmux=FakeTmux(delay=0.2))
    register(registry, tmp_path)
    assert (
        post_webhook(port, "issue_comment", issue_comment_payload("first"), "b-1")
        == 202
    )
    assert (
        post_webhook(port, "issue_comment", issue_comment_payload("second"), "b-2")
        == 202
    )
    assert wait_until(lambda: len(tmux.delivers) == 2, timeout=8.0)
    (_, first), (_, second) = tmux.delivers  # record is append-order = dispatch order
    assert "first" in first and "second" in second
    # Serialized: the second delivery did not start until the first had ended.
    assert tmux.max_in_flight == 1


def test_events_for_different_items_run_in_parallel(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: Events for different work items dispatch concurrently
        Given two sessions registered for two different work items
        And a tmux delivery that takes ~0.2s per event
        When an event arrives for each, back-to-back
        Then both deliveries overlap in time (multiple sessions per executor)
    Requirement: docs/specs/issue-15/requirements.md#R3 (R5.1, R5.3)
    """
    port, registry, tmux = server_factory(tmux=FakeTmux(delay=0.2))
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
    assert wait_until(lambda: len(tmux.delivers) == 2, timeout=8.0)
    # Overlap: both deliveries were in flight together → they ran concurrently.
    assert tmux.max_in_flight == 2


def test_duplicate_delivery_is_processed_at_most_once(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: A redelivered webhook does not double-trigger the session
        Given a session registered for github:octo/repo#15
        When the same delivery id is POSTed twice
        Then the prompt is delivered into the tmux session exactly once
    Requirement: docs/specs/issue-15/requirements.md#R3 (R3.4)
    """
    port, registry, tmux = server_factory()
    register(registry, tmp_path)
    payload = issue_comment_payload("one event, two deliveries")
    assert post_webhook(port, "issue_comment", payload, "dup-9") == 202
    assert post_webhook(port, "issue_comment", payload, "dup-9") == 202
    assert wait_until(lambda: len(tmux.delivers) >= 1)
    time.sleep(0.3)
    assert len(tmux.delivers) == 1


def test_delivery_error_is_isolated_and_redelivery_retries(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: A failed tmux delivery is logged and the delivery can be retried
        Given a tmux delivery that fails transiently (the paste errors)
        When an event is POSTed and the delivery fails
        Then the delivery id is NOT recorded (so GitHub can redeliver)
        And re-POSTing the same delivery triggers the delivery again
        And the receiver stays alive throughout (still returns 202)
    Requirement: docs/specs/issue-15/requirements.md#R3 (error handling)
    """
    tmux = FakeTmux()
    tmux.deliver_ok = False  # every paste fails transiently
    port, registry, _ = server_factory(tmux=tmux)
    register(registry, tmp_path)
    assert (
        post_webhook(port, "issue_comment", issue_comment_payload("boom"), "e-1") == 202
    )
    assert wait_until(lambda: len(tmux.delivers) == 1)
    # Failure is isolated: the delivery is not marked processed...
    time.sleep(0.2)
    found = registry.find_by_work_item(REF)
    assert found is not None and "e-1" not in found.recent_deliveries
    # ...so a redelivery of the same id is retried, not deduped away.
    assert (
        post_webhook(port, "issue_comment", issue_comment_payload("boom"), "e-1") == 202
    )
    assert wait_until(lambda: len(tmux.delivers) == 2)


def test_invalid_signature_is_rejected_before_routing(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: An event with a bad HMAC signature never reaches the harness
        Given a receiver with a configured secret and a registered session
        When a POST arrives with an incorrect X-Hub-Signature-256
        Then the receiver responds 401 and nothing reaches the tmux session
    Requirement: docs/specs/issue-15/requirements.md#R3 (security)
    """
    port, registry, tmux = server_factory()
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
    assert tmux.delivers == [] and tmux.spawns == []


def test_disabled_event_type_is_not_routed(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: An event type outside the configured list is ignored
        Given a receiver routing only issue_comment / pull_request_review_comment
        When a signed pull_request webhook arrives
        Then nothing is delivered into the tmux session
    Requirement: docs/specs/issue-15/requirements.md#R3 (R3.5)
    """
    port, registry, tmux = server_factory()
    register(registry, tmp_path)
    payload = {
        "action": "synchronize",
        "repository": {"full_name": "octo/repo"},
        "pull_request": {"number": 15, "head": {"ref": "main"}, "body": ""},
    }
    assert post_webhook(port, "pull_request", payload, "f-1") == 202
    time.sleep(0.3)
    assert tmux.delivers == [] and tmux.spawns == []


def pr_close_payload(number=16, branch="claude/github-issue-15-x"):
    return {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "pull_request": {
            "number": number,
            "head": {"ref": branch},
            "body": "Closes #15",
            "merged": True,
        },
    }


def test_pr_close_auto_closes_the_prs_own_session(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: A session registered against a PR auto-closes when that PR merges
        Given a session registered for github:octo/repo#16 (the PR is the work item)
        When a signed pull_request 'closed' webhook (merged) for PR 16 arrives
        Then the session is closed in the registry
        And nothing is delivered into the tmux session for the close event
    Requirement: docs/specs/issue-101/requirements.md#AC4
    """
    port, registry, tmux = server_factory(events=["pull_request"])
    pr_ref = "github:octo/repo#16"
    register(registry, tmp_path, ref=pr_ref)
    assert post_webhook(port, "pull_request", pr_close_payload(), "close-1") == 202
    assert wait_until(lambda: registry.find_by_work_item(pr_ref) is None)
    time.sleep(0.2)
    assert tmux.delivers == []  # auto-closed, never delivered into the conversation


def test_the_work_items_session_survives_its_first_pr_merging(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: The work item's session survives one of its PRs merging
        Given a session registered for github:octo/repo#15
        And PR 16, one of several PRs delivering that work item
        When a signed pull_request 'closed' (merged) webhook for PR 16 arrives
        Then the session for issue 15 is still active
        And nothing is delivered into its tmux session for the close event
        When a signed issues 'closed' webhook for issue 15 arrives
        Then the session is closed in the registry
    Requirement: docs/specs/issue-101/requirements.md#AC1
    """
    port, registry, tmux = server_factory(events=["pull_request", "issues"])
    register(registry, tmp_path)

    assert post_webhook(port, "pull_request", pr_close_payload(), "close-pr-1") == 202
    time.sleep(0.3)
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "active"  # work item is open
    assert tmux.delivers == []  # a close is never delivered into the conversation

    issue_closed = {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15, "state_reason": "completed"},
        "sender": {"login": "octocat"},
    }
    assert post_webhook(port, "issues", issue_closed, "close-issue-1") == 202
    assert wait_until(lambda: registry.find_by_work_item(REF) is None)
    assert tmux.delivers == []


def test_issue_close_auto_closes_session(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: A session auto-closes when its issue is closed
        Given a session registered for github:octo/repo#15
        When a signed issues 'closed' webhook for that issue arrives
        Then the session is closed in the registry
        And nothing is delivered into its tmux session for the close event
    Requirement: docs/specs/issue-94/requirements.md#R2
    """
    port, registry, tmux = server_factory(events=["issues"])
    register(registry, tmp_path)
    payload = {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15, "state_reason": "completed"},
        "sender": {"login": "octocat"},
    }
    assert post_webhook(port, "issues", payload, "iclose-1") == 202
    assert wait_until(lambda: registry.find_by_work_item(REF) is None)
    time.sleep(0.2)
    assert tmux.delivers == []  # closed, never delivered into the conversation


AUTO_LABEL = "the-loop: auto-execute"


def labeled_issue_event(number=15, label=AUTO_LABEL):
    return {
        "action": "labeled",
        "repository": {"full_name": "octo/repo"},
        "label": {"name": label},
        "issue": {"number": number, "labels": [{"name": label}]},
        "sender": {"login": "octocat"},
    }


def test_auto_execute_label_spawns_a_session(server_factory):
    """
    Feature: Webhook event routing
    Scenario: Adding the auto-execute label spawns a session and starts work
        Given a receiver with spawnOnUnmatched: labeled and an empty registry
        When the 'the-loop: auto-execute' label is added to issue 15
        Then a fresh tmux session is spawned and registered for the issue
        And the spawn prompt kicks off /the-loop:work-on for that work item
    Requirement: docs/specs/issue-15/requirements.md#R6
    """
    port, registry, tmux = server_factory(
        events=["issues"], spawn_on_unmatched="labeled", auto_execute_label=AUTO_LABEL
    )
    assert post_webhook(port, "issues", labeled_issue_event(), "lbl-1") == 202
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)
    ((ref, prompt, _, resume),) = tmux.spawns
    assert ref == REF
    assert resume is False  # spawned fresh, not resumed
    assert "/the-loop:work-on" in prompt
    session = registry.find_by_work_item(REF)
    assert session is not None and session.harness_session_id  # pre-assigned uuid
    assert session.tmux_target == "loop-github-octo-repo-15"


def pr_conversation_comment_payload(pr_number=16, body="Closes #15"):
    """A PR conversation comment — GitHub delivers these as ``issue_comment``
    with a ``pull_request`` key on the issue object and the PR's own labels."""
    return {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {
            "number": pr_number,
            "body": body,
            "labels": [{"name": AUTO_LABEL}],
            "pull_request": {"html_url": "https://github.com/octo/repo/pull/16"},
        },
        "comment": {"body": "please rerun CI"},
        "sender": {"login": "octocat"},
    }


def test_pr_comment_reuses_the_linked_issues_session(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: A comment on a labelled PR reaches the linked issue's session
        Given a session registered for github:octo/repo#15
        And a labelled PR 16 whose body closes issue 15
        And spawnOnUnmatched: labeled (so an unmatched PR event would spawn)
        When a conversation comment is posted on PR 16
        Then the comment is delivered into issue 15's existing tmux session
        And no second session is registered for the PR's own ref
    Requirement: docs/specs/issue-93/bugfix.md#AC4
    """
    port, registry, tmux = server_factory(
        spawn_on_unmatched="labeled", auto_execute_label=AUTO_LABEL
    )
    register(registry, tmp_path)

    assert (
        post_webhook(port, "issue_comment", pr_conversation_comment_payload(), "pr-c-1")
        == 202
    )

    def delivery_recorded():
        found = registry.find_by_work_item(REF)
        return found is not None and "pr-c-1" in found.recent_deliveries

    assert wait_until(delivery_recorded)
    ((ref, prompt),) = tmux.delivers  # exactly one dispatch — a delivery
    assert ref == REF
    assert "please rerun CI" in prompt
    assert tmux.spawns == []  # ...not a spawn
    assert registry.find_by_work_item("github:octo/repo#16") is None


def test_new_issue_without_label_does_nothing(server_factory):
    """
    Feature: Webhook event routing
    Scenario: A new issue without the auto-execute label is ignored
        Given a receiver with spawnOnUnmatched: labeled and an empty registry
        When an issue is opened WITHOUT the auto-execute label
        Then the receiver acknowledges but no session is spawned
    Requirement: docs/specs/issue-15/requirements.md#R6
    """
    port, registry, tmux = server_factory(
        events=["issues"], spawn_on_unmatched="labeled", auto_execute_label=AUTO_LABEL
    )
    payload = {
        "action": "opened",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15, "labels": []},
    }
    assert post_webhook(port, "issues", payload, "open-1") == 202
    time.sleep(0.3)
    assert tmux.spawns == [] and tmux.delivers == []
    assert registry.find_by_work_item(REF) is None


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
