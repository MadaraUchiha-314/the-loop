"""CI monitoring on the poll ingress (issue-462, PR #470 review).

A webhook pushes CI results; a poll-only installation has to ask. These tests
cover the asking: the GitHub provider turns a pull request's completed checks
into the webhook-shaped events the dispatcher's CI gate already judges; the
poller reads them on `polling.ci.intervalSeconds`, only for a pull request a
live session owns, and forwards each result once across cycles and restarts.

Feature: a poll-only installation heals failing checks too
Requirement: docs/specs/issue-462/requirements.md#R6
"""

from __future__ import annotations

import time

import pytest

from conftest import FakeTmux, StubInteractiveAdapter
from ghfakes import FakeGitHubClient, http_error
from the_loop.control import ControlConfig
from the_loop.poller import (
    GitHubPollProvider,
    PollConfig,
    Poller,
    PollState,
    RepoSpec,
    WorkItem,
)
from the_loop.poller.poller import CI_INTERVAL_MIN, PollCiConfig
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.workitem import WorkItemStore

LABEL = "the-loop: auto-execute"
ISSUE = "github:octo/repo#15"
PR = "github:octo/repo#12"
SHA = "d" * 40


def pr_item(number=12, head="issue-15"):
    return WorkItem(
        "github",
        "octo",
        "repo",
        number,
        "pull-request",
        title="the fix",
        url=f"https://github.com/octo/repo/pull/{number}",
        author="octocat",
        labels=[LABEL],
        raw={"headRef": head, "body": "", "linkedIssues": []},
    )


def fake_client(runs=(), statuses=()):
    client = FakeGitHubClient()
    client.pulls[("octo", "repo", 12)] = {"state": "open", "head": {"sha": SHA}}
    client.check_runs[SHA] = list(runs)
    client.statuses[SHA] = list(statuses)
    return client


def provider_over(client):
    return GitHubPollProvider(
        repos=[RepoSpec(owner="octo", repo="repo")], labels=[LABEL], api=client
    )


def run(name="test", conclusion="failure", status="completed", job=77):
    return {
        "id": job,
        "name": name,
        "status": status,
        "conclusion": conclusion if status == "completed" else None,
        "html_url": f"https://github.com/octo/repo/actions/runs/1/job/{job}",
        "app": {"slug": "github-actions"},
        "output": {"title": "1 failed", "summary": "E assert 1 == 2"},
    }


# -- the provider ----------------------------------------------------------------


def test_the_provider_turns_completed_checks_into_webhook_shaped_events():
    client = fake_client(
        runs=[
            run("test"),
            run("lint", "success", job=78),
            run("e2e", status="in_progress"),
        ],
        statuses=[
            {"context": "ci/jenkins", "state": "error", "target_url": "https://j/1"},
            {"context": "ci/slow", "state": "pending"},
        ],
    )
    provider = provider_over(client)
    item = pr_item()
    events = provider.ci_events(item, provider.refs(item))
    assert [(key, value) for key, value, _ in events] == [
        ("check-run:test", f"{SHA}:failure"),
        ("check-run:lint", f"{SHA}:success"),
        ("status:ci/jenkins", f"{SHA}:error"),
    ]
    _, _, failed = events[0]
    assert failed.event == "check_run" and failed.action == "completed"
    check = failed.payload["check_run"]
    assert check["head_sha"] == SHA and check["pull_requests"] == [{"number": 12}]
    assert check["conclusion"] == "failure" and check["id"] == 77
    assert failed.payload["repository"]["full_name"] == "octo/repo"
    assert PR in {ref.ref for ref in failed.work_items}
    assert ISSUE in {ref.ref for ref in failed.work_items}
    status = events[2][2]
    assert status.event == "status" and status.payload["sha"] == SHA
    assert client.calls_to == ["get_pull", "commit_checks"]


def test_an_issue_has_no_checks_to_read():
    client = fake_client()
    provider = provider_over(client)
    issue = WorkItem("github", "octo", "repo", 15, "issue", labels=[LABEL])
    assert provider.ci_events(issue, provider.refs(issue)) == []
    assert client.calls == []


# -- the poller ------------------------------------------------------------------


class Recorder:
    """A dispatcher double that records what the poller hands it."""

    def __init__(self):
        self.events = []
        self.config = RoutingConfig(control=ControlConfig(require_start_command=False))

    def handle(self, routed):
        self.events.append(routed)

    def delivery_status(self, delivery_id, refs):
        return "done"

    def delivery_outcome(self, delivery_id):
        return ""

    def is_closing(self, ref):
        return False


@pytest.fixture
def registry(tmp_path):
    reg = SessionRegistry(tmp_path / "sessions")
    reg.register(
        Session(
            work_item=WorkItemRef.parse(ISSUE),
            harness="claude",
            harness_session_id="s1",
            cwd=str(tmp_path),
        )
    )
    return reg


def poller(tmp_path, registry, client, dispatcher, ci=PollCiConfig()):
    from the_loop.control import ControlStore
    from the_loop.collaborators import CollaboratorStore

    return Poller(
        providers=[ListingProvider(client)],
        registry=registry,
        dispatcher=dispatcher,  # type: ignore[arg-type]
        config=PollConfig(ci=ci),
        state=PollState(WorkItemStore(tmp_path / "portable")),
        authorized_users=["octocat"],
        control_store=ControlStore(str(tmp_path / "control")),
        collaborator_store=CollaboratorStore(str(tmp_path / "collaborators")),
    )


