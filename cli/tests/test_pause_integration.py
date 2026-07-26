"""Integration tests: pausing a work item on both ingress paths (issue-98).

These drive the *real* poller + provider + dispatcher (like
``test_poller_integration.py``) and the *real* dispatcher for webhook-shaped
events, so they prove that a pause — from the local ledger or from the GitHub
label — stops work on exactly one work item without ending its session, and
that resuming picks it back up.

Feature: pause and resume the-loop on a single work item
"""

import json
import subprocess
import threading
import time

from the_loop.harness import DispatchResult
from the_loop.poller import (
    GhClient,
    GitHubPollProvider,
    PollConfig,
    Poller,
    PollState,
    parse_repos,
)
from the_loop.sessions import PauseStore, Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent

LABEL = "the-loop: auto-execute"
PAUSED_LABEL = "the-loop: paused"
REF = "github:octo/repo#15"


def wait_until(predicate, timeout=5.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class FakeAdapter:
    """In-process HarnessAdapter double recording spawns and resumes."""

    name = "claude"

    def __init__(self):
        self.spawns = []
        self.resumes = []
        self._lock = threading.Lock()

    def is_available(self):
        return True

    def spawn(self, work_item, prompt, cwd, timeout=None):
        with self._lock:
            self.spawns.append((work_item.ref, prompt, cwd))
        return DispatchResult(ok=True, session_id="spawned-1")

    def resume(self, session, prompt, timeout=None):
        with self._lock:
            self.resumes.append((session.work_item.ref, prompt))
        return DispatchResult(ok=True, session_id=session.harness_session_id)


class GhState:
    """Mutable canned gh responses shared across poll cycles."""

    def __init__(self):
        self.labels = [{"name": LABEL}]
        self.comments = []
        self.item_state = {"number": 15, "state": "open"}
        # `/issues/N/events` — who added/removed which label (issue-98 review).
        self.label_events = []

    def label_event(self, action, actor, label=PAUSED_LABEL):
        self.label_events.append(
            {"event": action, "actor": {"login": actor}, "label": {"name": label}}
        )

    @property
    def issues(self):
        return [
            {
                "number": 15,
                "title": "i",
                "labels": self.labels,
                "url": "u",
                "author": {"login": "octocat"},
            }
        ]

    def runner(self, cmd, **kwargs):
        if cmd[1] == "api":
            path = cmd[-1]
            if path.endswith("/events"):
                return subprocess.CompletedProcess(
                    cmd, 0, json.dumps(self.label_events), ""
                )
            return subprocess.CompletedProcess(cmd, 0, json.dumps(self.item_state), "")
        sub = (cmd[1], cmd[2])
        if sub == ("issue", "list"):
            out = json.dumps(self.issues if not self.closed else [])
        elif sub == ("pr", "list"):
            out = json.dumps([])
        else:
            out = json.dumps({"comments": self.comments})
        return subprocess.CompletedProcess(cmd, 0, out, "")

    @property
    def closed(self):
        return self.item_state.get("state") == "closed"

    def close_issue(self):
        self.item_state = {"number": 15, "state": "closed"}


def _comment(cid, body):
    return {
        "id": cid,
        "body": body,
        "author": {"login": "octocat"},
        "createdAt": "",
        "url": "u",
    }


def _dispatcher(registry, adapter, config, pauses):
    # adapter intentionally unannotated so the in-process FakeAdapter double
    # satisfies Dict[str, HarnessAdapter] (mirrors test_poller_integration).
    return Dispatcher(
        registry=registry,
        adapters={"claude": adapter},
        config=config,
        pauses=pauses,
    )


def _make(tmp_path, gh_state):
    registry = SessionRegistry(tmp_path / "sessions")
    adapter = FakeAdapter()
    pauses = PauseStore(tmp_path / "paused.json", paused_label=PAUSED_LABEL)
    dispatcher = _dispatcher(
        registry,
        adapter,
        RoutingConfig(
            spawn_on_unmatched="labeled",
            paused_label=PAUSED_LABEL,
            pause_file=str(tmp_path / "paused.json"),
            # The dispatcher gates the label control on this list too — an empty
            # one fails closed, exactly like every other authz check.
            authorized_users=["octocat"],
        ),
        pauses,
    )
    provider = GitHubPollProvider(
        parse_repos(["octo/repo"]),
        LABEL,
        monitor_issues=True,
        monitor_prs=False,
        gh=GhClient(runner=gh_state.runner),
    )
    poller = Poller(
        providers=[provider],
        registry=registry,
        dispatcher=dispatcher,
        config=PollConfig(),
        state=PollState(tmp_path / "state.json"),
        authorized_users=["octocat"],
        pauses=pauses,
    )
    return registry, adapter, dispatcher, poller, pauses


def _issue_comment_event(body="please look", delivery="d-1", labels=None):
    payload = {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {
            "number": 15,
            "title": "i",
            "html_url": "u",
            "labels": labels if labels is not None else [{"name": LABEL}],
        },
        "comment": {"id": 1, "body": body, "user": {"login": "octocat"}},
    }
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id=delivery,
        work_items=[WorkItemRef.parse(REF)],
        payload=payload,
        labeled=False,
    )


