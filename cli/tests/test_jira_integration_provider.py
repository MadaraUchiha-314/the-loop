"""The Jira control-plane integration (issue-475, T3; abuse case 8).

``JiraProvider`` answers the operations the graph's hooks call with the same
result shapes ``GitHubProvider`` returns, over :class:`jirafakes.FakeJiraClient`.
``resolve("jira", config)`` builds it when ``integrations.jira`` is configured
and its credentials are set, and refuses — naming the variables — when not.

Spec: docs/specs/issue-475/design.md §C4, §Error handling; requirements R3.1–R3.3, R3.7.
"""

from __future__ import annotations

import pytest
from ghfakes import FakeGitHubClient
from jirafakes import FakeJiraClient, cloud_config, http_error

from the_loop.ghapi import GhComment
from the_loop.graph.integrations import (
    IntegrationError,
    OperationUnsupported,
    TransportUnavailable,
    resolve,
)
from the_loop.graph.integrations.github import GitHubProvider
from the_loop.graph.integrations.jira import JiraProvider
from the_loop.jiraapi import JiraApiConfig, JiraComment, JiraTransition

REF = "jira:acme.atlassian.net/PROJ-7"
KEY = "PROJ-7"


def _provider(**fake) -> tuple[JiraProvider, FakeJiraClient]:
    client = FakeJiraClient(**fake)
    return JiraProvider(client=client), client


# -- per-operation shapes ----------------------------------------------------------


def test_add_comment_returns_the_comment_permalink():
    provider, client = _provider()
    result = provider.call("add-comment", ref=REF, body="Hello")
    assert result == {
        "result": {
            "html_url": "https://acme.atlassian.net/browse/PROJ-7?focusedCommentId=10001"
        }
    }
    # The body carries the visible Jira self-marker (PR 3, R4.6).
    assert client.posted == [
        {
            "key": KEY,
            "body": "Hello\n\n🤖 the-loop, autonomous comment · [the-loop:agent-comment]\n",
            "url": result["result"]["html_url"],
        }
    ]


def test_set_labels_merges_into_the_existing_labels():
    provider, client = _provider(label_table={KEY: ["keep-me"]})
    assert provider.call("set-labels", ref=REF, labels=["loop:design"]) == {
        "result": "ok"
    }
    assert client.label_table[KEY] == ["keep-me", "loop:design"]


def test_create_label_is_noop_on_jira():
    """R3.1 — Jira creates a label on first use; the no-op says so."""
    provider, client = _provider()
    result = provider.call("create-label", ref=REF, name="loop:design", color="0e8a16")
    assert result == {"result": "exists", "note": "jira creates labels on use"}
    assert client.calls == []


def test_remove_label_says_ok_or_absent():
    provider, _ = _provider(label_table={KEY: ["loop:design"]})
    assert provider.call("remove-label", ref=REF, label="loop:design") == {
        "result": "ok"
    }
    assert provider.call("remove-label", ref=REF, label="loop:design") == {
        "result": "absent"
    }


def test_get_labels():
    provider, _ = _provider(label_table={KEY: ["a", "b"]})
    assert provider.call("get-labels", ref=REF) == {"labels": ["a", "b"]}


def test_get_thread_is_always_an_issue():
    provider, _ = _provider()
    assert provider.call("get-thread", ref=REF) == {"kind": "issue"}


def test_list_comments_has_the_shape_github_returns():
    provider, _ = _provider(
        comment_table={
            KEY: [
                JiraComment(
                    id="7",
                    author_id="5b10ac8d",
                    body_md="the-loop start",
                    created="2026-10-06T01:02:03.000+0000",
                    url="https://acme.atlassian.net/browse/PROJ-7?focusedCommentId=7",
                )
            ]
        }
    )
    [comment] = provider.call("list-comments", ref=REF)["comments"]
    assert comment == {
        "id": "7",
        "body": "the-loop start",
        "author": {"login": "5b10ac8d"},
        "user": {"login": "5b10ac8d"},
        "created_at": "2026-10-06T01:02:03.000+0000",
        "createdAt": "2026-10-06T01:02:03.000+0000",
        "html_url": "https://acme.atlassian.net/browse/PROJ-7?focusedCommentId=7",
        "url": "https://acme.atlassian.net/browse/PROJ-7?focusedCommentId=7",
    }
    github = GitHubProvider(
        client=FakeGitHubClient(
            comments={
                ("o", "r", 1): [
                    GhComment(id="1", body="x", author="a", created_at="t", url="u")
                ]
            }
        )
    )
    [theirs] = github.call("list-comments", ref="github:o/r#1")["comments"]
    assert set(comment) == set(theirs)


# -- transition (R3.7) ----------------------------------------------------------------


def _transitions(*rows: tuple[str, str, str]) -> dict:
    return {
        KEY: [
            JiraTransition(id=i, name=n, to_status=n, to_category=c) for i, n, c in rows
        ]
    }


def test_transition_done_picks_single_done_category():
    provider, client = _provider(
        transition_table=_transitions(
            ("11", "Start", "indeterminate"), ("31", "Close", "done")
        )
    )
    assert provider.call("transition", ref=REF, to="done") == {
        "result": "ok",
        "transition": "Close",
    }
    assert client.transitioned == [{"key": KEY, "transition_id": "31"}]


