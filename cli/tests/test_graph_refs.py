"""Ref derivation and degradation reporting — the pure halves (issue-194).

Two silent failures composed into one: the ref was never derived, so every
outbound GitHub call raised; and the error each hook carefully recorded had no
reader, so the command printed a clean answer over a ticket that never received
the question its gate was waiting on.

The unit tests here pin the two seams that make the fix analysable without a
runtime:

* ``derive_ref`` — total, pure, and **refusing** far more often than it accepts.
  Most of these cases are refusals on purpose: the failure mode this function
  must never have is deriving a ref that points somewhere else, so every input
  that is not unambiguously ``issue-<n>`` in ``<owner>/<repo>`` yields ``""``.
* ``_degradations`` — which passing hook results count as a failure to report,
  and which are legitimate no-ops that must stay quiet.

The observable behaviour — what lands on stdout, what reaches the ticket, which
edge is taken — is in ``test_graph_refs_integration.py``.
"""

from __future__ import annotations

import pytest

from the_loop.graph.chain import ChainOutcome
from the_loop.graph.contract import HookResult
from the_loop.graph.integrations.base import IntegrationError
from the_loop.graph.integrations.github import _split_ref
from the_loop.graph.refs import derive_ref, ref_for
from the_loop.graph.runtime import _degradations
from the_loop.graphlink import spec_id_for
from the_loop.sessions import WorkItemRef

# -- derive_ref: the happy path -------------------------------------------------


def test_derive_ref_builds_the_ref_the_integration_expects():
    assert derive_ref("issue-194", "octo/repo") == "github:octo/repo#194"


def test_derive_ref_round_trips_with_the_ingress_translation():
    """The inverse of ``graphlink.spec_id_for`` — the two must agree, or the
    ingress and the graph name different work items."""
    ref = derive_ref("issue-194", "octo/repo")
    assert spec_id_for(WorkItemRef.parse(ref)) == "issue-194"


def test_derive_ref_output_parses_as_a_ref_and_as_a_split():
    ref = derive_ref("issue-7", "Octo-Cat/the.repo_name")
    assert WorkItemRef.parse(ref).number == 7
    assert _split_ref(ref) == ("Octo-Cat", "the.repo_name", "7")


def test_derive_ref_ignores_leading_and_trailing_whitespace():
    assert derive_ref("  issue-1\n", " octo/repo ") == "github:octo/repo#1"


# -- derive_ref: refusals (R1.3, R1.4 — abuse cases A1 and A2) ------------------


@pytest.mark.parametrize(
    "work_item_id",
    [
        "draft-some-slug",  # a pre-ticket draft directory
        "194",  # the number alone
        "issue-",  # no number
        "issue-1x",  # not only digits
        "issue-1/../issue-2",  # a traversal attempt (abuse case A2)
        "ISSUE-1",  # the convention is lowercase
        "",
    ],
)
def test_derive_ref_refuses_non_issue_ids(work_item_id):
    assert derive_ref(work_item_id, "octo/repo") == ""


@pytest.mark.parametrize(
    "origin_repo",
    [
        "",  # not GitHub-ticketed, or nothing declared
        "octo",  # no repository half
        "/repo",  # no owner half
        "octo/",  # empty repository half
        "octo/repo/sub",  # abuse case A1: an extra segment
        "ghe.example.com/octo/repo",  # a host-qualified path (abuse case A1)
        "octo/re po",  # whitespace
        "octo/repo#1",  # a ref smuggled into the config
        "../../etc",  # a traversal attempt
    ],
)
def test_derive_ref_refuses_malformed_origin_repo(origin_repo):
    assert derive_ref("issue-194", origin_repo) == ""


def test_derive_ref_is_total():
    """No input raises. This runs on the way out to an integration, and a
    translation helper that threw would turn a best-effort comment into a
    wedged work item."""
    for bad in ("", "\x00", "issue-" + "9" * 400, "issue-1"):
        assert isinstance(derive_ref(bad, "octo/repo"), str)
        assert isinstance(derive_ref("issue-1", bad), str)


