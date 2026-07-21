"""Unit tests for the provider-agnostic poller (issue-34).

Three layers, kept separate:
  * the ``gh`` JSON wrapper (`GhClient`) and the GitHub provider that maps gh
    shapes onto the neutral WorkItem/Comment + shared RoutedEvent;
  * the provider registry (`build_provider`);
  * the provider-agnostic Poller core, exercised through a fake provider + a
    recording dispatcher so the decision logic (spawn-once, forward-new) is
    asserted deterministically (no threads, no GitHub).

Spec: docs/specs/issue-34/design.md.
"""

import json
import subprocess

import pytest

from the_loop.poller import (
    Comment,
    GhClient,
    GhComment,
    GitHubPollProvider,
    PollConfig,
    Poller,
    PollState,
    ProviderError,
    RepoSpec,
    WorkItem,
    build_provider,
    check_gh_dependency,
    parse_repos,
    provider_names,
)
from the_loop.poller.poller import PollSummary  # noqa: F401 (re-exported too)
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.router import RoutedEvent

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
    with pytest.raises(ProviderError) as exc:  # GhError is a ProviderError
        client.list_labeled_issues(OWNER, REPO, LABEL)
    assert "not found" in str(exc.value)


def test_gh_error_on_bad_json():
    client = GhClient(runner=FakeRun(stdout="{not json"))
    with pytest.raises(ProviderError):
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


# -- GitHub provider ----------------------------------------------------------


def _gh_client(issues=None, prs=None, comments=None):
    """A GhClient whose runner returns canned JSON keyed by the gh sub-command."""
    issues = issues or []
    prs = prs or []
    comments = comments or []

    class Router:
        calls = []

        def __call__(self, cmd, **kwargs):
            self.calls.append(list(cmd))
            sub = (cmd[1], cmd[2])
            if sub == ("issue", "list"):
                out = json.dumps(issues)
            elif sub == ("pr", "list"):
                out = json.dumps(prs)
            else:  # issue/pr view --json comments
                out = json.dumps({"comments": comments})
            return subprocess.CompletedProcess(cmd, 0, out, "")

    return GhClient(runner=Router())


def test_provider_from_source_resolves_label_and_repos():
    provider = GitHubPollProvider.from_source(
        {"provider": "github", "monitor": {"pullRequests": False}},
        default_label=LABEL,
        fallback_repos=["octo/repo"],
    )
    assert provider.label == LABEL  # fell back to routing label
    assert [s.full_name for s in provider.repos] == ["octo/repo"]  # ticketing fallback
    assert provider.monitor_prs is False


def test_provider_lists_issues_and_prs_as_work_items():
    gh = _gh_client(
        issues=[{"number": 15, "title": "i", "labels": [{"name": LABEL}], "url": "u"}],
        prs=[
            {
                "number": 42,
                "title": "p",
                "labels": [{"name": LABEL}],
                "url": "u",
                "headRefName": "x",
                "body": "b",
            }
        ],
    )
    provider = GitHubPollProvider(parse_repos(["octo/repo"]), LABEL, gh=gh)
    items = provider.list_work_items()
    kinds = {(i.number, i.kind) for i in items}
    assert kinds == {(15, "issue"), (42, "pull-request")}


def test_provider_presence_event_is_labeled_and_maps_ref():
    gh = _gh_client(
        issues=[{"number": 15, "title": "i", "labels": [{"name": LABEL}], "url": "u"}]
    )
    provider = GitHubPollProvider(parse_repos(["octo/repo"]), LABEL, gh=gh)
    item = provider.list_work_items()[0]
    refs = provider.refs(item)
    ev = provider.presence_event(item, refs)
    assert ev.event == "issues" and ev.labeled is True
    assert ev.work_items[0].ref == "github:octo/repo#15"
    assert ev.delivery_id.startswith("poll-presence-github:octo/repo#15-")


def test_provider_pr_refs_link_head_branch_issue():
    gh = _gh_client(
        prs=[
            {
                "number": 42,
                "title": "p",
                "labels": [{"name": LABEL}],
                "url": "u",
                "headRefName": "claude/github-issue-15-abc",
                "body": "Closes #15",
            }
        ]
    )
    provider = GitHubPollProvider(parse_repos(["octo/repo"]), LABEL, gh=gh)
    item = provider.list_work_items()[0]
    refs = {r.ref for r in provider.refs(item)}
    assert "github:octo/repo#42" in refs and "github:octo/repo#15" in refs