class ListingProvider(GitHubPollProvider):
    """The real provider, listing one pull request with no comments."""

    def __init__(self, client):
        super().__init__(
            repos=[RepoSpec(owner="octo", repo="repo")], labels=[LABEL], api=client
        )

    def list_work_items(self):
        return [pr_item()]

    def listing(self):
        from the_loop.poller.base import Listing

        return Listing(items=[pr_item()], polled=["octo/repo"])

    def list_comments(self, item):
        return []


def test_each_result_is_forwarded_once_and_a_new_one_again(tmp_path, registry):
    """
    Scenario: the poller forwards a check's result once, and its next result
      Given a pull request a live session owns, with a failing and a passing check
      When two poll cycles read its checks
      Then each result is handed to the dispatcher once
      And when the failing check passes, that new result is handed over too
    """
    client = fake_client(runs=[run("test"), run("lint", "success", job=78)])
    disp = Recorder()
    p = poller(tmp_path, registry, client, disp, ci=PollCiConfig(interval_seconds=60))
    first = p.poll_once()
    assert first.ci_forwarded == 2
    assert sorted(e.payload["check_run"]["name"] for e in disp.events) == [
        "lint",
        "test",
    ]

    p._ci_last = None  # the CI interval has passed
    assert p.poll_once().ci_forwarded == 0  # nothing new

    client.check_runs[SHA] = [run("test", "success"), run("lint", "success", job=78)]
    p._ci_last = None
    assert p.poll_once().ci_forwarded == 1
    assert disp.events[-1].payload["check_run"]["conclusion"] == "success"


def test_the_ledger_survives_a_restart(tmp_path, registry):
    client = fake_client(runs=[run("test")])
    disp = Recorder()
    poller(tmp_path, registry, client, disp).poll_once()
    restarted = poller(tmp_path, registry, client, disp)
    assert restarted.poll_once().ci_forwarded == 0
    assert len(disp.events) == 1


def test_checks_are_read_on_their_own_interval(tmp_path, registry):
    client = fake_client(runs=[run("test")])
    p = poller(
        tmp_path, registry, client, Recorder(), ci=PollCiConfig(interval_seconds=600)
    )
    p.poll_once()
    p.poll_once()  # the next cycle, well inside 600 s
    assert client.calls_to.count("commit_checks") == 1


def test_a_pull_request_without_a_live_session_is_not_read(tmp_path):
    client = fake_client(runs=[run("test")])
    disp = Recorder()
    summary = poller(
        tmp_path, SessionRegistry(tmp_path / "none"), client, disp
    ).poll_once()
    assert "commit_checks" not in client.calls_to
    assert summary.ci_forwarded == 0
    assert all(e.event != "check_run" for e in disp.events)


def test_ci_polling_can_be_turned_off(tmp_path, registry):
    client = fake_client(runs=[run("test")])
    poller(
        tmp_path, registry, client, Recorder(), ci=PollCiConfig(enabled=False)
    ).poll_once()
    assert "commit_checks" not in client.calls_to


def test_a_failed_read_is_reported_and_the_cycle_goes_on(tmp_path, registry):
    client = fake_client(runs=[run("test")])
    client.fail_on["commit_checks"] = http_error(502, "bad gateway")
    summary = poller(tmp_path, registry, client, Recorder()).poll_once()
    assert summary.ci_forwarded == 0
    assert any("checks" in e and "bad gateway" in e for e in summary.errors)


def test_polling_ci_config_defaults_and_floor():
    assert PollConfig.from_mapping({}).ci == PollCiConfig(
        enabled=True, interval_seconds=300
    )
    parsed = PollConfig.from_mapping({"ci": {"enabled": False, "intervalSeconds": 900}})
    assert parsed.ci == PollCiConfig(enabled=False, interval_seconds=900)
    floored = PollConfig.from_mapping({"ci": {"intervalSeconds": 5}})
    assert floored.ci.interval_seconds == CI_INTERVAL_MIN


def test_the_schema_takes_polling_ci():
    from the_loop import configschema
    from the_loop.migrations import CURRENT_CONFIG_VERSION

    def errors(ci):
        return configschema.validate(
            {"version": CURRENT_CONFIG_VERSION, "polling": {"ci": ci}}
        )

    assert errors({"enabled": True, "intervalSeconds": 600}) == []
    assert errors({"intervalSeconds": 10})
    assert errors({"every": 5})


# -- end to end ------------------------------------------------------------------


def test_a_polled_failure_reaches_the_session_with_the_healing_frame(
    tmp_path, registry
):
    """
    Scenario: a poll-only installation heals a failing check
      Given a live session for the work item a labelled pull request delivers
      And no webhook, only the poller
      When the pull request's head has a failing check run
      Then the poller hands it to the real dispatcher
      And the session receives it with the CI section, attempt 1 of 3
      And a passing check on the same head is not delivered
    """
    client = fake_client(runs=[run("test"), run("lint", "success", job=78)])
    tmux = FakeTmux()
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=RoutingConfig(
            registry_dir=str(tmp_path),
            control=ControlConfig(require_start_command=False),
        ),
        tmux_runner=tmux,
    )
    try:
        summary = poller(tmp_path, registry, client, dispatcher).poll_once()
        deadline = time.monotonic() + 5
        while not tmux.delivers and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.05)
    finally:
        dispatcher.stop()
    assert summary.ci_forwarded == 2
    (delivered,) = [prompt for _, prompt in tmux.delivers]
    assert "CI: a check failed" in delivered and "attempt 1 of 3" in delivered
    assert f"the-loop pr checks {PR} --failing" in delivered
    assert "`test`" in delivered and "`lint`" not in delivered
