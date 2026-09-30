"""Unit tests for the shared comment and issue writers (issue-106, issue-442).

The writing sites — reactions (issue-84), the session announcement (issue-86),
the control paper trail (issue-106), the ledger's kickoff (issue-309) — all
rely on the contract asserted here: one client, coordinates validated before
they reach it, and best-effort failure that never raises. Driven by the
in-memory client double (``ghfakes``); the real client is proved in
``test_ghapi.py``.
"""

import pytest
from ghfakes import FakeGitHubClient, http_error, missing_token

from the_loop.comments import (
    create_issue,
    post_issue_comment,
    post_issue_comment_with_url,
)
from the_loop.ghapi import GitHubApiConfig
from the_loop.sessions import WorkItemRef

REF = WorkItemRef.parse("github:octo/repo#15")
GHE = "ghe.corp.example"
GHE_REF = WorkItemRef.parse(f"github:{GHE}/octo/repo#15")


def test_a_successful_post_reports_ok():
    gh = FakeGitHubClient()
    ok, error = post_issue_comment(REF, "hello", client=gh)
    assert (ok, error) == (True, "")
    assert gh.posted == [("octo", "repo", 15, "hello", "")]


def test_the_post_reaches_the_issues_endpoint_for_issues_and_pull_requests():
    """One operation covers both kinds — the client's `post_comment` is the
    issues endpoint, which serves PR conversations too."""
    gh = FakeGitHubClient()
    post_issue_comment(REF, "hi", client=gh)
    assert gh.calls_to == ["post_comment"]
    assert gh.calls[0][1]["number"] == 15


def test_a_missing_token_is_a_reason_not_an_exception():
    gh = FakeGitHubClient(token=False)
    ok, error = post_issue_comment(REF, "hi", client=gh)
    assert ok is False
    assert error.startswith("no GitHub token")
    assert "GH_TOKEN" in error and "GITHUB_TOKEN" in error


def test_a_failing_call_reports_githubs_status_and_message():
    gh = FakeGitHubClient(fail=http_error(401, "Bad credentials"))
    ok, error = post_issue_comment(REF, "hi", client=gh)
    assert ok is False
    assert error == "GitHub 401: Bad credentials"


def test_a_client_that_raises_anything_else_never_propagates():
    class Exploding(FakeGitHubClient):
        def post_comment(self, *a, **k):
            raise RuntimeError("socket vanished")

    ok, error = post_issue_comment(REF, "hi", client=Exploding())
    assert ok is False and "socket vanished" in error


def test_a_non_github_work_item_is_refused():
    gh = FakeGitHubClient()
    ref = WorkItemRef(provider="jira", owner="octo", repo="repo", number=15)
    ok, error = post_issue_comment(ref, "hi", client=gh)
    assert ok is False
    assert "not a GitHub one" in error
    assert gh.calls == []


def test_unusable_coordinates_never_reach_the_client():
    ref = WorkItemRef(provider="github", owner="octo/../x", repo="repo", number=15)
    gh = FakeGitHubClient()
    ok, error = post_issue_comment(ref, "hi", client=gh)
    assert ok is False
    assert "unusable repo coordinates" in error
    assert gh.calls == []


def test_the_shared_client_is_built_from_the_api_config(monkeypatch):
    """Without an injected client the writer uses the process-wide client for
    the config it was handed — one HTTP session per host for every writer."""
    from the_loop.ghapi import GitHubClient

    GitHubClient._shared.clear()
    api = GitHubApiConfig(token_envs=("MY_TOKEN",))
    monkeypatch.delenv("MY_TOKEN", raising=False)
    ok, error = post_issue_comment(REF, "hi", api=api)
    assert ok is False and "MY_TOKEN" in error
    assert GitHubClient.shared(api) is GitHubClient.shared(api)


# -- post_issue_comment_with_url (issue-208) -------------------------------------


def test_with_url_returns_the_created_comments_html_url():
    gh = FakeGitHubClient(
        comment_url="https://github.com/octo/repo/issues/15#issuecomment-9"
    )
    ok, error, url = post_issue_comment_with_url(REF, "hello", client=gh)
    assert ok and error == ""
    assert url == "https://github.com/octo/repo/issues/15#issuecomment-9"


def test_with_url_degrades_to_empty_never_to_a_failed_post():
    """The comment is on the ticket either way; the URL is best-effort."""
    gh = FakeGitHubClient(comment_url="")
    ok, error, url = post_issue_comment_with_url(REF, "hello", client=gh)
    assert ok and error == "" and url == ""


def test_with_url_shares_the_failure_contract():
    gh = FakeGitHubClient(fail=http_error(500, "boom"))
    ok, error, url = post_issue_comment_with_url(REF, "hello", client=gh)
    assert not ok and "GitHub 500" in error and url == ""


# -- the host (issue-311, R4) ----------------------------------------------------


def test_a_hosted_comment_is_posted_on_its_host():
    gh = FakeGitHubClient()
    post_issue_comment(GHE_REF, "hi", client=gh)
    assert gh.posted == [("octo", "repo", 15, "hi", GHE)]


def test_a_github_com_comment_names_no_host():
    gh = FakeGitHubClient()
    post_issue_comment(REF, "hi", client=gh)
    assert gh.posted[0][4] == ""


# -- create_issue (issue-309) ----------------------------------------------------


def test_an_issue_is_opened_with_its_labels_and_the_ref_comes_back():
    gh = FakeGitHubClient(next_issue_number=9)
    ok, error, ref, url = create_issue(
        "octo/repo", "t", "b", ["the-loop: auto-execute", " "], client=gh
    )
    assert ok, error
    assert ref == "github:octo/repo#9"
    assert url == "https://github.com/octo/repo/issues/9"
    assert gh.created == [("octo", "repo", "t", "b", ["the-loop: auto-execute"], "")]


def test_a_kickoff_slug_may_name_its_host():
    """R4.4 — the ref the ledger composes carries the host it was asked on, so
    the Slack thread binds to the right work item."""
    gh = FakeGitHubClient(next_issue_number=9)
    ok, error, ref, url = create_issue(f"{GHE}/octo/repo", "t", "b", client=gh)
    assert ok, error
    assert ref == f"github:{GHE}/octo/repo#9"
    assert gh.created[0][5] == GHE


@pytest.mark.parametrize(
    "slug", ["https://ghe.corp.example/octo/repo", "ghe/octo/repo", "a/b/c/d", "x"]
)
def test_a_kickoff_slug_with_a_bad_host_is_refused(slug):
    gh = FakeGitHubClient()
    ok, error, ref, _ = create_issue(slug, "t", "b", client=gh)
    assert ok is False and ref == ""
    assert gh.calls == []


def test_an_issue_needs_a_title():
    gh = FakeGitHubClient()
    ok, error, _, _ = create_issue("octo/repo", "  ", "b", client=gh)
    assert ok is False and "title" in error
    assert gh.calls == []


def test_an_issue_write_without_a_token_is_a_reason():
    ok, error, ref, url = create_issue(
        "octo/repo", "t", "b", client=FakeGitHubClient(token=False)
    )
    assert (ok, ref, url) == (False, "", "")
    assert error == missing_token().message