def test_transition_done_prefers_the_configured_close_transition():
    client = FakeJiraClient(
        config=JiraApiConfig.from_cli_config(cloud_config(closeTransition="Resolve")),
        transition_table=_transitions(
            ("31", "Close", "done"), ("41", "Resolve", "done")
        ),
    )
    result = JiraProvider(client=client).call("transition", ref=REF, to="done")
    assert result == {"result": "ok", "transition": "Resolve"}
    assert client.transitioned == [{"key": KEY, "transition_id": "41"}]


def test_a_configured_close_transition_that_is_not_available_is_an_error():
    client = FakeJiraClient(
        config=JiraApiConfig.from_cli_config(cloud_config(closeTransition="Resolve")),
        transition_table=_transitions(("31", "Close", "done")),
    )
    with pytest.raises(IntegrationError, match="Resolve") as exc:
        JiraProvider(client=client).call("transition", ref=REF, to="done")
    assert "Close" in str(exc.value)
    assert client.transitioned == []


@pytest.mark.parametrize(
    "rows",
    [
        (("31", "Close", "done"), ("32", "Won't do", "done")),
        (("11", "Start", "indeterminate"),),
        (),
    ],
    ids=["two-done", "none-done", "no-transitions"],
)
def test_transition_ambiguous_lists_candidates_and_does_nothing(rows):
    """R3.7 — zero or several candidates: an error listing them, never a guess."""
    provider, client = _provider(transition_table=_transitions(*rows))
    with pytest.raises(IntegrationError) as exc:
        provider.call("transition", ref=REF, to="done")
    for _, name, _ in rows:
        assert name in str(exc.value)
    assert client.transitioned == []


def test_transition_to_anything_but_done_is_refused():
    provider, client = _provider()
    with pytest.raises(IntegrationError, match="done"):
        provider.call("transition", ref=REF, to="in-progress")
    assert client.calls == []


# -- refusals before any request ---------------------------------------------------


def test_ref_on_unknown_site_sends_no_credential():
    """Abuse case 8 — a ref on another site is refused before the client is used."""
    provider, client = _provider()
    with pytest.raises(IntegrationError, match="evil.example"):
        provider.call("add-comment", ref="jira:evil.example/PROJ-7", body="hi")
    assert client.calls == []


def test_ref_on_an_unconfigured_project_is_refused():
    provider, client = _provider()
    with pytest.raises(IntegrationError, match="NOPE"):
        provider.call("get-labels", ref="jira:acme.atlassian.net/NOPE-1")
    assert client.calls == []


def test_a_mirror_only_project_is_still_reachable():
    """``OPS: {}`` names no repository, but it is configured: a room can be written."""
    provider, client = _provider()
    provider.call("add-comment", ref="jira:acme.atlassian.net/OPS-3", body="mirror")
    assert client.posted[0]["key"] == "OPS-3"


@pytest.mark.parametrize("ref", ["github:octo/repo#1", "PROJ-7", "jira:PROJ-7"])
def test_a_ref_that_is_not_a_jira_ref_is_refused(ref):
    provider, client = _provider()
    with pytest.raises(IntegrationError):
        provider.call("get-labels", ref=ref)
    assert client.calls == []


def test_an_api_error_becomes_an_integration_error():
    provider, _ = _provider(fail=http_error(403, "Forbidden"))
    with pytest.raises(IntegrationError, match=r"jira: Jira 403: Forbidden"):
        provider.call("get-labels", ref=REF)


def test_an_undeclared_operation_is_refused():
    provider, _ = _provider()
    with pytest.raises(OperationUnsupported):
        provider.call("linked-pulls", ref=REF)


# -- resolve() ---------------------------------------------------------------------


@pytest.fixture
def no_jira_env(monkeypatch):
    for name in ("JIRA_EMAIL", "JIRA_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)


def test_resolve_builds_the_jira_provider_when_configured(monkeypatch, no_jira_env):
    monkeypatch.setenv("JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "tok")
    provider = resolve("jira", cloud_config())
    assert isinstance(provider, JiraProvider)
    assert provider.name == "jira" and "transition" in provider.operations


def test_resolve_refuses_a_missing_credential_naming_the_variable(
    monkeypatch, no_jira_env
):
    monkeypatch.setenv("JIRA_EMAIL", "bot@example.com")
    with pytest.raises(TransportUnavailable, match="JIRA_API_TOKEN is not set"):
        resolve("jira", cloud_config())


def test_resolve_refuses_an_unconfigured_jira(no_jira_env):
    with pytest.raises(
        TransportUnavailable, match="integrations.jira is not configured"
    ):
        resolve("jira", {})


def test_resolve_refuses_the_retired_cli_transport(monkeypatch, no_jira_env):
    monkeypatch.setenv("JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "tok")
    config = cloud_config(transport="cli")
    with pytest.raises(TransportUnavailable, match="retired") as exc:
        resolve("jira", config)
    assert "the-loop migrate-config" in str(exc.value)
