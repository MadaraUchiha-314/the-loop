"""Commands of the operator's own, and arming commands they re-point (issue-343).

A new word is ``start`` with a loop attached; an overridden arming command is
itself with a loop attached. Everything here is the pure parse and the durable
record — the dispatcher's handling is ``test_custom_graph_integration.py``'s.

The negatives come first in spirit: comment text is untrusted, so a word the
operator did not declare must match nothing, and the loop a result carries must
come from the operator's bindings, never from the body.
"""

from __future__ import annotations

import pytest

from the_loop.control import (
    DO,
    REVIEW,
    START,
    STOP,
    ControlConfig,
    ControlStore,
    parse_command,
)
from the_loop.graph.model import GraphConfigError
from the_loop.sessions import WorkItemRef

NAME = "acme-triage-loop"
QUICK = "acme-quick-loop"
REF = "github:octo/repo#343"


def _config(**control) -> ControlConfig:
    return ControlConfig.from_mapping(
        control,
        graph={
            "graphs": [
                {"name": NAME, "path": "t.yaml", "commands": ["triage"]},
                {"name": QUICK, "path": "q.yaml", "commands": ["do", "review"]},
            ]
        },
    )


def test_bindings_and_declared_loops_reach_the_config():
    config = _config()
    assert config.bindings == {"triage": NAME, "do": QUICK, "review": QUICK}
    assert config.loops == (NAME, QUICK)
    assert config.custom_commands == ("triage",)
    assert config.keyword("triage") == "the-loop triage"


def test_no_graph_block_is_exactly_the_shipped_vocabulary():
    config = ControlConfig.from_mapping({})
    assert config.bindings == {} and config.loops == ()
    assert parse_command("the-loop do", config).loop == ""


def test_a_new_word_parses_as_start_onto_its_loop():
    """R3.4, R3.5"""
    result = parse_command("please the-loop triage this", _config())
    assert result.command == START
    assert result.loop == NAME
    assert result.matched == ["triage"]


@pytest.mark.parametrize("command", [DO, REVIEW])
def test_an_overridden_arming_command_keeps_its_command_and_gains_a_loop(command):
    """R3.6, R3.7 — `review` stays `review`, so its PR binding still applies."""
    result = parse_command(f"the-loop {command}", _config())
    assert result.command == command
    assert result.loop == QUICK


def test_an_unbound_arming_command_selects_what_it_always_did():
    result = parse_command("the-loop start", _config())
    assert result.command == START and result.loop == ""


def test_a_non_arming_command_never_carries_a_loop():
    assert parse_command("the-loop stop", _config()).loop == ""
    assert parse_command("the-loop stop", _config()).command == STOP


def test_undeclared_word_is_no_command():
    """Abuse case 2 — a keyword-shaped word nobody declared matches nothing."""
    assert not parse_command("the-loop triage", ControlConfig())
    assert not parse_command("the-loop deploy", _config())


@pytest.mark.parametrize(
    "body", ["the-loop triaged", "the-loop triage-now", "xthe-loop triage"]
)
def test_a_new_word_obeys_the_whole_token_boundary(body):
    """R3.4"""
    assert not parse_command(body, _config())


def test_custom_and_builtin_command_is_ambiguous():
    """Abuse case 4 — two different commands: refuse, execute nothing."""
    result = parse_command("the-loop triage\nthe-loop stop", _config())
    assert result.ambiguous and result.command is None
    assert set(result.matched) == {"triage", "stop"}


def test_a_new_word_matches_case_insensitively():
    assert parse_command("The-Loop TRIAGE", _config()).loop == NAME


def test_a_new_keyword_that_clashes_with_a_configured_one_is_refused():
    """Two commands on one keyword would make every such comment ambiguous."""
    with pytest.raises(GraphConfigError, match="already uses"):
        ControlConfig.from_mapping(
            {"keywords": {"start": "the-loop triage"}},
            graph={"graphs": [{"name": NAME, "path": "t", "commands": ["triage"]}]},
        )


def test_a_malformed_graph_block_fails_the_control_config():
    with pytest.raises(GraphConfigError):
        ControlConfig.from_mapping(
            {}, graph={"graphs": [{"name": NAME, "path": "t", "commands": ["stop"]}]}
        )


def test_the_control_record_carries_the_loop(tmp_path):
    """R3.5 — recorded, read back; an older record without it reads as ""."""
    store = ControlStore(tmp_path / "portable")
    ref = WorkItemRef.parse(REF)
    store.record(ref, START, actor="owner", loop=NAME)
    record = store.get(ref)
    assert record is not None and record.loop == NAME
    assert record.to_dict()["loop"] == NAME
    assert store.start_requested(ref)

    store.record(ref, START, actor="owner")
    record = store.get(ref)
    assert record is not None and record.loop == ""
    assert "loop" not in record.to_dict()
