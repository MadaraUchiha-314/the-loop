"""Unit tests for instance identity and scope (issue-322).

The block (``InstanceConfig``), the address token (``parse_address``), the decision
(``decide``), the fan-out into ``RoutingConfig``, the record field, the marks a named
instance leaves (comment, announcement, tmux argv) and the control-plane document.

Spec: docs/specs/issue-322/design.md §1–§6.
"""

from __future__ import annotations

import logging

import pytest

from the_loop import cli_config
from the_loop.announce import announcement_body
from the_loop.control import ControlConfig, ControlRecord, ControlStore, command_comment
from the_loop.instance import (
    ADDRESSED,
    ADDRESSED_ELSEWHERE,
    AMBIGUOUS_ADDRESS,
    CLAIMABLE,
    IN_SCOPE,
    INSTANCE_LOCKED,
    LOCKED,
    OPEN,
    UNADDRESSED,
    Address,
    InstanceConfig,
    decide,
    parse_address,
)
from the_loop.runner import TmuxRunner
from the_loop.sessions import Session, WorkItemRef
from the_loop.webhook.dispatcher import RoutingConfig

REF = "github:octo/repo#15"


# -- the block --------------------------------------------------------------------


def test_the_block_unset_is_an_unnamed_open_instance():
    """R1.2: no block → 13.3.1."""
    config = InstanceConfig.from_mapping(None)
    assert config == InstanceConfig()
    assert config.name == "" and config.mode == OPEN and config.declared == ()


def test_the_block_reads_name_mode_and_declared_refs():
    config = InstanceConfig.from_mapping(
        {
            "name": "laptop-b",
            "scope": {
                "mode": "addressed",
                "workItems": [
                    "github:octo/repo#15",
                    "https://github.com/octo/repo/pull/16",
                    "https://ghe.corp.example/octo/repo/issues/17",
                ],
            },
        }
    )
    assert config.name == "laptop-b"
    assert config.mode == ADDRESSED
    assert config.declared == (
        "github:octo/repo#15",
        "github:octo/repo#16",
        "github:ghe.corp.example/octo/repo#17",
    )
    assert config.declares("github:octo/repo#16")
    assert not config.declares("github:octo/repo#99")


@pytest.mark.parametrize("bad", ["Laptop", "-x", "a b", "a/b", "x" * 41])
def test_the_block_refuses_a_name_outside_the_grammar(bad, caplog):
    """R1.4: a bad name is a warning and an unnamed instance."""
    with caplog.at_level(logging.WARNING, logger="the-loop.instance"):
        config = InstanceConfig.from_mapping({"name": bad})
    assert config.name == ""
    assert any("instance.name" in r.getMessage() for r in caplog.records)


def test_an_unknown_mode_resolves_to_locked(caplog):
    """A4 / R1.4: a scope typo narrows, never widens."""
    with caplog.at_level(logging.WARNING, logger="the-loop.instance"):
        config = InstanceConfig.from_mapping({"name": "a", "scope": {"mode": "opne"}})
    assert config.mode == LOCKED
    assert any("scope.mode" in r.getMessage() for r in caplog.records)


def test_the_block_addressed_without_a_name_is_locked(caplog):
    """R1.5: nothing can address an unnamed instance."""
    with caplog.at_level(logging.WARNING, logger="the-loop.instance"):
        config = InstanceConfig.from_mapping({"scope": {"mode": "addressed"}})
    assert config.mode == LOCKED


def test_the_block_skips_a_bad_declaration_by_index_and_keeps_the_rest(caplog):
    """R1.4: the value is not echoed; the position is."""
    with caplog.at_level(logging.WARNING, logger="the-loop.instance"):
        config = InstanceConfig.from_mapping(
            {"scope": {"workItems": ["github:octo/repo#1", "not a ref", 42]}}
        )
    assert config.declared == ("github:octo/repo#1",)
    messages = [r.getMessage() for r in caplog.records]
    assert any("[1]" in m for m in messages) and any("[2]" in m for m in messages)
    assert not any("not a ref" in m for m in messages)


