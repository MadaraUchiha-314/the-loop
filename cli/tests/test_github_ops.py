"""The harness's GitHub verbs in core (issue-447, T2/T7).

Every operation runs over :class:`ghfakes.FakeGitHubClient`: what is asserted is
what core asked the client for and what it hands back — data, exit code, words.
The client's own requests are ``test_ghapi.py``'s.
"""

from __future__ import annotations

import pytest

from ghfakes import FakeGitHubClient, http_error, missing_token
from the_loop.authz import SELF_COMMENT_MARKER
from the_loop.channels.base import PostResult
from the_loop.channels.envelope import has_envelope
from the_loop.channels.publishers import publish_comment
from the_loop.core import github_ops
from the_loop.ghapi import GhComment
from the_loop.sessions.registry import Session, SessionRegistry
from the_loop.state import layout_from_config
from the_loop.workitem import WorkItemRef

REF = "github:octo/repo#5"
SHA = "a" * 40


def _config(tmp_path, **routing):
    config = {"state": {"root": str(tmp_path / ".the-loop")}}
    if routing:
        config["routing"] = routing
    return config


def _register(tmp_path, ref=REF):
    SessionRegistry(layout_from_config(_config(tmp_path)).local_dir).register(
        Session(
            work_item=WorkItemRef.parse(ref),
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(tmp_path),
        )
    )


def _linked(tmp_path, ref=REF):
    record = SessionRegistry(
        layout_from_config(_config(tmp_path)).local_dir
    ).find_by_work_item(ref)
    return [] if record is None else [pr.work_item.ref for pr in record.pull_requests]


def _words(result):
    return " ".join(m["text"] for m in result["messages"])


class _Channel:
    """A channel subscribed to the agent's comments, recording what it got."""

    name = "room"

    def __init__(self):
        self.events = []

    def subscribes(self, event_type):
        return event_type == "comment.agent"

    def post(self, event):
        self.events.append(event)
        return PostResult(channel=self.name, ok=True)


# -- comment ---------------------------------------------------------------------


def test_abuse_447_a4_a_comment_is_marked_enveloped_and_mirrored(tmp_path, monkeypatch):
    channel = _Channel()
    monkeypatch.setattr(
        "the_loop.channels.bus.load_channels", lambda *a, **k: [channel]
    )
    fake = FakeGitHubClient()
    result = github_ops.comment(
        REF, "The spec is ready.", _config(tmp_path), client=fake
    )
    assert result["exitCode"] == 0
    assert result["posted"] is True and result["channelsPosted"] == 1
    assert result["url"] == fake.comment_url
    ((owner, repo, number, body, _host),) = fake.posted
    assert (owner, repo, number) == ("octo", "repo", 5)
    assert SELF_COMMENT_MARKER in body and has_envelope(body)
    assert "The spec is ready." in body
    (event,) = channel.events
    assert event.event_type == "comment.agent" and event.source == "cli"
    # the ingress never re-publishes the record (issue-309 A10)
    assert publish_comment("agent", REF, "bot", body, "", {"channels": {}}) is False


def test_an_empty_comment_is_refused_before_a_request(tmp_path):
    fake = FakeGitHubClient()
    with pytest.raises(ValueError, match="empty"):
        github_ops.comment(REF, "  \n", _config(tmp_path), client=fake)
    assert fake.calls == []


def test_a_malformed_ref_is_refused(tmp_path):
    with pytest.raises(ValueError):
        github_ops.comment("octo/repo#5", "hi", _config(tmp_path))
    with pytest.raises(ValueError, match="not a GitHub"):
        github_ops.comment("jira:octo/repo#5", "hi", _config(tmp_path))


def test_a_comment_without_a_token_names_the_variables(tmp_path):
    result = github_ops.comment(
        REF, "hi", _config(tmp_path), client=FakeGitHubClient(token=False)
    )
    assert result["exitCode"] == 1 and result["posted"] is False
    assert "GH_TOKEN" in _words(result)