def test_paused_item_is_not_spawned_and_resumes_cleanly(tmp_path):
    """Scenario: the poller ignores a paused work item, then picks it back up

    Given a labelled issue that the-loop has not spawned for
    And an operator pauses that work item
    When poll cycles run and a comment is added while it is paused
    Then no session is spawned and nothing is forwarded
    And when the work item is resumed the next comment IS delivered
    Requirement: docs/specs/issue-98/requirements.md#R3 (R3.2, R3.4, R4.2)
    """
    gh = GhState()
    registry, adapter, dispatcher, poller, pauses = _make(tmp_path, gh)
    pauses.pause(REF, reason="not ready")

    poller.poll_once()
    gh.comments = [_comment("IC_1", "while paused")]
    poller.poll_once()
    time.sleep(0.1)
    assert adapter.spawns == []
    assert registry.find_by_work_item(REF) is None

    # Resumed: the pause-era comment is already baselined (R3.4), so the item
    # simply spawns once, and a genuinely new comment reaches it.
    pauses.resume(REF)
    poller.poll_once()
    # Wait for the *registration*, not just the spawn call: the next cycle must
    # see the session, or it would (correctly) re-arm the spawn it can't see yet.
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)
    assert len(adapter.spawns) == 1
    assert adapter.resumes == []

    gh.comments = [_comment("IC_1", "while paused"), _comment("IC_2", "after resume")]
    poller.poll_once()
    assert wait_until(lambda: len(adapter.resumes) == 1)
    dispatcher.stop()
    assert "after resume" in adapter.resumes[0][1]


def test_pausing_a_worked_item_stops_delivery_without_closing_it(tmp_path):
    """Scenario: pausing an item with a live session leaves the session alone

    Given a labelled issue with an active session
    When the work item is paused and a new comment arrives
    Then nothing is delivered to the session
    And the session is still registered as active
    Requirement: docs/specs/issue-98/requirements.md#R3 (R3.2, R3.5)
    """
    gh = GhState()
    registry, adapter, dispatcher, poller, pauses = _make(tmp_path, gh)

    poller.poll_once()
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)

    pauses.pause(REF)
    gh.comments = [_comment("IC_1", "hello?")]
    poller.poll_once()
    time.sleep(0.1)
    dispatcher.stop()

    assert adapter.resumes == []
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "active"