def test_the_block_that_is_not_a_mapping_is_the_default(caplog):
    with caplog.at_level(logging.WARNING, logger="the-loop.instance"):
        assert InstanceConfig.from_mapping(["x"]) == InstanceConfig()  # type: ignore[arg-type]
    assert InstanceConfig.from_mapping({"scope": "locked"}).mode == OPEN  # type: ignore[dict-item]


# -- the token --------------------------------------------------------------------


@pytest.mark.parametrize(
    "body,expected",
    [
        ("the-loop start instance:laptop-b", "laptop-b"),
        ("the-loop start INSTANCE:laptop-b please", "laptop-b"),
        ("instance:a\nthe-loop start", "a"),
        ("(instance:box-2)", "box-2"),
        ("the-loop start instance:laptop-b instance:laptop-b", "laptop-b"),
        ("the-loop do instance:box fix the flaky test", "box"),
    ],
)
def test_the_token_is_read_as_a_whole_word_with_a_case_insensitive_prefix(
    body, expected
):
    """R3.1."""
    assert parse_address(body) == Address(name=expected, matched=(expected,))


@pytest.mark.parametrize(
    "body",
    [
        None,
        "",
        "the-loop start",
        "instance:",
        "instance:LAPTOP",
        "instance:../etc",
        "instance:-x",
        "instance:a/b",
        "myinstance:a",
        "http://instance:a",
        "instance: a",
    ],
)
def test_a_malformed_token_is_not_an_address_and_reaches_no_record(body):
    """A2 / R3.4: only a grammar-valid name is an address; nothing else is kept."""
    address = parse_address(body)
    assert address == Address()
    assert address.name == "" and not address.ambiguous and address.matched == ()


def test_the_token_with_a_word_after_it_reads_the_word_before_the_space():
    """`instance:a b` names `a`; what follows is prose."""
    assert parse_address("instance:a b").name == "a"


def test_two_different_addresses_are_ambiguous():
    """R3.3."""
    address = parse_address("the-loop start instance:a instance:b")
    assert address.ambiguous and address.name == ""
    assert address.matched == ("a", "b")
    assert bool(address)


# -- the decision -----------------------------------------------------------------

NAMED_OPEN = InstanceConfig(name="a", mode=OPEN)
NAMED_ADDRESSED = InstanceConfig(name="a", mode=ADDRESSED)
NAMED_LOCKED = InstanceConfig(name="a", mode=LOCKED)
UNNAMED = InstanceConfig()
TO_A = Address(name="a", matched=("a",))
TO_B = Address(name="b", matched=("b",))
NONE = Address()
AMBIGUOUS = Address(ambiguous=True, matched=("a", "b"))


@pytest.mark.parametrize(
    "config,address,managed,outcome",
    [
        # row 1: ambiguity refuses everything, managed or not
        (NAMED_OPEN, AMBIGUOUS, True, AMBIGUOUS_ADDRESS),
        (UNNAMED, AMBIGUOUS, False, AMBIGUOUS_ADDRESS),
        # row 2: an explicit address to another instance is authoritative (R3.2)
        (NAMED_OPEN, TO_B, True, ADDRESSED_ELSEWHERE),
        (UNNAMED, TO_A, True, ADDRESSED_ELSEWHERE),
        (NAMED_LOCKED, TO_B, True, ADDRESSED_ELSEWHERE),
        # row 3: managed is in scope in every mode (R2.1)
        (NAMED_OPEN, NONE, True, IN_SCOPE),
        (NAMED_ADDRESSED, NONE, True, IN_SCOPE),
        (NAMED_LOCKED, NONE, True, IN_SCOPE),
        (NAMED_LOCKED, TO_A, True, IN_SCOPE),
        (UNNAMED, NONE, True, IN_SCOPE),
        # row 4: open takes anything new (R2.2)
        (NAMED_OPEN, NONE, False, CLAIMABLE),
        (NAMED_OPEN, TO_A, False, CLAIMABLE),
        (UNNAMED, NONE, False, CLAIMABLE),
        # row 5: locked takes nothing new, addressed or not (R2.4)
        (NAMED_LOCKED, NONE, False, INSTANCE_LOCKED),
        (NAMED_LOCKED, TO_A, False, INSTANCE_LOCKED),
        # rows 6–7: addressed takes only what names it (R2.3)
        (NAMED_ADDRESSED, TO_A, False, CLAIMABLE),
        (NAMED_ADDRESSED, NONE, False, UNADDRESSED),
    ],
)
def test_decide_follows_the_table(config, address, managed, outcome):
    decision = decide(config, address, managed)
    assert decision.outcome == outcome
    assert decision.accepted == (outcome in (IN_SCOPE, CLAIMABLE))


