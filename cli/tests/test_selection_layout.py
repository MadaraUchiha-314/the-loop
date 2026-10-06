"""The phase-selection comment's layout (issue-472): sections a reader can tell
apart, the action and each default before any explanation, every explanation
collapsed — and the rows, which are the reply contract, exactly as they were.

Pure rendering: the hook's ``_checklist_body`` over the shipped graphs, read back
with the gate's own parser and the Slack mirror's.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from the_loop.authz import SELF_COMMENT_MARKER
from the_loop.channels.slack import selection_rows
from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks import selection
from the_loop.graph.model import (
    PDLC_CONTRIBUTION_LOOP,
    PDLC_WORK_ITEM_LOOP,
    compile_graph,
    load_graph,
)
from test_graph_skips import SELECT_GRAPH

#: Everything a deployment can offer, so every section is rendered.
FULL_CONFIG = {
    "authorizedUsers": ["owner"],
    "harness": "claude",
    "offeredHarnesses": ["claude", "codex"],
    "harnesses": [{"name": "claude", "defaultModel": "sonnet"}, {"name": "codex"}],
    "models": [{"name": "opus", "about": "deepest"}, {"name": "sonnet"}],
    "effort": ["low", "high"],
}

_HEADING = re.compile(r"^(#{2,4}) (\S+) (.+)$", re.MULTILINE)
_ROW = re.compile(r"^- \[[ x]\] ", re.MULTILINE)


def _body(config=None, loop: str = PDLC_WORK_ITEM_LOOP, graph=None) -> str:
    ctx = HookContext(
        work_item=WorkItem(ref="github:o/r#7", id="issue-7", spec_dir=Path(".")),
        node={"id": "phase-selection"},
        boundary="entry",
        repo=Path("."),
        config=dict(config or FULL_CONFIG),
        graph=graph or load_graph(name=loop),
    )
    return selection._checklist_body(ctx)


def _headings(body: str):
    return [(len(m.group(1)), m.group(2), m.group(3)) for m in _HEADING.finditer(body)]


def _details(body: str):
    """``(summary, inner text)`` for every collapsed block, in order."""
    return re.findall(
        r"<details>\n<summary>(.+?)</summary>\n(.*?)\n</details>", body, re.DOTALL
    )


# -- R1: sections a reader can tell apart ------------------------------------------


def test_the_comment_opens_with_its_question_and_the_quick_start():
    """
    Scenario: the checklist is posted for a work item
      Given the shipped outer loop and a deployment offering every choice
      When the gate renders its comment
      Then the first line is the titled question
      And the quick start comes before any row
    """
    body = _body()
    first = body.split("\n", 1)[0]
    assert first == "## 🤖 the-loop — which phases does this work item need?"
    first_row = _ROW.search(body)
    assert first_row is not None
    assert body.index("Quick start") < first_row.start()
    assert "reply `the-loop execute` with the boxes untouched" in body[:400]


def test_every_question_is_a_heading_with_an_emoji_of_its_own():
    body = _body()
    headings = _headings(body)
    titles = [title for _, _, title in headings]
    for question in (
        "Phases — ticked ones run",
        "Optional phases — off unless you tick them",
        "Settings — not phases; each has a default",
        "Where should the outer loop happen?",
        "Publish the spec chain as a Claude artifact too?",
        "How many sessions should this work item's pull requests get?",
        "Is this work item worked in a channel of its own?",
        "Which harness should this work item run on?",
        "Which model should this work item run on?",
        "How hard should it think?",
        "Ready?",
    ):
        assert question in titles, question
    emoji = [mark for _, mark, _ in headings]
    assert len(emoji) == len(set(emoji)), emoji
    assert all(not mark[0].isalnum() for mark in emoji), emoji


def test_the_phases_and_the_settings_are_two_groups():
    body = _body()
    levels = {title: level for level, _, title in _headings(body)}
    assert levels["Phases — ticked ones run"] == 3
    assert levels["Settings — not phases; each has a default"] == 3
    assert levels["Ready?"] == 3
    assert levels["Where should the outer loop happen?"] == 4
    # every phase row sits between the two group headings; every setting row after
    settings_at = body.index("Settings — not phases")
    for node in load_graph().ordered():
        if node.skippable:
            row = re.search(rf"^- \[[ x]\] {re.escape(node.id)}( —|$)", body, re.M)
            assert row is not None and row.start() < settings_at, node.id
    assert body.index(f"`{selection.SURFACE_TOKEN}`") > settings_at


def test_a_contribution_says_why_there_is_no_surface_under_the_settings():
    body = _body(loop=PDLC_CONTRIBUTION_LOOP)
    titles = [title for _, _, title in _headings(body)]
    assert "Where should the outer loop happen?" not in titles
    assert "Publish the spec chain as a Claude artifact too?" not in titles
    assert selection.SURFACE_TOKEN not in body
    assert selection.CLAUDE_ARTIFACT_TOKEN not in body
    assert (
        body.index("Settings — not phases")
        < body.index("There is no outer loop to place on this one")
        < body.index("How many sessions should")
    )


# -- R2: the action first, the explanation on demand -------------------------------


def test_each_setting_states_its_default_before_its_rows():
    body = _body()
    sections = re.split(r"^#### ", body, flags=re.MULTILINE)[1:]
    settings = [s for s in sections if not s.startswith("➕")]
    assert len(settings) == 7
    for section in settings:
        default = section.index("**Default:**")
        row = _ROW.search(section)
        assert row is None or default < row.start(), section[:60]
    assert "**Default:** `claude`, this deployment's default." in body
    assert "**Default:** `sonnet`, the `claude` harness's default model." in body
    assert "**Default:** `cross-repository`" in body


def test_every_explanation_is_collapsed_and_no_box_is():
    body = _body()
    assert body.count("<details>") == body.count("</details>") == len(_details(body))
    assert len(_details(body)) >= 8
    for summary, inner in _details(body):
        assert not _ROW.search(inner), summary
        assert summary[0] not in "*_`", summary  # plain text: GitHub may not render it


def test_no_fact_the_comment_stated_is_lost():
    """R2.5 — moved under a summary, never dropped."""
    body = _body()
    for fact in (
        "The tick state at that moment is frozen and becomes the graph this item walks",
        "A doc fix usually needs little more than implementation and verification",
        "a checklist in the `the-loop execute` comment wins over the boxes",
        "the **authorization is your reply**",
        "each repository this work item contributes code to gets its own pull request",
        "On any other harness the-loop ignores this box",
        "The markdown files stay the source of truth either way",
        "the operator's `routing.tmux.sessionPerPr`",
        "`session.pr_session_declined`",
        "none declared — this item's updates go to the operator's central channel",
        "a comment may carry only one keyword",
        "A model or effort ticked below is kept only if the harness it ends up on",
        "Ticking more than one means the same thing",
        "Every phase of this loop is selectable",
        "recorded as its own declared choice",
    ):
        assert fact in body, fact


# -- R3: the reply contract does not move ------------------------------------------


def test_the_rows_read_back_exactly_as_the_graph_lists_them():
    body = _body()
    graph = load_graph()
    ordered = list(graph.ordered())
    rows = selection_rows(body)
    assert rows is not None
    assert [r.token for r in rows.phases] == [
        n.id for n in ordered if n.skippable and not n.opt_in
    ] + [n.id for n in ordered if n.opt_in]
    assert rows.surface is not None and not rows.surface.ticked
    assert [r.token for r in rows.others] == [
        selection.CLAUDE_ARTIFACT_TOKEN,
        *selection.PR_SESSIONS_TOKENS,
        "harness-claude",
        "harness-codex",
        "model-opus",
        "model-sonnet",
        "effort-low",
        "effort-high",
    ]
    for node in ordered:
        if node.skippable and not node.opt_in:
            assert f"\n- [x] {node.id}\n" in body, node.id


def test_only_the_protected_phases_read_as_always_runs():
    """R3.2 — the Slack mirror reads a bare one-token bullet as a protected phase,
    so the new text must carry none of its own."""
    graph = compile_graph(copy.deepcopy(SELECT_GRAPH))
    protected = [
        n.id
        for n in graph.ordered()
        if not n.skippable and not n.terminal and n.id != "phase-selection"
    ]
    assert protected  # the fixture protects something, or this proves nothing
    body = _body(graph=graph)
    rows = selection_rows(body)
    assert rows is not None
    assert list(rows.always) == protected
    # collapsed, because they are not choices — and said how many
    summary = next(s for s, inner in _details(body) if f"- {protected[0]}" in inner)
    assert f"{len(protected)} more phases always run" in summary
    # the shipped loop protects nothing, and its mirror reads no stray bullet
    shipped = selection_rows(_body())
    assert shipped is not None and shipped.always == ()


def test_the_comment_still_ends_with_the_marker_and_the_stamp():
    body = _body()
    assert selection.SELECTION_MARKER in body
    assert body.index("Ready?") < body.index(selection.SELECTION_MARKER)
    assert SELF_COMMENT_MARKER in body


def test_no_graph_means_no_empty_phases_heading():
    """With nothing truthful to offer, the gate just asks for the keyword."""
    ctx = HookContext(
        work_item=WorkItem(ref="github:o/r#7", id="issue-7", spec_dir=Path(".")),
        node={"id": "phase-selection"},
        boundary="entry",
        repo=Path("."),
        config={"authorizedUsers": ["owner"]},
        graph=None,
    )
    body = selection._checklist_body(ctx)
    assert "Phases — ticked ones run" not in body
    assert "Reply `the-loop execute`" in body
