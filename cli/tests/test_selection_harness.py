"""The harness section of the phase-selection gate (issue-440).

Feature: a work item picks the harness it runs on at the same gate, and by the same
signed reply, as its model and effort.

A reply can only pick a **key into the harnesses the operator declared that this build
can host a session on**; the model and effort it ticks are then kept only if that
harness can run them. Everything else resolves to the default harness.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks import selection
from the_loop.graph.state import WorkItemState
from the_loop.harness import (
    ClaudeCodeAdapter,
    CursorAgentAdapter,
    HarnessAdapter,
    hosting_harnesses,
    hosts_sessions,
)
from the_loop.modelchoice import config_findings, default_harness, offered_harnesses

# -- which harnesses can be offered (T1) -----------------------------------------


def test_only_an_adapter_that_implements_hosting_hosts():
    """R1.2: derived from the method, so an adapter cannot claim it."""
    assert hosts_sessions(ClaudeCodeAdapter) is True
    assert hosts_sessions(ClaudeCodeAdapter()) is True
    assert hosts_sessions(CursorAgentAdapter) is False
    assert hosts_sessions(HarnessAdapter) is False
    assert hosts_sessions(object()) is False
    assert hosting_harnesses() == ["claude"]


def test_offered_harnesses_are_declared_and_hosting_in_declaration_order():
    config = {"harnesses": ["pi", {"name": "claude"}, "cursor", "codex"]}
    hosts = {"claude", "codex", "pi"}.__contains__
    assert offered_harnesses(config, hosts) == ["pi", "claude", "codex"]
    assert offered_harnesses({}, hosts) == []


@pytest.mark.parametrize(
    "harnesses, expected",
    [
        ([{"name": "codex", "default": True}, "claude"], "codex"),
        # A default that cannot host is not obeyed (R4.2).
        ([{"name": "cursor", "default": True}, "claude"], "claude"),
        (["codex", "claude"], "claude"),  # no `default: true` → routing's
        ([], "claude"),
    ],
)
def test_the_default_is_one_rule(harnesses, expected):
    """R4.1: the flagged entry when it can host, else `routing.defaultHarness`."""
    hosts = {"claude", "codex"}.__contains__
    assert default_harness({"harnesses": harnesses}, "claude", hosts) == expected


def test_a_non_hosting_default_is_reported():
    config = {"harnesses": [{"name": "cursor", "default": True}, "claude"]}
    adapters = {"claude": ClaudeCodeAdapter(), "cursor": CursorAgentAdapter()}
    findings = config_findings(config, adapters)
    assert any(
        f.where == "harnesses[cursor].default" and f.level == "warning"
        for f in findings
    )


def test_bootstrap_seeds_the_gate_with_the_daemons_rule(tmp_path, monkeypatch):
    """R4.1: the gate's default and offered list come from the same resolvers."""
    from the_loop.graph import bootstrap

    monkeypatch.setattr(
        bootstrap,
        "load_cli_config_best_effort",
        lambda: {
            "harnesses": [{"name": "cursor", "default": True}, "claude"],
            "routing": {"defaultHarness": "claude"},
        },
    )
    config = bootstrap.build_runtime(tmp_path).config
    assert config["harness"] == "claude"  # cursor cannot host, so not the default
    assert config["offeredHarnesses"] == ["claude"]


# -- what the checklist says (T2) ------------------------------------------------


def _ctx(boundary="entry", comments=None, **config):
    config.setdefault("harness", "claude")
    config.setdefault("authorizedUsers", ["owner"])
    return HookContext(
        work_item=WorkItem(
            ref="github:octo/repo#440", id="issue-440", spec_dir=Path(".")
        ),
        node={"id": "phase-selection"},
        boundary=boundary,
        repo=Path("."),
        config=config,
        event={"comments": comments or []},
    )


def _declared(**over):
    config = {
        "harnesses": [{"name": "claude", "default": True}, {"name": "codex"}],
        "offeredHarnesses": ["claude", "codex"],
        "models": [
            "opus-5",
            {"name": "gpt-5.6-sol", "harnesses": ["codex"]},
        ],
        "effort": ["high"],
    }
    config.update(over)
    return config


def test_the_harness_section_comes_first_with_one_row_per_harness():
    body = "\n".join(selection._choice_lines(_ctx(**_declared())))
    assert "- [ ] `harness-claude`" in body
    assert "- [ ] `harness-codex`" in body
    assert body.index("harness-claude") < body.index("model-opus-5")
    assert "runs on `claude`, this deployment's default" in body


@pytest.mark.parametrize("offered", [[], ["claude"]])
def test_one_harness_is_not_a_choice_and_changes_nothing(offered):
    """R1.3/R5.1: fewer than two offered harnesses leaves the checklist as it was."""
    with_key = _declared(offeredHarnesses=offered)
    without_key = {k: v for k, v in with_key.items() if k != "offeredHarnesses"}
    assert selection._harness_rows(_ctx(**with_key)) == []
    assert selection._choice_lines(_ctx(**with_key)) == selection._choice_lines(
        _ctx(**without_key)
    )


def test_models_are_offered_across_every_offered_harness():
    """R2.1: a codex-only model is offered once a codex session is possible."""
    ctx = _ctx(**_declared())
    assert selection._model_rows(ctx) == ["opus-5", "gpt-5.6-sol"]
    assert selection._model_rows(ctx, "claude") == ["opus-5"]
    # Without a harness section, only the default's column counts, as before.
    assert selection._model_rows(_ctx(**_declared(offeredHarnesses=[]))) == ["opus-5"]


def test_an_unrenderable_name_is_never_offered():
    ctx = _ctx(**_declared(offeredHarnesses=["claude", "../bin/sh", "codex"]))
    assert selection._harness_rows(ctx) == ["claude", "codex"]


