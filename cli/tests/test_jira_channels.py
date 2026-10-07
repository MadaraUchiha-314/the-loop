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
    mark_relayed_on_jira,
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


# -- the ledger routes by the ref (design §C7, R4.1) -------------------------------

from the_loop.channels.base import Event, RoutedLedger, ledger_name, load_ledger  # noqa: E402
from the_loop.channels.github import GitHubLedger  # noqa: E402
from the_loop.identity import Principal  # noqa: E402

PR_REF = "github:acme/web#41"
PERSON = Principal(ids={"github": "octocat", "slack": "U1"}, name="Octo")


def _jira_cli_config(**channels: Any) -> Dict[str, Any]:
    config = cloud_config()
    if channels:
        config["channels"] = dict(channels)
    return config


def _routed(cli_config: Dict[str, Any]):
    from the_loop.channels.jira import JiraLedger

    posted: List[Any] = []

    def post(item, body, api=None):
        posted.append((item.ref, body))
        return True, "", "https://github.com/acme/web/pull/41#c1"

    github = GitHubLedger(cli_config, post_comment=post)
    client = FakeJiraClient()
    jira = JiraLedger(cli_config, client=client)
    ledger = RoutedLedger(
        {"github": github, "jira": jira}, default=ledger_name(cli_config)
    )
    return ledger, posted, client


def _event(event_type: str, work_item: str = REF, **kw: Any) -> Event:
    return Event(
        event_type=event_type,
        work_item=work_item,
        text=kw.pop("text", "A or B?"),
        source=kw.pop("source", "slack"),
        actor=kw.pop("actor", PERSON),
        **kw,
    )


def test_routed_ledger_records_jira_event_on_jira():
    """
    Scenario: an ask on a Jira work item is recorded on its ticket
      Given a deployment with the Jira integration configured
      When a session.awaiting_input event is recorded for a Jira work item
      Then the Jira ticket gets the comment and GitHub gets nothing
    """
    ledger, posted, client = _routed(_jira_cli_config())
    result = ledger.record(_event("session.awaiting_input", source="cli"))
    assert result.ok and result.channel == "jira"
    assert result.url.endswith("/browse/PROJ-7?focusedCommentId=10001")
    assert [p["key"] for p in client.posted] == [KEY]
    assert posted == []


def test_pr_event_still_recorded_on_github():
    """channels.ledger: jira changes where a ticket is CREATED, not where a PR is."""
    ledger, posted, client = _routed(_jira_cli_config(ledger="jira"))
    result = ledger.record(_event("work-item.reply", work_item=PR_REF))
    assert result.ok and result.channel == "github"
    assert [ref for ref, _ in posted] == [PR_REF]
    assert client.posted == []


@pytest.mark.parametrize(
    "event_type",
    [
        "session.awaiting_input",  # the ask
        "work-item.reply",  # a mirror
        "phase.started",  # any other event, stamped
    ],
)
def test_jira_ledger_stamps_visible_marker(event_type):
    ledger, _, client = _routed(_jira_cli_config())
    assert ledger.record(_event(event_type)).ok
    [posted] = client.posted
    assert posted["body"].rstrip("\n").endswith(JIRA_SELF_ATTRIBUTION)
    assert SELF_COMMENT_MARKER not in posted["body"]


@pytest.mark.parametrize("event_type", ["gate.feedback", "control.command"])
def test_jira_ledger_marks_a_relay_with_the_relay_marker(event_type):
    """A relay is the operator's words on Jira as on GitHub (PR 4 design addendum).

    It carries the relay marker and NOT the self-marker — the self-marker would
    make the Jira ingress drop the very answer the relay exists to deliver — and
    its keywords are kept. The marker survives the trip to ADF and back as text.
    """
    from the_loop.authz import JIRA_RELAY_ATTRIBUTION, JIRA_RELAY_MARKER
    from the_loop.jiraformat import adf_to_markdown, markdown_to_adf

    ledger, _, client = _routed(_jira_cli_config())
    detail = {"gate": "design-approval"} if event_type == "gate.feedback" else {}
    text = "approved" if event_type == "gate.feedback" else "the-loop pause"
    assert ledger.record(_event(event_type, detail=detail, text=text)).ok
    [posted] = client.posted
    body = posted["body"]
    assert body.rstrip("\n").endswith(JIRA_RELAY_ATTRIBUTION)
    assert JIRA_SELF_MARKER not in body and SELF_COMMENT_MARKER not in body
    assert text in body
    assert JIRA_RELAY_MARKER in adf_to_markdown(markdown_to_adf(body))


