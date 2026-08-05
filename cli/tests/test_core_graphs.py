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
