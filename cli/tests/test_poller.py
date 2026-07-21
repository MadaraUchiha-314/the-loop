"""Unit tests for the GitHub poller (issue-34).

Covers the pure pieces the integration file wires together: the ``gh`` JSON
wrapper, poll-config parsing, durable comment dedup state, and the Poller's
decision logic (spawn-once, forward-new-comments) driven through a recording
dispatcher double so the assertions are deterministic (no threads).

Spec: docs/specs/issue-34/design.md.
"""

import json
import subprocess

import pytest

from the_loop.poller import (
    GhClient,
    GhComment,
    GhError,
    GhItem,
    PollConfig,
    Poller,
    PollState,
    RepoSpec,
    check_gh_dependency,
    parse_repos,
)
from the_loop.poller.poller import PollSummary  # noqa: F401 (re-exported too)
from the_loop.sessions import Session, SessionRegistry, WorkItemRef

LABEL = "the-loop: auto-execute"
OWNER, REPO = "octo", "repo"


# -- gh CLI wrapper -----------------------------------------------------------


class FakeRun:
    """Stand-in for subprocess.run capturing argv and returning canned JSON."""

    def __init__(self, stdout="null", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr
        self.calls = []

    def __call__(self, cmd, **kwargs) -> subprocess.CompletedProcess:
        self.calls.append(list(cmd))
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )


def test_gh_list_labeled_issues_parses_and_builds_argv():
    payload = json.dumps(
        [
            {
                "number": 15,
                "title": "Fix the thing",
                "labels": [{"name": LABEL}, {"name": "bug"}],
                "updatedAt": "2026-07-20T00:00:00Z",
                "url": "https://github.com/octo/repo/issues/15",
            }
        ]
    )
    run = FakeRun(stdout=payload)
    client = GhClient(runner=run)
    items = client.list_labeled_issues(OWNER, REPO, LABEL)
    assert len(items) == 1
    item = items[0]
    assert (item.number, item.is_pr) == (15, False)
    assert item.labels == [LABEL, "bug"]
    argv = run.calls[0]
    assert argv[:4] == ["gh", "issue", "list", "--repo"]
    assert "--label" in argv and LABEL in argv
    assert "--state" in argv and "open" in argv


def test_gh_list_labeled_prs_carries_head_ref_and_body():
    payload = json.dumps(
        [
            {
                "number": 42,
                "title": "PR",
                "labels": [{"name": LABEL}],
                "updatedAt": "2026-07-20T00:00:00Z",
                "url": "u",
                "headRefName": "claude/github-issue-15-abc",
                "body": "Closes #15",
            }
        ]
    )
    client = GhClient(runner=FakeRun(stdout=payload))
    prs = client.list_labeled_prs(OWNER, REPO, LABEL)
    assert prs[0].is_pr is True
    assert prs[0].head_ref == "claude/github-issue-15-abc"
    assert prs[0].body == "Closes #15"


@pytest.mark.parametrize("is_pr,sub", [(False, "issue"), (True, "pr")])
def test_gh_list_comments_uses_kind_subcommand(is_pr, sub):
    payload = json.dumps(
        {
            "comments": [
                {
                    "id": "IC_1",
                    "body": "please fix",
                    "author": {"login": "octocat"},
                    "createdAt": "2026-07-20T01:00:00Z",
                    "url": "c-url",
                }
            ]
        }
    )
    run = FakeRun(stdout=payload)
    client = GhClient(runner=run)
    comments = client.list_comments(OWNER, REPO, 15, is_pr=is_pr)
    assert comments == [
        GhComment(
            id="IC_1",
            body="please fix",
            author="octocat",
            created_at="2026-07-20T01:00:00Z",
            url="c-url",
        )
    ]
    assert run.calls[0][1] == sub  # gh <issue|pr> view …


def test_gh_error_on_nonzero_exit():
    client = GhClient(runner=FakeRun(returncode=1, stderr="not found"))
    with pytest.raises(GhError) as exc:
        client.list_labeled_issues(OWNER, REPO, LABEL)
    assert "not found" in str(exc.value)


def test_gh_error_on_bad_json():
    client = GhClient(runner=FakeRun(stdout="{not json"))
    with pytest.raises(GhError):
        client.list_labeled_issues(OWNER, REPO, LABEL)


