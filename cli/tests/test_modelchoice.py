"""Unit tests for the model/effort vocabulary (issue-358).

Pure pieces only: what the operator declared, how a declaration becomes argv, and
the merge order. Whether a harness can actually *run* a name is
:mod:`the_loop.modelprobe`'s question, and the dispatcher's wiring lives in
``test_dispatcher_choice.py``.
"""

import pytest

from the_loop.harness import ClaudeCodeAdapter, CursorAgentAdapter
from the_loop.modelchoice import (
    EFFORT_LEVELS,
    config_findings,
    harness_args,
    candidate_harnesses,
    declared_effort,
    declared_models,
    effective_args,
    effort_args,
    model_args,
)


# -- declared_models ------------------------------------------------------------


def test_a_bare_name_is_a_model():
    config = {"models": ["opus-5", "fable-5.1"]}
    assert declared_models(config) == ["opus-5", "fable-5.1"]


def test_a_mapping_entry_carries_the_name():
    config = {"models": [{"name": "gpt-5.6-sol", "harnesses": ["cursor"]}]}
    assert declared_models(config) == ["gpt-5.6-sol"]


def test_declaration_order_is_kept_and_duplicates_collapse():
    config = {"models": ["opus-5", "fable-5.1", "opus-5"]}
    assert declared_models(config) == ["opus-5", "fable-5.1"]


@pytest.mark.parametrize(
    "entry",
    [
        "--dangerously-skip-permissions",  # a flag is not a name
        "../../etc/passwd",  # nor a path
        "opus 5; rm -rf /",  # nor a shell fragment
        "",
        {"harnesses": ["claude"]},  # a mapping with no name
        {"name": 5},
        None,
        [],
    ],
)
def test_a_malformed_entry_contributes_nothing(entry):
    """Fail-closed in the shrinking direction: a fault can only remove a choice."""
    assert declared_models({"models": [entry, "opus-5"]}) == ["opus-5"]


def test_no_section_declares_no_models():
    assert declared_models({}) == []
    assert declared_models({"models": None}) == []
    assert declared_models({"models": "opus-5"}) == []


# -- candidate_harnesses --------------------------------------------------------


def test_a_bare_name_is_a_candidate_for_every_declared_harness():
    config = {
        "harnesses": [{"name": "claude"}, {"name": "cursor"}],
        "models": ["opus-5"],
    }
    assert candidate_harnesses(config, "opus-5") == ["claude", "cursor"]


def test_a_declared_link_narrows_the_candidates():
    config = {
        "harnesses": [{"name": "claude"}, {"name": "cursor"}],
        "models": [{"name": "gpt-5.6-sol", "harnesses": ["cursor"]}],
    }
    assert candidate_harnesses(config, "gpt-5.6-sol") == ["cursor"]


def test_a_link_to_an_undeclared_harness_contributes_nothing():
    """A fault may only ever shrink the offered set, never widen it (R2.4)."""
    config = {
        "harnesses": [{"name": "claude"}],
        "models": [{"name": "gpt-5.6-sol", "harnesses": ["cursor", "claude"]}],
    }
    assert candidate_harnesses(config, "gpt-5.6-sol") == ["claude"]


def test_an_undeclared_model_has_no_candidates():
    config = {"harnesses": [{"name": "claude"}], "models": ["opus-5"]}
    assert candidate_harnesses(config, "sonnet-9") == []


# -- declared_effort ------------------------------------------------------------


def test_effort_is_the_loops_own_enum():
    assert EFFORT_LEVELS == ("low", "medium", "high")


def test_declared_effort_keeps_enum_order_not_declaration_order():
    """One vocabulary, rendered the same way whatever order it was written in."""
    assert declared_effort({"effort": ["high", "low"]}) == ["low", "high"]


def test_a_level_outside_the_enum_contributes_nothing():
    assert declared_effort({"effort": ["low", "ludicrous", 7, None]}) == ["low"]


# -- model_args / effort_args ---------------------------------------------------


