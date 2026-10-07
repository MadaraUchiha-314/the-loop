"""``the-loop doctor jira`` — a configured Jira block the daemon cannot use (issue-475).

``resolve("jira")`` fails closed when a credential variable is empty; the doctor
says so up front, naming the variables and never a value, so an operator finds
out before the first gate hook does. Offline: it reads the configuration and the
environment, and sends nothing to Jira.

Spec: docs/specs/issue-475/design.md §Error handling (first row); testing-plan T2.
"""

from __future__ import annotations

import argparse
import json

import pytest
from jirafakes import CLOUD, DATA_CENTER

EMAIL = "bot@example.com"
TOKEN = "ATATT3xFfGF0-secret"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PAT"):
        monkeypatch.delenv(name, raising=False)


def run_doctor(tmp_path, monkeypatch, capsys, config):
    from the_loop.commands.diagnose_cmd import DoctorCommand

    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    (tmp_path / "cli-config.yaml").write_text(json.dumps(config), encoding="utf-8")
    parser = argparse.ArgumentParser()
    DoctorCommand().add_arguments(parser)
    code = DoctorCommand().run(parser.parse_args(["jira"]))
    return code, capsys.readouterr().out


def test_doctor_jira_reports_a_missing_token_by_name(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JIRA_EMAIL", EMAIL)
    code, out = run_doctor(
        tmp_path, monkeypatch, capsys, {"integrations": {"jira": CLOUD}}
    )
    assert code == 1
    assert "[!] JIRA_API_TOKEN is not set" in out
    assert "[ok] JIRA_EMAIL is set" in out
    assert EMAIL not in out


def test_doctor_jira_is_clean_when_every_credential_is_set(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("JIRA_EMAIL", EMAIL)
    monkeypatch.setenv("JIRA_API_TOKEN", TOKEN)
    code, out = run_doctor(
        tmp_path, monkeypatch, capsys, {"integrations": {"jira": CLOUD}}
    )
    assert code == 0
    assert "acme.atlassian.net" in out and "cloud" in out
    assert "PROJ → acme/web" in out and "OPS — mirror-only" in out
    assert TOKEN not in out and EMAIL not in out


def test_doctor_jira_on_data_center_needs_only_the_pat(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JIRA_PAT", TOKEN)
    code, out = run_doctor(
        tmp_path, monkeypatch, capsys, {"integrations": {"jira": DATA_CENTER}}
    )
    assert code == 0
    assert "REST v2" in out and "JIRA_EMAIL" not in out


def test_doctor_jira_without_a_block_says_so_and_finds_nothing(
    tmp_path, monkeypatch, capsys
):
    code, out = run_doctor(tmp_path, monkeypatch, capsys, {})
    assert code == 0
    assert "[?] integrations.jira is not configured" in out


def test_doctor_jira_reports_a_cloud_scoped_block_without_a_cloud_id(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("JIRA_EMAIL", EMAIL)
    monkeypatch.setenv("JIRA_API_TOKEN", TOKEN)
    code, out = run_doctor(
        tmp_path,
        monkeypatch,
        capsys,
        {"integrations": {"jira": {**CLOUD, "deployment": "cloud-scoped"}}},
    )
    assert code == 1
    assert "[!]" in out and "cloudId" in out
