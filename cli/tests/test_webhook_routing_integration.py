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

    def __call__(
        self,
        tmux=None,
        registry=None,
        events=None,
        tmux_config=None,
        **routing_overrides,
    ):
        tmux = tmux if tmux is not None else FakeTmux()
        registry = registry or SessionRegistry(self._tmp_path / "sessions")
        if tmux_config is not None:
            # Maps to RoutingConfig.tmux — named apart because the positional
            # `tmux` here is the runner double.
            routing_overrides["tmux"] = tmux_config
        config = RoutingConfig(
            dispatch_timeout_seconds=30,
            spawn_workdir=str(self._tmp_path),
            # An accepted control command records on the portable work-item
            # record, and `RoutingConfig`'s default is the process's own
            # `.the-loop/portable` — i.e. this repository's. Point it at the
            # test's tmp path so a control scenario cannot write into the
            # checkout it is running from.
            portable_dir=str(self._tmp_path / "portable"),
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

    @property
    def dispatcher(self):
        """The dispatcher behind the receiver started last.

        The call returns what nearly every test wants — port, registry, tmux. A
        test that needs a dispatch's *outcome* rather than its attempt (whether a
        failed delivery id has been released for retry, say) needs the dispatcher
        itself, and reaches it here instead of widening that tuple everywhere.
        """
        return self.started[-1][1]


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
    # Wait for the failure to be RECORDED, not for the paste that failed. The
    # dispatcher releases the delivery id after the failed deliver, on its own
    # thread, and the re-POST below is deduped away until it does — so waiting on
    # `tmux.delivers` and sleeping over the gap is a race the loaded machine wins
    # (issue-251).
    assert wait_until(lambda: "e-1" not in server_factory.dispatcher.deduper)
    assert len(tmux.delivers) == 1
    # Failure is isolated: the delivery is not marked processed...
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


def test_pr_comment_reaches_the_linked_issues_work_item(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: A comment on a labelled PR reaches the linked issue's one session
        Given a session registered for github:octo/repo#15
        And a labelled PR 16 in the SAME repository whose body closes issue 15
        And spawnOnUnmatched: labeled (so an unmatched PR event would spawn)
        When a conversation comment is posted on PR 16
        Then it is delivered into issue 15's own session
        And no second session is spawned into issue 15's working tree
        And no second work-item record is created for the PR's own ref
        And the PR is still recorded as delivering issue 15
    Requirement: docs/specs/issue-93/bugfix.md#AC4, docs/specs/issue-172/bugfix.md#R2,
        docs/specs/issue-253/bugfix.md#R1
    """
    port, registry, tmux = server_factory(
        spawn_on_unmatched="labeled", auto_execute_label=AUTO_LABEL
    )
    register(registry, tmp_path)

    assert (
        post_webhook(port, "issue_comment", pr_conversation_comment_payload(), "pr-c-1")
        == 202
    )

    assert wait_until(lambda: len(tmux.delivers) == 1)
    ((ref, prompt),) = tmux.delivers
    assert ref == REF  # the work item's own session — one owner, one tree
    assert "please rerun CI" in prompt
    assert tmux.spawns == []
    assert registry.find_by_work_item("github:octo/repo#16") is None  # no record
    record = registry.find_by_work_item(REF)
    assert record is not None
    assert [pr.work_item.ref for pr in record.pull_requests] == ["github:octo/repo#16"]


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


# -- durable PR → session bindings (issue-172) --------------------------------

PR_REF = "github:octo/repo#16"


def pr_comment_payload(body, pr_body="", number=16, repo="octo/repo"):
    """A comment on a PR — GitHub delivers it as ``issue_comment``.

    ``pr_body`` is the **PR description**, which is where the closing keyword
    lives; emptying it is how these scenarios remove the linkage without touching
    anything else. ``repo`` puts the pull request in another repository, which is
    the boundary the `sessionPerPr` modes disagree about (issue-183, issue-260).
    """
    return {
        "action": "created",
        "repository": {"full_name": repo},
        "issue": {
            "number": number,
            "body": pr_body,
            "pull_request": {"html_url": f"https://github.com/{repo}/pull/{number}"},
        },
        "comment": {"body": body, "user": {"login": "octocat"}},
        "sender": {"login": "octocat"},
    }


def test_pr_event_still_reaches_its_work_item_after_the_link_is_removed(
    server_factory, tmp_path
):
    """
    Feature: Webhook event routing
    Scenario: A PR event still reaches its work item after the linkage is removed
        Given a session registered for github:octo/repo#15
        And a comment on PR 16 whose description declares "Closes #15"
        When that comment routes, PR 16 is recorded on issue 15's session record
        And when a second comment arrives on PR 16 with the closing keyword gone
        Then it is still delivered into issue 15's session, off the recorded
             binding alone — the derivation the ticket describes as fragile is
             never consulted again
        And no work-item record is ever created for the PR's own ref
    Requirement: docs/specs/issue-172/bugfix.md#R5 (R2.1, R1.1, R5.1),
        docs/specs/issue-253/bugfix.md#R1
    """
    port, registry, tmux = server_factory()
    register(registry, tmp_path)

    # Step 3 of the ticket's reproduction: the linkage is present. The routing
    # decision now leaves a trace — the PR on the record.
    assert (
        post_webhook(
            port,
            "issue_comment",
            pr_comment_payload("please rerun CI", pr_body="Closes #15"),
            "link-1",
        )
        == 202
    )
    assert wait_until(lambda: len(tmux.delivers) == 1)
    record = registry.find_by_work_item(REF)
    assert record is not None
    assert [pr.work_item.ref for pr in record.pull_requests] == [PR_REF]

    # Steps 4 and 5: the Development-panel link is gone, the closing keyword is
    # edited out — derivation fails exactly as the ticket describes, and the
    # recorded binding is still what carries the event to the work item.
    assert (
        post_webhook(
            port,
            "issue_comment",
            pr_comment_payload("and again please", pr_body=""),
            "link-2",
        )
        == 202
    )
    assert wait_until(lambda: len(tmux.delivers) == 2)
    assert [ref for ref, _ in tmux.delivers] == [REF, REF]
    assert "and again please" in tmux.delivers[1][1]
    assert tmux.spawns == []  # never a second session in the work item's tree
    assert registry.find_by_work_item(PR_REF) is None  # no record for the PR


def test_a_recorded_pr_does_not_suppress_a_work_item_the_linkage_still_finds(
    server_factory, tmp_path
):
    """
    Feature: Webhook event routing
    Scenario: A recorded PR adds a resolution and never removes one
        Given sessions registered for issues 15 and 20
        And PR 16 already recorded on issue 15's record
        When a comment arrives on PR 16 whose description now declares "Closes #20"
        Then both work items' records match it — the derived one and the recorded
        one — so a deliberate re-link is loud, never silently lost
    Requirement: docs/specs/issue-172/bugfix.md#R2 (R2.5)
    """
    from the_loop.webhook.dispatcher import TmuxConfig

    # Collapsed mode keeps this scenario's assertion sharp: both WORK ITEMS see
    # the event. (Under a splitting mode each record would race to own the PR's
    # one `loop-<slug>` tmux name; the second falls back to its work-item
    # session.)
    port, registry, tmux = server_factory(
        tmux_config=TmuxConfig(session_per_pr="never")
    )
    register(registry, tmp_path)
    register(registry, tmp_path, ref="github:octo/repo#20", session_id="sess-2")
    registry.link_pull_request(REF, PR_REF)

    assert (
        post_webhook(
            port,
            "issue_comment",
            pr_comment_payload("re-linked", pr_body="Closes #20"),
            "link-3",
        )
        == 202
    )
    assert wait_until(lambda: len(tmux.delivers) == 2)
    assert {ref for ref, _ in tmux.delivers} == {REF, "github:octo/repo#20"}


CROSS_PR_REF = "github:octo/other#16"


@pytest.mark.parametrize(
    "frozen, receives",
    [(None, CROSS_PR_REF), ("never", REF)],
)
def test_the_work_items_own_selection_decides_which_session_a_pr_talks_to(
    server_factory, tmp_path, frozen, receives
):
    """
    Feature: Webhook event routing
    Scenario: A work item's phase-selection answer overrides the operator's default
        Given a daemon configured `sessionPerPr: cross-repository`
        And issue 15 with a live conversation for its pull request in octo/other
        When a comment arrives on that pull request
        Then it is delivered into the pull request's own conversation
        But when issue 15's frozen phase selection says `never`
        Then the same comment is delivered into issue 15's own session instead
    Requirement: docs/specs/issue-260/requirements.md#R2 (R2.1)
    """
    from the_loop.webhook.dispatcher import TmuxConfig

    port, registry, tmux = server_factory(
        tmux_config=TmuxConfig(session_per_pr="cross-repository")
    )
    register(registry, tmp_path)
    endpoint = registry.link_pull_request(REF, CROSS_PR_REF)
    assert endpoint is not None
    # Already worked once: the endpoint has a conversation, so the routing
    # decision is visible at the tmux seam instead of being hidden behind the
    # "no checkout, no session" decline every mode shares.
    endpoint.tmux_target = "loop-github-octo-other-16"
    endpoint.harness_session_id = "pr-sess"
    registry.save_endpoint(REF, endpoint)
    if frozen is not None:
        server_factory.dispatcher.control_store.record_frozen_graph(
            REF, {"sessionPerPr": frozen}
        )

    assert (
        post_webhook(
            port,
            "issue_comment",
            pr_comment_payload(
                "please rebase", pr_body="Closes octo/repo#15", repo="octo/other"
            ),
            f"sel-{frozen}",
        )
        == 202
    )
    assert wait_until(lambda: len(tmux.delivers) == 1)
    assert tmux.delivers[0][0] == receives
    assert tmux.spawns == []


def test_spawning_for_a_linked_issue_records_the_binding(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: The PR is recorded at the moment the session is spawned
        Given an empty registry and spawnOnUnmatched: always
        When a comment arrives on PR 16 whose description declares "Closes #15"
        Then a session is spawned against issue 15, not the PR
        And the binding PR 16 -> issue 15 is recorded
    Requirement: docs/specs/issue-172/bugfix.md#R1 (R1.2)
    """
    port, registry, tmux = server_factory(spawn_on_unmatched="always")
    assert (
        post_webhook(
            port,
            "issue_comment",
            pr_comment_payload("start here", pr_body="Closes #15"),
            "link-4",
        )
        == 202
    )

    # Wait for the linkage too, not just for the record to exist: the pull
    # request is recorded against the session after the session itself is, so a
    # wait on the record alone can return between the two writes.
    def linked():
        record = registry.find_by_work_item(REF)
        return record is not None and [
            pr.work_item.ref for pr in record.pull_requests
        ] == [PR_REF]

    assert wait_until(linked)
    ((ref, _, _, _),) = tmux.spawns
    assert ref == REF  # spawned against the issue, not the PR


def test_a_stop_on_an_unlinked_pr_stops_the_bound_session(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: A control command on a PR resolves through the recorded PR list
        Given a session registered for issue 15 and PR 16 recorded on it
        When an authorized user comments "the-loop stop" on PR 16
        And the PR no longer declares any closing keyword
        Then issue 15's session is closed
    Requirement: docs/specs/issue-172/bugfix.md#R2 (R2.7)
    """
    # The control path re-checks authorization against the *dispatcher's* config,
    # more strictly than the ingress guard — so this fixture names the actor there
    # as well as on the router.
    port, registry, tmux = server_factory(authorized_users=["octocat"])
    register(registry, tmp_path)
    registry.link_pull_request(REF, PR_REF)

    assert (
        post_webhook(
            port, "issue_comment", pr_comment_payload("the-loop stop"), "link-5"
        )
        == 202
    )
    assert wait_until(lambda: registry.find_by_work_item(REF) is None)
    assert tmux.delivers == []  # a command is executed, never forwarded


def test_a_pr_close_matched_through_a_binding_leaves_the_session_open(
    server_factory, tmp_path
):
    """
    Feature: Webhook event routing
    Scenario: Merging one PR ends its endpoint, not the work item
        Given a session registered for issue 15 and PR 16 recorded on it
        When PR 16 is closed and no longer declares a closing keyword
        Then the PR's own endpoint is closed
        And issue 15's session is left active, because a work item may be
             delivered by several PRs
    Requirement: docs/specs/issue-172/bugfix.md#R3 (R3.1)
    """
    port, registry, tmux = server_factory(events=["pull_request"])
    register(registry, tmp_path)
    endpoint = registry.link_pull_request(REF, PR_REF)
    assert endpoint is not None
    endpoint.tmux_target = "loop-github-octo-repo-16"
    registry.save_endpoint(REF, endpoint)

    payload = {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "pull_request": {"number": 16, "merged": True, "head": {"ref": "topic"}},
        "sender": {"login": "octocat"},
    }
    assert post_webhook(port, "pull_request", payload, "link-6") == 202

    def endpoint_closed():
        record = registry.find_by_work_item(REF)
        return record is not None and all(not pr.is_live for pr in record.pull_requests)

    assert wait_until(endpoint_closed)  # the PR's own session ended with it...
    session = registry.find_by_work_item(REF)
    assert session is not None and session.is_live  # issue-101, unchanged
    assert tmux.delivers == [] and tmux.spawns == []


def test_a_pr_with_its_own_session_is_still_auto_closed(server_factory, tmp_path):
    """
    Feature: Webhook event routing
    Scenario: A PR that is its own work item still ends when it closes
        Given a session registered against PR 16 itself
        When PR 16 is closed
        Then that session is auto-closed
    Requirement: docs/specs/issue-172/bugfix.md#R3 (R3.2)
    """
    port, registry, tmux = server_factory(events=["pull_request"])
    register(registry, tmp_path, ref=PR_REF, session_id="sess-pr")

    payload = {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "pull_request": {"number": 16, "merged": True, "head": {"ref": "topic"}},
        "sender": {"login": "octocat"},
    }
    assert post_webhook(port, "pull_request", payload, "link-7") == 202
    assert wait_until(lambda: registry.find_by_work_item(PR_REF) is None)


def test_receiver_routing_follows_the_config(tmp_path, monkeypatch):
    """
    Feature: Webhook event routing
    Scenario: Routing is opt-in on the receiver
        Given the receiver's options resolved from the CLI config
        When routing.enabled is true or false
        Then the resolved `route` option follows it — the command flag it used
             to be died with the gh-webhook command (issue-228, PR #229 review)
    Requirement: docs/specs/issue-15/requirements.md#R3
    """
    from the_loop.webhook import daemon as webhook_daemon

    cfg = tmp_path / "config.yaml"
    monkeypatch.setattr(webhook_daemon, "_config_path", lambda: cfg)
    cfg.write_text("routing:\n  enabled: true\n")
    assert webhook_daemon.default_options().route is True
    cfg.write_text("routing:\n  enabled: false\n")
    assert webhook_daemon.default_options().route is False
    cfg.write_text("webhooks: {}\n")
    assert webhook_daemon.default_options().route is False
