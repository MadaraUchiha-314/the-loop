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