def test_an_address_does_not_unlock_a_locked_instance():
    """A3: locked means locked — the config is the only door."""
    assert decide(NAMED_LOCKED, TO_A, False).outcome == INSTANCE_LOCKED


# -- the fan-out ------------------------------------------------------------------


def test_the_block_reaches_routing_config_through_the_loaded_config(tmp_path):
    """Design §2: one construction, the `_ghBinary` precedent."""
    path = tmp_path / "cli-config.yaml"
    path.write_text(
        "version: '0.9.0'\n"
        "instance:\n  name: laptop-b\n  scope:\n    mode: addressed\n"
        "    workItems: [github:octo/repo#15]\n"
        "routing:\n  enabled: true\n"
    )
    loaded = cli_config.load_cli_config(path)
    routing = RoutingConfig.from_mapping(loaded["routing"])
    assert routing.instance == InstanceConfig(
        name="laptop-b", mode=ADDRESSED, declared=("github:octo/repo#15",)
    )


def test_a_bare_routing_mapping_is_an_unnamed_open_instance():
    assert RoutingConfig.from_mapping({"enabled": True}).instance == InstanceConfig()


def test_a_config_without_routing_still_carries_the_block(tmp_path):
    path = tmp_path / "cli-config.yaml"
    path.write_text("version: '0.9.0'\ninstance:\n  name: solo\n")
    loaded = cli_config.load_cli_config(path)
    assert RoutingConfig.from_mapping(loaded["routing"]).instance.name == "solo"


# -- the record -------------------------------------------------------------------


def test_the_control_record_carries_the_instance_and_reads_old_records_as_unnamed(
    tmp_path,
):
    """R4.1."""
    store = ControlStore(tmp_path / "portable")
    store.record(REF, "start", source="comment", actor="octocat", instance="laptop-b")
    record = store.get(REF)
    assert record is not None and record.instance == "laptop-b"
    assert record.to_dict()["instance"] == "laptop-b"
    old = ControlRecord.from_dict({"ref": REF, "command": "start"})
    assert old.instance == ""
    store.record(REF, "stop")
    assert store.get(REF).instance == ""  # type: ignore[union-attr]


# -- the marks --------------------------------------------------------------------


def test_the_posted_keyword_carries_the_address():
    """R4.2."""
    body = command_comment("start", ControlConfig(), actor="me", address="laptop-b")
    assert body.splitlines()[0] == "the-loop start instance:laptop-b"
    plain = command_comment("start", ControlConfig(), actor="me")
    assert plain.splitlines()[0] == "the-loop start"
    granted = command_comment(
        "add-collaborator", ControlConfig(), subject="dana", address="laptop-b"
    )
    assert (
        granted.splitlines()[0] == "the-loop add-collaborator @dana instance:laptop-b"
    )


def _session():
    return Session(
        work_item=WorkItemRef.parse(REF),
        harness="claude",
        harness_session_id="sess-0",
        cwd="/tmp/x",
        status="active",
        tmux_target="loop-github-octo-repo-15",
    )


def test_the_announcement_names_the_instance():
    """R4.3."""
    named = announcement_body(_session(), instance="laptop-b")
    assert "| instance | `laptop-b` |" in named
    assert "instance" not in announcement_body(_session()).replace(
        "interactive session", ""
    )


class _Probe(TmuxRunner):
    def __init__(self, version="tmux 3.3a", instance=""):
        super().__init__(instance=instance)
        self.argv = []
        self._version = version

    def is_available(self):
        return True

    def _run(self, argv, timeout=None):
        from the_loop.runner import TmuxResult

        self.argv.append(list(argv))
        return TmuxResult(ok=True, output=self._version if argv == ["-V"] else "")

    def _clear_target(self, target, timeout, present=False):
        return None

    def _set_remain_on_exit(self, target, timeout):
        return None


