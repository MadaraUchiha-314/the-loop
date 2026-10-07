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


# -- hooks resolve the integration from the ref (design §C4, R4.3, R5.5) -------------


class _NeverGitHub:
    """A GitHub provider a Jira work item must never reach."""

    def call(self, op, **params):
        raise AssertionError(f"a Jira work item reached GitHub: {op} {params}")


def _route(monkeypatch, jira_client: FakeJiraClient) -> JiraProvider:
    jira = JiraProvider(client=jira_client)
    providers = {"github": _NeverGitHub(), "jira": jira}
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve",
        lambda target, config: providers[target],
    )
    return jira


def _hook_ctx(tmp_path, node: Dict[str, Any], config=None) -> HookContext:
    from the_loop.graph.model import PDLC_WORK_ITEM_LOOP, load_graph

    spec = tmp_path / "docs" / "specs" / "jira-proj-7"
    spec.mkdir(parents=True, exist_ok=True)
    return HookContext(
        work_item=WorkItem(ref=REF, id="jira-proj-7", spec_dir=spec),
        node=node,
        boundary="entry",
        repo=tmp_path,
        config=dict(config or {"authorizedUsers": [ADA]}),
        graph=load_graph(name=PDLC_WORK_ITEM_LOOP),
    )


def test_integration_for_picks_the_provider_by_the_ref(monkeypatch):
    from the_loop.graph import integrations

    asked: List[str] = []
    monkeypatch.setattr(
        integrations, "resolve", lambda target, config: asked.append(target) or target
    )
    assert integrations.integration_for(REF, {}) == "jira"
    assert integrations.integration_for("github:o/r#1", {}) == "github"
    # Not a work-item ref at all: the GitHub provider, as before issue-475.
    assert integrations.integration_for("not a ref", {}) == "github"
    assert asked == ["jira", "github", "github"]


def test_set_phase_label_on_jira_keeps_one_loop_label(tmp_path, monkeypatch):
    """
    Scenario: a Jira work item advances to design
      Given the ticket carries an old loop label, an arming label and another
      When set-phase-label runs for the design node
      Then the ticket carries exactly one loop label, loop:design
      And nothing else was touched, and GitHub was never asked
    """
    from the_loop.graph.hooks.sideeffects import set_phase_label

    client = FakeJiraClient(
        label_table={KEY: ["loop:requirements", "the-loop:auto-execute", "keep"]}
    )
    _route(monkeypatch, client)
    result = set_phase_label(_hook_ctx(tmp_path, {"id": "design", "phase": "design"}))
    assert result.data["applied"] is True
    labels = client.label_table[KEY]
    assert [label for label in labels if label.startswith("loop:")] == ["loop:design"]
    assert set(labels) == {"loop:design", "the-loop:auto-execute", "keep"}


def test_jira_label_operations_write_the_jira_safe_form():
    client = FakeJiraClient(label_table={KEY: ["the-loop:auto-execute"]})
    provider = JiraProvider(client=client)
    provider.call("set-labels", ref=REF, labels=["the-loop: rr"])
    assert client.label_table[KEY] == ["the-loop:auto-execute", "the-loop:rr"]
    assert provider.call("remove-label", ref=REF, label="the-loop: auto-execute") == {
        "result": "ok"
    }
    assert client.label_table[KEY] == ["the-loop:rr"]


def _as_stored_on_jira(client: FakeJiraClient) -> None:
    """What Jira gives back: each stored body through ADF and back."""
    from dataclasses import replace

    from the_loop.jiraformat import adf_to_markdown

    client.comment_table[KEY] = [
        replace(c, body_md=adf_to_markdown(markdown_to_adf(c.body_md)))
        for c in client.comment_table.get(KEY, [])
    ]


def test_selection_reads_a_jira_checklist_ticked_in_place(tmp_path, monkeypatch):
    """
    Scenario: the phase-selection checklist is posted to, and ticked on, Jira
      Given a Jira work item at the phase-selection gate
      When the checklist is posted, and a reviewer ticks an optional box in Jira
      Then the gate finds its own checklist through list-comments
      And reads the ticked box as ticked
    """
    import copy

    from the_loop.graph.hooks import selection
    from the_loop.jiraformat import adf_to_markdown

    client = FakeJiraClient()
    _route(monkeypatch, client)
    ctx = _hook_ctx(tmp_path, {"id": "phase-selection"})

    assert selection.post_phase_selection(ctx).data["posted"] is True
    _as_stored_on_jira(client)
    assert selection.post_phase_selection(ctx).data["posted"] is False  # found it

    [stored] = client.comment_table[KEY]
    adf = copy.deepcopy(markdown_to_adf(stored.body_md))
    items = [
        node
        for block in adf["content"]
        if block["type"] == "taskList"
        for node in block["content"]
    ]
    todo = next(item for item in items if item["attrs"]["state"] == "TODO")
    todo["attrs"]["state"] = "DONE"
    from dataclasses import replace

    client.comment_table[KEY] = [replace(stored, body_md=adf_to_markdown(adf))]

    body = selection._checklist_state(ctx)
    assert selection.SELECTION_MARKER in body
    ticked = {
        m.group("token")
        for m in selection._CHECK_LINE.finditer(body)
        if m.group("mark").lower() == "x"
    }
    before = {
        m.group("token")
        for m in selection._CHECK_LINE.finditer(stored.body_md)
        if m.group("mark").lower() == "x"
    }
    assert len(ticked - before) == 1


def test_a_slack_reply_reads_the_jira_checklist(monkeypatch):
    """channels/inbound reads the checklist through the ref's own integration."""
    from the_loop.channels import inbound
    from the_loop.graph.hooks.selection import SELECTION_MARKER

    client = FakeJiraClient()
    _route(monkeypatch, client)
    client.add_comment(KEY, f"- [ ] `design`\n\n{SELECTION_MARKER}")
    _as_stored_on_jira(client)
    body = inbound._selection_checklist(REF, cloud_config())
    assert SELECTION_MARKER in body and "- [ ] `design`" in body
