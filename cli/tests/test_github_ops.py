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


def _register_pr(tmp_path, pr="github:octo/repo#12", ref=REF):
    """A registered work item with ``pr`` recorded as delivering it."""
    from the_loop.core import sessions as core_sessions

    _register(tmp_path, ref)
    assert core_sessions.link_pull_request(ref, pr, config=_config(tmp_path))["linked"]


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


def test_pr_create_without_a_registered_work_item_opens_nothing(tmp_path):
    """R1.10 — a PR the-loop opens belongs to a work item it tracks."""
    fake = FakeGitHubClient()
    result = github_ops.create_pull_request(
        REF, "T", "B", "claude/x", config=_config(tmp_path), client=fake
    )
    assert result["exitCode"] == 1 and "sessions register" in _words(result)
    assert fake.calls == [] and fake.opened == []


def test_a_link_that_fails_after_the_open_is_a_note(tmp_path, monkeypatch):
    """R1.5 — the PR exists; a failure would invite a second one."""
    _register(tmp_path)
    monkeypatch.setattr(
        "the_loop.core.sessions.link_pull_request",
        lambda *a, **k: {
            "exitCode": 1,
            "messages": [{"stream": "err", "text": "registry is read-only"}],
        },
    )
    result = github_ops.create_pull_request(
        REF, "T", "B", "claude/x", config=_config(tmp_path), client=FakeGitHubClient()
    )
    assert result["exitCode"] == 0 and result["linked"] is False
    errs = [m["text"] for m in result["messages"] if m["stream"] == "err"]
    assert errs and "not linked" in errs[0]


def test_pr_create_refused_by_github_is_exit_1(tmp_path):
    _register(tmp_path)
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
    _register_pr(tmp_path)
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
    _register_pr(tmp_path)
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


# -- issue-447 review: the host allow-list and the merge's edges ------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda c, f: github_ops.show_ticket("github:evil.example/o/r#1", c, client=f),
        lambda c, f: github_ops.comment("github:evil.example/o/r#1", "x", c, client=f),
        lambda c, f: github_ops.pull_request_status(
            "https://evil.example/o/r/pull/1", config=c, client=f
        ),
        lambda c, f: github_ops.pull_request_threads(
            "https://127.0.0.1:8443/o/r/pull/1", config=c, client=f
        ),
        lambda c, f: github_ops.merge_pull_request(
            "github:evil.example/o/r#1", config=c, client=f
        ),
        lambda c, f: github_ops.create_ticket(
            "evil.example/o/r", "T", "B", (), c, client=f
        ),
        lambda c, f: github_ops.create_pull_request(
            REF, "T", "B", "x", repository="evil.example/o/r", config=c, client=f
        ),
        lambda c, f: github_ops.discover_pull_requests(
            REF, "x", "evil.example/o/r", c, client=f
        ),
    ],
)
def test_abuse_447_a3_a_host_the_operator_did_not_configure_is_refused(tmp_path, call):
    """The token goes only to github.com or the operator's own host (review H1)."""
    fake = FakeGitHubClient()
    with pytest.raises(ValueError, match="not a GitHub host"):
        call(_config(tmp_path), fake)
    assert fake.calls == []


def test_the_operators_own_enterprise_host_is_trusted(tmp_path):
    config: dict = {
        **_config(tmp_path),
        "integrations": {"github": {"host": "ghe.corp.example"}},
    }
    fake = FakeGitHubClient()
    fake.threads[("o", "r", 3)] = []
    result = github_ops.pull_request_threads(
        "github:ghe.corp.example/o/r#3", config=config, client=fake
    )
    assert result["exitCode"] == 0
    assert fake.calls[0][1]["host"] == "ghe.corp.example"


@pytest.mark.parametrize(
    "given", ["github:octo/repo#0", "0", "https://github.com/o/r/pull/0"]
)
def test_a_zero_pull_request_number_is_a_caller_mistake(given):
    with pytest.raises(ValueError, match="positive"):
        github_ops.resolve_pull_request(given, REF)


