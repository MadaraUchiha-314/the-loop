"""`graph status` / `check` read the state file the runtime wrote, and say which (issue-396).

The daemon roots a work item's runtime at the **session's checkout** and writes
``docs/specs/<id>/work-item-state.json`` there. Until issue-396 the CLI's read verbs
looked in the working directory only, took the positional as a spec id only, and
fell back to the graph's start node in silence when nothing was there — so
``graph status github:…#1`` from the daemon's config directory printed
"at phase-selection" for an item three nodes further on (B7/O6 of the 2026-09-19
e2e run).

Every scenario builds a real checkout under ``tmp_path`` with a real state file, a
real CLI config naming a registry directory, and a real registry record whose
``cwd`` is that checkout, then drives the real commands in-process. No network, no
subprocess.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pytest

from the_loop.commands.graph_cmd import CheckCommand, GraphCommand
from the_loop.sessions import Session, SessionRegistry, WorkItemRef

WORK_ITEM = "issue-1"
REF = "github:octo/repo#1"
NODE = "brainstorming"


def _checkout(root: Path, node: str = NODE) -> Path:
    """A checkout whose work item the daemon already advanced to ``node``."""
    spec_dir = root / "docs" / "specs" / WORK_ITEM
    spec_dir.mkdir(parents=True)
    (spec_dir / "work-item-state.json").write_text(
        json.dumps({"workItem": WORK_ITEM, "currentNode": node, "nodes": {}})
    )
    return root


def _registry(tmp_path: Path, monkeypatch, cwd: Path) -> Path:
    """A CLI config naming a registry directory, and one record pointing at ``cwd``."""
    registry_dir = tmp_path / "registry"
    config = tmp_path / "cli-config.yaml"
    config.write_text(f'version: "0.10.0"\nrouting:\n  registryDir: {registry_dir}\n')
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(config))
    SessionRegistry(registry_dir).register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(cwd),
        )
    )
    return registry_dir


@pytest.fixture
def elsewhere(tmp_path, monkeypatch) -> Path:
    """The daemon's config directory: not a checkout of anything."""
    config_dir = tmp_path / "daemon"
    config_dir.mkdir()
    monkeypatch.chdir(config_dir)
    return config_dir


def _status(work_item: str, repo: str = "") -> int:
    args = argparse.Namespace(
        repo=repo,
        spec_dir="",
        action="status",
        work_item=work_item,
        pr=None,
        pr_repo="",
    )
    return GraphCommand().run(args)


def _check(work_item: str = "", repo: str = "", fmt: str = "table", all_items=False):
    args = argparse.Namespace(
        repo=repo,
        spec_dir="",
        work_item=work_item or None,
        format=fmt,
        all=all_items,
        recompute=False,
        fail_on="unmet",
    )
    return CheckCommand().run(args)


def test_a_ref_from_the_daemons_config_directory_reports_the_runtimes_node(
    tmp_path, monkeypatch, elsewhere, capsys
):
    """
    Feature: `graph status` reads the state file the runtime wrote
      Scenario: graph status with a ref from the daemon's config directory
        Given a checkout whose work-item-state.json the daemon advanced to brainstorming
        And a session registry recording that checkout as the work item's cwd
        When the operator runs `graph status github:octo/repo#1` from the config directory
        Then the command reports brainstorming, not the graph's start node
        And prints the checkout it resolved and the state file it read

    Requirement: docs/specs/issue-396/bugfix.md R1.1, R1.2, R2.1
    """
    checkout = _checkout(tmp_path / "worktree")
    _registry(tmp_path, monkeypatch, checkout)

    _status(REF)

    out = capsys.readouterr().out
    assert f"{WORK_ITEM}: at {NODE}" in out
    assert "phase-selection" not in out.splitlines()[0]
    assert f"repo: {checkout.resolve()} (from the session registry)" in out
    state_file = checkout / "docs" / "specs" / WORK_ITEM / "work-item-state.json"
    assert f"state: {state_file.resolve()}" in out
    assert "not found" not in out


def test_a_bare_id_from_a_foreign_directory_says_what_it_could_not_find(
    tmp_path, monkeypatch, elsewhere, capsys
):
    """
    Feature: a wrong answer is diagnosable
      Scenario: graph status with a bare id from a foreign directory
        Given a directory holding no spec directory for the work item
        When the operator runs `graph status issue-1` there
        Then the command names the state file it looked for as not found
        And says the directory does not exist and how to point it at the checkout

    Requirement: docs/specs/issue-396/bugfix.md R2.1
    """
    _registry(tmp_path, monkeypatch, _checkout(tmp_path / "worktree"))

    _status(WORK_ITEM)

    out = capsys.readouterr().out
    looked_for = elsewhere / "docs" / "specs" / WORK_ITEM / "work-item-state.json"
    assert f"state: {looked_for.resolve()} (not found; " in out
    assert "does not exist" in out
    assert "--repo" in out
    assert "repo:" not in out