def test_a_model_resolves_through_the_adapters_flag():
    assert model_args("fable-5.1", ClaudeCodeAdapter()) == ("--model", "fable-5.1")
    assert model_args("gpt-5.6-sol", CursorAgentAdapter()) == ("-m", "gpt-5.6-sol")


def test_a_harness_with_no_model_flag_resolves_a_model_to_nothing():
    class Flagless(ClaudeCodeAdapter):
        model_flag = ""

    assert model_args("fable-5.1", Flagless()) == ()


def test_effort_resolves_through_the_adapter_and_is_empty_where_unexpressible():
    """No adapter the-loop ships has an effort flag today, and a spec does not
    invent one — the mapping is filled in from each CLI's own --help and probed."""
    assert ClaudeCodeAdapter().effort_args("high") == ()
    assert CursorAgentAdapter().effort_args("high") == ()


def test_an_adapter_that_grows_an_effort_mapping_is_used():
    class Thoughtful(ClaudeCodeAdapter):
        _EFFORT_ARGS = {"high": ("--think", "hard")}

    assert effort_args("high", Thoughtful()) == ("--think", "hard")
    assert effort_args("low", Thoughtful()) == ()
    assert effort_args("ludicrous", Thoughtful()) == ()


# -- effective_args -------------------------------------------------------------


def test_the_merge_order_is_base_then_model_then_effort():
    merged = effective_args(
        ["--dangerously-skip-permissions"],
        ("--model", "fable-5.1"),
        ("--think", "hard"),
    )
    assert merged == [
        "--dangerously-skip-permissions",
        "--model",
        "fable-5.1",
        "--think",
        "hard",
    ]


def test_an_absent_choice_contributes_nothing():
    assert effective_args(["--x"], (), None) == ["--x"]
    assert effective_args([]) == []


def test_the_operators_own_arguments_are_never_rewritten():
    base = ["--dangerously-skip-permissions", "--model", "opus-5"]
    merged = effective_args(base, ("--model", "fable-5.1"))
    assert merged[: len(base)] == base


# -- config_findings ------------------------------------------------------------


def _adapters():
    return {"claude": ClaudeCodeAdapter(), "cursor": CursorAgentAdapter()}


def test_a_clean_config_has_nothing_to_say():
    config = {
        "harnesses": [{"name": "claude", "default": True}],
        "models": ["opus-5"],
        "effort": ["high"],
    }
    assert config_findings(config, _adapters()) == []


def test_two_default_harnesses_is_an_error():
    config = {
        "harnesses": [
            {"name": "claude", "default": True},
            {"name": "cursor", "default": True},
        ]
    }
    findings = config_findings(config, _adapters())
    assert [f.level for f in findings] == ["error"]


def test_a_narrowing_to_an_undeclared_harness_warns():
    config = {
        "harnesses": [{"name": "claude"}],
        "models": [{"name": "gpt-5.6-sol", "harnesses": ["cursor"]}],
    }
    findings = config_findings(config, _adapters())
    assert any("not a declared harness" in f.message for f in findings)


def test_a_harness_with_no_adapter_warns():
    findings = config_findings({"harnesses": [{"name": "codex"}]}, _adapters())
    assert any("no adapter" in f.message for f in findings)


def test_a_duplicated_model_flag_warns_rather_than_rewriting_it():
    """R3.4 — the-loop never edits the operator's own arguments, so it says so instead."""
    config = {
        "harnesses": [{"name": "claude", "args": ["--model", "opus-5"]}],
        "models": ["fable-5.1"],
    }
    findings = config_findings(config, _adapters())
    assert any("APPENDED" in f.message for f in findings)


def test_the_deprecated_routing_args_are_still_read():
    config = {"harnesses": [{"name": "claude"}]}
    assert harness_args(config, "claude", ["--dangerously-skip-permissions"]) == [
        "--dangerously-skip-permissions"
    ]


def test_harnesses_args_wins_over_the_deprecated_key():
    config = {"harnesses": [{"name": "claude", "args": ["--new"]}]}
    assert harness_args(config, "claude", ["--old"]) == ["--new"]