def test_provider_comment_event_carries_body_and_is_unlabeled():
    gh = _gh_client(
        issues=[{"number": 15, "title": "i", "labels": [{"name": LABEL}], "url": "u"}]
    )
    provider = GitHubPollProvider(parse_repos(["octo/repo"]), LABEL, gh=gh)
    item = provider.list_work_items()[0]
    refs = provider.refs(item)
    ev = provider.comment_event(
        item, Comment("IC_9", "the build is red", "octocat", "", "u"), refs
    )
    assert ev.event == "issue_comment" and ev.labeled is False
    assert ev.delivery_id == "poll-comment-IC_9"
    assert ev.payload["comment"]["body"] == "the build is red"


def test_provider_without_repos_raises_on_list():
    provider = GitHubPollProvider([], LABEL, gh=_gh_client())
    with pytest.raises(ProviderError):
        provider.list_work_items()


# -- provider registry --------------------------------------------------------


def test_provider_registry_knows_github():
    assert "github" in provider_names()


def test_build_provider_rejects_missing_and_unknown_provider():
    with pytest.raises(ProviderError):
        build_provider({}, default_label=LABEL, fallback_repos=[])
    with pytest.raises(ProviderError):
        build_provider({"provider": "gitlab"}, default_label=LABEL, fallback_repos=[])


def test_build_provider_constructs_github():
    provider = build_provider(
        {"provider": "github", "repos": ["octo/repo"]},
        default_label=LABEL,
        fallback_repos=[],
    )
    assert isinstance(provider, GitHubPollProvider)
    assert "github octo/repo" == provider.describe()


# -- poll config --------------------------------------------------------------


def test_poll_config_from_mapping_defaults_and_overrides():
    assert PollConfig.from_mapping(None).interval_seconds == 60
    cfg = PollConfig.from_mapping(
        {
            "intervalSeconds": 5,
            "stateFile": ".x/state.json",
            "sources": [{"provider": "github", "repos": ["a/b"]}],
        }
    )
    assert cfg.interval_seconds == 5
    assert cfg.state_file == ".x/state.json"
    assert cfg.sources == [{"provider": "github", "repos": ["a/b"]}]


# -- durable dedup state ------------------------------------------------------


def test_poll_state_roundtrips_and_dedups(tmp_path):
    path = tmp_path / "poll-state.json"
    state = PollState(path)
    ref = "github:octo/repo#15"
    assert state.is_known(ref) is False
    state.update(ref, ["IC_1", "IC_2"], "2026-07-20T00:00:00Z")
    state.save()
    reloaded = PollState(path)  # restart-surviving dedup
    assert reloaded.is_known(ref) is True
    assert reloaded.seen_comments(ref) == {"IC_1", "IC_2"}
    stored = json.loads(path.read_text())
    assert stored["items"][ref]["seenComments"] == ["IC_1", "IC_2"]


def test_poll_state_ignores_corrupt_file(tmp_path):
    path = tmp_path / "poll-state.json"
    path.write_text("{not json")
    state = PollState(path)  # must not raise
    assert state.is_known("github:octo/repo#1") is False


# -- Poller core (provider-agnostic, recording dispatcher double) -------------


class FakeProvider:
    """A provider-agnostic double: canned items/comments, records event asks."""

    def __init__(self, items=(), comments=None, linked=None):
        self._items = list(items)
        self._comments = comments or {}
        self._linked = linked or {}  # ref -> extra linked WorkItemRefs

    def describe(self):
        return "fake"

    def list_work_items(self):
        return list(self._items)

    def list_comments(self, item):
        return list(self._comments.get(item.number, []))

    def refs(self, item):
        refs = [WorkItemRef.parse(item.ref)]
        refs += [WorkItemRef.parse(r) for r in self._linked.get(item.ref, [])]
        return refs

    def presence_event(self, item, refs):
        return RoutedEvent(
            event="issues",
            action="labeled",
            delivery_id=f"presence-{item.ref}",
            work_items=refs,
            payload={},
            labeled=True,
        )

    def comment_event(self, item, comment, refs):
        return RoutedEvent(
            event="issue_comment",
            action="created",
            delivery_id=f"comment-{comment.id}",
            work_items=refs,
            payload={"comment": {"id": comment.id}},
            labeled=False,
        )