def test_a_merge_github_did_not_do_is_exit_1(tmp_path, monkeypatch):
    _register_pr(tmp_path)
    fake = FakeGitHubClient()
    monkeypatch.setattr(
        fake, "merge_pull", lambda *a, **k: {"merged": False, "message": "conflict"}
    )
    result = github_ops.merge_pull_request(
        "12", REF, "merge", _config(tmp_path), client=fake
    )
    assert result["exitCode"] == 1 and "conflict" in _words(result)


def test_merge_pins_the_reviewed_head(tmp_path):
    _register_pr(tmp_path)
    fake = FakeGitHubClient()
    github_ops.merge_pull_request(
        "12", REF, "merge", _config(tmp_path), sha="a" * 40, client=fake
    )
    assert fake.calls[-1][1]["sha"] == "a" * 40
    with pytest.raises(ValueError, match="sha"):
        github_ops.merge_pull_request("12", REF, "merge", _config(tmp_path), sha="x;y")


def test_pr_create_keys_the_link_by_githubs_own_spelling(tmp_path):
    _register(tmp_path, "github:Octo/Repo#5")
    fake = FakeGitHubClient()
    fake.create_pull = lambda *a, **k: (12, "https://github.com/Octo/Repo/pull/12")
    result = github_ops.create_pull_request(
        "github:Octo/Repo#5",
        "T",
        "B",
        "x",
        base="main",
        repository="octo/repo",
        config=_config(tmp_path),
        client=fake,
    )
    assert result["pullRequest"] == "github:Octo/Repo#12"


# -- the owner's rule: a lifecycle act needs a registered work item (R1.10) ------


def test_merge_of_a_pull_request_no_work_item_owns_is_refused(tmp_path):
    _register(tmp_path)  # the work item is registered, the PR is not linked
    fake = FakeGitHubClient()
    result = github_ops.merge_pull_request(
        "12", REF, "merge", _config(tmp_path), client=fake
    )
    assert result["exitCode"] == 1 and "not a work item registered" in _words(result)
    assert fake.calls == [] and fake.merged == []


def test_a_pull_request_that_is_itself_the_work_item_may_be_merged(tmp_path):
    _register(tmp_path, "github:octo/repo#12")
    fake = FakeGitHubClient()
    result = github_ops.merge_pull_request(
        "github:octo/repo#12", config=_config(tmp_path), client=fake
    )
    assert result["exitCode"] == 0


def test_an_adhoc_work_item_may_merge_a_pull_request_it_names(tmp_path):
    """The `the-loop do` exception the owner named."""
    from the_loop.core import sessions as core_sessions

    _register(tmp_path)
    core_sessions._control_store(_config(tmp_path)).record(REF, "do", source="cli")
    fake = FakeGitHubClient()
    result = github_ops.merge_pull_request(
        "github:octo/other#9", REF, "merge", _config(tmp_path), client=fake
    )
    assert result["exitCode"] == 0 and fake.merged == [("octo", "other", 9, "merge")]


def test_a_non_adhoc_work_item_cannot_merge_a_stranger(tmp_path):
    from the_loop.core import sessions as core_sessions

    _register(tmp_path)
    core_sessions._control_store(_config(tmp_path)).record(REF, "start", source="cli")
    fake = FakeGitHubClient()
    result = github_ops.merge_pull_request(
        "github:octo/other#9", REF, "merge", _config(tmp_path), client=fake
    )
    assert result["exitCode"] == 1 and fake.merged == []


def test_close_ticket_closes_a_registered_work_item(tmp_path):
    _register(tmp_path)
    fake = FakeGitHubClient()
    result = github_ops.close_ticket(
        REF, "completed", config=_config(tmp_path), client=fake
    )
    assert result["exitCode"] == 0 and result["closed"] is True
    assert fake.closed == [("octo", "repo", 5, "completed")]


def test_close_ticket_refuses_an_unregistered_ticket(tmp_path):
    fake = FakeGitHubClient()
    result = github_ops.close_ticket(REF, config=_config(tmp_path), client=fake)
    assert result["exitCode"] == 1 and fake.closed == []


def test_close_ticket_refuses_an_unknown_reason(tmp_path):
    with pytest.raises(ValueError, match="close reason"):
        github_ops.close_ticket(REF, "duplicate", config=_config(tmp_path))


