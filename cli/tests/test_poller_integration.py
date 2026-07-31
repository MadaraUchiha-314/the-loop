"""Integration tests: gh poll → GitHub provider → dispatcher → harness spawn.

Unlike ``test_poller.py`` (which asserts on synthesised events via doubles),
these drive the *real* GitHub provider and the *real* Dispatcher — a poll cycle
actually spawns and registers a session and a later cycle actually resumes it —
so they prove the provider-agnostic poller reuses the webhook routing/dispatch
stack end to end, including the one-session-per-work-item guarantee.

Feature: Poll GitHub and spawn/route harness sessions
Requirement: docs/specs/issue-34/requirements.md#R1
"""

import json
import subprocess
import threading
import time

from the_loop.control import ControlConfig
from the_loop.announce import announcement_body
from the_loop.harness import DispatchResult
from the_loop.poller import (
    GhClient,
    GitHubPollProvider,
    PollConfig,
    Poller,
    PollState,
    parse_repos,
)
from the_loop.workitem import WorkItemStore
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig

LABEL = "the-loop: auto-execute"
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

    def __init__(self, spawn_id="spawned-1"):
        self.spawn_id = spawn_id
        self.spawns = []
        self.resumes = []
        self._lock = threading.Lock()

    def is_available(self):
        return True

    def spawn(self, work_item, prompt, cwd, timeout=None):
        with self._lock:
            self.spawns.append((work_item.ref, prompt, cwd))
        return DispatchResult(ok=True, session_id=self.spawn_id)

    def resume(self, session, prompt, timeout=None):
        with self._lock:
            self.resumes.append((session.work_item.ref, prompt))
        return DispatchResult(ok=True, session_id=session.harness_session_id)


class GhState:
    """Mutable canned gh responses shared across poll cycles."""

    def __init__(self):
        self.issues = [
            {
                "number": 15,
                "title": "i",
                "labels": [{"name": LABEL}],
                "url": "u",
                "author": {"login": "octocat"},
            }
        ]
        self.comments = []
        self.prs = []
        self.pr_comments = []
        # `gh api repos/…/issues/<n>` — the closure question (issue-94).
        self.item_state = {"number": 15, "state": "open"}
        self.list_fails = False
        self.state_fails = False
        self.api_calls = []

    def runner(self, cmd, **kwargs):
        if cmd[1] == "api":
            self.api_calls.append(cmd[2])
            if self.state_fails:
                return subprocess.CompletedProcess(cmd, 1, "", "HTTP 502")
            return subprocess.CompletedProcess(cmd, 0, json.dumps(self.item_state), "")
        sub = (cmd[1], cmd[2])
        if sub in (("issue", "list"), ("pr", "list")):
            if self.list_fails:
                return subprocess.CompletedProcess(cmd, 1, "", "gh exploded")
            out = json.dumps(self.issues if sub[0] == "issue" else self.prs)
        elif sub == ("pr", "view"):
            out = json.dumps({"comments": self.pr_comments})
        else:  # issue view --json comments
            out = json.dumps({"comments": self.comments})
        return subprocess.CompletedProcess(cmd, 0, out, "")

    def close_issue(self, merged=None):
        """Close issue #15 upstream: it leaves the listing and reports closed."""
        self.issues = []
        self.item_state = {"number": 15, "state": "closed"}
        if merged is not None:
            self.item_state["pull_request"] = {
                "merged_at": "2026-07-25T00:00:00Z" if merged else None
            }


def _comment(cid, body):
    return {
        "id": cid,
        "body": body,
        "author": {"login": "octocat"},
        "createdAt": "",
        "url": "u",
    }


def _dispatcher(registry, adapter, config):
    # adapter intentionally unannotated so the in-process FakeAdapter double
    # satisfies Dict[str, HarnessAdapter] (mirrors test_routing.make_dispatcher).
    return Dispatcher(registry=registry, adapters={"claude": adapter}, config=config)


