"""The ticket's exact symptom, end to end through the shipped seams (issue-194).

    the-loop graph advance 194        (no --ref)
        → build_runtime reads ticketing.github from the repository
        → Runtime.work_item derives github:octo/repo#194
        → the entry chain's post-phase-selection reaches THAT ref
        → and when it cannot, the command says so on stdout

Every scenario walks a real ``Runtime`` over a real compiled graph, with only
``the_loop.graph.integrations.resolve`` replaced — the same seam
``test_graph_skips.py`` uses. No network, no credentials, no ``gh`` binary: a
test here that reached GitHub would be a test that fails in CI.

Two of these drive :class:`GraphCommand` itself and assert on captured stdout,
because "the command printed a clean answer" is half of what the ticket
reported, and a test on the runtime alone would not have caught it.
"""

from __future__ import annotations

import argparse
import copy

import pytest

from the_loop import eventlog
from the_loop.commands.graph_cmd import GraphCommand
from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.bootstrap import build_runtime
from the_loop.graph.integrations.base import IntegrationError
from the_loop.graph.model import compile_graph
from the_loop.graph.runtime import Runtime, declare_skips, force
from the_loop.graph.state import GraphState

WORK_ITEM = "issue-194"
DERIVED = "github:octo/repo#194"

#: A miniature of the shipped shape: a human selection gate whose entry chain
#: posts to GitHub, then one skippable node to route to.
GRAPH = {
    "start": "phase-selection",
    "nodes": [
        {
            "id": "phase-selection",
            "phase": "phase-selection",
            "actor": "human",
            "required": True,
            "entry": ["set-phase-label", "post-phase-selection"],
            "exit": ["classify-phase-selection"],
        },
        {
            "id": "requirements",
            "phase": "requirements-definition",
            "skippable": True,
            "produces": ["requirements.md"],
            "entry": ["set-phase-label"],
            "exit": [],
        },
        {"id": "done", "terminal": True},
    ],
    "edges": [
        {"from": "phase-selection", "to": "requirements", "on": "selected"},
        {"from": "requirements", "to": "done", "on": "pass"},
        {"from": "requirements", "to": "done", "on": "skipped"},
    ],
}


class _FakeGitHub:
    """Records what the-loop sends, and where it sent it.

    A failing provider raises :class:`IntegrationError`, which is what every
    real transport raises — the hooks' ``except`` clauses are written to that
    type, so a fake raising anything else would test a path production never
    takes.
    """

    def __init__(self, fail: str = ""):
        self.fail = fail
        self.calls: list[tuple[str, str]] = []  # (op, ref)
        self.posted: list[str] = []

    def call(self, op, **params):
        ref = str(params.get("ref") or "")
        if self.fail:
            raise IntegrationError(self.fail)
        self.calls.append((op, ref))
        if op == "list-comments":
            return {"comments": []}
        if op == "add-comment":
            self.posted.append(str(params.get("body") or ""))
        return {}


@pytest.fixture()
def github(monkeypatch):
    provider = _FakeGitHub()
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve", lambda target, config: provider
    )
    return provider


def _repo(tmp_path, ticketing: str = "octo/repo"):
    """A checkout whose harness config declares (or does not declare) its ticketing."""
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    (tmp_path / ".the-loop").mkdir()
    owner, _, name = ticketing.partition("/")
    config = "workflow:\n  specDir: docs/specs\n"
    if ticketing:
        config += f"ticketing:\n  github:\n    owner: {owner}\n    repo: {name}\n"
    (tmp_path / ".the-loop" / "harness-config.yaml").write_text(
        config, encoding="utf-8"
    )
    return tmp_path


def _runtime(repo, **config):
    return Runtime(
        repo,
        graph=compile_graph(copy.deepcopy(GRAPH)),
        config={
            "originRepo": build_runtime(repo).config["originRepo"],
            "authorizedUsers": ["@owner"],
            **config,
        },
    )


def _spec_dir(repo):
    return repo / "docs" / "specs" / WORK_ITEM


def _args(action, **kwargs):
    return argparse.Namespace(action=action, pr=None, pr_repo="", **kwargs)


# -- the ticket's headline: a verb with no --ref reaches the right ticket -------


def test_a_verb_with_no_ref_posts_to_the_repository_the_config_declares(
    tmp_path, github
):
    """
    Feature: outbound graph hooks reach the ticket
      Scenario: a graph verb with no --ref posts to the repository the config declares
        Given a work item issue-194 in a repo whose harness config names octo/repo
        And no --ref is passed, exactly as the docs and the skill show the command
        When the work item enters the graph
        Then the phase-selection checklist is posted to github:octo/repo#194
        And the loop:phase-selection label is applied to the same ref

    Requirement: docs/specs/issue-194/bugfix.md R1.1
    """
    repo = _repo(tmp_path)
    _runtime(repo).start(WORK_ITEM)  # no ref — the pre-fix reproduction

    assert ("add-comment", DERIVED) in github.calls
    assert ("set-labels", DERIVED) in github.calls
    assert github.posted and "the-loop execute" in github.posted[0]


