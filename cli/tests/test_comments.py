"""Unit tests for the shared ``gh``-backed comment poster (issue-106).

The third gh-writing site after reactions (issue-84) and the session
announcement (issue-86); these assert the contract all three rely on — the
operator's own credentials, an argv that reaches the issues endpoint (which
serves PR conversations too), and best-effort failure that never raises.
"""

import subprocess

import pytest

from the_loop import comments as comments_mod
from the_loop.comments import comment_argv, post_issue_comment
from the_loop.sessions import WorkItemRef

REF = WorkItemRef.parse("github:octo/repo#15")


class FakeRun:
    def __init__(self, returncode=0, raises=None, stderr="boom"):
        self.calls = []
        self.returncode = returncode
        self.raises = raises
        self.stderr = stderr

    def __call__(self, cmd, capture_output=True, text=True, timeout=None):
        self.calls.append(list(cmd))
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(cmd, self.returncode, "", self.stderr)


@pytest.fixture
def gh_present(monkeypatch):
    monkeypatch.setattr(comments_mod.shutil, "which", lambda _: "/usr/bin/gh")


def test_argv_posts_to_the_issues_endpoint():
    argv = comment_argv(REF, "hello")
    assert argv[:3] == ["api", "--method", "POST"]
    assert argv[3] == "repos/octo/repo/issues/15/comments"
    assert argv[-1] == "body=hello"


def test_a_successful_post_reports_ok(gh_present):
    run = FakeRun()
    ok, error = post_issue_comment(REF, "hello", runner=run)
    assert (ok, error) == (True, "")
    assert run.calls[0][0] == "gh"


def test_a_configured_binary_is_used(gh_present):
    run = FakeRun()
    post_issue_comment(REF, "hi", gh_binary="/opt/gh", runner=run)
    assert run.calls[0][0] == "/opt/gh"


def test_a_missing_gh_is_a_reason_not_an_exception(monkeypatch):
    monkeypatch.setattr(comments_mod.shutil, "which", lambda _: None)
    ok, error = post_issue_comment(REF, "hi", runner=FakeRun())
    assert ok is False
    assert "not found on PATH" in error


def test_a_failing_gh_reports_its_output(gh_present):
    ok, error = post_issue_comment(REF, "hi", runner=FakeRun(returncode=1))
    assert ok is False
    assert "gh exited 1" in error and "boom" in error


@pytest.mark.parametrize(
    "raises", [OSError("no such binary"), subprocess.TimeoutExpired("gh", 1)]
)
def test_a_subprocess_failure_never_raises(gh_present, raises):
    ok, error = post_issue_comment(REF, "hi", runner=FakeRun(raises=raises))
    assert ok is False and error


def test_a_non_github_work_item_is_refused(gh_present):
    ref = WorkItemRef(provider="jira", owner="octo", repo="repo", number=15)
    ok, error = post_issue_comment(ref, "hi", runner=FakeRun())
    assert ok is False
    assert "not a GitHub one" in error


def test_unusable_coordinates_never_reach_an_argv(gh_present):
    ref = WorkItemRef(provider="github", owner="octo/../x", repo="repo", number=15)
    run = FakeRun()
    ok, error = post_issue_comment(ref, "hi", runner=run)
    assert ok is False
    assert "unusable repo coordinates" in error
    assert run.calls == []


# -- post_issue_comment_with_url (issue-208) -------------------------------------


class FakeRunStdout(FakeRun):
    def __init__(self, stdout="", **kwargs):
        super().__init__(**kwargs)
        self.stdout = stdout

    def __call__(self, cmd, capture_output=True, text=True, timeout=None):
        self.calls.append(list(cmd))
        return subprocess.CompletedProcess(
            cmd, self.returncode, self.stdout, self.stderr
        )


