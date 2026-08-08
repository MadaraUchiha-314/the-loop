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


def test_check_malformed_repo_never_reaches_the_graph(tmp_path):
    with pytest.raises(ValueError):
        graphs.check(str(tmp_path / "nope"), "issue-1")


def test_skip_declares_against_the_shipped_vocabulary(tmp_path):
    """
    Feature: declared skips over the control plane (issue-177)
      Scenario: an operator declares the spec chain skipped for a doc fix
        Given a repository with a spec directory for a work item
        When the core skip operation declares the spec-chain set with a reason
        Then the six spec-chain nodes are declared and a protected node is rejected

    Requirement: docs/specs/issue-177/requirements.md R2.3, R2.5
    """
    spec = tmp_path / "docs" / "specs" / "issue-9"
    spec.mkdir(parents=True)
    result = graphs.skip(
        str(tmp_path),
        "issue-9",
        ["spec-chain", "security-review"],
        reason="docs-only change",
        actor="@owner",
    )
    assert set(result["declared"]) == {
        "brainstorming",
        "requirements-definition",
        "requirements-approval",
        "design",
        "design-approval",
        "tasks-breakdown",
    }
    assert [r["token"] for r in result["rejected"]] == ["security-review"]


def test_skip_requires_a_reason(tmp_path):
    (tmp_path / "docs" / "specs" / "issue-9").mkdir(parents=True)
    with pytest.raises(ValueError, match="reason is required"):
        graphs.skip(str(tmp_path), "issue-9", ["spec-chain"], reason=" ")