class RecordingDispatcher:
    """Captures RoutedEvents instead of dispatching (deterministic, no threads)."""

    def __init__(self):
        self.events = []

    def handle(self, routed):
        self.events.append(routed)

    def stop(self, timeout=None):
        pass


def _item(number=15):
    return WorkItem("github", OWNER, REPO, number, "issue", labels=[LABEL])


def _comment(cid, body="hello"):
    return Comment(id=cid, body=body, author="octocat", created_at="", url="")


def make_poller(provider, registry, dispatcher, state):
    return Poller(
        providers=[provider],
        registry=registry,
        dispatcher=dispatcher,
        config=PollConfig(),
        state=state,
    )


def test_first_sight_spawns_and_baselines_comments(tmp_path):
    provider = FakeProvider(items=[_item(15)], comments={15: [_comment("IC_1")]})
    registry = SessionRegistry(tmp_path / "sessions")
    disp = RecordingDispatcher()
    state = PollState(tmp_path / "state.json")
    summary = make_poller(provider, registry, disp, state).poll_once()

    assert summary.spawns == 1 and summary.comments_forwarded == 0
    assert [e.event for e in disp.events] == ["issues"]
    assert state.seen_comments("github:octo/repo#15") == {"IC_1"}


def test_existing_session_skips_presence_and_forwards_new_comment(tmp_path):
    ref = "github:octo/repo#15"
    registry = SessionRegistry(tmp_path / "sessions")
    registry.register(Session(WorkItemRef.parse(ref), "claude", "sess-1", "."))
    state = PollState(tmp_path / "state.json")
    state.update(ref, ["IC_1"], "t")
    provider = FakeProvider(
        items=[_item(15)], comments={15: [_comment("IC_1"), _comment("IC_2")]}
    )
    disp = RecordingDispatcher()
    summary = make_poller(provider, registry, disp, state).poll_once()

    assert summary.spawns == 0 and summary.comments_forwarded == 1
    ev = disp.events[0]
    assert ev.event == "issue_comment" and ev.delivery_id == "comment-IC_2"


def test_new_activity_without_session_retries_spawn_and_forwards(tmp_path):
    ref = "github:octo/repo#15"
    state = PollState(tmp_path / "state.json")
    state.update(ref, ["IC_1"], "t")  # known, but no session registered
    provider = FakeProvider(
        items=[_item(15)], comments={15: [_comment("IC_1"), _comment("IC_2")]}
    )
    disp = RecordingDispatcher()
    summary = make_poller(
        provider, SessionRegistry(tmp_path / "sessions"), disp, state
    ).poll_once()

    assert summary.spawns == 1 and summary.comments_forwarded == 1
    assert [e.event for e in disp.events] == ["issues", "issue_comment"]


def test_first_sight_with_existing_session_only_baselines(tmp_path):
    ref = "github:octo/repo#15"
    registry = SessionRegistry(tmp_path / "sessions")
    registry.register(Session(WorkItemRef.parse(ref), "claude", "sess-1", "."))
    provider = FakeProvider(items=[_item(15)], comments={15: [_comment("IC_1")]})
    disp = RecordingDispatcher()
    summary = make_poller(
        provider, registry, disp, PollState(tmp_path / "state.json")
    ).poll_once()

    assert summary.spawns == 0 and summary.comments_forwarded == 0
    assert disp.events == []


def test_linked_ref_session_suppresses_presence(tmp_path):
    # A PR whose linked issue already has a session must not spawn again.
    registry = SessionRegistry(tmp_path / "sessions")
    registry.register(
        Session(WorkItemRef.parse("github:octo/repo#15"), "claude", "s", ".")
    )
    pr = WorkItem("github", OWNER, REPO, 42, "pull-request", labels=[LABEL])
    provider = FakeProvider(
        items=[pr],
        comments={42: []},
        linked={"github:octo/repo#42": ["github:octo/repo#15"]},
    )
    disp = RecordingDispatcher()
    make_poller(
        provider, registry, disp, PollState(tmp_path / "state.json")
    ).poll_once()
    assert disp.events == []  # linked issue's session matched -> no spawn


def test_provider_error_is_captured_not_raised(tmp_path):
    class Boom(FakeProvider):
        def list_work_items(self):
            raise ProviderError("boom")

    disp = RecordingDispatcher()
    summary = make_poller(
        Boom(), SessionRegistry(tmp_path / "s"), disp, PollState(tmp_path / "st.json")
    ).poll_once()
    assert summary.errors and "boom" in summary.errors[0]
    assert disp.events == []