def test_jira_ledger_bodies_are_the_github_bodies():
    """One body selection for both ledgers (channels/bodies.py)."""
    from the_loop.channels.bodies import ledger_body

    cli_config = _jira_cli_config()
    for event_type in ("session.awaiting_input", "gate.feedback", "work-item.reply"):
        ledger, _, client = _routed(cli_config)
        event = _event(event_type)
        ledger.record(event)
        if event_type == "gate.feedback":  # a relay: the relay marker (PR 4)
            expected = mark_relayed_on_jira(ledger_body(event, cli_config))
        else:
            expected = mark_self_authored_on_jira(ledger_body(event, cli_config))
        assert _no_ts(client.posted[0]["body"]) == _no_ts(expected)


def _no_ts(body: str) -> str:
    import re

    return re.sub(r'"ts":"[^"]*"', '"ts":""', body)


def test_work_item_create_opens_a_jira_ticket_when_the_ledger_is_jira():
    ledger, posted, client = _routed(_jira_cli_config(ledger="jira"))
    result = ledger.record(
        Event(
            event_type="work-item.create",
            work_item="",
            text="Fix the login page\n\nIt 500s.",
            detail={"project": "PROJ", "labels": "the-loop: auto-execute,bug"},
            source="slack",
            actor=PERSON,
        )
    )
    assert result.ok and result.channel == "jira"
    assert result.ref == f"jira:{SITE}/PROJ-101"
    assert client.created == [
        {
            "key": "PROJ-101",
            "summary": "Fix the login page",
            "labels": ["the-loop:auto-execute", "bug"],
        }
    ]
    assert posted == []


def test_work_item_create_refuses_a_mirror_only_project():
    ledger, _, client = _routed(_jira_cli_config(ledger="jira"))
    result = ledger.record(
        Event(
            event_type="work-item.create",
            work_item="",
            text="x",
            detail={"project": "OPS"},
            source="slack",
        )
    )
    assert not result.ok and "OPS" in result.error
    assert client.created == []


def test_work_item_create_stays_on_github_by_default():
    ledger, posted, client = _routed(_jira_cli_config())
    assert ledger.route(Event("work-item.create", "", "x")).name == "github"


def test_a_jira_ledger_refuses_a_github_ref_and_an_unknown_project():
    from the_loop.channels.jira import JiraLedger

    client = FakeJiraClient()
    jira = JiraLedger(_jira_cli_config(), client=client)
    assert not jira.record(_event("phase.started", work_item=PR_REF)).ok
    bad = jira.record(_event("phase.started", work_item=f"jira:{SITE}/NOPE-1"))
    assert not bad.ok and "NOPE" in bad.error
    assert client.calls == []


def test_load_ledger_routes_only_when_jira_is_configured():
    assert isinstance(load_ledger({}), GitHubLedger)
    routed = load_ledger(_jira_cli_config(ledger="jira"))
    assert isinstance(routed, RoutedLedger)
    assert ledger_name(_jira_cli_config(ledger="jira")) == "jira"
    # Without integrations.jira, `jira` still resolves to github (and is logged).
    assert ledger_name({"channels": {"ledger": "jira"}}) == "github"


def test_the_bus_never_records_an_event_back_on_its_own_tracker():
    """A Jira-sourced event on a Jira item is not re-recorded on the Jira ticket."""
    from the_loop.channels.bus import publish

    ledger, posted, client = _routed(_jira_cli_config())
    publish(_event("work-item.reply", source="jira"), channels=[], ledger=ledger)
    assert client.posted == []
    publish(_event("work-item.reply", source="slack"), channels=[], ledger=ledger)
    assert len(client.posted) == 1


# -- the Jira channel and the room grammar (design §C7, R4.2) ----------------------

from the_loop.workchannels import (  # noqa: E402
    CollaborationChannelStore,
    describe_refusal,
    parse_channel_ref,
    resolve_channel_ref,
)

GH_ITEM = "github:acme/web#15"
MIRROR_ROOM = "jira@OPS-5"


def _channel_config(tmp_path, **jira: Any) -> Dict[str, Any]:
    config = cloud_config()
    config["state"] = {"root": str(tmp_path / "state")}
    config["channels"] = {
        "jira": {
            "enabled": True,
            "subscribe": ["phase.started", "work-item.closed"],
            **jira,
        }
    }
    return config


def _jira_channel(tmp_path, **jira: Any):
    from the_loop.channels.jira import JiraChannel, JiraChannelConfig

    config = _channel_config(tmp_path, **jira)
    client = FakeJiraClient()
    store = CollaborationChannelStore(tmp_path / "state" / "portable")
    channel = JiraChannel(
        JiraChannelConfig.from_mapping(config), config, client=client, store=store
    )
    return channel, client, store, config


@pytest.mark.parametrize("raw", ["jira@PROJ-1", "jira://PROJ-1", "jira@OPS_2-99"])
def test_a_jira_room_ref_parses(raw):
    channel = parse_channel_ref(raw)
    assert channel is not None and channel.type == "jira"
    assert channel.ref == f"jira@{raw.split('@')[-1].split('//')[-1]}"
    assert channel.is_id


