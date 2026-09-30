"""Transport resolution and the provider contract (issue-109 R6, issue-442)."""

from __future__ import annotations

import pytest
from ghfakes import FakeGitHubClient, http_error

from the_loop.ghapi import GhComment, GitHubApiConfig
from the_loop.graph.integrations import (
    IntegrationError,
    OperationUnsupported,
    TransportUnavailable,
    resolve,
)
from the_loop.graph.integrations.github import (
    OPERATIONS,
    GitHubProvider,
    _ref_parts,
    _split_ref,
)

GHE = "ghe.corp.example"
GHE_REF = f"github:{GHE}/octo/repo#42"
REF = "github:octo/repo#42"


# -- resolve ---------------------------------------------------------------------


def test_auto_and_api_build_the_one_provider_when_a_token_is_present(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "x")
    for transport in ("auto", "api"):
        provider = resolve(
            "github", {"integrations": {"github": {"transport": transport}}}
        )
        assert isinstance(provider, GitHubProvider)
        assert provider.transport == "api"


def test_a_missing_token_fails_closed_naming_the_variables(monkeypatch):
    """R6.3, issue-442 R2.3 — fail closed, and tell the operator the fix."""
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(TransportUnavailable) as exc:
        resolve("github", {})
    message = str(exc.value)
    assert "GH_TOKEN" in message and "GITHUB_TOKEN" in message
    assert "gh" not in message.replace("GH_TOKEN", "").replace("GITHUB_TOKEN", "")