def test_only_an_authorized_labeller_can_pause_the_poller(tmp_path):
    """Scenario: the paused label pauses only when an authorized person added it

    Given a labelled issue that also carries the paused label
    When an unauthorized user added that label
    Then the item is not paused and a session is still spawned
    And when an authorized user adds it, the next cycle pauses the item
    Requirement: docs/specs/issue-98/requirements.md#R5 (R5.1, R5.6)
    """
    gh = GhState()
    gh.labels = [{"name": LABEL}, {"name": PAUSED_LABEL}]
    gh.label_event("labeled", "a-stranger")
    registry, adapter, dispatcher, poller, pauses = _make(tmp_path, gh)

    poller.poll_once()
    assert wait_until(lambda: len(adapter.spawns) == 1)  # label ignored
    assert pauses.is_paused(REF) is False

    # The same label, now attributed to an authorized login, does pause it.
    gh.label_event("labeled", "octocat")
    poller._label_denials.clear()  # a fresh transition, not the refused one
    poller.poll_once()
    assert pauses.is_paused(REF) is True
    record = pauses.record(REF)
    assert record is not None and record.by == "octocat"

    gh.comments = [_comment("IC_1", "while paused")]
    poller.poll_once()
    time.sleep(0.1)
    dispatcher.stop()
    assert adapter.resumes == []


def test_an_unauthorized_label_removal_cannot_resume_the_poller(tmp_path):
    """Scenario: taking the label off without authorization leaves it paused

    Given an item paused because an authorized user added the label
    When an unauthorized user removes the label
    Then the item stays paused
    And an authorized removal resumes it
    Requirement: docs/specs/issue-98/requirements.md#R5 (R5.4)
    """
    gh = GhState()
    registry, adapter, dispatcher, poller, pauses = _make(tmp_path, gh)
    pauses.pause(REF, source="label", by="octocat")

    gh.labels = [{"name": LABEL}]  # label gone from the ticket
    gh.label_event("unlabeled", "a-stranger")
    poller.poll_once()
    assert pauses.is_paused(REF) is True  # unauthorized removal changes nothing

    gh.label_event("unlabeled", "octocat")
    poller._label_denials.clear()
    poller.poll_once()
    assert pauses.is_paused(REF) is False
    assert wait_until(lambda: len(adapter.spawns) == 1)  # picked back up
    dispatcher.stop()


def _label_event(action, actor, delivery, label=PAUSED_LABEL):
    """An `issues` labeled/unlabeled webhook — the shape GitHub sends."""
    return RoutedEvent(
        event="issues",
        action=action,
        delivery_id=delivery,
        work_items=[WorkItemRef.parse(REF)],
        payload={
            "action": action,
            "repository": {"full_name": "octo/repo"},
            "issue": {"number": 15, "title": "i", "html_url": "u", "labels": []},
            "label": {"name": label},
            "sender": {"login": actor},
        },
        labeled=False,
    )


def test_an_authorized_label_add_pauses_the_webhook_path(tmp_path):
    """Scenario: labelling an item pauses it — for an authorized labeller

    Given an active session for a work item
    When an authorized user adds the paused label
    Then the work item is paused and later events are not delivered
    Requirement: docs/specs/issue-98/requirements.md#R5 (R5.1, R5.2)
    """
    gh = GhState()
    registry, adapter, dispatcher, _poller, pauses = _make(tmp_path, gh)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="uuid-1",
            cwd=".",
        )
    )

    dispatcher.handle(_label_event("labeled", "octocat", "d-label"))
    assert pauses.is_paused(REF) is True
    record = pauses.record(REF)
    assert record is not None and record.by == "octocat"

    dispatcher.handle(_issue_comment_event(body="ignored", delivery="d-after"))
    time.sleep(0.1)
    dispatcher.stop()
    assert adapter.resumes == []


