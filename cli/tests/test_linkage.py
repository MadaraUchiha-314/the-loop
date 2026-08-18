"""Unit tests for the work-item existence check (issue-269).

Pure pieces only: the ``gh api`` invocation, the five answer classes, the cache
and the payload → argv trust boundary. Driven by a fake runner — no real ``gh``,
no network. Dispatcher-level scenarios live in ``test_routing.py`` and
``test_webhook_routing_integration.py``.
"""

import subprocess

import pytest

from the_loop import linkage as linkage_mod
from the_loop.linkage import WorkItemVerifier, existence_argv, looks_not_found
from the_loop.sessions import WorkItemRef

REF = WorkItemRef.parse("github:octo/repo#285")
GHE_REF = WorkItemRef.parse("github:ghe.corp.example/octo/repo#285")

NOT_FOUND = "gh: Not Found (HTTP 404)"


class FakeRun:
    """Record ``gh`` invocations without running one."""

    def __init__(self, returncode=0, stderr="", stdout="", raises=None):
        self.calls = []
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout
        self.raises = raises

    def __call__(self, cmd, capture_output=True, text=True, timeout=None):
        self.calls.append(list(cmd))
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(
            cmd, self.returncode, stdout=self.stdout, stderr=self.stderr
        )


@pytest.fixture
def gh_present(monkeypatch):
    monkeypatch.setattr(linkage_mod.shutil, "which", lambda _: "/usr/bin/gh")


@pytest.fixture
def gh_absent(monkeypatch):
    monkeypatch.setattr(linkage_mod.shutil, "which", lambda _: None)


# -- the argv -------------------------------------------------------------------


def test_the_endpoint_answers_for_issues_and_pull_requests():
    """One REST path covers both kinds — the ref says nothing about which."""
    assert existence_argv(REF) == ["api", "repos/octo/repo/issues/285"]


def test_a_non_default_host_is_asked_of_that_host():
    """A GitHub Enterprise ref must never be declared missing by github.com."""
    assert existence_argv(GHE_REF) == [
        "api",
        "--hostname",
        "ghe.corp.example",
        "repos/octo/repo/issues/285",
    ]


# -- the five answer classes ----------------------------------------------------


def test_an_existing_work_item_is_not_missing(gh_present):
    runner = FakeRun(returncode=0, stdout='{"number": 285}')
    verifier = WorkItemVerifier(runner=runner)
    assert verifier.is_missing(REF) is False
    assert runner.calls == [["gh"] + existence_argv(REF)]


def test_a_404_is_the_one_definitive_answer(gh_present):
    verifier = WorkItemVerifier(runner=FakeRun(returncode=1, stderr=NOT_FOUND))
    assert verifier.is_missing(REF) is True


@pytest.mark.parametrize(
    "returncode,stderr",
    [
        (1, "gh: Bad credentials (HTTP 401)"),
        (1, "gh: Resource protected by organization SAML (HTTP 403)"),
        (1, "gh: Internal Server Error (HTTP 500)"),
        (1, ""),
    ],
)
def test_every_other_failure_keeps_the_ref(gh_present, returncode, stderr):
    """Unknown is not absence: a broken read must not mute the daemon."""
    verifier = WorkItemVerifier(runner=FakeRun(returncode=returncode, stderr=stderr))
    assert verifier.is_missing(REF) is False


@pytest.mark.parametrize(
    "boom",
    [OSError("no such file"), subprocess.TimeoutExpired(cmd="gh", timeout=10.0)],
)
def test_a_transport_failure_keeps_the_ref(gh_present, boom):
    verifier = WorkItemVerifier(runner=FakeRun(raises=boom))
    assert verifier.is_missing(REF) is False


def test_no_gh_on_path_keeps_every_ref_and_warns_once(gh_absent, caplog):
    runner = FakeRun()
    verifier = WorkItemVerifier(runner=runner)
    with caplog.at_level("WARNING"):
        assert verifier.is_missing(REF) is False
        assert verifier.is_missing(WorkItemRef.parse("github:octo/repo#9")) is False
    assert runner.calls == []
    assert len([r for r in caplog.records if "not found on PATH" in r.message]) == 1


# -- the cache ------------------------------------------------------------------


def test_a_second_question_about_the_same_ref_costs_no_second_call(gh_present):
    runner = FakeRun(returncode=1, stderr=NOT_FOUND)
    verifier = WorkItemVerifier(runner=runner)
    assert verifier.is_missing(REF) is True
    assert verifier.is_missing(REF) is True
    assert len(runner.calls) == 1


def test_an_existing_item_is_cached_too(gh_present):
    runner = FakeRun(returncode=0)
    verifier = WorkItemVerifier(runner=runner)
    verifier.is_missing(REF)
    verifier.is_missing(REF)
    assert len(runner.calls) == 1


def test_an_unknown_answer_is_never_cached(gh_present):
    """A transient failure must not freeze into a permanent verdict."""
    runner = FakeRun(returncode=1, stderr="gh: Internal Server Error (HTTP 500)")
    verifier = WorkItemVerifier(runner=runner)
    verifier.is_missing(REF)
    verifier.is_missing(REF)
    assert len(runner.calls) == 2


def test_the_cache_is_bounded(gh_present):
    runner = FakeRun(returncode=0)
    verifier = WorkItemVerifier(runner=runner, cache_size=2)
    for number in (1, 2, 3):
        verifier.is_missing(WorkItemRef.parse(f"github:octo/repo#{number}"))
    verifier.is_missing(WorkItemRef.parse("github:octo/repo#1"))  # evicted, re-asked
    assert len(runner.calls) == 4


def test_recorded_evidence_answers_without_a_call(gh_present):
    """The announcement's own 404 is evidence — issue-269 R3.2."""
    runner = FakeRun(returncode=0)
    verifier = WorkItemVerifier(runner=runner)
    verifier.record_missing(REF)
    assert verifier.is_missing(REF) is True
    assert runner.calls == []


# -- the payload → argv boundary (abuse cases) ----------------------------------


@pytest.mark.parametrize(
    "owner,repo",
    [("octo;rm -rf /", "repo"), ("octo", "repo && curl evil"), ("../..", "repo")],
)
def test_hostile_coordinates_never_reach_a_gh_argv(gh_present, owner, repo):
    """Refused before the call — and answered "unknown", so a bad ref is KEPT.

    Dropping it would let a malformed payload delete a work item from routing.
    """
    runner = FakeRun(returncode=1, stderr=NOT_FOUND)
    verifier = WorkItemVerifier(runner=runner)
    item = WorkItemRef(provider="github", owner=owner, repo=repo, number=1)
    assert verifier.is_missing(item) is False
    assert runner.calls == []


def test_a_non_github_provider_is_never_asked(gh_present):
    runner = FakeRun(returncode=1, stderr=NOT_FOUND)
    verifier = WorkItemVerifier(runner=runner)
    item = WorkItemRef(provider="jira", owner="octo", repo="repo", number=1)
    assert verifier.is_missing(item) is False
    assert runner.calls == []


# -- the shared 404 test --------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("gh exited 1: gh: Not Found (HTTP 404)", True),
        ("HTTP 404: Not Found", True),
        ("gh exited 1: gh: Bad credentials (HTTP 401)", False),
        ("", False),
        ("posted 404 comments", False),
    ],
)
def test_looks_not_found(text, expected):
    assert looks_not_found(text) is expected