def test_resolve_thread_resolves_one_of_the_prs_own_threads(tmp_path):
    _register_pr(tmp_path)
    fake = FakeGitHubClient()
    fake.threads[("octo", "repo", 12)] = [{"id": "PRRT_1", "isResolved": False}]
    result = github_ops.resolve_thread(
        "12", "PRRT_1", REF, _config(tmp_path), client=fake
    )
    assert result["exitCode"] == 0 and fake.resolved == ["PRRT_1"]


def test_abuse_447_a3_a_thread_of_another_pull_request_is_refused(tmp_path):
    _register_pr(tmp_path)
    fake = FakeGitHubClient()
    fake.threads[("octo", "repo", 12)] = [{"id": "PRRT_1", "isResolved": False}]
    result = github_ops.resolve_thread(
        "12", "PRRT_elsewhere", REF, _config(tmp_path), client=fake
    )
    assert result["exitCode"] == 1 and fake.resolved == []


def test_resolve_thread_of_an_unowned_pull_request_is_refused(tmp_path):
    fake = FakeGitHubClient()
    result = github_ops.resolve_thread(
        "github:octo/repo#12", "PRRT_1", config=_config(tmp_path), client=fake
    )
    assert result["exitCode"] == 1 and fake.calls == []


# -- pr ready (issue-465) ---------------------------------------------------------


def _draft(fake, number=12, **fields):
    doc = {"number": number, "state": "open", "draft": True, "node_id": "PR_kw12"}
    doc.update(fields)
    fake.pulls[("octo", "repo", number)] = doc


def test_issue_465_pr_ready_marks_a_registered_work_items_draft_ready(
    tmp_path, monkeypatch
):
    _register_pr(tmp_path)
    fake = FakeGitHubClient()
    _draft(fake)
    emitted = []
    monkeypatch.setattr(
        github_ops.eventlog, "emit", lambda name, **kw: emitted.append((name, kw))
    )
    result = github_ops.mark_ready("12", REF, _config(tmp_path), client=fake)
    assert result["exitCode"] == 0
    assert result["pullRequest"] == "github:octo/repo#12"
    assert result["ready"] is True and result["changed"] is True
    assert fake.readied == ["PR_kw12"]
    assert fake.pulls[("octo", "repo", 12)]["draft"] is False
    assert "ready for review" in _words(result)
    assert ("work_item.pr_ready", {"pull_request": "github:octo/repo#12"}) in emitted


def test_issue_465_pr_ready_on_a_ready_pull_request_writes_nothing(tmp_path):
    _register_pr(tmp_path)
    fake = FakeGitHubClient()
    _draft(fake, draft=False)
    result = github_ops.mark_ready("12", REF, _config(tmp_path), client=fake)
    assert result["exitCode"] == 0
    assert result["ready"] is True and result["changed"] is False
    assert fake.readied == [] and fake.calls_to == ["get_pull"]
    assert "already ready" in _words(result)


@pytest.mark.parametrize(
    "fields, word",
    [({"state": "closed", "merged": True}, "merged"), ({"state": "closed"}, "closed")],
)
def test_issue_465_pr_ready_refuses_a_pull_request_that_is_not_open(
    tmp_path, fields, word
):
    _register_pr(tmp_path)
    fake = FakeGitHubClient()
    _draft(fake, **fields)
    result = github_ops.mark_ready("12", REF, _config(tmp_path), client=fake)
    assert result["exitCode"] == 1 and result["ready"] is False
    assert fake.readied == [] and word in _words(result)


def test_issue_465_pr_ready_still_draft_after_the_mutation_is_exit_1(tmp_path):
    _register_pr(tmp_path)
    fake = FakeGitHubClient()
    _draft(fake)
    fake.stays_draft = True
    result = github_ops.mark_ready("12", REF, _config(tmp_path), client=fake)
    assert result["exitCode"] == 1 and result["ready"] is False


