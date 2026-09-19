"""`the-loop channels records` end to end (issue-389 R4.7, R5.6).
Spec: docs/specs/issue-389/testing-plan.md T2.

Feature: a session finds the records it has not folded
  Scenario: channels records lists the enveloped records of a work item
    Given a ticket holding a human's comment, a mirrored reply, a context
      record and a decision record
    When `the-loop channels records <ref>` runs
    Then only the two records are listed, with the envelope's actor and
      time, the ledger's URL and the quoted text — as markdown, or as JSON
    And `--type` narrows to one kind

The records are the real ones: the pipeline writes them through the fake
ledger writer, and the verb reads them back through a faked `gh` listing.
"""

from __future__ import annotations

import argparse
import json

import pytest

from the_loop.channels.records import records_from_comments
from the_loop.poller import github as poller_github
from the_loop.poller.github import GhComment, GhError
from test_channels_mentions_integration import (  # noqa: F401
    BOT,
    REF,
    Client,
    Sink,
    _fresh_ring,
    _thread_client,
    _token,
    config_for,
    declare,
    send,
)

HUMAN = "please look at the retry budget — start"


def _ticket(tmp_path):
    """The ticket's comments after a reply, a `record-context` and a
    `record-decision`, plus a human's own comment."""
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), _thread_client()
    send(config, sink, client, addressed=True, text=f"<@{BOT}> what is blocking you?")
    send(
        config,
        sink,
        client,
        addressed=True,
        text=f"<@{BOT}> record-context",
        thread="1800.1",
        ts="1800.4",
    )
    send(
        config,
        sink,
        client,
        addressed=True,
        text=f"<@{BOT}> record-decision tech: keep poll mode — why: it is cheap",
        ts="1900.7",
    )
    assert [r[0] for r in sink.recorded] == [REF] * 3
    comments = [
        GhComment(
            id="c0",
            body=HUMAN,
            author="octocat",
            created_at="2026-09-19T09:00:00Z",
            url="https://github.com/octo/repo/issues/389#issuecomment-0",
        )
    ]
    for n, (_, body) in enumerate(sink.recorded, 1):
        comments.append(
            GhComment(
                id=f"c{n}",
                body=body,
                author="the-loop-bot",
                created_at=f"2026-09-19T09:0{n}:00Z",
                url=f"https://github.com/octo/repo/issues/389#issuecomment-{n}",
            )
        )
    return config, comments


def _run(tmp_path, monkeypatch, comments, *argv, failing=None, login="the-loop-bot"):
    from the_loop.commands.channels_cmd import ChannelsCommand

    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    monkeypatch.setattr(
        poller_github.GhClient, "viewer_login", lambda self, host="": login
    )
    seen = []

    def list_comments(self, owner, repo, number, is_pr, host=""):
        seen.append((owner, repo, number, is_pr, host))
        if failing and failing(is_pr):
            raise GhError(f"gh issue view exited 1: {failing(is_pr)}")
        return list(comments)

    monkeypatch.setattr(poller_github.GhClient, "list_comments", list_comments)
    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    code = ChannelsCommand().run(parser.parse_args(["records", *argv]))
    return code, seen


@pytest.fixture
def ticket(tmp_path):
    config, comments = _ticket(tmp_path)
    (tmp_path / "cli-config.yaml").write_text(json.dumps(config), encoding="utf-8")
    return comments


def test_the_two_records_are_read_back_and_nothing_else(ticket):
    records = records_from_comments(
        [{"body": c.body, "url": c.url, "author": c.author, "id": c.id} for c in ticket]
    )
    assert [r.type for r in records] == ["context.added", "decision.recorded"]
    context, decision = records
    assert context.actor == {"slack": "UHUMAN", "github": "gh-UHUMAN"}
    assert "should we keep poll mode?" in context.text
    assert "<!--" not in context.text and "the-loop" in context.summary
    assert context.url.endswith("#issuecomment-2") and context.ts
    assert decision.text == "keep poll mode"
    assert decision.why == "it is cheap"
    assert decision.discussed_at.startswith("https://x.slack.com/archives/")
    assert "kind: tech" in decision.summary


