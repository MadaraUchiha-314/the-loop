"""The harness's GitHub verbs across real process boundaries (issue-447, T4).

The bus, the ledger, the session registry and the control-plane app are the real
ones; GitHub is the fake client standing in for the process-wide client every
writer resolves. No network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ghfakes import FakeGitHubClient
from the_loop.api.app import create_app
from the_loop.channels.base import PostResult
from the_loop.channels.publishers import publish_comment
from the_loop.core import github_ops
from the_loop.ghapi import GitHubClient
from the_loop.sessions.registry import Session, SessionRegistry
from the_loop.state import layout_from_config
from the_loop.workitem import WorkItemRef

REF = "github:octo/repo#5"
SHA = "c" * 40


@pytest.fixture
def fake(monkeypatch):
    client = FakeGitHubClient()
    monkeypatch.setattr(
        GitHubClient, "shared", classmethod(lambda cls, *a, **k: client)
    )
    return client


def _config(tmp_path, **routing):
    config = {"state": {"root": str(tmp_path / ".the-loop")}}
    if routing:
        config["routing"] = routing
    return config


class _Room:
    name = "room"

    def __init__(self):
        self.events = []

    def subscribes(self, event_type):
        return event_type == "comment.agent"

    def post(self, event):
        self.events.append(event)
        return PostResult(channel=self.name, ok=True)


def test_an_agents_comment_is_recorded_and_mirrored_never_republished(
    fake, tmp_path, monkeypatch
):
    """
    Feature: the harness comments through the-loop, not gh
      Scenario: An agent's comment is recorded and mirrored, never re-published
        Given a channel subscribed to comment.agent
        When the agent runs `the-loop comment` on its work item
        Then the ledger posts one marked, enveloped comment on the ticket
        And the channel receives the comment once
        And when the ingress later reads that comment back it publishes nothing

    Requirement: docs/specs/issue-447/requirements.md R1.1
    """
    room = _Room()
    monkeypatch.setattr("the_loop.channels.bus.load_channels", lambda *a, **k: [room])
    result = github_ops.comment(REF, "The completion summary.", _config(tmp_path))
    assert result["exitCode"] == 0
    (posted,) = fake.posted
    assert len(room.events) == 1
    assert (
        publish_comment("agent", REF, "bot", posted[3], "", {"channels": {}}) is False
    )


def test_a_pull_request_opened_by_the_verb_is_linked_in_the_same_act(fake, tmp_path):
    """
    Feature: the harness opens its pull request through the-loop
      Scenario: A pull request opened by `pr create` is recorded against its work item
        Given a session registered for the work item
        When the agent runs `the-loop pr create` from its branch
        Then GitHub is asked to open the pull request on the default branch
        And the session registry records it as delivering the work item
        And no hook has to parse any tool output for it

    Requirement: docs/specs/issue-447/requirements.md R1.4
    """
    config = _config(tmp_path)
    registry = SessionRegistry(layout_from_config(config).local_dir)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="s1",
            cwd=str(tmp_path),
        )
    )
    result = github_ops.create_pull_request(
        REF, "feat: x", "Closes #5", "claude/issue-5", config=config
    )
    assert result["linked"] is True
    record = registry.find_by_work_item(REF)
    assert record is not None
    assert [pr.work_item.ref for pr in record.pull_requests] == ["github:octo/repo#12"]


@pytest.fixture
def api(fake, tmp_path):
    config = _config(tmp_path)
    SessionRegistry(layout_from_config(config).local_dir).register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="s1",
            cwd=str(tmp_path),
        )
    )
    return TestClient(create_app(config))


def test_the_service_serves_every_verb(fake, api):
    """
    Feature: the service holds the token, the session holds none
      Scenario: Every harness verb answers through the control-plane routes
        Given a running control-plane service
        When each verb's route is called as the CLI calls it
        Then each answers with the core result and its exit code

    Requirement: docs/specs/issue-447/requirements.md R2.1, R3.1
    """
    fake.states[("octo", "repo", 5)] = {"number": 5, "title": "T"}
    fake.pulls[("octo", "repo", 12)] = {"state": "open", "head": {"sha": SHA}}
    fake.threads[("octo", "repo", 12)] = [{"id": "PRRT_1", "isResolved": True}]

    comment = api.post("/api/v1/work-items/comments", json={"ref": REF, "body": "hi"})
    assert comment.status_code == 200 and comment.json()["exitCode"] == 0

    ticket = api.get("/api/v1/work-items/ticket", params={"ref": REF})
    assert ticket.json()["title"] == "T"

    created = api.post(
        "/api/v1/work-items/tickets",
        json={"repository": "octo/repo", "title": "New", "labels": ["x"]},
    )
    assert created.json()["ref"] == "github:octo/repo#42"

    opened = api.post(
        "/api/v1/work-items/pull-requests",
        json={"ref": REF, "title": "T", "body": "B", "head": "claude/x"},
    )
    assert opened.json()["pullRequest"] == "github:octo/repo#12"

    status = api.get(
        "/api/v1/pull-requests/status", params={"ref": "12", "workItem": REF}
    )
    assert status.json()["checks"]["conclusion"] == "none"

    threads = api.get(
        "/api/v1/pull-requests/threads",
        params={"ref": "github:octo/repo#12", "all": "true"},
    )
    assert [t["id"] for t in threads.json()["threads"]] == ["PRRT_1"]

    merged = api.post(
        "/api/v1/pull-requests/merge", json={"ref": "github:octo/repo#12"}
    )
    assert merged.json()["merged"] is True

    discovered = api.post(
        "/api/v1/sessions/link-pr",
        json={"ref": REF, "discover": True, "branch": "claude/x"},
    )
    assert discovered.json()["found"] == []


def test_a_caller_mistake_is_a_400(fake, api):
    """
    Feature: the service maps a caller mistake onto the CLI's exit 2
      Scenario: An empty comment is refused before any request
        When the comment route is called with an empty body
        Then it answers 400 and GitHub is never asked

    Requirement: docs/specs/issue-447/requirements.md R3.3
    """
    response = api.post("/api/v1/work-items/comments", json={"ref": REF, "body": " "})
    assert response.status_code == 400
    assert fake.calls == []


def test_abuse_447_a2_the_service_merges_by_its_own_policy_only(fake, tmp_path):
    """
    Feature: the merge policy lives in one place
      Scenario: A session cannot bring a merge policy of its own
        Given a service whose config says routing.mergeOnApproval is false
        When the merge route is called, even with extra fields in the body
        Then nothing is merged and the answer names the key

    Requirement: docs/specs/issue-447/requirements.md R1.8
    """
    api = TestClient(create_app(_config(tmp_path, mergeOnApproval=False)))
    response = api.post(
        "/api/v1/pull-requests/merge",
        json={"ref": "github:octo/repo#12", "mergeOnApproval": True},
    )
    body = response.json()
    assert body["exitCode"] == 1 and fake.merged == []
    assert "routing.mergeOnApproval" in body["messages"][0]["text"]


def test_the_service_closes_and_resolves_only_for_a_registered_work_item(fake, api):
    """
    Feature: lifecycle acts need a registered work item
      Scenario: The service resolves a thread and closes the ticket of its work item
        Given a work item registered on the service, with its pull request recorded
        When the resolve-thread and close routes are called
        Then the thread is resolved and the ticket closed
        And the same acts on a pull request and a ticket nobody registered are refused

    Requirement: docs/specs/issue-447/requirements.md R1.10, R1.11, R1.12
    """
    api.post("/api/v1/sessions/link-pr", json={"ref": REF, "pullRequest": "12"})
    fake.threads[("octo", "repo", 12)] = [{"id": "PRRT_1", "isResolved": False}]
    resolved = api.post(
        "/api/v1/pull-requests/threads/resolve",
        json={"ref": "github:octo/repo#12", "thread": "PRRT_1"},
    )
    assert resolved.json()["resolved"] is True
    closed = api.post("/api/v1/work-items/tickets/close", json={"ref": REF})
    assert closed.json()["closed"] is True

    stranger = api.post(
        "/api/v1/pull-requests/threads/resolve",
        json={"ref": "github:octo/repo#99", "thread": "PRRT_1"},
    )
    assert stranger.json()["exitCode"] == 1
    unregistered = api.post(
        "/api/v1/work-items/tickets/close", json={"ref": "github:octo/repo#77"}
    )
    assert unregistered.json()["exitCode"] == 1
    assert fake.closed == [("octo", "repo", 5, "completed")]


def test_issue_465_the_service_marks_only_its_own_draft_ready(fake, api):
    """
    Feature: a draft pull request is marked ready through the-loop, not gh
      Scenario: The service readies the draft of its work item and no other
        Given a work item registered on the service, with its draft pull request
              recorded
        When the ready route is called for that pull request
        Then the pull request is marked ready for review
        And a second call is a no-op that still exits 0
        And the same call on a draft nobody registered is refused before GitHub
            is asked

    Requirement: docs/specs/issue-465/requirements.md R1.1, R1.3, R2.2
    """
    api.post("/api/v1/sessions/link-pr", json={"ref": REF, "pullRequest": "12"})
    fake.pulls[("octo", "repo", 12)] = {
        "state": "open",
        "draft": True,
        "node_id": "PR_kw12",
    }
    fake.pulls[("octo", "repo", 99)] = {
        "state": "open",
        "draft": True,
        "node_id": "PR_kw99",
    }
    ready = api.post(
        "/api/v1/pull-requests/ready", json={"ref": "github:octo/repo#12"}
    ).json()
    assert ready["exitCode"] == 0 and ready["changed"] is True
    again = api.post(
        "/api/v1/pull-requests/ready", json={"ref": "12", "workItem": REF}
    ).json()
    assert again["exitCode"] == 0 and again["changed"] is False

    stranger = api.post(
        "/api/v1/pull-requests/ready", json={"ref": "github:octo/repo#99"}
    ).json()
    assert stranger["exitCode"] == 1
    assert fake.readied == ["PR_kw12"]


def test_issue_462_the_service_lists_a_pull_requests_failing_checks(fake, api):
    """
    Feature: a failing check is diagnosed through the-loop, not gh
      Scenario: The service lists the failing checks with the failed job's log
        Given a pull request whose head commit has a passing and a failing
              GitHub Actions job
        When the checks route is called with failing=true
        Then only the failing job is listed
        And it carries the tail of its log

    Requirement: docs/specs/issue-462/requirements.md R1.1, R1.3, R1.4, R2.2
    """
    sha = "c" * 40
    fake.pulls[("octo", "repo", 12)] = {"state": "open", "head": {"sha": sha}}
    fake.check_runs[sha] = [
        {"id": 1, "name": "lint", "status": "completed", "conclusion": "success"},
        {
            "id": 2,
            "name": "test",
            "status": "completed",
            "conclusion": "failure",
            "app": {"slug": "github-actions"},
        },
    ]
    fake.job_logs[2] = ["E   assert 1 == 2"]
    result = api.get(
        "/api/v1/pull-requests/checks",
        params={"ref": "github:octo/repo#12", "failing": "true", "logLines": "5"},
    ).json()
    assert result["exitCode"] == 0
    assert [c["name"] for c in result["checks"]] == ["test"]
    assert result["checks"][0]["logTail"] == ["E   assert 1 == 2"]


def test_issue_466_a_linked_pull_request_is_listed_by_a_two_label_poller(
    fake, tmp_path
):
    """
    Feature: a pull request the-loop links is one the poller can see
      Scenario: Every auto-execute label lands on the pull request it opens and records
        Given an operator whose routing.autoExecuteLabels holds two labels
        And a session registered for the work item
        When the agent opens one pull request with `pr create` through the service
        And records a second, opened by hand, with `sessions link-pr`
        Then both pull requests carry both labels
        And a poller requiring both labels lists both, so their review comments reach the session

    Requirement: docs/specs/issue-466/bugfix.md R1, R2
    """
    from the_loop.ghapi import GhItem
    from the_loop.poller.github import GitHubPollProvider, RepoSpec

    labels = ["the-loop: auto-execute", "the-loop: rr"]
    config = _config(tmp_path, autoExecuteLabels=labels)
    SessionRegistry(layout_from_config(config).local_dir).register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="s1",
            cwd=str(tmp_path),
        )
    )
    api = TestClient(create_app(config))
    opened = api.post(
        "/api/v1/work-items/pull-requests",
        json={"ref": REF, "title": "T", "body": "B", "head": "claude/x"},
    ).json()
    assert opened["pullRequest"] == "github:octo/repo#12" and opened["linked"]
    linked = api.post(
        "/api/v1/sessions/link-pr", json={"ref": REF, "pullRequest": "23"}
    ).json()
    assert linked["exitCode"] == 0 and linked["linked"]

    fake.prs[("octo", "repo")] = [
        GhItem(
            number=number,
            title="T",
            labels=fake.labels.get(("octo", "repo", number), []),
            updated_at="",
            url="",
            is_pr=True,
        )
        for number in (12, 23)
    ]
    poller = GitHubPollProvider([RepoSpec("octo", "repo")], labels, api=fake)
    assert [item.ref for item in poller.list_work_items()] == [
        "github:octo/repo#12",
        "github:octo/repo#23",
    ]