@pytest.mark.parametrize("method", ["get_pull", "mark_pull_ready"])
def test_issue_465_pr_ready_refused_by_github_is_exit_1(tmp_path, method):
    _register_pr(tmp_path)
    fake = FakeGitHubClient(
        fail_on={method: http_error(403, "Resource not accessible")}
    )
    _draft(fake)
    result = github_ops.mark_ready("12", REF, _config(tmp_path), client=fake)
    assert result["exitCode"] == 1 and result["changed"] is False
    assert "403" in _words(result) and "Resource not accessible" in _words(result)


def test_abuse_465_pr_ready_of_an_unowned_pull_request_asks_github_nothing(tmp_path):
    fake = FakeGitHubClient()
    _draft(fake)
    result = github_ops.mark_ready(
        "github:octo/repo#12", config=_config(tmp_path), client=fake
    )
    assert result["exitCode"] == 1 and fake.calls == []
    assert "not a work item registered" in _words(result)


def test_abuse_465_pr_ready_on_an_untrusted_host_is_refused_before_a_request(
    tmp_path,
):
    fake = FakeGitHubClient()
    with pytest.raises(ValueError, match="not a GitHub host"):
        github_ops.mark_ready(
            "https://evil.example/octo/repo/pull/12",
            config=_config(tmp_path),
            client=fake,
        )
    with pytest.raises(ValueError, match="--work-item"):
        github_ops.mark_ready("12", config=_config(tmp_path), client=fake)
    assert fake.calls == []


def test_discover_finds_a_pull_request_opened_from_a_fork(tmp_path):
    """R4.5 — the checkout is a fork; the PR lives in the work item's repository."""
    _register(tmp_path)
    fake = FakeGitHubClient()
    fake.heads[("octo", "repo", "me:feat/x")] = [
        {"number": 21, "html_url": "https://github.com/octo/repo/pull/21"}
    ]
    result = github_ops.discover_pull_requests(
        REF, "feat/x", "me/repo", _config(tmp_path), client=fake
    )
    assert result["found"] == ["github:octo/repo#21"]
    asked = [
        (c[1]["owner"], c[1]["head_owner"])
        for c in fake.calls
        if c[0] == "open_pulls_for_head"
    ]
    assert asked == [("me", "me"), ("octo", "me")]


def test_discover_takes_an_explicit_head_owner(tmp_path):
    _register(tmp_path)
    fake = FakeGitHubClient()
    fake.heads[("octo", "repo", "me:feat/x")] = [{"number": 22}]
    result = github_ops.discover_pull_requests(
        REF, "feat/x", config=_config(tmp_path), head_owner="me", client=fake
    )
    assert result["found"] == ["github:octo/repo#22"]


# -- ownership of an accepted, parked work item (issue-453) ----------------------


def _named(tmp_path, name="alpha"):
    config = _config(tmp_path)
    config["instance"] = {"name": name}
    return config


def _store(config):
    from the_loop.core import sessions as core_sessions

    return core_sessions._control_store(config)


def _park(config, ref=REF, instance="alpha", command="start"):
    """What `sessions start` leaves when it parks at the first human gate: a
    control record stamped with the instance, and no session."""
    return _store(config).record(
        ref, command, source="cli", actor="op", instance=instance
    )


def test_close_ticket_closes_a_work_item_this_instance_parked(tmp_path):
    config = _named(tmp_path)
    _park(config)
    fake = FakeGitHubClient()
    result = github_ops.close_ticket(REF, "not_planned", config=config, client=fake)
    assert result["exitCode"] == 0 and result["closed"] is True
    assert fake.closed == [("octo", "repo", 5, "not_planned")]


def test_closing_a_parked_work_item_cancels_its_pending_start(tmp_path):
    config = _named(tmp_path)
    _park(config)
    store = _store(config)
    assert store.mark_started(REF) and store.start_requested(REF)
    result = github_ops.close_ticket(REF, config=config, client=FakeGitHubClient())
    assert result["startCancelled"] is True
    assert "cancelled the pending start" in _words(result)
    record = store.get(REF)
    assert record is not None and record.command == "stop"
    assert record.source == "cli" and record.instance == "alpha"
    assert not store.start_requested(REF)
    assert store.mark_started(REF), "the work_item_start mark was forgotten"