def test_check_gh_dependency_reports_when_missing():
    assert check_gh_dependency("definitely-not-a-real-binary-xyz")
    assert check_gh_dependency("python") == []  # present on PATH


@pytest.mark.parametrize("bad", ["", "octo", "/repo", "octo/"])
def test_repospec_rejects_garbage(bad):
    with pytest.raises(ValueError):
        RepoSpec.parse(bad)


def test_parse_repos_dedupes_in_order():
    specs = parse_repos(["a/b", "c/d", "a/b"])
    assert [s.full_name for s in specs] == ["a/b", "c/d"]


# -- poll config --------------------------------------------------------------


def test_poll_config_from_mapping_defaults_and_overrides():
    assert PollConfig.from_mapping(None).interval_seconds == 60
    cfg = PollConfig.from_mapping(
        {
            "intervalSeconds": 5,
            "repos": ["a/b"],
            "monitor": {"issues": False, "pullRequests": True},
            "label": "custom",
            "stateFile": ".x/state.json",
            "ghBinary": "/usr/bin/gh",
        }
    )
    assert cfg.interval_seconds == 5
    assert cfg.repos == ["a/b"]
    assert (cfg.monitor_issues, cfg.monitor_prs) == (False, True)
    assert cfg.label == "custom"
    assert cfg.state_file == ".x/state.json"
    assert cfg.gh_binary == "/usr/bin/gh"


# -- durable dedup state ------------------------------------------------------


def test_poll_state_roundtrips_and_dedups(tmp_path):
    path = tmp_path / "poll-state.json"
    state = PollState(path)
    ref = "github:octo/repo#15"
    assert state.is_known(ref) is False
    state.update(ref, ["IC_1", "IC_2"], "2026-07-20T00:00:00Z")
    state.save()
    # a fresh instance reads the same on-disk state (restart-surviving dedup)
    reloaded = PollState(path)
    assert reloaded.is_known(ref) is True
    assert reloaded.seen_comments(ref) == {"IC_1", "IC_2"}
    stored = json.loads(path.read_text())
    assert stored["items"][ref]["seenComments"] == ["IC_1", "IC_2"]


def test_poll_state_ignores_corrupt_file(tmp_path):
    path = tmp_path / "poll-state.json"
    path.write_text("{not json")
    state = PollState(path)  # must not raise
    assert state.is_known("github:octo/repo#1") is False


# -- Poller decision logic (recording dispatcher double) ----------------------


class FakeGh:
    """Duck-typed GhClient: canned issues/PRs and per-number comments."""

    def __init__(self, issues=(), prs=(), comments=None):
        self._issues = list(issues)
        self._prs = list(prs)
        self._comments = comments or {}

    def list_labeled_issues(self, owner, repo, label):
        return list(self._issues)

    def list_labeled_prs(self, owner, repo, label):
        return list(self._prs)

    def list_comments(self, owner, repo, number, is_pr):
        return list(self._comments.get(number, []))


class RecordingDispatcher:
    """Captures RoutedEvents instead of dispatching (deterministic, no threads)."""

    def __init__(self):
        self.events = []

    def handle(self, routed):
        self.events.append(routed)

    def stop(self, timeout=None):
        pass


def issue(number=15, labels=(LABEL,)):
    return GhItem(
        number=number,
        title="t",
        labels=list(labels),
        updated_at="2026-07-20T00:00:00Z",
        url="u",
        is_pr=False,
    )


def comment(cid, body="hello"):
    return GhComment(id=cid, body=body, author="octocat", created_at="", url="")


def make_poller(gh, registry, dispatcher, state, label=LABEL, repos=("octo/repo",)):
    cfg = PollConfig(repos=list(repos))
    return Poller(
        gh=gh,
        registry=registry,
        dispatcher=dispatcher,
        config=cfg,
        auto_execute_label=label,
        state=state,
    )


def test_first_sight_labeled_issue_spawns_and_baselines_comments(tmp_path):
    gh = FakeGh(issues=[issue(15)], comments={15: [comment("IC_1")]})
    registry = SessionRegistry(tmp_path / "sessions")
    disp = RecordingDispatcher()
    state = PollState(tmp_path / "state.json")
    poller = make_poller(gh, registry, disp, state)

    summary = poller.poll_once()

    assert summary.spawns == 1 and summary.comments_forwarded == 0
    assert len(disp.events) == 1
    ev = disp.events[0]
    assert ev.event == "issues" and ev.labeled is True
    assert ev.work_items[0].ref == "github:octo/repo#15"
    # the pre-existing comment is baselined, not replayed
    assert state.seen_comments("github:octo/repo#15") == {"IC_1"}