@pytest.mark.parametrize(
    "raw", ["jira@proj-1", "jira@PROJ", "jira@PROJ-0", "jira@P-1", "jira@PROJ-1/x"]
)
def test_a_bad_jira_room_ref_is_refused(raw):
    assert parse_channel_ref(raw) is None
    if raw != "jira@PROJ-1/x":
        assert "Jira issue key" in describe_refusal(raw)


def test_mirror_only_project_accepts_room_refuses_work_item(tmp_path):
    """
    Scenario: OPS is configured with no repository — a mirror-only project
      When an authorized user declares jira@OPS-5 on a GitHub work item
      Then the room is accepted and the channel posts there
      But a ticket in OPS is never a work item
    """
    from the_loop.sessions import WorkItemRef
    from the_loop.sessions.refs import UnknownJiraProject, origin_repository

    channel, client, store, config = _jira_channel(tmp_path)
    room = parse_channel_ref(MIRROR_ROOM)
    assert room is not None
    resolved, name = resolve_channel_ref(room, config)
    assert (resolved, name) == (room, "")
    store.add(GH_ITEM, resolved)

    result = channel.post(_event("phase.started", work_item=GH_ITEM, text="design"))
    assert result.ok and [p["key"] for p in client.posted] == ["OPS-5"]

    with pytest.raises(UnknownJiraProject):
        origin_repository(WorkItemRef.parse(f"jira:{SITE}/OPS-1"), config)


def test_a_room_in_an_unconfigured_project_is_refused_at_declaration(tmp_path):
    config = _channel_config(tmp_path)
    room = parse_channel_ref("jira@NOPE-1")
    assert room is not None
    with pytest.raises(ValueError, match="NOPE"):
        resolve_channel_ref(room, config)


def test_jira_channel_without_room_mirrors_nothing(tmp_path):
    """No central fallback: a work item with no declared jira@ room is not mirrored."""
    from the_loop.channels.bus import publish

    channel, client, _, _ = _jira_channel(tmp_path)
    event = _event("phase.started", work_item=GH_ITEM, text="design")
    assert channel.addresses(event) is False
    result = publish(event, channels=[channel], record=False)
    assert result.posts == [] and client.posted == []


def test_comment_on_mirror_ticket_never_reaches_session(tmp_path):
    """Output only: the channel opens no conversation and may publish nothing."""
    from the_loop.channels.base import Conversational
    from the_loop.channels.events import PUBLISHABLE_EVENTS

    channel, _, _, _ = _jira_channel(tmp_path, subscribe=["phase.started"])
    assert not isinstance(channel, Conversational)
    assert not any(channel.may_publish(e) for e in PUBLISHABLE_EVENTS)
    assert not hasattr(channel, "read") and not hasattr(channel, "poll")


def test_the_channel_honours_subscribe_and_verbosity(tmp_path):
    channel, client, store, _ = _jira_channel(tmp_path, verbosity="quiet")
    store.add(GH_ITEM, MIRROR_ROOM)
    assert channel.subscribes("phase.started")
    assert not channel.subscribes("session.awaiting_input")
    channel.post(_event("phase.started", work_item=GH_ITEM, text="the long words"))
    [posted] = client.posted
    assert posted["body"].startswith(f"the-loop: phase.started on {GH_ITEM}")
    assert "the long words" not in posted["body"]
    assert posted["body"].rstrip("\n").endswith(JIRA_SELF_ATTRIBUTION)


def test_a_room_outside_the_configured_projects_is_not_written(tmp_path):
    channel, client, store, _ = _jira_channel(tmp_path)
    store.add(GH_ITEM, "jira@NOPE-1")
    result = channel.post(_event("phase.started", work_item=GH_ITEM))
    assert not result.ok and "NOPE" in result.error
    assert client.calls == []


def test_the_jira_channel_loads_from_config(tmp_path):
    from the_loop.channels.base import load_channels
    from the_loop.channels.jira import JiraChannel

    loaded = load_channels(_channel_config(tmp_path))
    assert [type(c) for c in loaded] == [JiraChannel]
    disabled = _channel_config(tmp_path, enabled=False)
    assert load_channels(disabled) == []
    no_jira = _channel_config(tmp_path)
    del no_jira["integrations"]
    assert load_channels(no_jira) == []  # a room needs the integration


def test_the_schema_has_no_publish_for_jira():
    from the_loop.configschema import validate

    ok = {"channels": {"jira": {"enabled": True, "subscribe": ["phase.started"]}}}
    assert validate(ok) == []
    bad = {"channels": {"jira": {"enabled": True, "publish": ["work-item.reply"]}}}
    assert any("publish" in error for error in validate(bad))