def test_a_second_close_of_a_parked_work_item_is_a_no_op_with_exit_0(tmp_path):
    config = _named(tmp_path)
    _park(config)
    fake = FakeGitHubClient()
    first = github_ops.close_ticket(REF, config=config, client=fake)
    before = _store(config).get(REF)
    second = github_ops.close_ticket(REF, config=config, client=fake)
    assert first["startCancelled"] is True and second["startCancelled"] is False
    assert second["exitCode"] == 0 and len(fake.closed) == 2
    after = _store(config).get(REF)
    assert after is not None and before is not None
    assert after.to_dict() == before.to_dict(), "nothing was re-recorded"


def test_a_close_github_refuses_leaves_the_parked_item_armed(tmp_path):
    config = _named(tmp_path)
    _park(config)
    fake = FakeGitHubClient(missing={("octo", "repo", 5)})
    result = github_ops.close_ticket(REF, config=config, client=fake)
    assert result["exitCode"] == 1 and result["closed"] is False
    assert "startCancelled" not in result
    assert _store(config).start_requested(REF)


def test_a_session_backed_close_records_no_stop(tmp_path):
    config = _named(tmp_path)
    _register(tmp_path)
    _park(config)  # the arming that spawned the session is still recorded
    result = github_ops.close_ticket(REF, config=config, client=FakeGitHubClient())
    assert result["exitCode"] == 0 and result["startCancelled"] is False
    record = _store(config).get(REF)
    assert record is not None and record.command == "start"


def test_abuse_453_a1_a_record_another_instance_wrote_grants_nothing(tmp_path):
    config = _named(tmp_path, "alpha")
    _park(config, instance="beta")
    fake = FakeGitHubClient()
    result = github_ops.close_ticket(REF, config=config, client=fake)
    assert result["exitCode"] == 1 and fake.closed == []
    assert "not a work item registered on this instance" in _words(result)
    assert _store(config).start_requested(REF), "the other instance's arming stands"


def test_abuse_453_a2_an_unnamed_record_is_not_a_named_instances(tmp_path):
    config = _named(tmp_path, "alpha")
    _park(config, instance="")
    fake = FakeGitHubClient()
    assert github_ops.close_ticket(REF, config=config, client=fake)["exitCode"] == 1
    assert fake.closed == []


def test_abuse_453_a2_a_named_record_is_not_an_unnamed_instances(tmp_path):
    config = _config(tmp_path)
    _park(config, instance="alpha")
    fake = FakeGitHubClient()
    assert github_ops.close_ticket(REF, config=config, client=fake)["exitCode"] == 1
    assert fake.closed == []


def test_an_unnamed_instance_owns_the_records_it_wrote(tmp_path):
    config = _config(tmp_path)
    _park(config, instance="")
    fake = FakeGitHubClient()
    assert github_ops.close_ticket(REF, config=config, client=fake)["exitCode"] == 0
    assert fake.closed == [("octo", "repo", 5, "completed")]


def test_abuse_453_a3_an_ended_items_record_grants_nothing(tmp_path):
    config = _named(tmp_path)
    _park(config)
    _store(config).record_ended(REF, {"state": "closed", "kind": "issue"})
    fake = FakeGitHubClient()
    assert github_ops.close_ticket(REF, config=config, client=fake)["exitCode"] == 1
    assert fake.closed == []


def test_an_unreadable_control_record_grants_nothing(tmp_path, monkeypatch):
    from the_loop.control import ControlStore

    config = _named(tmp_path)
    _park(config)
    monkeypatch.setattr(
        ControlStore, "get", lambda self, item: (_ for _ in ()).throw(OSError("disk"))
    )
    fake = FakeGitHubClient()
    assert github_ops.close_ticket(REF, config=config, client=fake)["exitCode"] == 1
    assert fake.closed == []


def test_a_parked_work_item_owns_no_pull_request(tmp_path):
    """R1.3: the record reaches its own ref only — a stranger PR named beside a
    parked --work-item is still refused."""
    config = _named(tmp_path)
    _park(config)
    fake = FakeGitHubClient()
    result = github_ops.merge_pull_request(
        "github:octo/repo#12", work_item=REF, config=config, client=fake
    )
    assert result["exitCode"] == 1 and fake.merged == []