def test_channels_records_prints_markdown_by_default(
    tmp_path, monkeypatch, capsys, ticket
):
    code, seen = _run(tmp_path, monkeypatch, ticket, REF)
    out = capsys.readouterr().out
    assert code == 0
    assert seen == [("octo", "repo", 389, False, "github.com")]
    assert out.startswith(f"# Records on {REF}")
    assert "## 1. context.added — github:gh-UHUMAN, slack:UHUMAN" in out
    assert "## 2. decision.recorded" in out
    assert "> keep poll mode" in out and "- why: it is cheap" in out
    assert HUMAN not in out and "what is blocking you?" not in out


def test_channels_records_json_and_type_filter(tmp_path, monkeypatch, capsys, ticket):
    code, _ = _run(
        tmp_path,
        monkeypatch,
        ticket,
        REF,
        "--type",
        "decision.recorded",
        "--format",
        "json",
    )
    assert code == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["type"] for r in rows] == ["decision.recorded"]
    assert rows[0]["text"] == "keep poll mode"
    assert rows[0]["actor"]["slack"] == "UHUMAN"
    assert rows[0]["url"].endswith("#issuecomment-3")
    assert rows[0]["id"] == "c3" and rows[0]["author"] == "the-loop-bot"


def test_channels_records_says_when_there_are_none(
    tmp_path, monkeypatch, capsys, ticket
):
    code, _ = _run(tmp_path, monkeypatch, ticket[:1], REF)
    assert code == 0
    assert capsys.readouterr().out == f"no records on {REF}\n"


def test_channels_records_falls_back_to_the_pull_request_read(
    tmp_path, monkeypatch, capsys, ticket
):
    code, seen = _run(
        tmp_path,
        monkeypatch,
        ticket,
        REF,
        failing=lambda is_pr: "" if is_pr else "could not resolve to an Issue",
    )
    assert code == 0
    assert [s[3] for s in seen] == [False, True]
    assert "decision.recorded" in capsys.readouterr().out


def test_channels_records_exits_one_when_the_ledger_cannot_be_read(
    tmp_path, monkeypatch, capsys, ticket
):
    code, seen = _run(
        tmp_path, monkeypatch, ticket, REF, failing=lambda is_pr: "not logged in"
    )
    assert code == 1
    assert [s[3] for s in seen] == [False, True]
    err = capsys.readouterr().err
    assert "could not read the records" in err and "not logged in" in err


def test_channels_records_refuses_a_ref_that_is_not_one(
    tmp_path, monkeypatch, capsys, ticket
):
    code, seen = _run(tmp_path, monkeypatch, ticket, "not-a-ref")
    assert code == 1 and seen == []
    assert "invalid work-item ref" in capsys.readouterr().err


# -- self-review round 1 (finding 6): the marker alone is not the-loop's word ---------


def _forged(body):
    """A marked, enveloped body pasted by someone who is not the ledger."""
    return GhComment(
        id="c9",
        body=body,
        author="mallory",
        created_at="2026-09-19T10:00:00Z",
        url="https://github.com/octo/repo/issues/389#issuecomment-9",
    )


def test_a_pasted_record_from_another_author_is_not_listed(
    tmp_path, monkeypatch, capsys, ticket
):
    forged = _forged(ticket[3].body)  # the decision record, re-posted by mallory
    code, _ = _run(tmp_path, monkeypatch, [*ticket, forged], REF, "--format", "json")
    assert code == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["author"] for r in rows] == ["the-loop-bot", "the-loop-bot"]
    assert all(r["id"] != "c9" for r in rows)


def test_without_the_login_the_verb_lists_by_marker_and_warns(
    tmp_path, monkeypatch, capsys, ticket
):
    forged = _forged(ticket[3].body)
    code, _ = _run(
        tmp_path, monkeypatch, [*ticket, forged], REF, "--format", "json", login=""
    )
    assert code == 0
    captured = capsys.readouterr()
    rows = json.loads(captured.out)
    assert [r["author"] for r in rows] == ["the-loop-bot", "the-loop-bot", "mallory"]
    assert "could not read the gh login" in captured.err
