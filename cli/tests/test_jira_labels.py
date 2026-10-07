"""Jira-safe labels (issue-475, design §C5, R4.4).

Jira label names cannot hold whitespace. ``jira_label`` maps a configured name to
the form written to Jira — deterministic, pure, and applied only at the Jira
boundary — and a configured label with no safe form fails the config load,
naming it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jirafakes import CLOUD

from the_loop.cli_config import load_cli_config
from the_loop.jiralabels import JiraLabelError, check_config_labels, jira_label
from the_loop.migrations import CURRENT_CONFIG_VERSION

# -- the mapping table (design §C5) ------------------------------------------------


@pytest.mark.parametrize(
    "configured, on_jira",
    [
        ("the-loop: auto-execute", "the-loop:auto-execute"),
        ("the-loop: rr", "the-loop:rr"),
        ("loop:design", "loop:design"),
        ("  loop:design  ", "loop:design"),
        ("needs  triage", "needs-triage"),
        ("a\tb\nc", "a-b-c"),
        ("team:\t ops", "team:ops"),
        ("ready for: review", "ready-for:review"),
    ],
)
def test_jira_label_mapping_table(configured, on_jira):
    assert jira_label(configured) == on_jira


def test_jira_label_is_idempotent():
    once = jira_label("the-loop: auto-execute")
    assert jira_label(once) == once


@pytest.mark.parametrize("bad", ["", "   ", "\t\n", "x" * 256])
def test_a_label_with_no_safe_form_is_refused_naming_it(bad):
    with pytest.raises(JiraLabelError) as caught:
        jira_label(bad)
    assert repr(bad)[:40] in str(caught.value)


def test_jira_label_error_is_a_value_error():
    assert issubclass(JiraLabelError, ValueError)


# -- wired into config load (R4.4) -------------------------------------------------


def _write(tmp_path: Path, document: dict) -> Path:
    path = tmp_path / "cli-config.yaml"
    path.write_text(yaml.safe_dump({"version": CURRENT_CONFIG_VERSION, **document}))
    return path


def test_label_without_safe_form_fails_config(tmp_path):
    long_label = "x" * 300
    path = _write(
        tmp_path,
        {
            "integrations": {"jira": dict(CLOUD)},
            "routing": {"autoExecuteLabels": ["the-loop: auto-execute", long_label]},
        },
    )
    with pytest.raises(JiraLabelError, match="autoExecuteLabels"):
        load_cli_config(path)


def test_labels_are_not_checked_without_a_jira_block(tmp_path):
    """A GitHub-only deployment is unaffected: GitHub takes the label as written."""
    path = _write(tmp_path, {"routing": {"autoExecuteLabels": ["x" * 300]}})
    assert load_cli_config(path)["routing"]["autoExecuteLabels"] == ["x" * 300]


def test_safe_labels_load_with_a_jira_block(tmp_path):
    path = _write(
        tmp_path,
        {
            "integrations": {"jira": dict(CLOUD)},
            "routing": {"autoExecuteLabels": ["the-loop: auto-execute"]},
        },
    )
    assert load_cli_config(path)["routing"]["autoExecuteLabels"] == [
        "the-loop: auto-execute"
    ]


def test_check_config_labels_reports_the_default_label_safe():
    """No ``autoExecuteLabels`` means the default ``the-loop: auto-execute``."""
    assert check_config_labels({"integrations": {"jira": dict(CLOUD)}}) == {
        "the-loop: auto-execute": "the-loop:auto-execute"
    }
