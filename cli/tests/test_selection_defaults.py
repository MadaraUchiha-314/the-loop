"""The checklist's pre-ticked defaults (issue-510).

Feature: a work item whose author replies `the-loop execute` without touching a
box gets the owner's chosen defaults — the outer loop on a pull request, the spec
chain published as a Claude artifact, the deployment's default harness and model,
`medium` effort — and no brainstorm.
"""

from __future__ import annotations

import pytest

from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.model import load_graph
from the_loop.graph.runtime import Runtime
from the_loop.graph.state import WorkItemState

WORK_ITEM = "issue-1"
REF = "github:o/r#1"

CONFIG = {
    "authorizedUsers": ["@owner"],
    "harness": "claude",
    "harnesses": [
        {"name": "claude", "default": True, "defaultModel": "opus-5"},
        {"name": "codex"},
    ],
    "offeredHarnesses": ["claude", "codex"],
    "models": [{"name": "opus-5", "harnesses": ["claude"]}, "sonnet-5"],
    "effort": ["low", "medium", "high"],
}


class _FakeGitHub:
    """Keeps what the-loop posts as the ticket's comments, so the checklist's own
    tick state is what an untouched `the-loop execute` reads back."""

    def __init__(self):
        self.comments = []

    def call(self, op, **params):
        if op == "list-comments":
            return {"comments": list(self.comments)}
        if op == "add-comment":
            self.comments.append(
                {"author": "the-loop", "body": str(params.get("body") or "")}
            )
        return {}


@pytest.fixture()
def fake_github(monkeypatch):
    provider = _FakeGitHub()
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve", lambda target, config: provider
    )
    return provider


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    return tmp_path


def test_an_untouched_checklist_freezes_the_owners_defaults(repo, fake_github):
    """
    Scenario: the author replies without touching a box
      Given the shipped outer loop and a deployment offering two harnesses
      When the checklist is posted and `the-loop execute` is replied
      Then the outer loop is on a pull request, the Claude artifact is on,
        the harness, model and effort are the ticked defaults,
        and brainstorming and its approval are declared skipped
    """
    runtime = Runtime(repo, graph=load_graph(), config=dict(CONFIG))
    runtime.start(WORK_ITEM, ref=REF)
    checklist = fake_github.comments[0]["body"]
    for row in (
        "- [ ] brainstorming",
        "- [ ] brainstorm-approval",
        "- [x] requirements-definition",
        "- [x] `outer-loop-on-pull-request`",
        "- [x] `claude-artifact`",
        "- [x] `harness-claude`",
        "- [ ] `harness-codex`",
        "- [x] `model-opus-5`",
        "- [ ] `model-sonnet-5`",
        "- [x] `effort-medium`",
        "- [ ] `effort-high`",
    ):
        assert row in checklist, row

    fake_github.comments.append({"author": "@owner", "body": "the-loop execute"})
    runtime.advance(
        WORK_ITEM, ref=REF, event={"comments": list(fake_github.comments)}
    )
    state = WorkItemState.load(repo / "docs" / "specs" / WORK_ITEM, WORK_ITEM)
    assert state.surface == "pull-request"
    assert state.claude_artifact is True
    assert (state.harness, state.model, state.effort) == ("claude", "opus-5", "medium")
    assert {"brainstorming", "brainstorm-approval"} <= set(state.skips)
    assert "requirements-definition" not in state.skips


def test_a_default_not_on_offer_is_not_ticked(repo, fake_github):
    """An effort the operator does not offer has no row to tick, so the section
    falls back to the harness's own default, as before."""
    config = {**CONFIG, "effort": ["high"]}
    Runtime(repo, graph=load_graph(), config=config).start(WORK_ITEM, ref=REF)
    checklist = fake_github.comments[0]["body"]
    assert "- [ ] `effort-high`" in checklist
    assert "the harness's own default effort." in checklist
