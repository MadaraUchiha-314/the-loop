"""Unit tests for the core facade's repo-scoped queries (issue-161, T2; issue-352)."""

import pytest

from the_loop.core import repo as core_repo
from the_loop.critics import CriticConfigError
from the_loop.scenarios import DEFAULT_GLOBS


def _cli_config(tmp_path, monkeypatch, body: str = "") -> None:
    path = tmp_path / "cli-config.yaml"
    path.write_text('version: "0.10.0"\n' + body)
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))


def test_scenarios_collects_from_the_callers_globs(tmp_path):
    """The globs are the caller's (the agent reads `testing.integrationTestGlobs`
    and passes them) — the CLI reads no harness config (issue-352)."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_thing_integration.py").write_text(
        'def test_x():\n    """\n    Feature: f\n      Scenario: s\n        Given g\n        When w\n        Then t\n    """\n'
    )
    report = core_repo.scenarios(str(tmp_path), globs=["tests/test_*_integration.py"])
    assert report["globs"] == ["tests/test_*_integration.py"]
    assert len(report["scenarios"]) == 1
    assert report["scenarios"][0]["scenario"] == "s"


def test_scenarios_without_globs_search_the_defaults(tmp_path):
    assert core_repo.scenarios(str(tmp_path))["globs"] == list(DEFAULT_GLOBS)


def test_instructions_reports_the_docs_handed_in(tmp_path):
    report = core_repo.instructions(
        str(tmp_path), docs=["docs/house.md"], on_missing="warn"
    )
    assert report["onMissing"] == "warn"
    docs = report["docs"]
    assert len(docs) == 1
    assert docs[0]["path"] == "docs/house.md"
    assert docs[0]["state"] == "missing"
    assert docs[0]["resolvedOk"] is False


def test_instructions_accepts_the_mapping_shape_with_notes(tmp_path):
    (tmp_path / "rules.md").write_text("x\n")
    report = core_repo.instructions(
        str(tmp_path), docs=[{"path": "rules.md", "notes": "house style"}]
    )
    assert report["docs"][0]["state"] == "present"
    assert report["docs"][0]["notes"] == "house style"


def test_critics_lists_the_cli_configs_entries_without_argv(tmp_path, monkeypatch):
    _cli_config(
        tmp_path,
        monkeypatch,
        "critics:\n  - name: c1\n    harness: cursor\n    model: gpt-5.5\n",
    )
    critics = core_repo.critics(str(tmp_path))
    assert critics == [
        {
            "name": "c1",
            "harness": "cursor",
            "model": "gpt-5.5",
            # The executable and whether it resolves — never the composed argv.
            "binary": "cursor-agent",
            "available": False,
            "enabled": True,
            "error": "",
        }
    ]


def test_critics_never_come_from_the_repositorys_harness_config(tmp_path, monkeypatch):
    """issue-352: a critic entry committed to a repository is inert."""
    (tmp_path / ".the-loop").mkdir()
    (tmp_path / ".the-loop" / "harness-config.yaml").write_text(
        "reviews:\n  critics:\n    - name: smuggled\n      harness: cursor\n"
    )
    _cli_config(tmp_path, monkeypatch)
    assert core_repo.critics(str(tmp_path)) == []


def test_review_policy_is_the_cli_configs_defaulted_block(tmp_path, monkeypatch):
    """issue-352: the round caps are the operator's; a committed `reviews` block in a
    repository's harness config is never read."""
    (tmp_path / ".the-loop").mkdir()
    (tmp_path / ".the-loop" / "harness-config.yaml").write_text(
        "reviews:\n  selfReviewCount: 9\n"
    )
    _cli_config(tmp_path, monkeypatch, "reviews:\n  selfReviewCount: 1\n")
    policy = core_repo.review_policy(str(tmp_path))
    # issue-393 R5.3 adds per-critic effective timeouts; with no critics
    # configured it is present and empty. The counts are unchanged.
    assert policy["selfReviewCount"] == 1
    assert policy["criticReviewCount"] == 3
    assert policy["stopOnNoNewFindings"] is True
    assert policy["escalateOnRepeatFinding"] is True
    assert policy["criticTimeouts"] == {}


def test_review_policy_surfaces_each_critics_effective_timeout(tmp_path, monkeypatch):
    """
    Scenario: `critic policy` shows the timeout a round will actually use

    Requirement: issue-393 R5.3 (B9). An operator must be able to see, without
    reading the source, that a round is not capped at a hidden 120 s — so the
    policy carries each configured critic's effective timeout (its own
    timeoutSeconds, or the generous default).
    """
    _cli_config(
        tmp_path,
        monkeypatch,
        "critics:\n"
        "  - name: fast\n    harness: claude\n    timeoutSeconds: 300\n"
        "  - name: default\n    harness: claude\n",
    )
    timeouts = core_repo.review_policy(str(tmp_path))["criticTimeouts"]
    assert timeouts["fast"] == 300
    from the_loop import critics as critics_mod

    assert timeouts["default"] == critics_mod.DEFAULT_TIMEOUT_SECONDS


def test_critic_run_unknown_name_is_config_error(tmp_path, monkeypatch):
    _cli_config(tmp_path, monkeypatch)
    with pytest.raises(CriticConfigError):
        core_repo.critic_run(str(tmp_path), "ghost", "p", "prompt.md")