def test_existing_session_skips_presence_and_forwards_new_comment(tmp_path):
    ref = "github:octo/repo#15"
    registry = SessionRegistry(tmp_path / "sessions")
    registry.register(
        Session(
            work_item=WorkItemRef.parse(ref),
            harness="claude",
            harness_session_id="sess-1",
            cwd=".",
        )
    )
    state = PollState(tmp_path / "state.json")
    state.update(ref, ["IC_1"], "t")  # IC_1 already processed
    gh = FakeGh(issues=[issue(15)], comments={15: [comment("IC_1"), comment("IC_2")]})
    disp = RecordingDispatcher()
    poller = make_poller(gh, registry, disp, state)

    summary = poller.poll_once()

    assert summary.spawns == 0  # session already exists
    assert summary.comments_forwarded == 1
    ev = disp.events[0]
    assert ev.event == "issue_comment" and ev.labeled is False
    assert ev.delivery_id == "poll-comment-IC_2"
    assert "IC_2" in ev.payload["comment"]["id"]


def test_new_activity_without_session_retries_spawn_and_forwards(tmp_path):
    ref = "github:octo/repo#15"
    state = PollState(tmp_path / "state.json")
    state.update(ref, ["IC_1"], "t")  # known item, but no session registered
    gh = FakeGh(issues=[issue(15)], comments={15: [comment("IC_1"), comment("IC_2")]})
    disp = RecordingDispatcher()
    poller = make_poller(gh, SessionRegistry(tmp_path / "sessions"), disp, state)

    summary = poller.poll_once()

    # no session + new comment => presence (spawn retry) AND the new comment
    assert summary.spawns == 1 and summary.comments_forwarded == 1
    kinds = [e.event for e in disp.events]
    assert kinds == ["issues", "issue_comment"]  # presence enqueued before comment


def test_first_sight_with_existing_session_only_baselines(tmp_path):
    ref = "github:octo/repo#15"
    registry = SessionRegistry(tmp_path / "sessions")
    registry.register(
        Session(
            work_item=WorkItemRef.parse(ref),
            harness="claude",
            harness_session_id="sess-1",
            cwd=".",
        )
    )
    gh = FakeGh(issues=[issue(15)], comments={15: [comment("IC_1")]})
    disp = RecordingDispatcher()
    poller = make_poller(gh, registry, disp, PollState(tmp_path / "state.json"))

    summary = poller.poll_once()

    assert summary.spawns == 0 and summary.comments_forwarded == 0
    assert disp.events == []  # nothing to do — session exists, history baselined


def test_pr_presence_links_head_branch_issue(tmp_path):
    pr = GhItem(
        number=42,
        title="t",
        labels=[LABEL],
        updated_at="",
        url="u",
        is_pr=True,
        head_ref="claude/github-issue-15-abc",
        body="Closes #15",
    )
    gh = FakeGh(prs=[pr], comments={42: []})
    disp = RecordingDispatcher()
    poller = make_poller(
        gh,
        SessionRegistry(tmp_path / "sessions"),
        disp,
        PollState(tmp_path / "state.json"),
    )

    poller.poll_once()

    ev = disp.events[0]
    assert ev.event == "pull_request"
    refs = {wi.ref for wi in ev.work_items}
    # PR itself + the issue its head branch / closing keyword points at
    assert "github:octo/repo#42" in refs
    assert "github:octo/repo#15" in refs


def test_repo_list_error_is_captured_not_raised(tmp_path):
    class BoomGh(FakeGh):
        def list_labeled_issues(self, owner, repo, label):
            raise GhError("boom")

    disp = RecordingDispatcher()
    poller = make_poller(
        BoomGh(),
        SessionRegistry(tmp_path / "s"),
        disp,
        PollState(tmp_path / "state.json"),
    )
    summary = poller.poll_once()
    assert summary.errors and "boom" in summary.errors[0]
    assert disp.events == []
