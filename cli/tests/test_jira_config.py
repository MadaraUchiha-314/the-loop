"""The ``integrations.jira`` block of the CLI config (issue-475, T8).

The schema is where a Jira deployment is described, and the guard rails are
schema rules so that every path that validates a config — the control-plane
service's own validator (``configschema``) and the ``validate-the-loop-config``
pre-commit hook (``jsonschema``) — enforces them identically. Each case is
judged by both, and they must agree.

Spec: docs/specs/issue-475/design.md §Data models (config, schema guard rails);
requirements R3.4–R3.6.
"""

from __future__ import annotations

import copy
from typing import Any, Dict

import pytest

from the_loop import configschema

jsonschema = pytest.importorskip("jsonschema")

CLOUD: Dict[str, Any] = {
    "site": "acme.atlassian.net",
    "deployment": "cloud",
    "api": {"emailEnv": ["JIRA_EMAIL"], "tokenEnv": ["JIRA_API_TOKEN"]},
    "projects": {"PROJ": {"repository": "acme/web"}},
}


def _config(**overrides: Any) -> Dict[str, Any]:
    jira = copy.deepcopy(CLOUD)
    jira.update(overrides)
    return {"integrations": {"jira": jira}}


def _verdict(document: Dict[str, Any]) -> list:
    """This validator's errors — after checking jsonschema reaches the same verdict."""
    ours = configschema.validate(document)
    schema = configschema.load_schema("cli-config")
    try:
        jsonschema.validate(document, schema)
        theirs = True
    except jsonschema.ValidationError:
        theirs = False
    assert (not ours) == theirs, (ours, document)
    return ours


def test_a_cloud_deployment_is_valid():
    assert _verdict(_config()) == []


def test_a_mirror_only_project_is_valid():
    """``OPS: {}`` — a project with no repository is a room, never a source."""
    document = _config(projects={"PROJ": {"repository": "acme/web"}, "OPS": {}})
    assert _verdict(document) == []


def test_a_cloud_scoped_deployment_with_its_cloud_id_is_valid():
    document = _config(
        deployment="cloud-scoped", cloudId="11223344-a1b2-3b33-c444-def123456789"
    )
    assert _verdict(document) == []


def test_cloud_scoped_without_a_cloud_id_is_rejected():
    errors = _verdict(_config(deployment="cloud-scoped"))
    assert any("cloudId" in error for error in errors)


def test_a_data_center_deployment_needs_no_email():
    document = _config(
        site="jira.corp.example", deployment="data-center", api={"tokenEnv": ["PAT"]}
    )
    assert _verdict(document) == []


def test_a_cloud_deployment_without_an_email_variable_is_rejected():
    errors = _verdict(_config(api={"tokenEnv": ["JIRA_API_TOKEN"]}))
    assert any("emailEnv" in error for error in errors)


@pytest.mark.parametrize(
    "api",
    [
        {"emailEnv": ["JIRA_EMAIL"], "tokenEnv": ["ATATT3xFfGF0aBcD-eFg_hIjK1234=5"]},
        {"emailEnv": ["JIRA_EMAIL"], "tokenEnv": ["jira_api_token"]},
        {"emailEnv": ["ada@example.com"], "tokenEnv": ["JIRA_API_TOKEN"]},
        {"emailEnv": ["JIRA_EMAIL"], "tokenEnv": "JIRA_API_TOKEN"},
        {"emailEnv": ["JIRA_EMAIL"], "tokenEnv": []},
    ],
    ids=["literal-token", "lower-case", "literal-email", "string", "empty"],
)
def test_schema_rejects_literal_token(api):
    """R3.5 — credentials are named by environment variable only."""
    assert _verdict(_config(api=api))


@pytest.mark.parametrize("key", ["proj", "P", "PROJECTKEY1", "1PROJ", "PR-OJ"])
def test_invalid_project_key_fails_config(key):
    """Abuse case 6: a project key reaches JQL, so its grammar is checked at load."""
    errors = _verdict(_config(projects={key: {"repository": "acme/web"}}))
    assert errors


def test_no_projects_at_all_is_rejected():
    assert _verdict(_config(projects={}))


@pytest.mark.parametrize("repository", ["acme", "acme/web/extra", "https://x/y"])
def test_a_repository_that_is_not_owner_repo_is_rejected(repository):
    assert _verdict(_config(projects={"PROJ": {"repository": repository}}))


@pytest.mark.parametrize(
    "site", ["https://acme.atlassian.net", "acme.atlassian.net/jira", "acme"]
)
def test_a_site_that_is_not_a_bare_host_is_rejected(site):
    assert _verdict(_config(site=site))


@pytest.mark.parametrize("missing", ["site", "deployment", "api", "projects"])
def test_every_required_key_is_required(missing):
    jira = copy.deepcopy(CLOUD)
    jira.pop(missing)
    assert _verdict({"integrations": {"jira": jira}})


def test_an_unknown_deployment_is_rejected():
    assert _verdict(_config(deployment="server"))


@pytest.mark.parametrize("key", ["transport", "cli"])
def test_schema_rejects_the_retired_transport_keys_and_names_the_replacement(key):
    """R3.6 — the stub's `cli` transport is gone; the refusal says what replaced it."""
    errors = _verdict(_config(**{key: "cli" if key == "transport" else {}}))
    [error] = [e for e in errors if f"integrations.jira.{key}" in e]
    assert "unknown key" in error and "issue-442" in error
    assert "the-loop migrate-config" in error


def test_the_optional_close_transition_validates():
    assert _verdict(_config(closeTransition="Done")) == []