def test_with_url_returns_the_created_comments_html_url(gh_present):
    from the_loop.comments import post_issue_comment_with_url

    run = FakeRunStdout(
        stdout='{"id": 1, "html_url": "https://github.com/octo/repo/issues/15#issuecomment-9"}'
    )
    ok, error, url = post_issue_comment_with_url(REF, "hello", runner=run)
    assert ok and error == ""
    assert url == "https://github.com/octo/repo/issues/15#issuecomment-9"


@pytest.mark.parametrize("stdout", ["", "not json", "[1,2]", '{"html_url": 3}'])
def test_with_url_degrades_to_empty_never_to_a_failed_post(gh_present, stdout):
    """The comment is on the ticket either way; parsing is best-effort."""
    from the_loop.comments import post_issue_comment_with_url

    ok, error, url = post_issue_comment_with_url(
        REF, "hello", runner=FakeRunStdout(stdout=stdout)
    )
    assert ok and error == "" and url == ""


def test_with_url_shares_the_failure_contract(gh_present):
    from the_loop.comments import post_issue_comment_with_url

    ok, error, url = post_issue_comment_with_url(
        REF, "hello", runner=FakeRunStdout(returncode=1)
    )
    assert not ok and "gh exited 1" in error and url == ""


# -- the host (issue-311, R4) ----------------------------------------------------

from the_loop.comments import create_issue, gh_host_args, issue_argv  # noqa: E402

GHE = "ghe.corp.example"
GHE_REF = WorkItemRef.parse(f"github:{GHE}/octo/repo#15")


def test_gh_host_args_is_written_only_off_the_default():
    """A5: a github.com ref adds nothing to any argv it always had."""
    assert gh_host_args(REF) == []
    assert gh_host_args(GHE_REF) == ["--hostname", GHE]
    assert gh_host_args("") == []
    assert gh_host_args("github.com") == []
    assert gh_host_args(GHE) == ["--hostname", GHE]


def test_a_hosted_comment_is_posted_on_its_host():
    assert comment_argv(GHE_REF, "hi") == [
        "api",
        "--hostname",
        GHE,
        "--method",
        "POST",
        "repos/octo/repo/issues/15/comments",
        "-f",
        "body=hi",
    ]


def test_a_hosted_issue_is_opened_on_its_host():
    argv = issue_argv("octo", "repo", "t", "b", host=GHE)
    assert argv[:3] == ["api", "--hostname", GHE]
    assert "repos/octo/repo/issues" in argv
    assert "--hostname" not in issue_argv("octo", "repo", "t", "b")


def test_a_kickoff_slug_may_name_its_host(gh_present):
    """R4.4 — the ref the ledger composes from GitHub's answer carries the host
    it was asked on, so the Slack thread binds to the right work item."""
    run = FakeRunStdout(
        stdout='{"number": 9, "html_url": "https://ghe.corp.example/octo/repo/issues/9"}'
    )
    ok, error, ref, url = create_issue(f"{GHE}/octo/repo", "t", "b", runner=run)
    assert ok, error
    assert ref == f"github:{GHE}/octo/repo#9"
    assert url.startswith(f"https://{GHE}/")
    assert run.calls[0][1:4] == ["api", "--hostname", GHE]


def test_a_github_com_kickoff_slug_is_unchanged(gh_present):
    run = FakeRunStdout(stdout='{"number": 9}')
    ok, _, ref, _ = create_issue("octo/repo", "t", "b", runner=run)
    assert ok and ref == "github:octo/repo#9"
    assert "--hostname" not in run.calls[0]


@pytest.mark.parametrize(
    "slug", ["https://ghe.corp.example/octo/repo", "ghe/octo/repo", "a/b/c/d"]
)
def test_a_kickoff_slug_with_a_bad_host_is_refused(gh_present, slug):
    run = FakeRunStdout(stdout='{"number": 9}')
    ok, error, ref, _ = create_issue(slug, "t", "b", runner=run)
    assert ok is False and ref == ""
    assert run.calls == []