def test_a_parked_pull_request_work_item_may_be_acted_on(tmp_path):
    """A pull request that is itself the parked work item is the instance's."""
    config = _named(tmp_path)
    _park(config, ref="github:octo/repo#12")
    fake = FakeGitHubClient()
    result = github_ops.merge_pull_request(
        "github:octo/repo#12", config=config, client=fake
    )
    assert result["exitCode"] == 0 and fake.merged


# -- a linked pull request carries every arming label (issue-466) -----------------

TWO_LABELS = ["the-loop: auto-execute", "the-loop: rr"]


def test_issue_466_pr_create_applies_every_auto_execute_label(tmp_path):
    """R1: the PR is armed with the whole list, not the one label the skill named."""
    _register(tmp_path)
    fake = FakeGitHubClient()
    result = github_ops.create_pull_request(
        REF,
        "T",
        "B",
        "claude/x",
        base="main",
        config=_config(tmp_path, autoExecuteLabels=TWO_LABELS),
        client=fake,
    )
    assert result["exitCode"] == 0 and result["linked"] is True
    assert fake.labels[("octo", "repo", 12)] == TWO_LABELS
    assert result["labels"] == TWO_LABELS
    assert "the-loop: rr" in _words(result)


def test_issue_466_the_default_label_when_the_operator_set_none(tmp_path):
    """R1: no `routing.autoExecuteLabels` reads as the dispatcher reads it."""
    _register(tmp_path)
    fake = FakeGitHubClient()
    github_ops.create_pull_request(
        REF, "T", "B", "claude/x", base="main", config=_config(tmp_path), client=fake
    )
    assert fake.labels[("octo", "repo", 12)] == ["the-loop: auto-execute"]


def test_issue_466_an_empty_label_list_labels_nothing(tmp_path):
    _register(tmp_path)
    fake = FakeGitHubClient()
    result = github_ops.create_pull_request(
        REF,
        "T",
        "B",
        "claude/x",
        base="main",
        config=_config(tmp_path, autoExecuteLabels=[]),
        client=fake,
    )
    assert result["exitCode"] == 0 and result["labels"] == []
    assert "add_labels" not in fake.calls_to


def test_issue_466_a_pull_request_that_is_not_linked_is_not_labelled(
    tmp_path, monkeypatch
):
    """R3: armed but untracked, the PR would be spawned as a work item of its own."""
    _register(tmp_path)
    monkeypatch.setattr(
        "the_loop.core.sessions.link_pull_request",
        lambda *a, **k: {
            "exitCode": 1,
            "messages": [{"stream": "err", "text": "registry is read-only"}],
        },
    )
    fake = FakeGitHubClient()
    result = github_ops.create_pull_request(
        REF, "T", "B", "claude/x", base="main", config=_config(tmp_path), client=fake
    )
    assert result["linked"] is False and result["labels"] == []
    assert "add_labels" not in fake.calls_to


def test_issue_466_a_refused_label_is_a_note_not_a_failure(tmp_path):
    """R4: the PR exists and is linked; exit 1 would invite a second PR."""
    _register(tmp_path)
    fake = FakeGitHubClient(fail_on={"add_labels": http_error(403, "no triage")})
    result = github_ops.create_pull_request(
        REF,
        "T",
        "B",
        "claude/x",
        base="main",
        config=_config(tmp_path, autoExecuteLabels=TWO_LABELS),
        client=fake,
    )
    assert result["exitCode"] == 0 and result["linked"] is True
    assert result["labels"] == []
    errs = " ".join(m["text"] for m in result["messages"] if m["stream"] == "err")
    assert "not labelled" in errs and "the-loop: rr" in errs and "no triage" in errs


def test_issue_466_link_pr_labels_a_newly_linked_pull_request_once(tmp_path):
    """R2: `sessions link-pr` arms the PR it records; a re-run asks GitHub nothing."""
    _register(tmp_path)
    fake = FakeGitHubClient()
    config = _config(tmp_path, autoExecuteLabels=TWO_LABELS)
    first = github_ops.link_pull_request(REF, "12", config, client=fake)
    assert first["exitCode"] == 0 and first["linked"] is True
    assert first["labels"] == TWO_LABELS
    assert fake.labels[("octo", "repo", 12)] == TWO_LABELS
    again = github_ops.link_pull_request(REF, "12", config, client=fake)
    assert again["exitCode"] == 0 and again["linked"] is False
    assert again["labels"] == []
    assert fake.calls_to.count("add_labels") == 1