def _make(tmp_path, gh_state, monitor_issues=True, monitor_prs=False):
    registry = SessionRegistry(tmp_path / "sessions")
    adapter = FakeAdapter()
    dispatcher = _dispatcher(
        registry,
        adapter,
        RoutingConfig(
            spawn_on_unmatched="labeled",
            # Pre-issue-106: the label alone spawns (the start gate has its own tests).
            control=ControlConfig(require_start_command=False),
        ),
    )
    provider = GitHubPollProvider(
        parse_repos(["octo/repo"]),
        LABEL,
        monitor_issues=monitor_issues,
        monitor_prs=monitor_prs,
        gh=GhClient(runner=gh_state.runner),
    )
    poller = Poller(
        providers=[provider],
        registry=registry,
        dispatcher=dispatcher,
        config=PollConfig(),
        state=PollState(WorkItemStore(tmp_path / "portable")),
        authorized_users=["octocat"],  # the fixture author (authz guard)
    )
    return registry, adapter, dispatcher, poller


def test_labeled_issue_spawns_a_registered_session_once(tmp_path):
    """Scenario: a labelled issue with no session gets one, and only one.

    Given a labelled issue with no registered session
    When two poll cycles run
    Then a single harness session is spawned and registered for it
    """
    registry, adapter, dispatcher, poller = _make(tmp_path, GhState())

    poller.poll_once()
    assert wait_until(lambda: len(adapter.spawns) == 1)
    poller.poll_once()  # registry now has it -> must not spawn again
    time.sleep(0.1)
    dispatcher.stop()

    assert len(adapter.spawns) == 1
    session = registry.find_by_work_item(REF)
    assert session is not None and session.harness_session_id == "spawned-1"
    _, prompt, _ = adapter.spawns[0]
    assert "/the-loop:work-on" in prompt and REF in prompt


def test_new_comment_after_spawn_resumes_same_session(tmp_path):
    """Scenario: a new comment on an already-worked item resumes its session.

    Given a labelled issue that already spawned a session
    When a new comment appears and the next poll cycle runs
    Then the existing session is resumed with the comment (no new spawn)
    """
    gh = GhState()
    gh.comments = [_comment("IC_1", "old")]
    registry, adapter, dispatcher, poller = _make(tmp_path, gh)

    poller.poll_once()  # spawn + baseline IC_1
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)

    gh.comments = [_comment("IC_1", "old"), _comment("IC_2", "the build is red")]
    poller.poll_once()  # forward IC_2 only
    assert wait_until(lambda: len(adapter.resumes) == 1)
    dispatcher.stop()

    assert len(adapter.spawns) == 1  # no duplicate spawn
    ref, prompt = adapter.resumes[0]
    assert ref == REF
    assert "the build is red" in prompt and "UNTRUSTED" in prompt


def test_comment_not_reforwarded_across_cycles(tmp_path):
    """Scenario: the same comment is delivered at most once.

    Given a session and a comment already forwarded
    When further poll cycles run with no new comments
    Then the comment is not resumed again (durable dedup)
    """
    gh = GhState()
    gh.comments = [_comment("IC_1", "baseline")]
    registry, adapter, dispatcher, poller = _make(tmp_path, gh)

    poller.poll_once()
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)
    gh.comments = [_comment("IC_1", "baseline"), _comment("IC_2", "fix it")]
    poller.poll_once()
    assert wait_until(lambda: len(adapter.resumes) == 1)
    poller.poll_once()  # no new comments
    poller.poll_once()
    time.sleep(0.1)
    dispatcher.stop()

    assert len(adapter.resumes) == 1  # IC_2 delivered exactly once