def test_an_unauthorized_labeller_cannot_pause_or_resume(tmp_path):
    """Scenario: the label is a control, and only authorized logins hold it

    Given an active session for a work item
    When an unauthorized user adds the paused label
    Then nothing is paused and its events are still delivered
    And when an unauthorized user removes an authorized pause, it stays paused
    Requirement: docs/specs/issue-98/requirements.md#R5 (R5.3, R5.4)
    """
    gh = GhState()
    registry, adapter, dispatcher, _poller, pauses = _make(tmp_path, gh)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="uuid-1",
            cwd=".",
        )
    )

    dispatcher.handle(_label_event("labeled", "a-stranger", "d-bad-label"))
    assert pauses.is_paused(REF) is False
    dispatcher.handle(_issue_comment_event(body="delivered", delivery="d-live"))
    # The refused label event is still an ordinary event for the session, so
    # assert on the comment reaching it rather than on a resume count.
    assert wait_until(lambda: any("delivered" in p for _, p in adapter.resumes))

    # An authorized pause, then an unauthorized attempt to lift it.
    dispatcher.handle(_label_event("labeled", "octocat", "d-good-label"))
    assert pauses.is_paused(REF) is True
    dispatcher.handle(_label_event("unlabeled", "a-stranger", "d-bad-unlabel"))
    assert pauses.is_paused(REF) is True  # the removal changed nothing

    dispatcher.handle(_label_event("unlabeled", "octocat", "d-good-unlabel"))
    assert pauses.is_paused(REF) is False
    dispatcher.stop()


def test_a_locally_paused_item_drops_webhook_events(tmp_path):
    """Scenario: the local ledger pauses the webhook path too

    Given an active session whose work item was paused from the CLI
    When an event for it arrives
    Then it is dropped, and delivered once the item is resumed
    Requirement: docs/specs/issue-98/requirements.md#R3 (R3.3, R4.2)
    """
    gh = GhState()
    registry, adapter, dispatcher, _poller, pauses = _make(tmp_path, gh)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="uuid-1",
            cwd=".",
        )
    )
    pauses.pause(REF)

    dispatcher.handle(_issue_comment_event(body="ignored", delivery="d-1"))
    time.sleep(0.1)
    assert adapter.resumes == []

    pauses.resume(REF)
    # Same delivery id: the paused drop released it, so this is not a duplicate.
    dispatcher.handle(_issue_comment_event(body="now please", delivery="d-1"))
    assert wait_until(lambda: len(adapter.resumes) == 1)
    dispatcher.stop()


def test_a_paused_item_that_ends_still_closes_its_session(tmp_path):
    """Scenario: pause stops work, never cleanup

    Given a paused work item with an active session
    When the issue is closed upstream and a poll cycle runs
    Then its session is closed
    Requirement: docs/specs/issue-98/requirements.md#R3 (R3.6)
    """
    gh = GhState()
    registry, adapter, dispatcher, poller, pauses = _make(tmp_path, gh)

    poller.poll_once()
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)
    pauses.pause(REF)

    gh.close_issue()
    poller.poll_once()
    assert wait_until(lambda: registry.find_by_work_item(REF) is None)
    dispatcher.stop()
    closed = registry.find_by_work_item(REF, include_closed=True)
    assert closed is not None and closed.status == "closed"


def test_a_pr_event_links_the_pr_to_the_issue_session(tmp_path):
    """Scenario: the table can link work item → PR

    Given an active session registered against an issue
    When a pull_request event for that work item is dispatched
    Then the session records the PR's ref and url
    Requirement: docs/specs/issue-98/requirements.md#R2 (R2.4)
    """
    gh = GhState()
    registry, adapter, dispatcher, _poller, _pauses = _make(tmp_path, gh)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="uuid-1",
            cwd=".",
        )
    )
    event = RoutedEvent(
        event="pull_request",
        action="synchronize",
        delivery_id="d-pr",
        work_items=[WorkItemRef.parse(REF)],
        payload={
            "action": "synchronize",
            "repository": {"full_name": "octo/repo"},
            "pull_request": {
                "number": 20,
                "title": "pr",
                "html_url": "https://github.com/octo/repo/pull/20",
                "labels": [],
                "head": {"ref": "issue-15"},
            },
        },
        labeled=False,
    )
    dispatcher.handle(event)
    assert wait_until(lambda: len(adapter.resumes) == 1)
    dispatcher.stop()

    session = registry.find_by_work_item(REF)
    assert session is not None
    assert session.pr_ref == "github:octo/repo#20"
    assert session.pr_url.endswith("/pull/20")
