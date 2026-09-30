"""Unit tests for the work-item existence check (issue-269, issue-442).

Pure pieces only: the one question, the answer classes, the cache and the
payload → request trust boundary. Driven by the in-memory client double — no
network. Dispatcher-level scenarios live in ``test_routing.py`` and
``test_webhook_routing_integration.py``.
"""

import pytest
from ghfakes import FakeGitHubClient, http_error, not_found

from the_loop.ghapi import GitHubApiError
from the_loop.linkage import WorkItemVerifier, looks_not_found
from the_loop.sessions import WorkItemRef

REF = WorkItemRef.parse("github:octo/repo#285")
GHE_REF = WorkItemRef.parse("github:ghe.corp.example/octo/repo#285")


# -- the question ---------------------------------------------------------------


def test_the_question_is_the_issues_document_which_answers_for_both_kinds():
    """One read covers issues and pull requests — the ref says nothing about which."""
    gh = FakeGitHubClient()
    WorkItemVerifier(client=gh).is_missing(REF)
    assert gh.calls == [
        ("get_issue", {"owner": "octo", "repo": "repo", "number": 285, "host": ""})
    ]


def test_a_non_default_host_is_asked_of_that_host():
    """A GitHub Enterprise ref must never be declared missing by github.com."""
    gh = FakeGitHubClient()
    WorkItemVerifier(client=gh).is_missing(GHE_REF)
    assert gh.calls[0][1]["host"] == "ghe.corp.example"


# -- the answer classes ---------------------------------------------------------


def test_an_existing_work_item_is_not_missing():
    gh = FakeGitHubClient()
    assert WorkItemVerifier(client=gh).is_missing(REF) is False


def test_a_404_is_the_one_definitive_answer():
    gh = FakeGitHubClient(missing={("octo", "repo", 285)})
    assert WorkItemVerifier(client=gh).is_missing(REF) is True


@pytest.mark.parametrize(
    "error",
    [
        http_error(401, "Bad credentials"),
        http_error(403, "Resource protected by organization SAML"),
        http_error(500, "Internal Server Error"),
        GitHubApiError("GET: connection reset"),
    ],
)
def test_every_other_failure_keeps_the_ref(error):
    """Unknown is not absence: a broken read must not mute the daemon."""
    gh = FakeGitHubClient(fail=error)
    assert WorkItemVerifier(client=gh).is_missing(REF) is False


def test_a_client_raising_anything_else_keeps_the_ref():
    class Exploding(FakeGitHubClient):
        def get_issue(self, *a, **k):
            raise RuntimeError("boom")

    assert WorkItemVerifier(client=Exploding()).is_missing(REF) is False


def test_no_token_keeps_every_ref_and_warns_once(caplog):
    gh = FakeGitHubClient(token=False)
    verifier = WorkItemVerifier(client=gh)
    with caplog.at_level("WARNING"):
        assert verifier.is_missing(REF) is False
        assert verifier.is_missing(WorkItemRef.parse("github:octo/repo#9")) is False
    assert len([r for r in caplog.records if "no GitHub token" in r.message]) == 1


# -- the cache ------------------------------------------------------------------


def test_a_second_question_about_the_same_ref_costs_no_second_call():
    gh = FakeGitHubClient(missing={("octo", "repo", 285)})
    verifier = WorkItemVerifier(client=gh)
    assert verifier.is_missing(REF) is True
    assert verifier.is_missing(REF) is True
    assert len(gh.calls) == 1


def test_an_existing_item_is_cached_too():
    gh = FakeGitHubClient()
    verifier = WorkItemVerifier(client=gh)
    verifier.is_missing(REF)
    verifier.is_missing(REF)
    assert len(gh.calls) == 1


def test_an_unknown_answer_is_never_cached():
    """A transient failure must not freeze into a permanent verdict."""
    gh = FakeGitHubClient(fail=http_error(500, "Internal Server Error"))
    verifier = WorkItemVerifier(client=gh)
    verifier.is_missing(REF)
    verifier.is_missing(REF)
    assert len(gh.calls) == 2


def test_the_cache_is_bounded():
    gh = FakeGitHubClient()
    verifier = WorkItemVerifier(client=gh, cache_size=2)
    for number in (1, 2, 3):
        verifier.is_missing(WorkItemRef.parse(f"github:octo/repo#{number}"))
    verifier.is_missing(WorkItemRef.parse("github:octo/repo#1"))  # evicted, re-asked
    assert len(gh.calls) == 4


def test_recorded_evidence_answers_without_a_call():
    """The announcement's own 404 is evidence — issue-269 R3.2."""
    gh = FakeGitHubClient()
    verifier = WorkItemVerifier(client=gh)
    verifier.record_missing(REF)
    assert verifier.is_missing(REF) is True
    assert gh.calls == []


# -- the payload → request boundary (abuse cases) -------------------------------


@pytest.mark.parametrize(
    "owner,repo",
    [("octo;rm -rf /", "repo"), ("octo", "repo && curl evil"), ("../..", "repo")],
)
def test_hostile_coordinates_never_reach_the_client(owner, repo):
    """Refused before the call — and answered "unknown", so a bad ref is KEPT.

    Dropping it would let a malformed payload delete a work item from routing.
    """
    gh = FakeGitHubClient(missing={(owner, repo, 1)})
    verifier = WorkItemVerifier(client=gh)
    item = WorkItemRef(provider="github", owner=owner, repo=repo, number=1)
    assert verifier.is_missing(item) is False
    assert gh.calls == []


def test_a_non_github_provider_is_never_asked():
    gh = FakeGitHubClient()
    verifier = WorkItemVerifier(client=gh)
    item = WorkItemRef(provider="jira", owner="octo", repo="repo", number=1)
    assert verifier.is_missing(item) is False
    assert gh.calls == []


# -- the shared 404 test --------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        (str(not_found()), True),  # the client's own rendering: "GitHub 404: Not Found"
        ("HTTP 404: Not Found", True),
        ("gh exited 1: gh: Not Found (HTTP 404)", True),
        ("GitHub 401: Bad credentials", False),
        ("404 comments in this thread", False),  # a number, not an answer
        ("Not found: 404", True),
        ("", False),
    ],
)
def test_looks_not_found_is_narrow(text, expected):
    assert looks_not_found(text) is expected
