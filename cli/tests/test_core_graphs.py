"""Unit tests for the core facade's graph surface (issue-161, T2)."""

import pytest

from the_loop.core import graphs


def test_resolve_repo_rejects_non_directory(tmp_path):
    with pytest.raises(ValueError):
        graphs.resolve_repo(str(tmp_path / "missing"))
    file_path = tmp_path / "a-file"
    file_path.write_text("x")
    with pytest.raises(ValueError):
        graphs.resolve_repo(str(file_path))


def test_repo_resolves_agrees_with_resolve_repo(tmp_path):
    """The predicate and the raiser must not drift (issue-238).

    `check` asks `repo_resolves` and `resolve_repo` raises on the same question,
    so the day they disagree is the day a path one of them rejects reaches core
    through the other. Same three cases as the test above, on the predicate.
    """
    file_path = tmp_path / "a-file"
    file_path.write_text("x")

    assert graphs.repo_resolves(str(tmp_path)) is True
    assert graphs.repo_resolves(str(tmp_path / "missing")) is False
    assert graphs.repo_resolves(str(file_path)) is False


def test_check_reports_this_repos_own_work_item(tmp_path, monkeypatch):
    """
    Feature: control-plane graph reads
      Scenario: a client asks where a work item stands
        Given a repository with a checked-in spec for a work item
        When the core check operation runs against that repo path
        Then it returns the same status report `the-loop check` prints

    Requirement: docs/specs/issue-161/requirements.md R1.1
    """
    import pathlib

    repo_root = str(pathlib.Path(__file__).resolve().parents[2])
    report = graphs.check(repo_root, "issue-161", recompute=True)
    assert report["workItem"] == "issue-161"
    assert report["nodes"]
    node_ids = [n["node"] for n in report["nodes"]]
    assert "requirements-definition" in node_ids


def test_check_answers_a_vanished_checkout_instead_of_raising(tmp_path, monkeypatch):
    """A cleaned-up checkout is expected state, not caller error (issue-238).

    This test asserted `pytest.raises(ValueError)` until issue-238: `check` is
    the one polled verb, and reporting a worktree somebody deleted as a caller
    mistake made the control-plane UI log a 400 per session per poll tick,
    forever. The half that did not change is the half that matters — the path
    still reaches no graph read, asserted here by making `_runtime` fatal.

    Requirement: docs/specs/issue-238/bugfix.md R1.1, R3.2
    """

    def fatal(*args, **kwargs):
        raise AssertionError(
            "check reached core with a repo path that does not resolve"
        )

    monkeypatch.setattr(graphs, "_runtime", fatal)

    report = graphs.check(str(tmp_path / "nope"), "issue-1")

    assert report["repoResolved"] is False
    assert report["workItem"] == "issue-1"
    assert report["currentNode"] == ""
    assert report["nodes"] == []
    assert report["ok"] is False


def test_the_unknown_position_answer_is_not_a_filesystem_oracle(tmp_path):
    """Abuse case 1 of design.md §Security design (issue-238).

    Answering with a 200 must not tell the caller more than the 400 did. The
    400 echoed the path back; this body names nothing at all.
    """
    secret_ish = tmp_path / "some-private-directory-name" / "deeper"

    report = graphs.check(str(secret_ish), "issue-1")
    body = repr(report)

    assert "some-private-directory-name" not in body
    assert str(tmp_path) not in body
    # Pin the whole key set, not just the absence of today's leak: the test is
    # worth little if a later change can add a `detail` or a `path` beside them.
    assert set(report) == {
        "workItem",
        "currentNode",
        "ok",
        "parked",
        "nodes",
        "repoResolved",
    }


def test_a_resolving_repo_keeps_exactly_the_keys_it_always_had(tmp_path):
    """R2.2: the normal answer is byte-identical, so the field is absent.

    Requirement: docs/specs/issue-238/bugfix.md R2.2
    """
    import pathlib

    repo_root = str(pathlib.Path(__file__).resolve().parents[2])

    report = graphs.check(repo_root, "issue-161")

    assert set(report) == {"workItem", "currentNode", "ok", "parked", "nodes"}
    assert "repoResolved" not in report


def test_skip_declares_against_the_shipped_vocabulary(tmp_path):
    """
    Feature: declared skips over the control plane (issue-177)
      Scenario: an operator declares the spec chain skipped for a doc fix
        Given a repository with a spec directory for a work item
        When the core skip operation declares the spec-chain set with a reason
        Then the seven spec-chain nodes are declared and the selection gate is rejected

    Requirement: docs/specs/issue-177/requirements.md R2.3, R2.5;
    docs/specs/issue-179/requirements.md R1.2, R1.5
    """
    spec = tmp_path / "docs" / "specs" / "issue-9"
    spec.mkdir(parents=True)
    result = graphs.skip(
        str(tmp_path),
        "issue-9",
        ["spec-chain", "phase-selection"],
        reason="docs-only change",
        actor="@owner",
    )
    assert set(result["declared"]) == {
        "brainstorming",
        "requirements-definition",
        "requirements-approval",
        "design",
        "test-planning",
        "design-approval",
        "tasks-breakdown",
    }
    # issue-179: `security-review` is declarable now; the gate that does the
    # declaring is the one token the vocabulary still refuses.
    assert [r["token"] for r in result["rejected"]] == ["phase-selection"]


def test_skip_requires_a_reason(tmp_path):
    (tmp_path / "docs" / "specs" / "issue-9").mkdir(parents=True)
    with pytest.raises(ValueError, match="reason is required"):
        graphs.skip(str(tmp_path), "issue-9", ["spec-chain"], reason=" ")


def test_pr_repo_without_a_pr_is_refused(tmp_path):
    """A repository does not identify a loop (issue-183): `--pr-repo` alone would
    silently resolve the OUTER loop while the caller believed it named an inner
    one."""
    (tmp_path / "docs" / "specs" / "issue-1").mkdir(parents=True)
    with pytest.raises(ValueError):
        graphs.check(str(tmp_path), "issue-1", pr_repo="octo/infra")


@pytest.mark.parametrize("hostile", ["../../etc", "a//b", "octo", "a/../b"])
def test_a_hostile_pr_repo_argument_is_refused(tmp_path, hostile):
    """Abuse case 2: the value becomes a directory name, so it is validated at
    the boundary rather than sanitized into something that resolves."""
    (tmp_path / "docs" / "specs" / "issue-1").mkdir(parents=True)
    with pytest.raises(ValueError):
        graphs.check(str(tmp_path), "issue-1", pr=7, pr_repo=hostile)


def test_a_valid_pr_repo_selects_that_repositorys_inner_loop(tmp_path):
    (tmp_path / "docs" / "specs" / "issue-1").mkdir(parents=True)
    report = graphs.check(str(tmp_path), "issue-1", pr=7, pr_repo="octo/infra")
    assert report["workItem"] == "issue-1"