def test_the_configured_token_variable_is_the_one_named(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("LOOP_TOKEN", raising=False)
    config = {"integrations": {"github": {"api": {"tokenEnv": ["LOOP_TOKEN"]}}}}
    with pytest.raises(TransportUnavailable, match="LOOP_TOKEN"):
        resolve("github", config)
    monkeypatch.setenv("LOOP_TOKEN", "x")
    provider = resolve("github", config)
    assert isinstance(provider, GitHubProvider)
    assert provider.config == GitHubApiConfig(token_envs=("LOOP_TOKEN",))


def test_the_retired_cli_transport_is_refused_by_name(monkeypatch):
    """A configured choice is never silently served another way (issue-442 R4.2)."""
    monkeypatch.setenv("GH_TOKEN", "x")
    with pytest.raises(TransportUnavailable) as exc:
        resolve("github", {"integrations": {"github": {"transport": "cli"}}})
    message = str(exc.value)
    assert "retired" in message and "migrate-config" in message


def test_an_unknown_transport_is_refused():
    with pytest.raises(TransportUnavailable, match="unknown transport"):
        resolve("github", {"integrations": {"github": {"transport": "carrier-pigeon"}}})


def test_an_unknown_target_is_refused():
    with pytest.raises(TransportUnavailable, match="no integration registered"):
        resolve("mastodon", {})


def test_slack_is_a_named_refusal_pointing_at_channels():
    """issue-245 (PR #267 review): Slack converged on the channels layer. An
    embedder still resolving the old integration learns the replacement."""
    with pytest.raises(TransportUnavailable, match="channels.slack"):
        resolve("slack", {"integrations": {"slack": {"transport": "sdk"}}})


# -- the provider ----------------------------------------------------------------


def test_the_operations_are_unchanged():
    """A4 (issue-442): the move added no capability — the same seven operations."""
    assert OPERATIONS == frozenset(
        {
            "add-comment",
            "set-labels",
            "create-label",
            "remove-label",
            "get-labels",
            "list-comments",
            "get-thread",
        }
    )
    assert GitHubProvider(client=FakeGitHubClient()).operations == OPERATIONS


def test_an_unsupported_operation_is_refused():
    with pytest.raises(OperationUnsupported):
        GitHubProvider(client=FakeGitHubClient()).call("launch-rocket", ref=REF)


def test_add_comment_posts_and_returns_the_url():
    gh = FakeGitHubClient(comment_url="https://github.com/octo/repo/issues/42#c1")
    result = GitHubProvider(client=gh).call("add-comment", ref=REF, body="hi")
    assert gh.posted == [("octo", "repo", 42, "hi", "")]
    assert result == {
        "result": {"html_url": "https://github.com/octo/repo/issues/42#c1"}
    }


def test_set_labels_adds_without_replacing():
    """The shipped hooks remove the previous phase label themselves; the
    operation must not wipe `bug`, `enhancement` or the arming labels."""
    gh = FakeGitHubClient(labels={("octo", "repo", 42): ["bug"]})
    GitHubProvider(client=gh).call("set-labels", ref=REF, labels=["loop:design"])
    assert gh.labels[("octo", "repo", 42)] == ["bug", "loop:design"]


def test_create_label_is_idempotent_and_remove_label_tolerates_absence():
    gh = FakeGitHubClient(labels={("octo", "repo", 42): ["loop:design"]})
    provider = GitHubProvider(client=gh)
    assert provider.call("create-label", ref=REF, name="loop:design") == {
        "result": "ok"
    }
    assert provider.call("remove-label", ref=REF, label="loop:design") == {
        "result": "ok"
    }
    assert provider.call("remove-label", ref=REF, label="loop:design") == {
        "result": "absent"
    }

    class AlreadyThere(FakeGitHubClient):
        def ensure_label(self, *a, **k):
            super().ensure_label(*a, **k)
            return False

    assert GitHubProvider(client=AlreadyThere()).call(
        "create-label", ref=REF, name="loop:design"
    ) == {"result": "exists"}


def test_get_labels_get_thread_and_list_comments_read_through_the_client():
    gh = FakeGitHubClient(
        labels={("octo", "repo", 42): ["a", "b"]},
        states={("octo", "repo", 42): {"number": 42, "pull_request": {"url": "x"}}},
        comments={
            ("octo", "repo", 42): [
                GhComment("IC_1", "hello", "octocat", "2026-09-30T00:00:00Z", "u")
            ]
        },
    )
    provider = GitHubProvider(client=gh)
    assert provider.call("get-labels", ref=REF) == {"labels": ["a", "b"]}
    assert provider.call("get-thread", ref=REF) == {"kind": "pull-request"}
    comments = provider.call("list-comments", ref=REF)["comments"]
    assert comments[0]["body"] == "hello"
    # Both document shapes the consumers ever read (REST and gh's GraphQL).
    assert comments[0]["user"]["login"] == comments[0]["author"]["login"] == "octocat"
    assert comments[0]["created_at"] == comments[0]["createdAt"]


def test_a_client_failure_is_an_integration_error():
    gh = FakeGitHubClient(fail=http_error(403, "Resource not accessible"))
    with pytest.raises(IntegrationError, match="403"):
        GitHubProvider(client=gh).call("add-comment", ref=REF, body="hi")


# -- refs and the host (issue-311, R4) -------------------------------------------


def test_work_item_refs_parse():
    assert _split_ref("github:owner/repo#42") == ("owner", "repo", "42")
    assert _split_ref("owner/repo#7") == ("owner", "repo", "7")


def test_a_malformed_ref_is_refused():
    with pytest.raises(IntegrationError, match="malformed"):
        _split_ref("nonsense")


def test_ref_parts_reads_a_hosted_ref():
    assert _ref_parts(GHE_REF) == (GHE, "octo", "repo", "42")
    assert _ref_parts("github:octo/repo#42") == ("", "octo", "repo", "42")
    assert _split_ref(GHE_REF) == ("octo", "repo", "42")


def test_a_ref_with_a_bad_host_is_malformed():
    with pytest.raises(IntegrationError, match="malformed"):
        _split_ref("github:ghe/octo/repo#42")


def test_the_provider_names_the_host_on_every_operation():
    gh = FakeGitHubClient()
    provider = GitHubProvider(client=gh)
    provider.call("add-comment", ref=GHE_REF, body="hi")
    provider.call("set-labels", ref=GHE_REF, labels=["a"])
    provider.call("create-label", ref=GHE_REF, name="a")
    provider.call("remove-label", ref=GHE_REF, label="a")
    provider.call("get-labels", ref=GHE_REF)
    provider.call("get-thread", ref=GHE_REF)
    provider.call("list-comments", ref=GHE_REF)
    assert gh.calls and all(kwargs["host"] == GHE for _, kwargs in gh.calls)


def test_the_provider_is_unchanged_for_github_com():
    gh = FakeGitHubClient()
    provider = GitHubProvider(client=gh)
    provider.call("add-comment", ref=REF, body="hi")
    provider.call("get-thread", ref=REF)
    assert all(kwargs["host"] == "" for _, kwargs in gh.calls)


def test_the_provider_no_longer_answers_which_pulls_a_work_item_links():
    """T7 (issue-370, R3.1) — the-loop stopped asking GitHub that question.

    The pull requests delivering a work item are the ones it recorded opening
    (`work-item-state.json`); GitHub's "Development" panel never saw a spec PR.
    """
    assert "linked-pulls" not in OPERATIONS
    with pytest.raises(OperationUnsupported):
        GitHubProvider(client=FakeGitHubClient()).call("linked-pulls", ref=REF)