# -- ref_for: the primitive an inner loop needs directly ------------------------


def test_ref_for_builds_a_pull_requests_ref():
    assert ref_for("octo/repo", 7) == "github:octo/repo#7"


@pytest.mark.parametrize("number", [0, -1])
def test_ref_for_refuses_a_number_github_cannot_have(number):
    assert ref_for("octo/repo", number) == ""


def test_ref_for_shares_derive_refs_validation():
    """One validation, two callers — so an inner loop cannot accept a repository
    slug the outer one refuses."""
    for bad in ("", "octo", "octo/repo/sub", "octo/re po"):
        assert ref_for(bad, 7) == ""
        assert derive_ref("issue-7", bad) == ""


# -- _split_ref: the error names its remedies (R3.1) ---------------------------


def test_split_ref_names_both_remedies():
    with pytest.raises(IntegrationError) as excinfo:
        _split_ref("issue-194")
    message = str(excinfo.value)
    assert "issue-194" in message
    assert "<owner>/<repo>#<number>" in message
    assert "--ref" in message
    assert "ticketing.github" in message


def test_split_ref_still_accepts_every_shape_it_did_before():
    assert _split_ref("github:octo/repo#15") == ("octo", "repo", "15")
    assert _split_ref("octo/repo#15") == ("octo", "repo", "15")


# -- _degradations: what counts as a failure to report (R2.1) ------------------


def _outcome(*results) -> ChainOutcome:
    return ChainOutcome(status="pass", results=list(results))


def test_degradations_reports_a_pass_that_recorded_an_error():
    outcome = _outcome(
        HookResult.ok(
            "set-phase-label", label="loop:design", applied=False, error="boom"
        )
    )
    assert _degradations(outcome) == [("set-phase-label", "boom")]


def test_degradations_stays_quiet_about_a_legitimate_no_op():
    """`post-phase-selection` that finds its own marker returns
    ``posted=False`` with a reason and no error. That is idempotency working,
    not a degradation — reporting it would train operators to ignore the line."""
    outcome = _outcome(
        HookResult.ok("post-phase-selection", posted=False, reason="already asked")
    )
    assert _degradations(outcome) == []


def test_degradations_stays_quiet_about_an_ordinary_pass():
    assert _degradations(_outcome(HookResult.ok("log-entry", appended=True))) == []


def test_degradations_reports_every_failing_hook_in_order():
    outcome = _outcome(
        HookResult.ok("set-phase-label", applied=False, error="label failed"),
        HookResult.ok("log-entry", appended=True),
        HookResult.ok("post-phase-selection", posted=False, error="comment failed"),
    )
    assert _degradations(outcome) == [
        ("set-phase-label", "label failed"),
        ("post-phase-selection", "comment failed"),
    ]


def test_degradations_ignores_an_empty_error_field():
    outcome = _outcome(HookResult.ok("notify", sent=False, error=""))
    assert _degradations(outcome) == []


def test_degradation_message_is_the_loops_own_text():
    """Abuse case A3: the reported text is a hook name plus an
    ``IntegrationError`` message — the-loop's own vocabulary, never payload text
    from a comment (the ``Message`` rule, R3.6)."""
    with pytest.raises(IntegrationError) as excinfo:
        _split_ref("issue-194")
    error = str(excinfo.value)
    outcome = _outcome(HookResult.ok("post-phase-selection", posted=False, error=error))
    (hook_name, reported), *rest = _degradations(outcome)
    assert not rest
    assert hook_name == "post-phase-selection"
    # Everything in the line comes from the-loop: the hook's registered name and
    # the integration layer's own sentence. No token, no header, no body.
    assert reported == error
    assert "Bearer" not in reported and "token" not in reported.lower()