def test_a_bus_fault_still_posts_the_marked_comment(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("channel bug")

    monkeypatch.setattr("the_loop.channels.bus.publish", boom)
    fake = FakeGitHubClient()
    result = github_ops.comment(REF, "hi", _config(tmp_path), client=fake)
    assert result["exitCode"] == 0
    assert SELF_COMMENT_MARKER in fake.posted[0][3]


# -- ticket show / create ----------------------------------------------------------


def test_show_ticket_returns_the_body_every_comment_and_the_attachment_links(tmp_path):
    fake = FakeGitHubClient()
    key = ("octo", "repo", 5)
    fake.states[key] = {
        "number": 5,
        "title": "Add the verbs",
        "body": "See https://github.com/user-attachments/assets/abc-123 please",
        "state": "open",
        "labels": [{"name": "loop:design"}],
        "user": {"login": "owner"},
        "html_url": "https://github.com/octo/repo/issues/5",
    }
    fake.comments[key] = [
        GhComment(
            id="IC_1",
            body="and https://github.com/user-attachments/assets/def-456",
            author="alice",
            created_at="2026-09-30T10:00:00Z",
            url="u1",
        )
    ]
    result = github_ops.show_ticket(REF, _config(tmp_path), client=fake)
    assert result["exitCode"] == 0 and result["messages"] == []
    assert (result["title"], result["state"], result["author"]) == (
        "Add the verbs",
        "open",
        "owner",
    )
    assert result["isPullRequest"] is False
    assert result["labels"] == ["loop:design"]
    assert [c["author"] for c in result["comments"]] == ["alice"]
    assert result["attachments"] == [
        "https://github.com/user-attachments/assets/abc-123",
        "https://github.com/user-attachments/assets/def-456",
    ]


def test_abuse_447_a7_show_ticket_fetches_no_attachment(tmp_path, monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("an attachment was fetched")

    monkeypatch.setattr("the_loop.channels.attachments.github_attachments", refuse)
    fake = FakeGitHubClient()
    fake.states[("octo", "repo", 5)] = {
        "number": 5,
        "body": "https://github.com/user-attachments/assets/x",
    }
    assert github_ops.show_ticket(REF, _config(tmp_path), client=fake)["exitCode"] == 0


def test_show_ticket_of_a_pull_request_reads_every_surface(tmp_path):
    fake = FakeGitHubClient()
    key = ("octo", "repo", 5)
    fake.states[key] = {"number": 5, "pull_request": {"url": "x"}}
    fake.reviews[key] = [
        GhComment(
            "PRR_1", "lgtm", "bob", "2026-09-30T11:00:00Z", "u", "review", "APPROVED"
        )
    ]
    result = github_ops.show_ticket(REF, _config(tmp_path), client=fake)
    assert result["isPullRequest"] is True
    assert result["comments"][0]["kind"] == "review"
    assert result["comments"][0]["state"] == "APPROVED"


def test_show_ticket_of_a_missing_item_is_exit_1(tmp_path):
    fake = FakeGitHubClient(missing={("octo", "repo", 5)})
    result = github_ops.show_ticket(REF, _config(tmp_path), client=fake)
    assert result["exitCode"] == 1 and "Not Found" in _words(result)


def test_create_ticket_opens_the_issue(tmp_path):
    fake = FakeGitHubClient()
    result = github_ops.create_ticket(
        "octo/repo",
        "T",
        "B",
        ["loop:requirements-definition"],
        _config(tmp_path),
        client=fake,
    )
    assert result["exitCode"] == 0
    assert result["ref"] == "github:octo/repo#42"
    assert fake.created == [
        ("octo", "repo", "T", "B", ["loop:requirements-definition"], "")
    ]


@pytest.mark.parametrize("repository", ["", "octo", "a/b/c/d", "http:/x/y", "o/r;x"])
def test_abuse_447_a3_create_ticket_refuses_a_bad_repository(tmp_path, repository):
    fake = FakeGitHubClient()
    with pytest.raises(ValueError):
        github_ops.create_ticket(
            repository, "T", "B", (), _config(tmp_path), client=fake
        )
    assert fake.calls == []


# -- pr create -----------------------------------------------------------------


def test_pr_create_opens_on_the_default_branch_and_links(tmp_path):
    _register(tmp_path)
    fake = FakeGitHubClient(default_branch="trunk")
    result = github_ops.create_pull_request(
        REF, "feat: x", "Closes #5", "claude/x", config=_config(tmp_path), client=fake
    )
    assert result["exitCode"] == 0 and result["linked"] is True
    assert result["pullRequest"] == "github:octo/repo#12"
    (opened,) = fake.opened
    assert (opened["head"], opened["base"], opened["repo"]) == (
        "claude/x",
        "trunk",
        "repo",
    )
    assert _linked(tmp_path) == ["github:octo/repo#12"]


def test_pr_create_in_another_repository_links_its_full_ref(tmp_path):
    _register(tmp_path)
    fake = FakeGitHubClient()
    result = github_ops.create_pull_request(
        REF,
        "T",
        "B",
        "claude/x",
        base="develop",
        repository="octo/other",
        config=_config(tmp_path),
        client=fake,
    )
    assert result["pullRequest"] == "github:octo/other#12"
    assert "repository" not in fake.calls_to  # --base given: no lookup
    assert _linked(tmp_path) == ["github:octo/other#12"]


def test_pr_create_without_a_session_still_succeeds_and_says_so(tmp_path):
    fake = FakeGitHubClient()
    result = github_ops.create_pull_request(
        REF, "T", "B", "claude/x", config=_config(tmp_path), client=fake
    )
    assert result["exitCode"] == 0 and result["linked"] is False
    errs = [m["text"] for m in result["messages"] if m["stream"] == "err"]
    assert errs and "not linked" in errs[0] and "no session recorded" in errs[0]


def test_pr_create_refused_by_github_is_exit_1(tmp_path):
    fake = FakeGitHubClient(fail_on={"create_pull": http_error(422, "already exists")})
    result = github_ops.create_pull_request(
        REF, "T", "B", "claude/x", base="main", config=_config(tmp_path), client=fake
    )
    assert result["exitCode"] == 1 and "already exists" in _words(result)


@pytest.mark.parametrize("head", ["", "HEAD..x", "-x", "a b"])
def test_pr_create_refuses_a_hostile_head(tmp_path, head):
    with pytest.raises(ValueError, match="head"):
        github_ops.create_pull_request(
            REF, "T", "B", head, config=_config(tmp_path), client=FakeGitHubClient()
        )


# -- the PR argument -------------------------------------------------------------


@pytest.mark.parametrize(
    "given, work_item, expected",
    [
        ("github:octo/repo#12", "", "github:octo/repo#12"),
        ("https://github.com/octo/repo/pull/12", "", "github:octo/repo#12"),
        ("https://github.com/octo/repo/pull/12/files", "", "github:octo/repo#12"),
        ("https://ghe.corp/octo/repo/pull/3", "", "github:ghe.corp/octo/repo#3"),
        ("12", REF, "github:octo/repo#12"),
        ("#12", REF, "github:octo/repo#12"),
    ],
)
def test_a_pull_request_is_a_ref_a_url_or_a_number(given, work_item, expected):
    assert github_ops.resolve_pull_request(given, work_item).ref == expected


@pytest.mark.parametrize(
    "given", ["", "12", "octo/repo#12", "https://evil/x/pull/1;rm"]
)
def test_an_unusable_pull_request_argument_is_refused(given):
    with pytest.raises(ValueError):
        github_ops.resolve_pull_request(given)


# -- pr status -------------------------------------------------------------------


@pytest.mark.parametrize(
    "runs, statuses, conclusion",
    [
        ([], [], "none"),
        (
            [{"name": "t", "status": "completed", "conclusion": "success"}],
            [],
            "success",
        ),
        (
            [{"name": "t", "status": "completed", "conclusion": "skipped"}],
            [],
            "success",
        ),
        ([{"name": "t", "status": "in_progress"}], [], "pending"),
        ([], [{"context": "ci", "state": "pending"}], "pending"),
        (
            [{"name": "t", "status": "completed", "conclusion": "timed_out"}],
            [],
            "failure",
        ),
        ([], [{"context": "ci", "state": "error"}], "failure"),
        (
            [{"name": "t", "status": "queued"}],
            [{"context": "ci", "state": "failure"}],
            "failure",
        ),
    ],
)
def test_the_checks_rollup(runs, statuses, conclusion):
    assert github_ops.checks_rollup(runs, statuses)["conclusion"] == conclusion


def test_pr_status_reports_state_mergeability_and_the_failing_checks(tmp_path):
    fake = FakeGitHubClient()
    fake.pulls[("octo", "repo", 12)] = {
        "state": "open",
        "merged": False,
        "mergeable": True,
        "mergeable_state": "unstable",
        "draft": False,
        "head": {"sha": SHA},
        "html_url": "https://github.com/octo/repo/pull/12",
    }
    fake.check_runs[SHA] = [
        {"name": "lint", "status": "completed", "conclusion": "success"},
        {"name": "test (3.11)", "status": "completed", "conclusion": "failure"},
    ]
    result = github_ops.pull_request_status("12", REF, _config(tmp_path), client=fake)
    assert result["exitCode"] == 0
    assert result["mergeable"] is True and result["headSha"] == SHA
    assert result["checks"] == {
        "conclusion": "failure",
        "total": 2,
        "failing": ["test (3.11)"],
        "pending": [],
    }
    assert fake.calls_to == ["get_pull", "commit_checks"]


def test_pr_status_of_a_missing_pull_request_is_exit_1(tmp_path):
    result = github_ops.pull_request_status(
        "github:octo/repo#99", config=_config(tmp_path), client=FakeGitHubClient()
    )
    assert result["exitCode"] == 1


# -- pr threads ------------------------------------------------------------------


def test_pr_threads_are_the_unresolved_ones_unless_all(tmp_path):
    fake = FakeGitHubClient()
    fake.threads[("octo", "repo", 12)] = [
        {"id": "PRRT_1", "isResolved": False, "comments": []},
        {"id": "PRRT_2", "isResolved": True, "comments": []},
    ]
    open_only = github_ops.pull_request_threads(
        "12", REF, config=_config(tmp_path), client=fake
    )
    assert [t["id"] for t in open_only["threads"]] == ["PRRT_1"]
    every = github_ops.pull_request_threads(
        "12", REF, include_resolved=True, config=_config(tmp_path), client=fake
    )
    assert [t["id"] for t in every["threads"]] == ["PRRT_1", "PRRT_2"]


# -- pr merge --------------------------------------------------------------------


def test_pr_merge_merges_by_default(tmp_path):
    fake = FakeGitHubClient()
    result = github_ops.merge_pull_request(
        "12", REF, "squash", _config(tmp_path), client=fake
    )
    assert result["exitCode"] == 0 and result["merged"] is True
    assert fake.merged == [("octo", "repo", 12, "squash")]


def test_abuse_447_a2_merge_is_refused_when_the_operator_merges(tmp_path):
    fake = FakeGitHubClient()
    result = github_ops.merge_pull_request(
        "12", REF, "merge", _config(tmp_path, mergeOnApproval=False), client=fake
    )
    assert result["exitCode"] == 1 and result["merged"] is False
    assert "routing.mergeOnApproval" in _words(result)
    assert fake.calls == [] and fake.merged == []


def test_pr_merge_refused_by_github_is_exit_1(tmp_path):
    fake = FakeGitHubClient(fail_on={"merge_pull": http_error(405, "not mergeable")})
    result = github_ops.merge_pull_request(
        "12", REF, "merge", _config(tmp_path), client=fake
    )
    assert result["exitCode"] == 1 and "not mergeable" in _words(result)


def test_an_unknown_merge_method_is_a_caller_mistake(tmp_path):
    with pytest.raises(ValueError, match="merge method"):
        github_ops.merge_pull_request("12", REF, "octopus", _config(tmp_path))


def test_abuse_447_a1_a_token_never_reaches_a_verbs_words(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_secret_value_123")
    fake = FakeGitHubClient(fail_on={"merge_pull": http_error(401, "Bad credentials")})
    result = github_ops.merge_pull_request(
        "12", REF, "merge", _config(tmp_path), client=fake
    )
    assert "ghp_secret_value_123" not in repr(result)


def test_a_missing_token_is_exit_1_naming_the_variables(tmp_path):
    fake = FakeGitHubClient(fail=missing_token())
    result = github_ops.pull_request_threads(
        "12", REF, config=_config(tmp_path), client=fake
    )
    assert result["exitCode"] == 1 and "GH_TOKEN" in _words(result)


# -- link-pr --discover ----------------------------------------------------------


def test_discover_links_every_open_pull_request_for_the_branch(tmp_path):
    _register(tmp_path)
    fake = FakeGitHubClient()
    fake.heads[("octo", "repo", "claude/x")] = [
        {"number": 12, "html_url": "https://github.com/octo/repo/pull/12"},
    ]
    result = github_ops.discover_pull_requests(
        REF, "claude/x", config=_config(tmp_path), client=fake
    )
    assert result["exitCode"] == 0
    assert result["found"] == result["linked"] == ["github:octo/repo#12"]
    assert _linked(tmp_path) == ["github:octo/repo#12"]
    again = github_ops.discover_pull_requests(
        REF, "claude/x", config=_config(tmp_path), client=fake
    )
    assert again["exitCode"] == 0 and again["linked"] == []  # idempotent


def test_discover_keeps_the_repositorys_own_spelling(tmp_path):
    _register(tmp_path, "github:Octo/Repo#5")
    fake = FakeGitHubClient()
    # a checkout's origin reads lower-cased; GitHub is asked in the work item's
    # own spelling, and the ref keeps it
    fake.heads[("Octo", "Repo", "b")] = [
        {"number": 7, "html_url": "https://github.com/Octo/Repo/pull/7"}
    ]
    result = github_ops.discover_pull_requests(
        "github:Octo/Repo#5", "b", "octo/repo", _config(tmp_path), client=fake
    )
    assert result["found"] == ["github:Octo/Repo#7"]


def test_discover_with_nothing_open_is_exit_0(tmp_path):
    result = github_ops.discover_pull_requests(
        REF, "claude/x", config=_config(tmp_path), client=FakeGitHubClient()
    )
    assert result["exitCode"] == 0 and result["found"] == []
    assert "no open pull request" in _words(result)


def test_discover_without_a_session_is_exit_1(tmp_path):
    fake = FakeGitHubClient()
    fake.heads[("octo", "repo", "b")] = [{"number": 12}]
    result = github_ops.discover_pull_requests(
        REF, "b", config=_config(tmp_path), client=fake
    )
    assert result["exitCode"] == 1 and "no session recorded" in _words(result)


def test_discover_refuses_a_hostile_branch(tmp_path):
    with pytest.raises(ValueError, match="branch"):
        github_ops.discover_pull_requests(REF, "a..b", config=_config(tmp_path))