def test_issue_466_link_pr_without_a_session_labels_nothing(tmp_path):
    fake = FakeGitHubClient()
    result = github_ops.link_pull_request(REF, "12", _config(tmp_path), client=fake)
    assert result["exitCode"] == 1 and fake.calls == []


def test_issue_466_link_pr_to_an_untrusted_host_links_but_does_not_label(tmp_path):
    """A3: the token is never sent to a host the operator did not configure."""
    _register(tmp_path)
    fake = FakeGitHubClient()
    result = github_ops.link_pull_request(
        REF, "github:evil.example/octo/repo#12", _config(tmp_path), client=fake
    )
    assert result["exitCode"] == 0 and result["linked"] is True
    assert result["labels"] == [] and fake.calls == []
    assert "not labelled" in _words(result)


def test_issue_466_discover_labels_each_newly_linked_pull_request(tmp_path):
    """R2: the PostToolUse hook's path arms a PR opened by hand or by MCP."""
    _register(tmp_path)
    fake = FakeGitHubClient()
    fake.heads[("octo", "repo", "claude/x")] = [
        {"number": 12, "html_url": "https://github.com/octo/repo/pull/12"},
    ]
    config = _config(tmp_path, autoExecuteLabels=TWO_LABELS)
    result = github_ops.discover_pull_requests(
        REF, "claude/x", config=config, client=fake
    )
    assert result["linked"] == ["github:octo/repo#12"]
    assert fake.labels[("octo", "repo", 12)] == TWO_LABELS
    github_ops.discover_pull_requests(REF, "claude/x", config=config, client=fake)
    assert fake.calls_to.count("add_labels") == 1  # every push re-runs discovery


# -- pr checks (issue-462) -------------------------------------------------------


def _actions_run(job, name, conclusion="failure", status="completed"):
    return {
        "id": job,
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "html_url": f"https://github.com/octo/repo/actions/runs/1/job/{job}",
        "app": {"slug": "github-actions"},
        "output": {"title": f"{name} failed", "summary": "1 error"},
    }


def _checks_fake():
    fake = FakeGitHubClient()
    fake.pulls[("octo", "repo", 12)] = {
        "state": "open",
        "head": {"sha": SHA},
        "html_url": "https://github.com/octo/repo/pull/12",
    }
    return fake


def test_issue_462_pr_checks_lists_every_check_with_the_failing_logs(tmp_path):
    fake = _checks_fake()
    fake.check_runs[SHA] = [
        _actions_run(1, "lint", "success"),
        _actions_run(2, "test (3.12)"),
        {
            "id": 3,
            "name": "codecov",
            "status": "completed",
            "conclusion": "failure",
            "details_url": "https://codecov.example/x",
            "app": {"slug": "codecov"},
        },
    ]
    fake.statuses[SHA] = [
        {"context": "ci/jenkins", "state": "error", "description": "boom"}
    ]
    fake.job_logs[2] = ["E   assert 1 == 2", "FAILED"]
    result = github_ops.pull_request_checks(
        "12", REF, config=_config(tmp_path), client=fake
    )
    assert result["exitCode"] == 0
    assert result["headSha"] == SHA
    assert result["rollup"]["conclusion"] == "failure"
    by_name = {c["name"]: c for c in result["checks"]}
    assert set(by_name) == {"lint", "test (3.12)", "codecov", "ci/jenkins"}
    assert by_name["lint"]["failing"] is False and "logTail" not in by_name["lint"]
    assert by_name["test (3.12)"] == {
        "name": "test (3.12)",
        "kind": "check-run",
        "status": "completed",
        "conclusion": "failure",
        "failing": True,
        "url": "https://github.com/octo/repo/actions/runs/1/job/2",
        "summary": "test (3.12) failed\n\n1 error",
        "logTail": ["E   assert 1 == 2", "FAILED"],
    }
    # Not GitHub Actions: no log the API can serve, so none is asked for.
    assert by_name["codecov"]["failing"] is True
    assert by_name["codecov"]["url"] == "https://codecov.example/x"
    assert "logTail" not in by_name["codecov"]
    assert by_name["ci/jenkins"]["kind"] == "status"
    assert by_name["ci/jenkins"]["failing"] is True
    assert by_name["ci/jenkins"]["summary"] == "boom"
    assert fake.calls_to == ["get_pull", "commit_checks", "job_log_tail"]
    assert sorted(result["rollup"]["failing"]) == sorted(
        c["name"] for c in result["checks"] if c["failing"]
    )