# -- what a reply means (T3, T4) -------------------------------------------------


class _Integration:
    def __init__(self):
        self.posted = []

    def call(self, verb, **kw):
        self.posted.append((verb, kw))
        return {}


def _classify(monkeypatch, body, author="owner", **config):
    integration = _Integration()
    monkeypatch.setattr(selection, "_resolve", lambda ctx: integration)
    ctx = _ctx(
        boundary="exit",
        comments=[{"author": author, "body": body}],
        **_declared(**config),
    )
    result = selection.classify_phase_selection(ctx)
    confirmation = next(
        (kw["body"] for verb, kw in integration.posted if verb == "add-comment"), ""
    )
    return result, confirmation


def test_an_authorized_reply_freezes_the_harness_with_its_model(monkeypatch):
    """
    Feature: a work item picks its harness
      Scenario: harness and model ticked together
        Given claude and codex are offered and gpt-5.6-sol is codex-only
        When an authorized user ticks harness-codex and model-gpt-5.6-sol and
             replies `the-loop execute`
        Then the harness, the model and the effort are frozen and named back

    Requirement: docs/specs/issue-440/requirements.md R1.4-R1.6, R2.2
    """
    result, confirmation = _classify(
        monkeypatch,
        "- [x] `harness-codex`\n- [x] `model-gpt-5.6-sol`\n- [x] `effort-high`\n"
        "the-loop execute",
    )
    assert result.status == "pass"
    assert result.data["harness"] == "codex"
    assert result.data["model"] == "gpt-5.6-sol"
    assert result.data["effort"] == "high"
    assert result.data["frozenGraph"]["harness"] == "codex"
    assert "Harness: **`codex`**." in confirmation


def test_a_model_the_chosen_harness_cannot_run_is_dropped_and_named(monkeypatch):
    """R2.3: the pair is checked, and the human is told which half did not apply."""
    result, confirmation = _classify(
        monkeypatch, "- [x] `model-gpt-5.6-sol`\n- [x] `effort-high`\nthe-loop execute"
    )
    assert result.data["harness"] == ""
    assert result.data["model"] == ""
    assert result.data["effort"] == "high"  # the other section survives
    assert "Harness: **`claude`**, this deployment's default" in confirmation
    assert "Not applied: model `gpt-5.6-sol`" in confirmation


@pytest.mark.parametrize(
    "rows",
    [
        "- [ ] `harness-codex`",  # none ticked
        "- [x] `harness-codex`\n- [x] `harness-claude`",  # two ticked
        "- [x] `harness-cursor`",  # declared, cannot host, not offered
        "- [x] `harness-sh`",  # undeclared
        "- [x] `harness-/bin/sh`",  # a path
        "- [x] `harness---dangerously-skip-permissions`",  # a flag
    ],
)
def test_abuse_anything_but_one_offered_tick_is_no_choice(monkeypatch, rows):
    """Abuse case 2: a reply names a key into the offered set, or nothing."""
    result, _ = _classify(monkeypatch, rows + "\nthe-loop execute")
    assert result.status == "pass"
    assert result.data["harness"] == ""


def test_abuse_an_unauthorized_reply_freezes_no_harness(monkeypatch):
    """Abuse case 1."""
    monkeypatch.setattr(
        selection, "_resolve", lambda ctx: pytest.fail("must not reach GitHub")
    )
    ctx = _ctx(
        boundary="exit",
        comments=[
            {"author": "stranger", "body": "- [x] `harness-codex`\nthe-loop execute"}
        ],
        **_declared(),
    )
    result = selection.classify_phase_selection(ctx)
    assert result.status == "wait"
    assert "harness" not in (result.data or {})


def test_a_harness_row_is_never_read_as_a_phase():
    skips, opt_ins, refused = selection._parse_selection(
        "- [ ] `harness-codex`\n- [ ] `design`", ["design"], [], ["phase-selection"]
    )
    assert skips == ["design"] and refused == [] and opt_ins == []


# -- the frozen record (T5) ------------------------------------------------------


def test_the_harness_round_trips_through_the_state_file(tmp_path):
    state = WorkItemState(work_item="issue-440")
    state.harness = "codex"
    state.save(tmp_path)
    assert WorkItemState.load(tmp_path, "issue-440").harness == "codex"


def test_a_state_file_from_before_reads_as_no_choice(tmp_path):
    """R5.2."""
    state = WorkItemState(work_item="issue-440")
    path = state.save(tmp_path)
    text = path.read_text().replace('  "harness": "",\n', "")
    assert '"harness"' not in text
    path.write_text(text)
    assert WorkItemState.load(tmp_path, "issue-440").harness == ""


def test_the_union_keeps_the_declared_order(tmp_path):
    """R2.1: a row's position does not depend on which harness offered it first."""
    import time

    from the_loop.modelprobe import REFUSED, Verdict, VerdictCache

    path = tmp_path / "verdicts.json"
    cache = VerdictCache(str(path))
    cache.put(Verdict("claude", "effort", "low", "", REFUSED, time.time()))
    cache.put(Verdict("claude", "model", "opus-5", "", REFUSED, time.time()))
    ctx = _ctx(
        **_declared(
            models=["gpt-5.6-sol", "opus-5"],
            effort=["high", "low"],
            verdictCache=str(path),
        )
    )
    # claude offers [gpt-5.6-sol] and [high]; codex everything.
    assert selection._model_rows(ctx) == ["gpt-5.6-sol", "opus-5"]
    assert selection._effort_rows(ctx) == ["low", "high"]  # the loop's enum order
    assert selection._effort_rows(ctx, "claude") == ["high"]
