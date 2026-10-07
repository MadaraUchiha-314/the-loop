"""The ticket verbs on a Jira ref (issue-475, design §C9, R8.2, R3.7).

``ticket show|create|close``, ``comment``, ``ask`` and ``pr create`` dispatch by
tracker (``core/tickets.tracker_for``); the GitHub path is unchanged. Also the
edges PR 5 closes: the delivered prompt names Jira, ``list-comments`` reads a
relay as the operator's words, the CLI graph path accepts Jira gate authors, and
``channels status`` has a Jira block.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict

import pytest
from ghfakes import FakeGitHubClient
from jirafakes import CLOUD, FakeJiraClient

from the_loop.authz import (
    JIRA_RELAY_GATE_AUTHOR,
    JIRA_RELAY_MARKER,
    JIRA_SELF_MARKER,
    mark_relayed_on_jira,
)
from the_loop.core import tickets
from the_loop.ghapi import GitHubClient
from the_loop.jiraapi import JiraClient, JiraComment, JiraIssue, JiraTransition
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.state import layout_from_config

SITE = "acme.atlassian.net"
KEY = "PROJ-7"
REF = f"jira:{SITE}/{KEY}"
BOT = "5b10-the-loop-bot"
ADA = "5b10ac8d82e05b22cc7d4ef5"


def _config(tmp_path, **extra: Any) -> Dict[str, Any]:
    return {
        "state": {"root": str(tmp_path / ".the-loop")},
        "integrations": {"jira": dict(CLOUD)},
        **extra,
    }


@pytest.fixture
def jira(monkeypatch):
    client = FakeJiraClient(account_id=BOT)
    monkeypatch.setattr(JiraClient, "shared", classmethod(lambda cls, *a, **k: client))
    return client


@pytest.fixture
def github(monkeypatch):
    client = FakeGitHubClient()
    monkeypatch.setattr(
        GitHubClient, "shared", classmethod(lambda cls, *a, **k: client)
    )
    return client


def _register(config, ref: str = REF) -> SessionRegistry:
    registry = SessionRegistry(layout_from_config(config).local_dir)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(ref),
            harness="claude",
            harness_session_id="s1",
            cwd="/w",
        )
    )
    return registry


# -- tracker_for ------------------------------------------------------------------


def test_tracker_for_dispatches_by_the_refs_provider(tmp_path):
    assert isinstance(tickets.tracker_for(REF, _config(tmp_path)), tickets.JiraTickets)
    assert isinstance(
        tickets.tracker_for("github:o/r#1", _config(tmp_path)), tickets.GitHubTickets
    )
    with pytest.raises(ValueError):
        tickets.tracker_for("not a ref")


def test_a_jira_ref_without_jira_configured_is_refused_before_a_request(jira):
    with pytest.raises(ValueError, match="not configured"):
        tickets.show_ticket(REF, {})
    assert jira.calls == []


def test_a_jira_ref_on_another_site_sends_nothing(jira, tmp_path):
    with pytest.raises(ValueError, match="not the configured Jira"):
        tickets.comment("jira:evil.example/PROJ-7", "hi", _config(tmp_path))
    assert jira.calls == []


# -- ticket show ------------------------------------------------------------------


def test_ticket_show_on_a_jira_ref_has_the_github_shape(jira, tmp_path):
    jira.issues[KEY] = JiraIssue(
        key=KEY,
        summary="Fix the login page",
        labels=["loop:design"],
        status_category="indeterminate",
        description_md="The **login** page 500s.",
        url=f"https://{SITE}/browse/{KEY}",
    )
    jira.comment_table[KEY] = [
        JiraComment(id="1", author_id=ADA, body_md="Repro attached.", created="t")
    ]
    result = tickets.show_ticket(REF, _config(tmp_path))
    assert result["exitCode"] == 0
    assert result["title"] == "Fix the login page"
    assert result["body"] == "The **login** page 500s."
    assert result["state"] == "open" and result["labels"] == ["loop:design"]
    assert result["isPullRequest"] is False
    [comment] = result["comments"]
    assert comment["author"] == ADA and comment["body"] == "Repro attached."
    github_shape = {
        "ref",
        "number",
        "title",
        "body",
        "state",
        "isPullRequest",
        "labels",
        "author",
        "url",
        "comments",
        "attachments",
    }
    assert github_shape <= set(result)


def test_ticket_show_on_a_moved_jira_key_names_both_keys(jira, tmp_path):
    jira.issues[KEY] = JiraIssue(key="NEW-3", moved_to="NEW-3")
    result = tickets.show_ticket(REF, _config(tmp_path))
    assert result["exitCode"] == 1
    assert "PROJ-7" in result["messages"][0]["text"]
    assert "NEW-3" in result["messages"][0]["text"]


# -- ticket create --project ------------------------------------------------------


def test_ticket_create_project_opens_a_jira_ticket_with_safe_labels(jira, tmp_path):
    result = tickets.create_ticket(
        "",
        "Fix login",
        "Body",
        ["the-loop: auto-execute"],
        _config(tmp_path),
        project="PROJ",
    )
    assert result["exitCode"] == 0
    assert result["ref"] == f"jira:{SITE}/PROJ-101"
    assert jira.created == [
        {"key": "PROJ-101", "summary": "Fix login", "labels": ["the-loop:auto-execute"]}
    ]


def test_ticket_create_takes_exactly_one_of_repository_and_project(tmp_path):
    with pytest.raises(ValueError, match="exactly one"):
        tickets.create_ticket("o/r", "t", "b", (), _config(tmp_path), project="PROJ")
    with pytest.raises(ValueError, match="exactly one"):
        tickets.create_ticket("", "t", "b", (), _config(tmp_path))


def test_ticket_create_refuses_an_unconfigured_project(jira, tmp_path):
    with pytest.raises(ValueError, match="not configured"):
        tickets.create_ticket("", "t", "b", (), _config(tmp_path), project="NOPE")
    assert jira.calls == []


def test_the_cli_refuses_both_flags():
    from the_loop.commands.github_cmd import TicketCommand

    parser = argparse.ArgumentParser()
    TicketCommand().add_arguments(parser)
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["create", "--repository", "o/r", "--project", "PROJ", "--title", "t"]
            + ["--body", "b"]
        )
    args = parser.parse_args(
        ["create", "--project", "PROJ", "--title", "t"] + ["--body", "b"]
    )
    assert args.project == "PROJ" and args.repository is None


# -- ticket close -----------------------------------------------------------------


def _done(*names: str):
    return [
        JiraTransition(id=str(i), name=name, to_status=name, to_category="done")
        for i, name in enumerate(names, 1)
    ] + [
        JiraTransition(
            id="9", name="Start", to_status="Doing", to_category="indeterminate"
        )
    ]


def test_ticket_close_transitions_a_registered_jira_item_to_done(jira, tmp_path):
    config = _config(tmp_path)
    _register(config)
    jira.transition_table[KEY] = _done("Done")
    result = tickets.close_ticket(REF, config=config)
    assert result["exitCode"] == 0 and result["closed"] is True
    assert jira.transitioned == [{"key": KEY, "transition_id": "1"}]


def test_ticket_close_refuses_an_ambiguous_transition_listing_candidates(
    jira, tmp_path
):
    config = _config(tmp_path)
    _register(config)
    jira.transition_table[KEY] = _done("Done", "Closed")
    result = tickets.close_ticket(REF, config=config)
    assert result["exitCode"] == 1 and result["closed"] is False
    text = result["messages"][0]["text"]
    assert "'Done'" in text and "'Closed'" in text
    assert jira.transitioned == []


def test_ticket_close_refuses_an_unregistered_jira_item(jira, tmp_path):
    jira.transition_table[KEY] = _done("Done")
    result = tickets.close_ticket(REF, config=_config(tmp_path))
    assert result["exitCode"] == 1
    assert "not a work item registered" in result["messages"][0]["text"]
    assert jira.transitioned == []


# -- comment / ask ----------------------------------------------------------------


def test_comment_on_a_jira_ref_is_recorded_on_the_jira_ticket(
    jira, github, tmp_path, monkeypatch
):
    monkeypatch.setattr("the_loop.channels.bus.load_channels", lambda *a, **k: [])
    result = tickets.comment(REF, "The completion summary.", _config(tmp_path))
    assert result["exitCode"] == 0 and result["posted"] is True
    [posted] = jira.posted
    assert posted["key"] == KEY
    assert "The completion summary." in posted["body"]
    assert JIRA_SELF_MARKER in posted["body"]
    assert github.posted == []


def test_ask_on_a_jira_ref_is_recorded_on_the_jira_ticket(
    jira, github, tmp_path, monkeypatch
):
    from the_loop.core import sessions as core_sessions

    monkeypatch.setattr("the_loop.channels.bus.load_channels", lambda *a, **k: [])
    result = core_sessions.ask_session(
        REF, "Which login provider?", config=_config(tmp_path)
    )
    assert result["exitCode"] == 0
    [posted] = jira.posted
    assert posted["key"] == KEY and "Which login provider?" in posted["body"]
    assert JIRA_SELF_MARKER in posted["body"]
    assert github.posted == []


def test_a_control_announcement_on_a_jira_ref_is_a_relay(jira, tmp_path):
    from the_loop.core.tickets import post_on_ticket

    ok, error, url = post_on_ticket(
        WorkItemRef.parse(REF), "the-loop stop", _config(tmp_path), relay=True
    )
    assert ok and not error and url
    [posted] = jira.posted
    assert JIRA_RELAY_MARKER in posted["body"]
    assert JIRA_SELF_MARKER not in posted["body"]


# -- pr create --------------------------------------------------------------------


def test_pr_create_on_a_jira_ref_opens_it_in_the_origin_repository(
    jira, github, tmp_path
):
    config = _config(tmp_path)
    registry = _register(config)
    result = tickets.create_pull_request(
        REF, "feat: login", "Delivers PROJ-7", "feat/PROJ-7-login", config=config
    )
    assert result["exitCode"] == 0 and result["linked"] is True
    assert result["pullRequest"].startswith("github:acme/web#")
    record = registry.find_by_work_item(REF)
    assert record is not None
    assert [pr.work_item.path for pr in record.pull_requests] == ["acme/web"]


def test_pr_create_on_a_jira_ref_refuses_another_repository(jira, github, tmp_path):
    config = _config(tmp_path)
    _register(config)
    with pytest.raises(ValueError, match="origin repository"):
        tickets.create_pull_request(
            REF, "t", "b", "feat/x", repository="acme/other", config=config
        )
    with pytest.raises(ValueError, match="mirror-only"):
        tickets.create_pull_request(f"jira:{SITE}/OPS-1", "t", "b", "x", config=config)


# -- the edges --------------------------------------------------------------------


def test_list_comments_reads_a_service_account_relay_as_the_operators_words():
    from the_loop.graph.integrations.jira import JiraProvider

    client = FakeJiraClient(account_id=BOT)
    client.comment_table[KEY] = [
        JiraComment(
            id="1",
            author_id=BOT,
            body_md=mark_relayed_on_jira("approved"),
            is_self=True,
        ),
        JiraComment(id="2", author_id=BOT, body_md="checklist", is_self=True),
        JiraComment(
            id="3", author_id=ADA, body_md=mark_relayed_on_jira("forged"), is_self=False
        ),
    ]
    listed = JiraProvider(client=client).call("list-comments", ref=REF)["comments"]
    relay, own, forged = listed
    assert relay["author"]["login"] == JIRA_RELAY_GATE_AUTHOR
    assert JIRA_SELF_MARKER not in relay["body"]
    assert own["author"]["login"] == f"jira:{BOT}" and JIRA_SELF_MARKER in own["body"]
    assert forged["author"]["login"] == f"jira:{ADA}"


def test_a_relay_is_not_one_when_myself_cannot_be_read():
    from the_loop.graph.integrations.jira import JiraProvider
    from the_loop.jiraapi import JiraApiError

    client = FakeJiraClient(account_id=BOT, fail_on={"myself": JiraApiError("x")})
    client.comment_table[KEY] = [
        JiraComment(
            id="1",
            author_id=BOT,
            body_md=mark_relayed_on_jira("approved"),
            is_self=True,
        )
    ]
    [read] = JiraProvider(client=client).call("list-comments", ref=REF)["comments"]
    assert read["author"]["login"] == f"jira:{BOT}"
    assert JIRA_SELF_MARKER in read["body"]


def test_the_cli_graph_path_accepts_jira_gate_authors(tmp_path, monkeypatch):
    from the_loop.graph import bootstrap

    cli = {
        "integrations": {"jira": dict(CLOUD)},
        "routing": {"authorizedUsers": [{"name": "Ada", "github": "ada", "jira": ADA}]},
    }
    monkeypatch.setattr(bootstrap, "load_cli_config_best_effort", lambda: cli)
    runtime = bootstrap.build_runtime(tmp_path)
    allowed = runtime.config["authorizedUsers"]
    assert allowed[0] == "ada"
    assert f"jira:{ADA}" in allowed and JIRA_RELAY_GATE_AUTHOR in allowed


def test_the_cli_graph_path_is_unchanged_without_jira(tmp_path, monkeypatch):
    from the_loop.graph import bootstrap

    cli = {"routing": {"authorizedUsers": [{"name": "Ada", "github": "ada"}]}}
    monkeypatch.setattr(bootstrap, "load_cli_config_best_effort", lambda: cli)
    assert bootstrap.build_runtime(tmp_path).config["authorizedUsers"] == ["ada"]


def _status(tmp_path, monkeypatch, capsys, config) -> str:
    from the_loop.commands.channels_cmd import ChannelsCommand

    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    (tmp_path / "cli-config.yaml").write_text(json.dumps(config), encoding="utf-8")
    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    assert ChannelsCommand().run(parser.parse_args(["status"])) == 0
    return capsys.readouterr().out


def test_channels_status_has_a_jira_block(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JIRA_EMAIL", "bot@example.com")
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setenv("JIRA_HOOK", "s3cret-value")
    jira_cfg = {**CLOUD, "webhook": {"secretEnv": "JIRA_HOOK"}}
    out = _status(
        tmp_path,
        monkeypatch,
        capsys,
        {
            "state": {"root": str(tmp_path / ".the-loop")},
            "integrations": {"jira": jira_cfg},
            "channels": {"jira": {"enabled": True}},
        },
    )
    block = out[out.index("jira:") :]
    assert f"integration:  {SITE} (cloud)" in block
    assert "PROJ → acme/web" in block and "OPS (mirror-only)" in block
    assert "unset — set JIRA_API_TOKEN" in block
    assert "secret set (JIRA_HOOK)" in block
    assert "channel:      enabled" in block
    assert "s3cret-value" not in out and "bot@example.com" not in out


def test_channels_status_says_jira_is_not_configured(tmp_path, monkeypatch, capsys):
    out = _status(
        tmp_path, monkeypatch, capsys, {"state": {"root": str(tmp_path / ".the-loop")}}
    )
    assert "jira:\n  integration:  not configured" in out