def test_issue_462_pr_checks_failing_filters_and_log_lines_0_fetches_no_log(tmp_path):
    fake = _checks_fake()
    fake.check_runs[SHA] = [_actions_run(1, "lint", "success"), _actions_run(2, "test")]
    result = github_ops.pull_request_checks(
        "12", REF, failing_only=True, log_lines=0, config=_config(tmp_path), client=fake
    )
    assert [c["name"] for c in result["checks"]] == ["test"]
    assert "logTail" not in result["checks"][0]
    assert result["rollup"]["total"] == 2
    assert "job_log_tail" not in fake.calls_to


def test_issue_462_pr_checks_fetches_at_most_five_logs(tmp_path):
    fake = _checks_fake()
    fake.check_runs[SHA] = [_actions_run(n, f"job {n}") for n in range(1, 8)]
    fake.job_logs.update({n: [f"log {n}"] for n in range(1, 8)})
    result = github_ops.pull_request_checks(
        "12", REF, config=_config(tmp_path), client=fake
    )
    with_logs = [c for c in result["checks"] if "logTail" in c]
    assert len(with_logs) == 5
    assert fake.calls_to.count("job_log_tail") == 5


def test_issue_462_a_log_that_cannot_be_read_does_not_fail_the_read(tmp_path):
    fake = _checks_fake()
    fake.check_runs[SHA] = [_actions_run(2, "test")]
    fake.fail_on["job_log_tail"] = http_error(403, "Resource not accessible")
    result = github_ops.pull_request_checks(
        "12", REF, config=_config(tmp_path), client=fake
    )
    assert result["exitCode"] == 0
    assert "Resource not accessible" in result["checks"][0]["logError"]
    assert "logTail" not in result["checks"][0]


def test_issue_462_a_startup_failure_is_failing(tmp_path):
    runs = [{"name": "wf", "status": "completed", "conclusion": "startup_failure"}]
    assert github_ops.checks_rollup(runs, [])["conclusion"] == "failure"


def test_issue_462_pr_checks_of_a_missing_pull_request_is_exit_1(tmp_path):
    result = github_ops.pull_request_checks(
        "github:octo/repo#99", config=_config(tmp_path), client=FakeGitHubClient()
    )
    assert result["exitCode"] == 1


def test_issue_462_a_long_summary_is_capped(tmp_path):
    fake = _checks_fake()
    run = _actions_run(2, "test")
    run["output"] = {"title": "", "summary": "x" * 5000}
    fake.check_runs[SHA] = [run]
    result = github_ops.pull_request_checks(
        "12", REF, log_lines=0, config=_config(tmp_path), client=fake
    )
    assert len(result["checks"][0]["summary"]) == 2000


@pytest.mark.parametrize(
    "pr, work_item",
    [("12", ""), ("github:evil.example/octo/repo#12", "")],
)
def test_abuse_462_pr_checks_refuses_before_any_request(tmp_path, pr, work_item):
    fake = FakeGitHubClient()
    with pytest.raises(ValueError):
        github_ops.pull_request_checks(
            pr, work_item, config=_config(tmp_path), client=fake
        )
    assert fake.calls == []


def test_abuse_462_pr_checks_refuses_a_negative_log_line_count(tmp_path):
    fake = FakeGitHubClient()
    with pytest.raises(ValueError, match="log"):
        github_ops.pull_request_checks(
            "12", REF, log_lines=-1, config=_config(tmp_path), client=fake
        )
    assert fake.calls == []
