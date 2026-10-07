"""Markdown ⇄ Jira bodies (issue-475, design §C6, R4.5, R5.5).

Golden files under ``tests/fixtures/jira/`` hold what the-loop sends to Jira for
the four bodies that matter most — the phase-selection checklist, a gate's
request-review, an ask and the PR-briefing template — as ADF (Cloud, REST v3)
and wiki markup (Data Center, REST v2), plus the Markdown an ADF body reads back
as (``.read.txt`` — not ``.md``, so markdownlint leaves the snapshot alone). The bodies are rendered from the real code at test time, so a change to a
renderer that changes what Jira receives fails here until the golden file is
regenerated and reviewed (``THE_LOOP_REGEN_JIRA_GOLDEN=1``).

Beside the snapshots, the properties the gates depend on are asserted directly:
``- [ ]`` becomes an ADF ``taskList`` a person ticks in place, and the ticked box
reads back as ``- [x]`` through the selection gate's own parser.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest

from the_loop.channels.base import Event
from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks import selection
from the_loop.graph.model import PDLC_WORK_ITEM_LOOP, load_graph
from the_loop.jiraformat import (
    adf_to_markdown,
    from_jira,
    markdown_to_adf,
    markdown_to_wiki,
    to_jira,
    wiki_to_markdown,
)

FIXTURES = Path(__file__).parent / "fixtures" / "jira"
REPO_ROOT = Path(__file__).resolve().parents[2]
REGEN = os.environ.get("THE_LOOP_REGEN_JIRA_GOLDEN") == "1"

JIRA_REF = "jira:acme.atlassian.net/PROJ-7"

#: Everything a deployment can offer, so every checklist section is rendered.
FULL_CONFIG = {
    "authorizedUsers": ["owner"],
    "harness": "claude",
    "offeredHarnesses": ["claude", "codex"],
    "harnesses": [{"name": "claude", "defaultModel": "sonnet"}, {"name": "codex"}],
    "models": [{"name": "opus", "about": "deepest"}, {"name": "sonnet"}],
    "effort": ["low", "high"],
}


# -- the four real bodies ------------------------------------------------------------


def _ctx(node_id: str, config=None) -> HookContext:
    return HookContext(
        work_item=WorkItem(ref=JIRA_REF, id="jira-proj-7", spec_dir=Path(".")),
        node={"id": node_id},
        boundary="entry",
        repo=Path("."),
        config=dict(config or FULL_CONFIG),
        graph=load_graph(name=PDLC_WORK_ITEM_LOOP),
    )


def _checklist() -> str:
    return selection._checklist_body(_ctx("phase-selection"))


def _request_review(monkeypatch) -> str:
    from the_loop.graph.hooks.sideeffects import request_review

    posted: List[str] = []

    class _Recorder:
        def call(self, op, **params):
            posted.append(str(params.get("body") or ""))
            return {"result": {"html_url": "u"}}

    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve", lambda target, config: _Recorder()
    )
    request_review(_ctx("design-approval", {}))
    [body] = posted
    return body


def _ask() -> str:
    from the_loop.channels.github import ask_body

    question = (
        "**Question:** which database should the migration target?\n\n"
        "1. Postgres 16 — what production runs today\n"
        "2. MySQL 8 — what the reporting replica runs\n\n"
        "Reply on this ticket; the default is `postgres` if nobody answers."
    )
    return ask_body(
        Event(
            event_type="session.awaiting_input",
            work_item=JIRA_REF,
            text=question,
            source="cli",
        )
    )


def _pr_briefing() -> str:
    return (REPO_ROOT / "skills/the-loop/templates/pr-briefing.md").read_text()


def _bodies(monkeypatch) -> Dict[str, str]:
    """Each body as it is posted: the-loop's comments carry the Jira self-marker
    (the provider and the ledger apply it); the briefing is a document."""
    from the_loop.authz import mark_self_authored_on_jira as marked

    return {
        "checklist": marked(_checklist()),
        "request-review": marked(_request_review(monkeypatch)),
        "ask": marked(_ask()),
        "pr-briefing": _pr_briefing(),
    }


# -- golden files (T2, T10) ----------------------------------------------------------


def _golden(name: str, suffix: str, actual: str) -> None:
    path = FIXTURES / f"{name}.{suffix}"
    if REGEN:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
    assert path.is_file(), f"missing golden file {path}; regenerate with REGEN"
    assert actual == path.read_text(encoding="utf-8"), f"{path} differs"


def _adf_json(doc: Dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


@pytest.mark.parametrize("name", ["checklist", "request-review", "ask", "pr-briefing"])
def test_golden_bodies(name, monkeypatch):
    body = _bodies(monkeypatch)[name]
    adf = markdown_to_adf(body)
    _golden(name, "adf.json", _adf_json(adf))
    _golden(name, "wiki", markdown_to_wiki(body) + "\n")
    _golden(name, "read.txt", adf_to_markdown(adf) + "\n")


# -- the checklist: real checkboxes, read back by the gate (R5.5) ------------------


def _nodes(node: Any, kind: str) -> Iterator[Dict[str, Any]]:
    if isinstance(node, dict):
        if node.get("type") == kind:
            yield node
        for child in node.get("content") or []:
            yield from _nodes(child, kind)


def _checks(body: str):
    return [
        (m.group("mark").lower(), m.group("token"))
        for m in selection._CHECK_LINE.finditer(body)
    ]


def test_checklist_rows_become_task_items_with_their_state():
    body = _checklist()
    adf = markdown_to_adf(body)
    items = list(_nodes(adf, "taskItem"))
    assert items, "the checklist rows must be Jira checkboxes"
    states = [item["attrs"]["state"] for item in items]
    assert set(states) <= {"TODO", "DONE"}
    expected = ["DONE" if mark == "x" else "TODO" for mark, _ in _checks(body)]
    assert states == expected
    assert all(item["attrs"].get("localId") for item in items)
    assert all(lst["attrs"].get("localId") for lst in _nodes(adf, "taskList"))


def test_checklist_reads_back_through_the_gate_parser_unchanged():
    body = _checklist()
    assert _checks(adf_to_markdown(markdown_to_adf(body))) == _checks(body)
    assert _checks(wiki_to_markdown(markdown_to_wiki(body))) == _checks(body)


def test_a_box_ticked_in_jira_reads_back_as_ticked():
    """Scenario: a reviewer ticks an unticked phase in the Jira UI."""
    body = _checklist()
    adf = markdown_to_adf(body)
    ticked = copy.deepcopy(adf)
    first_todo = next(
        i for i in _nodes(ticked, "taskItem") if i["attrs"]["state"] == "TODO"
    )
    first_todo["attrs"]["state"] = "DONE"
    before = _checks(adf_to_markdown(adf))
    after = _checks(adf_to_markdown(ticked))
    changed = [(b, a) for b, a in zip(before, after) if b != a]
    assert len(changed) == 1
    (old_mark, token), (new_mark, same) = changed[0]
    assert (old_mark, new_mark) == (" ", "x") and token == same


def test_a_data_center_tick_reads_back_as_ticked():
    wiki = "* (x) {{design}} — the design\n* (/) {{implementation}} — the code"
    assert _checks(wiki_to_markdown(wiki)) == [
        (" ", "design"),
        ("x", "implementation"),
    ]


def test_the_selection_marker_survives_the_round_trip():
    body = _checklist()
    assert selection.SELECTION_MARKER in adf_to_markdown(markdown_to_adf(body))
    assert selection.SELECTION_MARKER in wiki_to_markdown(markdown_to_wiki(body))


# -- the constructs (design §C6 table) ---------------------------------------------


def test_details_are_dropped_and_the_summary_kept_bold():
    md = "<details>\n<summary>ℹ️ What this means</summary>\n\nInside.\n\n</details>\n"
    adf = markdown_to_adf(md)
    text = json.dumps(adf, ensure_ascii=False)
    assert "<details>" not in text and "<summary>" not in text
    first = adf["content"][0]
    assert first["type"] == "paragraph"
    assert first["content"] == [
        {"type": "text", "text": "ℹ️ What this means", "marks": [{"type": "strong"}]}
    ]
    assert adf["content"][1]["content"][0]["text"] == "Inside."
    wiki = markdown_to_wiki(md)
    assert "<details>" not in wiki and "*ℹ️ What this means*" in wiki


def test_html_comments_and_raw_html_are_dropped():
    md = "<!-- a note\nfor the author -->\n\nText <span>inline</span>.\n"
    adf = markdown_to_adf(md)
    assert "<!--" not in json.dumps(adf) and "<span>" not in json.dumps(adf)
    assert adf_to_markdown(adf) == "Text inline."
    assert "<!--" not in markdown_to_wiki(md)


def test_an_envelope_is_dropped_but_a_bare_marker_is_kept():
    md = (
        "Body.\n\n<!-- the-loop:event "
        '{"type":"x","source":"cli","actor":{},"ts":"t"} -->\n\n'
        "<!-- the-loop:goal-request -->\n"
    )
    back = adf_to_markdown(markdown_to_adf(md))
    assert "the-loop:event" not in back
    assert back.endswith("<!-- the-loop:goal-request -->")


def test_the_visible_self_marker_is_literal_text():
    """``[the-loop:agent-comment]`` looks like link syntax; it must stay text."""
    md = "Done.\n\n🤖 the-loop, autonomous comment · [the-loop:agent-comment]\n"
    adf = markdown_to_adf(md)
    last = adf["content"][-1]
    assert [n["type"] for n in last["content"]] == ["text"]
    assert last["content"][0]["text"].endswith("[the-loop:agent-comment]")
    assert "marks" not in last["content"][0]
    assert "[the-loop:agent-comment]" in adf_to_markdown(adf)
    wiki = markdown_to_wiki(md)
    assert "\\[the-loop:agent-comment\\]" in wiki  # never a wiki link
    assert "[the-loop:agent-comment]" in wiki_to_markdown(wiki)


def test_headings_emphasis_code_and_links():
    md = "## Title\n\n**b** _i_ `c` [t](https://e.example/x)\n"
    adf = markdown_to_adf(md)
    assert adf["content"][0] == {
        "type": "heading",
        "attrs": {"level": 2},
        "content": [{"type": "text", "text": "Title"}],
    }
    marks = [
        (n["text"], [m["type"] for m in n.get("marks", [])])
        for n in adf["content"][1]["content"]
    ]
    assert ("b", ["strong"]) in marks and ("i", ["em"]) in marks
    assert ("c", ["code"]) in marks and ("t", ["link"]) in marks
    link = next(n for n in adf["content"][1]["content"] if n["text"] == "t")
    assert link["marks"][0]["attrs"] == {"href": "https://e.example/x"}
    assert adf_to_markdown(adf) == "## Title\n\n**b** _i_ `c` [t](https://e.example/x)"
    wiki = markdown_to_wiki(md)
    assert wiki == "h2. Title\n\n*b* _i_ {{c}} [t|https://e.example/x]"
    assert (
        wiki_to_markdown(wiki) == "## Title\n\n**b** _i_ `c` [t](https://e.example/x)"
    )


def test_lists_nest_and_number():
    md = "- a\n  - b\n- c\n\n3. x\n4. y\n"
    adf = markdown_to_adf(md)
    bullet, ordered = adf["content"]
    assert bullet["type"] == "bulletList" and ordered["type"] == "orderedList"
    assert ordered["attrs"] == {"order": 3}
    nested = bullet["content"][0]["content"][1]
    assert nested["type"] == "bulletList"
    assert adf_to_markdown(adf) == "- a\n  - b\n- c\n\n3. x\n4. y"
    assert markdown_to_wiki(md) == "* a\n** b\n* c\n\n# x\n# y"


def test_fenced_code_keeps_its_language_and_text():
    md = "```python\nprint('[x]')\n```\n"
    adf = markdown_to_adf(md)
    assert adf["content"] == [
        {
            "type": "codeBlock",
            "attrs": {"language": "python"},
            "content": [{"type": "text", "text": "print('[x]')"}],
        }
    ]
    assert adf_to_markdown(adf) == "```python\nprint('[x]')\n```"
    assert markdown_to_wiki(md) == "{code:python}\nprint('[x]')\n{code}"
    assert wiki_to_markdown(markdown_to_wiki(md)) == "```python\nprint('[x]')\n```"


def test_tables_have_a_header_row():
    md = "| a | b |\n|---|---|\n| 1 | `2` |\n"
    adf = markdown_to_adf(md)
    [table] = adf["content"]
    assert table["type"] == "table"
    header, row = table["content"]
    assert [c["type"] for c in header["content"]] == ["tableHeader", "tableHeader"]
    assert [c["type"] for c in row["content"]] == ["tableCell", "tableCell"]
    assert adf_to_markdown(adf) == "| a | b |\n| --- | --- |\n| 1 | `2` |"
    assert markdown_to_wiki(md) == "||a||b||\n|1|{{2}}|"
    assert (
        wiki_to_markdown("||a||b||\n|1|{{2}}|")
        == "| a | b |\n| --- | --- |\n| 1 | `2` |"
    )


def test_quotes_and_rules():
    md = "> quoted **text**\n\n---\n\nafter\n"
    adf = markdown_to_adf(md)
    assert [n["type"] for n in adf["content"]] == ["blockquote", "rule", "paragraph"]
    assert adf_to_markdown(adf) == "> quoted **text**\n\n---\n\nafter"
    assert markdown_to_wiki(md) == "{quote}\nquoted *text*\n{quote}\n\n----\n\nafter"


def test_wiki_text_is_escaped_where_it_would_be_markup():
    md = "a {macro}, a|pipe, [link], 2^3, ~x, \\*star and snake_case\n"
    wiki = markdown_to_wiki(md)
    assert wiki == (
        "a \\{macro\\}, a\\|pipe, \\[link\\], 2\\^3, \\~x, \\*star and snake\\_case"
    )
    assert (
        wiki_to_markdown(wiki)
        == "a {macro}, a|pipe, [link], 2^3, ~x, *star and snake_case"
    )


def test_a_bare_url_in_wiki_text_is_not_escaped():
    md = "see https://github.com/o/r_x/pull/1 now\n"
    assert markdown_to_wiki(md) == "see https://github.com/o/r_x/pull/1 now"


def test_a_line_break_in_a_paragraph_is_kept():
    adf = markdown_to_adf("one\ntwo\n")
    assert adf["content"][0]["content"] == [
        {"type": "text", "text": "one"},
        {"type": "hardBreak"},
        {"type": "text", "text": "two"},
    ]
    assert adf_to_markdown(adf) == "one\ntwo"


# -- reading what a person wrote in Jira -------------------------------------------


def test_unknown_adf_nodes_are_read_as_their_text_and_logged(caplog):
    doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "panel",
                "attrs": {"panelType": "info"},
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "hi"}]}
                ],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "mention", "attrs": {"id": "5b10", "text": "@Ada"}},
                    {"type": "text", "text": " said "},
                    {"type": "emoji", "attrs": {"shortName": ":tada:", "text": "🎉"}},
                    {"type": "weirdInline", "content": [{"type": "text", "text": "!"}]},
                ],
            },
        ],
    }
    with caplog.at_level(logging.DEBUG, logger="the-loop.jiraformat"):
        assert adf_to_markdown(doc) == "hi\n\n@Ada said 🎉!"
    assert any("weirdInline" in r.getMessage() for r in caplog.records)


def test_from_jira_dispatches_on_the_body_shape():
    assert from_jira(markdown_to_adf("**x**")) == "**x**"
    assert from_jira("*x*") == "**x**"
    assert from_jira(None) == ""


def test_to_jira_picks_the_format_by_rest_version():
    assert to_jira("**x**", "3") == markdown_to_adf("**x**")
    assert to_jira("**x**", "2") == "*x*"


def test_an_empty_body_is_an_empty_document():
    assert markdown_to_adf("") == {"type": "doc", "version": 1, "content": []}
    assert adf_to_markdown({"type": "doc", "version": 1, "content": []}) == ""
    assert markdown_to_wiki("") == ""


# -- the client converts by REST version (design §C3) ------------------------------


def _sdk_client(config, monkeypatch):
    from jirafakes import FakeJiraSDK

    from the_loop.jiraapi import JiraApiConfig, JiraClient

    monkeypatch.setenv("JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "t0ken-value")
    monkeypatch.setenv("JIRA_PAT", "pat-value")
    sdk = FakeJiraSDK()
    client = JiraClient(
        JiraApiConfig.from_cli_config(config), factory=lambda api, auth: sdk
    )
    return client, sdk


def test_the_client_sends_adf_on_cloud_and_reads_it_back(monkeypatch):
    from jirafakes import cloud_config

    client, sdk = _sdk_client(cloud_config(), monkeypatch)
    comment = client.add_comment("PROJ-1", "- [ ] `design`\n- [x] `verify`")
    [call] = [c for c in sdk.calls if c["method"] == "add_comment"]
    assert call["body"] == markdown_to_adf("- [ ] `design`\n- [x] `verify`")
    assert comment.body_md == "- [ ] `design`\n- [x] `verify`"


def test_the_client_sends_wiki_on_data_center_and_reads_it_back(monkeypatch):
    from jirafakes import DATA_CENTER

    client, sdk = _sdk_client({"integrations": {"jira": DATA_CENTER}}, monkeypatch)
    comment = client.add_comment("PROJ-1", "**bold** and `code`")
    [call] = [c for c in sdk.calls if c["method"] == "add_comment"]
    assert call["body"] == "*bold* and {{code}}"
    assert comment.body_md == "**bold** and `code`"
