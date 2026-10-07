"""Jira as ledger and channel (issue-475, PR 3: design §C4–§C7, R4).

Every comment the-loop posts to Jira carries a visible self-marker, and a Jira
comment is the-loop's own when it carries that marker **or** its author is the
service account — either test alone keeps it from re-entering the loop
(abuse case 4).
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from jirafakes import FakeJiraClient, FakeJiraSDK, cloud_config

from the_loop.authz import (
    JIRA_SELF_ATTRIBUTION,
    JIRA_SELF_MARKER,
    SELF_COMMENT_MARKER,
    is_self_authored,
    mark_self_authored,
    mark_self_authored_on_jira,
)
from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks.feedback import _authorized_comments
from the_loop.graph.integrations.jira import JiraProvider
from the_loop.jiraapi import JiraApiConfig, JiraClient
from the_loop.jiraformat import markdown_to_adf

SITE = "acme.atlassian.net"
REF = f"jira:{SITE}/PROJ-7"
KEY = "PROJ-7"
BOT = "5b10-bot"
ADA = "5b10-ada"


@pytest.fixture
def cloud_env(monkeypatch):
    monkeypatch.setenv("JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "t0ken-value")


def _real_client(sdk: FakeJiraSDK) -> JiraClient:
    return JiraClient(
        JiraApiConfig.from_cli_config(cloud_config()), factory=lambda api, auth: sdk
    )


def _comment(cid: str, author: str, markdown: str) -> Dict[str, Any]:
    return {
        "id": cid,
        "author": {"accountId": author},
        "body": markdown_to_adf(markdown),
        "created": "2026-10-06T00:00:00.000+0000",
    }


# -- the marker itself (R4.6) --------------------------------------------------------


def test_the_jira_marker_is_visible_and_recognised():
    assert JIRA_SELF_MARKER == "[the-loop:agent-comment]"
    assert JIRA_SELF_ATTRIBUTION == (
        "🤖 the-loop, autonomous comment · [the-loop:agent-comment]"
    )
    assert is_self_authored(f"done\n\n{JIRA_SELF_ATTRIBUTION}")
    assert is_self_authored(f"x {SELF_COMMENT_MARKER}")
    assert not is_self_authored("the-loop:agent-comment without brackets")


def test_marking_for_jira_replaces_the_hidden_marker_with_the_visible_line():
    marked = mark_self_authored_on_jira(mark_self_authored("Ready for review."))
    assert SELF_COMMENT_MARKER not in marked
    assert marked.rstrip("\n").endswith(JIRA_SELF_ATTRIBUTION)
    assert marked.startswith("Ready for review.")
    assert "_the-loop, autonomous comment_" not in marked
    assert mark_self_authored_on_jira(marked) == marked  # idempotent
    plain = mark_self_authored_on_jira("Unmarked.")
    assert plain == f"Unmarked.\n\n{JIRA_SELF_ATTRIBUTION}\n"


def test_the_provider_posts_with_the_visible_marker():
    client = FakeJiraClient()
    JiraProvider(client=client).call(
        "add-comment", ref=REF, body=mark_self_authored("Gate is open.")
    )
    [posted] = client.posted
    assert SELF_COMMENT_MARKER not in posted["body"]
    assert posted["body"].rstrip("\n").endswith(JIRA_SELF_ATTRIBUTION)


def test_the_marker_survives_jira_storage(cloud_env):
    """Posted as ADF, read back as Markdown: still recognised."""
    sdk = FakeJiraSDK(me={"accountId": BOT})
    client = _real_client(sdk)
    JiraProvider(client=client).call("add-comment", ref=REF, body="Asked.")
    [stored] = sdk.comment_docs[KEY]
    stored["author"] = {"accountId": "someone-else"}  # isolate the marker test
    [read] = client.comments(KEY)
    assert JIRA_SELF_MARKER in read.body_md and is_self_authored(read.body_md)


# -- abuse case 4: a self comment never resumes -------------------------------------


def _gate_ctx(comments: List[Dict[str, Any]], authorized: List[str]) -> HookContext:
    from pathlib import Path

    return HookContext(
        work_item=WorkItem(ref=REF, id="jira-proj-7", spec_dir=Path(".")),
        node={"id": "design-approval"},
        boundary="exit",
        repo=Path("."),
        config={"authorizedUsers": authorized},
        event={"comments": comments},
    )


@pytest.mark.parametrize("variant", ["marker", "author"])
def test_jira_self_comment_never_resumes(variant, cloud_env):
    """
    Scenario: the-loop reads its own Jira comment back
      Given a comment carrying the visible marker, or one by the service account
      When the comments are read and the gate filters them
      Then the comment is the-loop's own and is never feedback
    """
    if variant == "marker":
        doc = _comment("1", ADA, mark_self_authored_on_jira("Approved."))
    else:
        doc = _comment("1", BOT, "Approved.")
    human = _comment("2", ADA, "Approved, ship it.")
    sdk = FakeJiraSDK(me={"accountId": BOT}, comment_docs={KEY: [doc, human]})
    client = _real_client(sdk)

    mine, theirs = client.comments(KEY)
    assert mine.is_self is True and theirs.is_self is False

    listed = JiraProvider(client=client).call("list-comments", ref=REF)["comments"]
    readable = _authorized_comments(_gate_ctx(listed, authorized=[ADA, BOT]))
    assert [c["body"] for c in readable] == ["Approved, ship it."]


def test_an_unreadable_myself_falls_back_to_the_marker(cloud_env):
    from jira.exceptions import JIRAError

    sdk = FakeJiraSDK(
        me={"accountId": BOT},
        comment_docs={KEY: [_comment("1", BOT, "plain")]},
        raise_on={"myself": JIRAError("nope", status_code=403)},
    )
    [comment] = _real_client(sdk).comments(KEY)
    assert comment.is_self is False  # no author proof, no marker: not ours
