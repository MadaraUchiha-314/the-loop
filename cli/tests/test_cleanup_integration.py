"""Integration tests: the three triggers that release a work item's local resources.

Every test here drives a real :class:`Dispatcher` — its registry, its
``FakeTmux`` seam, and a real :class:`the_loop.workspace.Workspace` on a
throwaway git repository under ``tmp_path``. The workspace is deliberately
**not** faked: worktree removal is precisely the thing that must be proved, and
git is the one native dependency the-loop already depends on.

The scenarios that matter are the two the ticket is actually about — a close
event that cannot name who closed it, and a named authorized human asking for
cleanup retroactively — plus the abuse cases that keep the new destructive verb
from becoming a weaker way in.

Feature: Cleanup after a work item is closed
Requirement: docs/specs/issue-186/requirements.md#R1
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from conftest import FakeTmux, StubInteractiveAdapter
from the_loop import eventlog
from the_loop.cleanup import SESSION, TMUX, WORKSPACE
from the_loop.control import ControlConfig, ControlStore
from the_loop.poller.poller import PollState
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import (
    Dispatcher,
    RoutingConfig,
    WorkspaceConfig,
)
from the_loop.webhook.router import RoutedEvent
from the_loop.workitem import CONTROL, POLL, WorkItemStore
from the_loop.workspace import RepoTarget, Workspace

REF = "github:octo/repo#15"
PR = "github:octo/repo#16"
AUTHORIZED = ["octocat"]


# -- fixtures --------------------------------------------------------------------


def _git(args, cwd):
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """A real (tiny) repository for the workspace to clone from."""
    repo = tmp_path / "origin"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@example.com"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "README.md").write_text("hello\n")
    _git(["add", "."], repo)
    _git(["commit", "-qm", "first"], repo)
    return repo


@pytest.fixture
def target(origin: Path) -> RepoTarget:
    return RepoTarget(
        host="github.com", owner="octo", repo="repo", clone_url=str(origin)
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path / "workspace", strategy="worktree")


class Harness:
    """A dispatcher plus everything a cleanup scenario needs to assert on."""

    def __init__(self, dispatcher, registry, tmux, workspace, store, events):
        self.dispatcher = dispatcher
        self.registry = registry
        self.tmux = tmux
        self.workspace = workspace
        self.store = store
        self.events = events

    def reasons(self, name):
        return [f for n, f in self.events if n == name]


@pytest.fixture
def harness(tmp_path, workspace, monkeypatch) -> Harness:
    events = []
    monkeypatch.setattr(
        eventlog, "emit", lambda name, **fields: events.append((name, fields))
    )
    registry = SessionRegistry(tmp_path / "local")
    tmux = FakeTmux()
    config = RoutingConfig(
        dispatch_timeout_seconds=30,
        spawn_workdir=str(tmp_path),
        portable_dir=str(tmp_path / "portable"),
        authorized_users=list(AUTHORIZED),
        control=ControlConfig(require_start_command=False),
        # Retention ON, so every scenario proves cleanup ignores it.
        workspace=WorkspaceConfig(
            root=str(workspace.root), keep_checkout_on_close=True
        ),
    )
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=config,
        tmux_runner=tmux,
        workspace=workspace,
    )
    return Harness(
        dispatcher,
        registry,
        tmux,
        workspace,
        WorkItemStore(tmp_path / "portable"),
        events,
    )


def prepared(harness: Harness, target: RepoTarget, ref: str = REF) -> Path:
    """A work item with a real worktree, a session and a PR endpoint."""
    item = WorkItemRef.parse(ref)
    checkout = harness.workspace.prepare(target, item.slug)
    session = Session(
        work_item=item,
        harness="claude",
        harness_session_id="sess-0",
        cwd=str(checkout),
        tmux_target=f"loop-{item.slug}",
    )
    harness.registry.register(session, force=True)
    harness.registry.link_pull_request(item, PR)
    endpoint = harness.registry.find_by_work_item(item).pull_requests[0]
    endpoint.tmux_target = "loop-github-octo-repo-16"
    harness.registry.save_endpoint(item, endpoint)
    return checkout


def comment(body: str, author: str = "octocat", ref: str = REF) -> RoutedEvent:
    item = WorkItemRef.parse(ref)
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id=f"d-{author}-{abs(hash(body)) % 10000}",
        work_items=[item],
        payload={
            "action": "created",
            "repository": {"full_name": f"{item.owner}/{item.repo}"},
            "issue": {"number": item.number},
            "comment": {"body": body, "user": {"login": author}},
            "sender": {"login": author},
        },
    )


def closed(sender: str = "octocat", ref: str = REF, key: str = "issue") -> RoutedEvent:
    item = WorkItemRef.parse(ref)
    payload = {
        "action": "closed",
        "repository": {"full_name": f"{item.owner}/{item.repo}"},
        key: {"number": item.number},
    }
    if sender:
        payload["sender"] = {"login": sender}
    return RoutedEvent(
        event="issues" if key == "issue" else "pull_request",
        action="closed",
        delivery_id=f"close-{item.number}-{sender or 'anon'}",
        work_items=[item],
        payload=payload,
    )


# -- the keyword -----------------------------------------------------------------


def test_an_authorized_comment_releases_every_local_resource(harness, target):
    """
    Scenario: an authorized user asks for cleanup on the ticket
      Given a work item with a worktree, its own tmux session and a PR endpoint
      When octocat comments "the-loop cleanup"
      Then both tmux sessions are killed, the worktree is gone and the local
           session record is deleted
      And the work item is durably disarmed
    """
    checkout = prepared(harness, target)

    harness.dispatcher.handle(comment("the-loop cleanup"))

    assert set(harness.tmux.kills) == {
        "loop-github-octo-repo-15",
        "loop-github-octo-repo-16",
    }
    assert not checkout.exists()
    assert harness.registry.find_by_work_item(REF, include_closed=True) is None
    assert ControlStore(harness.store.root).start_requested(REF) is False


def test_the_keyword_is_executed_not_forwarded_to_the_harness(harness, target):
    """
    Scenario: a control keyword never becomes agent input
      Given a work item with a live session
      When an authorized user comments "the-loop cleanup"
      Then nothing is pasted into the session
    """
    prepared(harness, target)

    harness.dispatcher.handle(comment("the-loop cleanup"))

    assert harness.tmux.delivers == []


def test_cleanup_ignores_the_retention_settings(harness, target):
    """
    Scenario: cleanup means cleanup
      Given routing.workspace.keepCheckoutOnClose is true
      And routing.tmux.keepSessionOnClose is true (the default)
      When an authorized user asks for cleanup
      Then the checkout and the tmux sessions go anyway
    """
    assert harness.dispatcher.config.workspace.keep_checkout_on_close is True
    assert harness.dispatcher.config.tmux.keep_session_on_close is True
    checkout = prepared(harness, target)

    harness.dispatcher.handle(comment("the-loop cleanup"))

    assert not checkout.exists()
    assert harness.tmux.kills


def test_the_portable_record_and_the_shared_clone_survive(harness, target):
    """
    Scenario: cleanup is not a reset
      Given a work item with a control record, a poll ledger and a shared clone
      When an authorized user asks for cleanup
      Then the portable record and the shared clone are still there
    """
    ControlStore(harness.store.root).record(
        REF, "start", source="comment", actor="octocat"
    )
    poll = PollState(harness.store)
    poll.baseline_comments(REF, ["c1"], "2026-08-09T00:00:00Z")
    poll.save()
    prepared(harness, target)
    shared = harness.workspace.repo_dir(target)

    harness.dispatcher.handle(comment("the-loop cleanup"))

    assert harness.store.section(REF, CONTROL) is not None
    assert harness.store.section(REF, POLL) is not None
    assert shared.is_dir()


def test_the_event_log_names_what_went(harness, target):
    prepared(harness, target)

    harness.dispatcher.handle(comment("the-loop cleanup"))

    cleaned = harness.reasons("session.cleaned")
    assert len(cleaned) == 1
    assert cleaned[0]["source"] == "comment"
    assert cleaned[0]["actor"] == "octocat"
    assert set(cleaned[0]["removed"]) == {TMUX, WORKSPACE, SESSION}


# -- closure -----------------------------------------------------------------------


def test_a_closure_by_an_authorized_user_cleans_up(harness, target):
    """
    Scenario: the ordinary path
      Given a work item with a worktree and a live session
      When the issue is closed by octocat
      Then the session is closed and its local resources are released
    """
    checkout = prepared(harness, target)

    harness.dispatcher.handle(closed(sender="octocat"))

    assert not checkout.exists()
    assert harness.registry.find_by_work_item(REF, include_closed=True) is None
    assert harness.reasons("session.cleaned")


def test_abuse_a_closure_naming_no_actor_defers_the_cleanup(harness, target):
    """
    Scenario: the ticket's own concern — a close action with no identity
      Given a work item with a worktree and a live session
      When the issue is closed by an event carrying no sender
      Then the session closes but nothing is removed
      And the deferral is recorded with its reason
    """
    checkout = prepared(harness, target)

    harness.dispatcher.handle(closed(sender=""))

    assert checkout.exists()
    assert harness.registry.find_by_work_item(REF, include_closed=True) is not None
    assert not harness.reasons("session.cleaned")
    deferred = harness.reasons("cleanup.deferred")
    assert deferred and deferred[0]["reason"] == "no-actor"


def test_abuse_a_closure_by_an_unauthorized_actor_defers_the_cleanup(harness, target):
    """
    Scenario: a closer who is not on the allowlist
      Given a work item with a worktree
      When the issue is closed by mallory
      Then nothing is removed and the deferral names her
    """
    checkout = prepared(harness, target)

    harness.dispatcher.handle(closed(sender="mallory"))

    assert checkout.exists()
    deferred = harness.reasons("cleanup.deferred")
    assert deferred and deferred[0]["reason"] == "unauthorized-actor"
    assert deferred[0]["actor"] == "mallory"


def test_abuse_an_unauthorized_commenter_cannot_ask_for_cleanup(harness, target):
    """
    Scenario: comment text must not become a destructive daemon action
      Given a work item with a worktree and two tmux sessions
      When mallory comments "the-loop cleanup"
      Then nothing is removed and the refusal is recorded
    """
    checkout = prepared(harness, target)

    harness.dispatcher.handle(comment("the-loop cleanup", author="mallory"))

    assert checkout.exists()
    assert harness.tmux.kills == []
    assert harness.registry.find_by_work_item(REF) is not None
    rejected = harness.reasons("control.rejected")
    assert rejected and rejected[0]["reason"] == "unauthorized-actor"


def test_abuse_two_different_keywords_in_one_comment_do_nothing(harness, target):
    """
    Scenario: ambiguity is refused outright
      When an authorized user comments both "the-loop cleanup" and "the-loop start"
      Then nothing is executed and nothing is forwarded
    """
    checkout = prepared(harness, target)

    harness.dispatcher.handle(comment("the-loop cleanup then the-loop start"))

    assert checkout.exists()
    assert harness.tmux.kills == [] and harness.tmux.delivers == []
    assert harness.reasons("control.ambiguous")


def test_abuse_a_merged_pull_request_never_cleans_up_its_work_item(harness, target):
    """
    Scenario: a work item may be delivered by several PRs (issue-101, unchanged)
      Given an open work item whose PR #16 merges
      When the merge event arrives
      Then the work item keeps its worktree, its record and its own session
    """
    checkout = prepared(harness, target)
    payload_event = closed(sender="octocat", ref=PR, key="pull_request")
    payload_event.work_items = [WorkItemRef.parse(REF), WorkItemRef.parse(PR)]
    payload_event.payload["pull_request"]["merged"] = True

    harness.dispatcher.handle(payload_event)

    assert checkout.exists()
    assert harness.registry.find_by_work_item(REF) is not None
    assert not harness.reasons("session.cleaned")


# -- retroactive -------------------------------------------------------------------


def test_a_checkout_with_no_session_record_is_still_reclaimed(harness, target):
    """
    Scenario: state left behind by a crash or an older version
      Given a worktree on disk and no session record at all
      When an authorized user comments "the-loop cleanup"
      Then the worktree is removed
    """
    item = WorkItemRef.parse(REF)
    checkout = harness.workspace.prepare(target, item.slug)
    assert harness.registry.find_by_work_item(REF, include_closed=True) is None

    harness.dispatcher.handle(comment("the-loop cleanup"))

    assert not checkout.exists()
    cleaned = harness.reasons("session.cleaned")
    assert cleaned and cleaned[0]["removed"] == [WORKSPACE]


def test_cleanup_after_a_deferred_closure_finishes_the_job(harness, target):
    """
    Scenario: the stated remedy for an unattributable closure
      Given a closure that deferred cleanup
      When an authorized user later comments "the-loop cleanup"
      Then everything the closure left behind is released
    """
    checkout = prepared(harness, target)
    harness.dispatcher.handle(closed(sender=""))
    assert checkout.exists()

    harness.dispatcher.handle(comment("the-loop cleanup"))

    assert not checkout.exists()
    assert harness.registry.find_by_work_item(REF, include_closed=True) is None


def test_a_work_item_with_nothing_left_reports_nothing_to_clean(harness):
    """
    Scenario: cleaning up twice is not an error
      When an authorized user asks for cleanup on a work item this machine
           holds nothing for
      Then it is recorded as found: false, and the item stays disarmed
    """
    harness.dispatcher.handle(comment("the-loop cleanup"))

    cleaned = harness.reasons("session.cleaned")
    assert cleaned and cleaned[0]["found"] is False
    assert ControlStore(harness.store.root).start_requested(REF) is False


def test_a_github_enterprise_work_item_finds_its_own_checkout(harness, origin):
    """
    Scenario: the workspace layout is keyed by HOST
      Given a work item on a GitHub Enterprise host, whose worktree therefore
            lives under <root>/ghe.corp.example/octo/repo/
      When an authorized user asks for cleanup
      Then that worktree is removed, not one under the default host
    """
    ref = "github:ghe.corp.example/octo/repo#15"
    item = WorkItemRef.parse(ref)
    ghe = RepoTarget(
        host="ghe.corp.example", owner="octo", repo="repo", clone_url=str(origin)
    )
    checkout = harness.workspace.prepare(ghe, item.slug)
    assert "ghe.corp.example" in str(checkout)

    harness.dispatcher.handle(comment("the-loop cleanup", ref=ref))

    assert not checkout.exists()


def test_the_clone_strategy_removes_the_whole_work_item_folder(
    tmp_path, target, harness
):
    """
    Scenario: the other workspace layout
      Given routing.workspace.strategy is clone
      When an authorized user asks for cleanup
      Then the work item's whole folder — every repo it cloned — is removed
    """
    workspace = Workspace(tmp_path / "clone-ws", strategy="clone")
    harness.dispatcher.workspace = workspace
    harness.workspace = workspace
    item = WorkItemRef.parse(REF)
    folder = workspace.workitem_dir(item.slug)
    workspace.prepare(target, item.slug)
    assert folder.is_dir()

    harness.dispatcher.handle(comment("the-loop cleanup"))

    assert not folder.exists()
