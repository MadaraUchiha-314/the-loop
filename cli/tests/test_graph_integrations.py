"""Transport resolution and the provider contract (issue-109, R6)."""

from __future__ import annotations

import pytest

from the_loop.graph.integrations import (
    OperationUnsupported,
    TransportUnavailable,
    resolve,
)
from the_loop.graph.integrations.github import GitHubApi, GitHubCli, _split_ref
from the_loop.graph.integrations.slack import SlackWebhook, _SlackBase


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


# --- the inline webhook url (issue-203) ------------------------------------
#
# Resolution is exercised through ``resolve()`` rather than by constructing a
# provider directly: the config key is what an operator writes, and a test that
# passed the URL to the constructor would prove the provider works while leaving
# the wiring — the half that was actually missing — unverified.

INLINE = "https://hooks.slack.example/inline"
FROM_ENV = "https://hooks.slack.example/from-env"


def _slack(section, transport="webhook") -> _SlackBase:
    config = {"integrations": {"slack": dict(section, transport=transport)}}
    provider = resolve("slack", config)
    # Both transports resolve the URL through _SlackBase, which is what makes
    # them undriftable — so asserting it here is part of the claim, not scaffolding.
    assert isinstance(provider, _SlackBase)
    return provider


TRANSPORTS = ["webhook", "sdk"]


def _skip_without_sdk(transport):
    if transport == "sdk":
        pytest.importorskip("slack_sdk", reason="the sdk transport needs slack-sdk")


@pytest.mark.parametrize("transport", TRANSPORTS)
def test_an_inline_url_is_used(monkeypatch, transport):
    """R1.1 — the URL an operator wrote in the config is the one posted to."""
    _skip_without_sdk(transport)
    monkeypatch.delenv("THE_LOOP_SLACK_WEBHOOK_URL", raising=False)
    assert _slack({"url": INLINE}, transport)._url() == INLINE


@pytest.mark.parametrize("transport", TRANSPORTS)
def test_an_inline_url_wins_over_the_environment(monkeypatch, transport):
    """R1.2 — precedence never depends on ambient environment.

    Were it the other way round, reading the config file would no longer tell
    you where a notification goes.
    """
    _skip_without_sdk(transport)
    monkeypatch.setenv("THE_LOOP_SLACK_WEBHOOK_URL", FROM_ENV)
    assert _slack({"url": INLINE}, transport)._url() == INLINE


@pytest.mark.parametrize("transport", TRANSPORTS)
def test_without_an_inline_url_the_environment_is_read(monkeypatch, transport):
    """R1.3 — the pre-issue-203 path, unchanged."""
    _skip_without_sdk(transport)
    monkeypatch.setenv("THE_LOOP_SLACK_WEBHOOK_URL", FROM_ENV)
    assert _slack({}, transport)._url() == FROM_ENV


def test_an_empty_inline_url_falls_back_to_the_environment(monkeypatch):
    """Abuse case 2 — a blank key cannot silently disable a working setup."""
    monkeypatch.setenv("THE_LOOP_SLACK_WEBHOOK_URL", FROM_ENV)
    assert _slack({"url": ""})._url() == FROM_ENV


def test_a_custom_url_env_is_still_honoured(monkeypatch):
    monkeypatch.setenv("MY_HOOK", FROM_ENV)
    assert _slack({"urlEnv": "MY_HOOK"})._url() == FROM_ENV


def test_the_failure_names_both_remedies_and_not_the_url(monkeypatch):
    """R2.1 + abuse case 3 — every remedy named, the credential never echoed."""
    monkeypatch.delenv("MY_HOOK", raising=False)
    from the_loop.graph.integrations.base import IntegrationError

    with pytest.raises(IntegrationError) as exc:
        _slack({"urlEnv": "MY_HOOK"})._url()
    message = str(exc.value)
    assert "integrations.slack.url" in message and "MY_HOOK" in message
    assert "hooks.slack" not in message, "the error names sources, never a URL"


def test_a_provider_built_the_old_way_still_works(monkeypatch):
    """R3.1 — `url` is keyword-defaulted, so existing call sites are untouched."""
    monkeypatch.setenv("THE_LOOP_SLACK_WEBHOOK_URL", FROM_ENV)
    assert SlackWebhook("THE_LOOP_SLACK_WEBHOOK_URL")._url() == FROM_ENV


def test_a_non_string_url_is_refused_by_the_schema():
    """Abuse case 1 — the schema rejects it before any code sees it."""
    import json
    from pathlib import Path

    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(
        (
            Path(__file__).resolve().parents[2] / ".the-loop" / "cli-config.schema.json"
        ).read_text(encoding="utf-8")
    )
    slack = schema["properties"]["integrations"]["properties"]["slack"]
    assert slack["additionalProperties"] is False, "the surface stays closed"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"url": {"not": "a string"}}, slack)
    jsonschema.validate({"url": INLINE}, slack)