class _Adapter:
    binary = "claude"
    name = "claude"

    def interactive_argv(self, prompt, session_id):
        return ["--session-id", session_id, prompt]

    def interactive_resume_argv(self, prompt, session_id):
        return ["--resume", session_id, prompt]


def _spawn(runner):
    return runner.spawn_in("loop-x", _Adapter(), "hi", cwd="/tmp", session_id="s")  # type: ignore[arg-type]


def test_a_named_instance_spawns_with_the_environment_variable():
    """R4.6."""
    runner = _Probe(instance="laptop-b")
    assert _spawn(runner).ok
    new_session = [a for a in runner.argv if a and a[0] == "new-session"][0]
    assert new_session[new_session.index("-e") + 1] == "THE_LOOP_INSTANCE=laptop-b"
    assert new_session.index("-e") < new_session.index("--")


def test_an_unnamed_instance_spawns_with_the_argv_it_used_before():
    runner = _Probe()
    assert _spawn(runner).ok
    assert all("-e" not in a for a in runner.argv)
    assert ["-V"] not in runner.argv


def test_an_old_tmux_gets_no_environment_flag_and_one_warning(caplog):
    runner = _Probe(version="tmux 3.1c", instance="laptop-b")
    with caplog.at_level(logging.WARNING, logger="the-loop.runner"):
        assert _spawn(runner).ok
        assert _spawn(runner).ok
    assert all("-e" not in a for a in runner.argv)
    warnings = [r for r in caplog.records if "THE_LOOP_INSTANCE" in r.getMessage()]
    assert len(warnings) == 1
    assert runner.argv.count(["-V"]) == 1


def test_only_the_configured_name_reaches_tmux_and_the_comment():
    """A6: the value interpolated is the validated config name, never event text."""
    config = InstanceConfig.from_mapping({"name": "instance:evil"})
    assert config.name == ""
    runner = _Probe(instance=config.name)
    _spawn(runner)
    assert all("-e" not in a for a in runner.argv)
    assert command_comment("start", ControlConfig(), address=config.name).startswith(
        "the-loop start\n"
    )


# -- the surface ------------------------------------------------------------------


def test_describe_instance_merges_declared_session_and_control_sources(tmp_path):
    """R4.4."""
    from the_loop.core.instance import describe_instance
    from the_loop.sessions import SessionRegistry

    config = {
        "state": {"root": str(tmp_path)},
        "instance": {
            "name": "laptop-b",
            "scope": {"mode": "addressed", "workItems": ["github:octo/repo#15"]},
        },
    }
    cli_config.apply_instance(config)
    ControlStore(tmp_path / "portable").record(
        "github:octo/repo#15", "start", instance="laptop-b"
    )
    ControlStore(tmp_path / "portable").record("github:octo/repo#16", "stop")
    SessionRegistry(tmp_path / "local").register(
        Session(
            work_item=WorkItemRef.parse("github:octo/repo#17"),
            harness="claude",
            harness_session_id="s",
            cwd=".",
        )
    )
    doc = describe_instance(config)
    assert doc["name"] == "laptop-b"
    assert doc["scope"] == {"mode": "addressed", "workItems": ["github:octo/repo#15"]}
    by_ref = {row["ref"]: row for row in doc["managed"]}
    assert by_ref["github:octo/repo#15"]["sources"] == ["declared", "control"]
    assert by_ref["github:octo/repo#16"]["sources"] == ["control"]
    assert by_ref["github:octo/repo#17"]["sources"] == ["session"]
    assert (
        by_ref["github:octo/repo#15"]["url"] == "https://github.com/octo/repo/issues/15"
    )
    assert [row["ref"] for row in doc["managed"]] == sorted(by_ref)


def test_describe_instance_for_an_unset_block_is_unnamed_open_and_empty(tmp_path):
    from the_loop.core.instance import describe_instance

    doc = describe_instance({"state": {"root": str(tmp_path)}})
    assert doc == {
        "name": "",
        "scope": {"mode": "open", "workItems": []},
        "managed": [],
    }