def test_the_daemons_own_announcement_is_not_forwarded(tmp_path):
    """Scenario: the-loop's session announcement never re-enters that session.

    Feature: Poll GitHub and route only human input into a session
    Given a labelled issue whose session the-loop announced on the ticket
    When the next poll cycle sees that announcement as a new comment
    Then it is resolved without being delivered into the session

    Requirement: docs/specs/issue-104/bugfix.md#AC5
    """
    gh = GhState()
    gh.comments = [_comment("IC_1", "old")]
    registry, adapter, dispatcher, poller = _make(tmp_path, gh)

    poller.poll_once()  # spawn + baseline IC_1
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)
    session = registry.find_by_work_item(REF)
    assert session is not None

    # What SessionAnnouncer posts on the first spawn — authored by the operator's
    # own (authorized) login, so only the marker keeps it out of the session.
    gh.comments = [
        _comment("IC_1", "old"),
        _comment("IC_2", announcement_body(session)),
    ]
    poller.poll_once()
    time.sleep(0.1)
    dispatcher.stop()

    assert adapter.resumes == []
    assert len(adapter.spawns) == 1


def test_pr_comment_reuses_the_linked_issues_session(tmp_path):
    """Scenario: a labelled PR's comment reaches its linked issue's session.

    Given a labelled PR 16 that GitHub reports as closing issue 15
    And an active session already registered for issue 15
    When poll cycles run and a new comment appears on the PR
    Then the comment resumes the issue's session
    And no second session is spawned for the PR's own ref

    Requirement: docs/specs/issue-93/bugfix.md#AC4
    """
    gh = GhState()
    gh.prs = [
        {
            "number": 16,
            "title": "pr",
            "labels": [{"name": LABEL}],
            "url": "u",
            "author": {"login": "octocat"},
            "headRefName": "feature/no-number-here",  # convention can't help
            "body": "see the linked issue",  # nor can a closing keyword
            "closingIssuesReferences": [{"number": 15}],
        }
    ]
    registry, adapter, dispatcher, poller = _make(
        tmp_path, gh, monitor_issues=False, monitor_prs=True
    )
    # The issue's session already exists — this is the reporter's scenario.
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-15",
            cwd=str(tmp_path),
        )
    )

    poller.poll_once()  # first sight: must NOT spawn, the issue has a session
    gh.pr_comments = [_comment("IC_9", "the build is red")]
    poller.poll_once()
    assert wait_until(lambda: len(adapter.resumes) == 1)
    time.sleep(0.1)
    dispatcher.stop()

    assert adapter.spawns == []
    assert registry.find_by_work_item("github:octo/repo#16") is None
    ref, prompt = adapter.resumes[0]
    assert ref == REF
    assert "the build is red" in prompt


def test_run_once_stops_after_a_single_cycle(tmp_path):
    _, adapter, dispatcher, poller = _make(tmp_path, GhState())
    poller.run(once=True, stop_event=threading.Event())
    assert wait_until(lambda: len(adapter.spawns) == 1)
    dispatcher.stop()


# -- closure reconciliation (issue-94) ----------------------------------------


def test_a_closed_issue_closes_its_session(tmp_path):
    """
    Feature: Poll GitHub and close finished work items
    Scenario: A closed issue ends the session the poller spawned for it
        Given a labelled issue with a spawned, registered session
        When the issue is closed upstream and the next poll cycle runs
        Then the session is closed in the registry
        And the harness is never resumed for the closure
    Requirement: docs/specs/issue-94/requirements.md#R1
    """
    gh = GhState()
    registry, adapter, dispatcher, poller = _make(tmp_path, gh)
    poller.poll_once()
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)

    gh.close_issue()
    summary = poller.poll_once()
    dispatcher.stop()

    assert summary.closures == 1
    assert registry.find_by_work_item(REF) is None  # closed
    assert registry.list_sessions(status="closed")  # …and persisted as such
    assert adapter.resumes == []  # never delivered into the conversation


def test_a_merged_pr_closes_its_session(tmp_path):
    """
    Feature: Poll GitHub and close finished work items
    Scenario: A merged pull request ends its session
        Given a work item with a spawned, registered session
        When the item is merged upstream and the next poll cycle runs
        Then the session is closed in the registry
    Requirement: docs/specs/issue-94/requirements.md#R1
    """
    gh = GhState()
    registry, adapter, dispatcher, poller = _make(tmp_path, gh)
    poller.poll_once()
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)

    gh.close_issue(merged=True)
    assert poller.poll_once().closures == 1
    dispatcher.stop()
    assert registry.find_by_work_item(REF) is None


