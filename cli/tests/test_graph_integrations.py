"""Transport resolution and the provider contract (issue-109, R6)."""

from __future__ import annotations

import pytest

from the_loop.graph.integrations import (
    OperationUnsupported,
    TransportUnavailable,
    resolve,
)
from the_loop.graph.integrations.github import GitHubApi, GitHubCli, _split_ref
from the_loop.graph.integrations.slack import SlackWebhook


def test_auto_prefers_the_api_transport_when_a_token_is_present(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "x")
    provider = resolve("github", {"integrations": {"github": {"transport": "auto"}}})
    assert provider.transport == "api"


def test_auto_falls_back_to_the_cli_when_the_binary_exists(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/gh")
    provider = resolve("github", {"integrations": {"github": {"transport": "auto"}}})
    assert provider.transport == "cli"


def test_auto_with_nothing_available_names_both_remedies(monkeypatch):
    """R6.3 — fail closed, and tell the operator every way to fix it."""
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("shutil.which", lambda b: None)
    with pytest.raises(TransportUnavailable) as exc:
        resolve("github", {"integrations": {"github": {"transport": "auto"}}})
    message = str(exc.value)
    assert "GH_TOKEN" in message and "gh" in message


def test_an_explicit_transport_is_honoured_verbatim(monkeypatch):
    """R6.4 — a configured choice never silently degrades to another."""
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/gh")
    provider = resolve("github", {"integrations": {"github": {"transport": "api"}}})
    assert provider.transport == "api", "explicit api must not fall back to cli"


def test_an_unknown_transport_is_refused():
    with pytest.raises(TransportUnavailable, match="unknown transport"):
        resolve("github", {"integrations": {"github": {"transport": "carrier-pigeon"}}})


def test_an_unknown_target_is_refused():
    with pytest.raises(TransportUnavailable, match="no integration registered"):
        resolve("mastodon", {})


def test_both_github_providers_declare_the_same_operations():
    """The contract: api and cli are interchangeable to a hook (R6.10)."""
    assert GitHubApi(["GH_TOKEN"]).operations == GitHubCli().operations


@pytest.mark.parametrize("provider", [GitHubApi(["GH_TOKEN"]), GitHubCli()])
def test_an_unsupported_operation_is_refused(provider):
    with pytest.raises(OperationUnsupported):
        provider.call("launch-rocket", ref="github:o/r#1")


def test_work_item_refs_parse():
    assert _split_ref("github:owner/repo#42") == ("owner", "repo", "42")
    assert _split_ref("owner/repo#7") == ("owner", "repo", "7")


def test_a_malformed_ref_is_refused():
    from the_loop.graph.integrations.base import IntegrationError

    with pytest.raises(IntegrationError, match="malformed"):
        _split_ref("nonsense")


def test_slack_without_a_url_fails_closed(monkeypatch):
    monkeypatch.delenv("THE_LOOP_SLACK_WEBHOOK_URL", raising=False)
    from the_loop.graph.integrations.base import IntegrationError

    with pytest.raises(IntegrationError, match="THE_LOOP_SLACK_WEBHOOK_URL"):
        SlackWebhook("THE_LOOP_SLACK_WEBHOOK_URL").call("post-message", text="hi")