def test_an_explicit_repo_wins_over_the_registry(
    tmp_path, monkeypatch, elsewhere, capsys
):
    """
    Feature: `--repo` is the operator's word
      Scenario: --repo is given
        Given a registry record pointing at one checkout
        And a second checkout whose state sits at a different node
        When the operator runs `graph status <ref> --repo <second checkout>`
        Then the second checkout is reported and the registry is not consulted

    Requirement: docs/specs/issue-396/bugfix.md R1.3
    """
    _registry(tmp_path, monkeypatch, _checkout(tmp_path / "worktree"))
    other = _checkout(tmp_path / "other", node="requirements-definition")

    _status(REF, repo=str(other))

    out = capsys.readouterr().out
    assert f"{WORK_ITEM}: at requirements-definition" in out
    assert "from the session registry" not in out
    assert f"state: {other.resolve()}" in out


def test_inside_the_checkout_the_registry_is_not_consulted(
    tmp_path, monkeypatch, capsys
):
    """
    Feature: the working directory keeps its meaning
      Scenario: run from inside the checkout
        Given a checkout holding the work item, and a registry pointing elsewhere
        When the operator runs `graph status <ref>` from inside the checkout
        Then the checkout's own state file is read and no `repo:` line is printed

    Requirement: docs/specs/issue-396/bugfix.md R1.3
    """
    checkout = _checkout(tmp_path / "worktree")
    _registry(tmp_path, monkeypatch, _checkout(tmp_path / "stale", node="design"))
    monkeypatch.chdir(checkout)

    _status(REF)

    out = capsys.readouterr().out
    assert f"{WORK_ITEM}: at {NODE}" in out
    assert "repo:" not in out
    state_file = checkout / "docs" / "specs" / WORK_ITEM / "work-item-state.json"
    assert f"state: {state_file.resolve()}" in out


def test_a_cleaned_up_checkout_falls_through_to_the_working_directory(
    tmp_path, monkeypatch, elsewhere, capsys
):
    """A registry `cwd` that is no longer a directory is ignored (abuse/failure case).

    Requirement: docs/specs/issue-396/bugfix.md § Security considerations (fail-closed)
    """
    _registry(tmp_path, monkeypatch, tmp_path / "gone")

    _status(REF)

    out = capsys.readouterr().out
    assert "from the session registry" not in out
    assert "(not found; " in out and "does not exist" in out


def test_check_resolves_the_same_way_and_carries_the_fields(
    tmp_path, monkeypatch, elsewhere, capsys
):
    """
    Feature: `check` shares the read path
      Scenario: check with a ref from the daemon's config directory
        Given the same checkout and registry record
        When the operator runs `check github:octo/repo#1` there, as a table and as json
        Then the table names the checkout and the state file
        And the json carries statePath and stateFound

    Requirement: docs/specs/issue-396/bugfix.md R1.2, R2.1, R2.3
    """
    checkout = _checkout(tmp_path / "worktree")
    _registry(tmp_path, monkeypatch, checkout)
    state_file = (
        checkout / "docs" / "specs" / WORK_ITEM / "work-item-state.json"
    ).resolve()

    _check(REF)
    table = capsys.readouterr().out
    # UNMET, honestly: the fixture's state never passed phase-selection.
    assert f"{WORK_ITEM}: UNMET (at {NODE})" in table
    assert f"repo: {checkout.resolve()} (from the session registry)" in table
    assert f"state: {state_file}" in table

    _check(REF, fmt="json")
    report = json.loads(capsys.readouterr().out)
    assert report["workItem"] == WORK_ITEM
    assert report["statePath"] == str(state_file)
    assert report["stateFound"] is True


def test_check_all_prints_no_state_line(tmp_path, monkeypatch, capsys):
    """`check --all` is a drift summary; one line per item, as before (R2.3)."""
    checkout = _checkout(tmp_path / "worktree")
    monkeypatch.chdir(checkout)

    _check(all_items=True)

    out = capsys.readouterr().out
    assert f"{WORK_ITEM}: UNMET (at {NODE})" in out
    assert "state:" not in out


def test_a_mutating_verb_keeps_the_working_directory(
    tmp_path, monkeypatch, elsewhere, capsys
):
    """
    Feature: a write goes where the operator pointed
      Scenario: a mutating verb with a ref from a foreign directory
        Given a registry record pointing at a checkout with a live work item
        When the operator runs `graph complete <ref>` from the daemon's config directory
        Then the claim addresses the working directory, not the registry's checkout
        And is refused there, because that work item never entered the graph

    Requirement: docs/specs/issue-396/bugfix.md R1.4
    """
    checkout = _checkout(tmp_path / "worktree")
    _registry(tmp_path, monkeypatch, checkout)
    before = (
        checkout / "docs" / "specs" / WORK_ITEM / "work-item-state.json"
    ).read_text()

    args = argparse.Namespace(
        repo="",
        spec_dir="",
        action="complete",
        work_item=REF,
        node="",
        actor="",
        ref="",
        pr=None,
        pr_repo="",
    )
    GraphCommand().run(args)

    envelope = json.loads(capsys.readouterr().out)
    assert envelope["status"] == "refused"
    assert "not entered the graph" in " ".join(envelope["messages"])
    assert (
        checkout / "docs" / "specs" / WORK_ITEM / "work-item-state.json"
    ).read_text() == before
    # Nothing was written where the registry points; the claim landed on the
    # working directory (which the lock file's mkdir is allowed to create).
    assert not (
        Path(os.getcwd()) / "docs" / "specs" / WORK_ITEM / "work-item-state.json"
    ).exists()