def test_an_explicit_ref_still_wins(tmp_path, github):
    """R1.2 — derivation never overrides what the caller said, including a ref
    in another repository entirely."""
    repo = _repo(tmp_path)
    _runtime(repo).start(WORK_ITEM, ref="github:other/place#7")

    assert {ref for _, ref in github.calls} == {"github:other/place#7"}


def test_a_repo_with_no_ticketing_config_derives_nothing(tmp_path, github):
    """
    Feature: outbound graph hooks reach the ticket
      Scenario: a repository with no ticketing config says what to do about it
        Given a repository whose harness config declares no ticketing.github
        When a graph verb runs with no --ref
        Then no ref is invented — the bare work-item id is used, as before
        And the integration error names both remedies

    Requirement: docs/specs/issue-194/bugfix.md R1.3, R3.1
    """
    repo = _repo(tmp_path, ticketing="")
    runtime = _runtime(repo)
    assert runtime.work_item(WORK_ITEM).ref == WORK_ITEM

    from the_loop.graph.integrations.github import _split_ref
    from the_loop.graph.integrations.base import IntegrationError

    with pytest.raises(IntegrationError, match="ticketing.github"):
        _split_ref(WORK_ITEM)


def test_an_inner_loop_derives_the_pull_requests_ref_not_the_work_items(tmp_path):
    """
    Feature: outbound graph hooks reach the ticket
      Scenario: a pull request's inner loop posts to the pull request
        Given a work item issue-194 in a repo whose harness config names octo/repo
        When a runtime is built for that work item's pull request 7 with no --ref
        Then the derived ref is the PULL REQUEST's, github:octo/repo#7
        And a pull request in another repository derives that repository's ref
        And nothing falls back to the work item's own ref

    Requirement: docs/specs/issue-194/bugfix.md R1.5
    """
    repo = _repo(tmp_path)
    assert build_runtime(repo).work_item(WORK_ITEM).ref == DERIVED  # outer: the ticket
    inner = build_runtime(repo, pr_number=7)
    assert inner.work_item(WORK_ITEM).ref == "github:octo/repo#7"
    foreign = build_runtime(repo, pr_number=7, pr_repo="octo/infra")
    assert foreign.work_item(WORK_ITEM).ref == "github:octo/infra#7"
    # …and an explicit ref still wins here too.
    assert inner.work_item(WORK_ITEM, ref="github:o/r#1").ref == "github:o/r#1"


def test_an_inner_loop_never_falls_back_to_the_work_items_ref(tmp_path):
    """The failure mode this guards: a repository whose config names no
    ticketing leaves the PR ref underivable, and the loop must then use the bare
    id — NOT the work item's ref, which would put a pull request's review
    comments on the ticket."""
    repo = _repo(tmp_path, ticketing="")
    assert build_runtime(repo, pr_number=7).work_item(WORK_ITEM).ref == WORK_ITEM


# -- the other half: a failure that used to be silent --------------------------


def test_a_failing_hook_is_reported_without_changing_the_edge(tmp_path, monkeypatch):
    """
    Feature: best-effort hooks are best-effort, not silent
      Scenario: an outbound hook that fails reports on stdout without changing the edge
        Given every GitHub call fails
        When the work item enters the graph and then advances
        Then the node's status, outcome and the pointer are exactly what they were
        And the report carries one warning line per hook that did not complete
        And a warning-level graph.hook_degraded event is recorded for each

    Requirement: docs/specs/issue-194/bugfix.md R2.1, R2.3, R2.4
    """
    repo = _repo(tmp_path)
    eventlog.configure(source="test", path=str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve",
        lambda target, config: _FakeGitHub(fail="github is down"),
    )
    runtime = _runtime(repo)

    started = runtime.start(WORK_ITEM)
    assert started is not None and started.status == "pass"  # R2.4: unchanged
    assert [m for m in started.messages if "set-phase-label" in m]
    assert [m for m in started.messages if "post-phase-selection" in m]
    assert all(m.startswith("warning: ") for m in started.messages)
    assert "github is down" in started.messages[0]

    report = runtime.advance(WORK_ITEM)
    assert report.status == "wait"  # R2.4: the gate still waits, as it must
    assert GraphState.load(_spec_dir(repo), WORK_ITEM).current_node == "phase-selection"

    records = (tmp_path / "events.jsonl").read_text().splitlines()
    degraded = [r for r in records if '"graph.hook_degraded"' in r]
    assert len(degraded) >= 2
    assert all('"warning"' in r for r in degraded)
    assert any('"post-phase-selection"' in r for r in degraded)