def test_a_merged_pr_does_not_close_its_still_open_work_item(tmp_path):
    """
    Feature: Poll GitHub and close finished work items
    Scenario: One PR merging does not end a work item that has more to come
        Given issue 15 with an active session and a labelled PR 16 linked to it
        When PR 16 is merged and leaves the listing while issue 15 is still listed
        Then reconciliation closes nothing and the issue's session stays active
    Requirement: docs/specs/issue-101/requirements.md#AC1
    """
    gh = GhState()
    gh.prs = [
        {
            "number": 16,
            "title": "pr",
            "labels": [{"name": LABEL}],
            "url": "u",
            "author": {"login": "octocat"},
            "headRefName": "claude/github-issue-15-x",
            "body": "Closes #15",
            "closingIssuesReferences": [{"number": 15}],
        }
    ]
    registry, adapter, dispatcher, poller = _make(tmp_path, gh, monitor_prs=True)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-15",
            cwd=str(tmp_path),
        )
    )
    poller.poll_once()

    gh.prs = []  # PR 16 merged; issue 15 is still open and still listed
    summary = poller.poll_once()
    dispatcher.stop()

    assert summary.closures == 0
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "active"
    assert adapter.spawns == [] and adapter.resumes == []


def test_a_still_open_item_that_left_the_listing_keeps_its_session(tmp_path):
    """
    Feature: Poll GitHub and close finished work items
    Scenario: Removing the auto-execute label does not close the session
        Given a work item with a registered session
        When the item leaves the listing but is still open upstream
        Then its session stays active
    Requirement: docs/specs/issue-94/requirements.md#R1
    """
    gh = GhState()
    registry, adapter, dispatcher, poller = _make(tmp_path, gh)
    poller.poll_once()
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)

    gh.issues = []  # label removed — gone from the listing, still open
    assert poller.poll_once().closures == 0
    dispatcher.stop()
    assert registry.find_by_work_item(REF) is not None


def test_an_unreachable_github_never_closes_a_session(tmp_path):
    """
    Feature: Poll GitHub and close finished work items
    Scenario: A failing listing or state query leaves sessions alone
        Given a work item with a registered session
        When the listing fails, and then the closure query fails
        Then no closure is dispatched and the session stays active
    Requirement: docs/specs/issue-94/requirements.md#R1
    """
    gh = GhState()
    registry, adapter, dispatcher, poller = _make(tmp_path, gh)
    poller.poll_once()
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)

    gh.list_fails = True
    assert poller.poll_once().closures == 0
    assert gh.api_calls == []  # a failed listing is never read as "all closed"

    gh.list_fails = False
    gh.issues = []
    gh.state_fails = True
    summary = poller.poll_once()
    dispatcher.stop()
    assert summary.closures == 0 and summary.errors
    assert gh.api_calls  # it did ask…
    assert registry.find_by_work_item(REF) is not None  # …and kept the session


def test_a_reopened_item_spawns_a_fresh_session(tmp_path):
    """
    Feature: Poll GitHub and close finished work items
    Scenario: Reopening a closed work item starts work again
        Given a work item whose session was closed by a poll cycle
        When the item is reopened and labelled again
        Then the next cycle spawns a new session for it
    Requirement: docs/specs/issue-94/requirements.md#R1
    """
    gh = GhState()
    registry, adapter, dispatcher, poller = _make(tmp_path, gh)
    poller.poll_once()
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)
    gh.close_issue()
    assert poller.poll_once().closures == 1

    gh.issues = [
        {
            "number": 15,
            "title": "i",
            "labels": [{"name": LABEL}],
            "url": "u",
            "author": {"login": "octocat"},
        }
    ]
    gh.item_state = {"number": 15, "state": "open"}
    poller.poll_once()
    assert wait_until(lambda: len(adapter.spawns) == 2)
    dispatcher.stop()
    assert registry.find_by_work_item(REF) is not None
