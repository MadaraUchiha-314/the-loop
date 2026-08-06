"""Unit tests for the core facade's repo-scoped queries (issue-161, T2)."""

import pytest

from the_loop.core import repo as core_repo
from the_loop.critics import CriticConfigError


def _write_harness_config(root, body):
    conf_dir = root / ".the-loop"
    conf_dir.mkdir(parents=True, exist_ok=True)
    (conf_dir / "harness-config.yaml").write_text(body)


def test_scenarios_collects_from_configured_globs(tmp_path):
    _write_harness_config(
        tmp_path,
        "version: '0.2.0'\ntesting:\n  integrationTestGlobs:\n    - tests/test_*_integration.py\n",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_thing_integration.py").write_text(
        'def test_x():\n    """\n    Feature: f\n      Scenario: s\n        Given g\n        When w\n        Then t\n    """\n'
    )
    report = core_repo.scenarios(str(tmp_path))
    assert report["globs"] == ["tests/test_*_integration.py"]
    assert len(report["scenarios"]) == 1
    assert report["scenarios"][0]["scenario"] == "s"


def test_instructions_reports_registered_docs(tmp_path):
    _write_harness_config(
        tmp_path,
        "version: '0.2.0'\ncustomInstructions:\n  docs:\n    - path: docs/house.md\n  onMissing: warn\n",
    )
    report = core_repo.instructions(str(tmp_path))
    assert report["onMissing"] == "warn"
    docs = report["docs"]
    assert len(docs) == 1
    assert docs[0]["path"] == "docs/house.md"
    assert docs[0]["state"] == "missing"
    assert docs[0]["resolvedOk"] is False


def test_critics_lists_configured_entries_without_argv(tmp_path):
    _write_harness_config(
        tmp_path,
        "version: '0.2.0'\nreviews:\n  critics:\n    - name: c1\n      harness: cursor\n      model: gpt-5.5\n",
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


def test_critic_run_unknown_name_is_config_error(tmp_path):
    _write_harness_config(tmp_path, "version: '0.2.0'\n")
    with pytest.raises(CriticConfigError):
        core_repo.critic_run(str(tmp_path), "ghost", "p", "prompt.md")