def test_a_healthy_run_reports_no_warnings(tmp_path, github):
    """The line only appears when something is actually wrong — a warning that
    shows up on every healthy run is one operators learn to skip."""
    repo = _repo(tmp_path)
    report = _runtime(repo).start(WORK_ITEM)
    assert report is not None and report.messages == []


def test_an_idempotent_re_entry_is_not_reported_as_a_failure(
    tmp_path, github, monkeypatch
):
    """`post-phase-selection` finding its own marker returns posted=False with a
    reason and NO error, so nothing is reported. That is idempotency working —
    reporting it would train operators to skip the warning line."""
    repo = _repo(tmp_path)
    runtime = _runtime(repo)
    runtime.start(WORK_ITEM)
    already = _FakeGitHub()
    already.call = lambda op, **params: (  # type: ignore[method-assign]
        {"comments": [{"author": "@bot", "body": github.posted[0]}]}
        if op == "list-comments"
        else pytest.fail(f"a second checklist was attempted via {op!r}")
    )
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve", lambda target, config: already
    )

    from the_loop.graph.contract import HookContext, WorkItem
    from the_loop.graph.hooks.selection import post_phase_selection

    result = post_phase_selection(
        HookContext(
            work_item=WorkItem(ref=DERIVED, id=WORK_ITEM, spec_dir=_spec_dir(repo)),
            node={"id": "phase-selection"},
            boundary="entry",
            repo=repo,
        )
    )
    assert result.data == {"posted": False, "reason": "already asked"}


# -- the audit comments the two operator verbs post ----------------------------


def test_a_force_whose_audit_comment_fails_says_so(tmp_path, monkeypatch):
    """R2.5 — the force takes effect either way, but the operator is told its
    paper trail did not reach the ticket."""
    repo = _repo(tmp_path)
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve",
        lambda target, config: _FakeGitHub(fail="github is down"),
    )
    result = force(
        _runtime(repo), WORK_ITEM, "requirements", reason="unblocking", actor="@owner"
    )
    assert GraphState.load(_spec_dir(repo), WORK_ITEM).current_node == "requirements"
    assert any("could not post the audit comment" in w for w in result.warnings)


def test_a_skip_whose_audit_comment_fails_says_so(tmp_path, monkeypatch):
    """R2.6 — same posture for the skip verb, whose result had nowhere to say it."""
    repo = _repo(tmp_path)
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve",
        lambda target, config: _FakeGitHub(fail="github is down"),
    )
    result = declare_skips(
        _runtime(repo), WORK_ITEM, ["requirements"], reason="docs-only", actor="@owner"
    )
    assert result.declared == ["requirements"]  # the declaration still stands
    assert any("could not post the audit comment" in w for w in result.warnings)


# -- the CLI surface: what the operator actually sees ---------------------------


def test_cli_advance_prints_the_warning(tmp_path, monkeypatch, capsys):
    """
    Feature: best-effort hooks are best-effort, not silent
      Scenario: the advance verb prints what did not happen
        Given a work item whose phase-selection gate is already answered
        And every GitHub call fails
        When `the-loop graph advance issue-194` runs with no --ref
        Then stdout carries the transition AND a warning naming the hook
        And the exit code is unchanged — a degraded comment is not a failed verb

    Requirement: docs/specs/issue-194/bugfix.md R2.2
    """
    repo = _repo(tmp_path)
    # The SHIPPED graph, driven through the real command — no miniature here:
    # what the ticket reported is what `the-loop graph advance` prints.
    state = GraphState.load(_spec_dir(repo), WORK_ITEM)
    state.enter("phase-selection")
    state.decisions["phase-selection"] = {"at": "2026-08-10T00:00:00+00:00"}
    state.save(_spec_dir(repo))
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve",
        lambda target, config: _FakeGitHub(fail="github is down"),
    )
    code = GraphCommand().run(
        _args("advance", repo=str(repo), work_item=WORK_ITEM, ref="")
    )
    out = capsys.readouterr().out
    assert code == 0  # the edge was taken; only the label sync degraded
    assert "advanced to brainstorming" in out
    assert "warning: set-phase-label did not complete" in out
    assert "github is down" in out


def test_cli_skip_prints_the_warning(tmp_path, monkeypatch, capsys):
    """R2.6 at the surface the operator reads — same voice as `force`'s."""
    repo = _repo(tmp_path)
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve",
        lambda target, config: _FakeGitHub(fail="github is down"),
    )
    code = GraphCommand().run(
        _args(
            "skip",
            repo=str(repo),
            work_item=WORK_ITEM,
            nodes=["requirements-definition"],  # a node of the SHIPPED graph
            reason="docs-only",
            actor="@owner",
            ref="",
        )
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "declared: requirements-definition will be skipped" in out
    assert "WARNING: could not post the audit comment" in out
