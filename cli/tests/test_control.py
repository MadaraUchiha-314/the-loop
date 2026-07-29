"""Unit tests for the execution-control vocabulary and its record (issue-106).

Pure pieces only: config parsing, keyword matching (boundaries, case,
ambiguity), the CLI's paper-trail comment body, and the durable
:class:`ControlStore`. Dispatcher/poller behaviour lives in
``test_control_integration.py``.
"""

import pytest

from the_loop.authz import SELF_COMMENT_MARKER, is_self_authored
from the_loop.control import (
    COMMANDS,
    DEFAULT_KEYWORDS,
    PAUSE,
    RESUME,
    START,
    STOP,
    ControlConfig,
    ControlStore,
    command_comment,
    parse_command,
)
from the_loop.sessions import WorkItemRef

REF = "github:octo/repo#15"


# -- ControlConfig --------------------------------------------------------------


def test_defaults_declare_the_four_documented_keywords():
    config = ControlConfig()
    assert config.enabled and config.require_start_command
    assert config.keyword(START) == "the-loop:start-execution"
    assert config.keyword(STOP) == "the-loop:stop-execution"
    assert config.keyword(PAUSE) == "the-loop:pause-execution"
    assert config.keyword(RESUME) == "the-loop:resume-execution"
    assert set(DEFAULT_KEYWORDS) == set(COMMANDS)


def test_from_mapping_overrides_one_keyword_and_keeps_the_rest():
    config = ControlConfig.from_mapping({"keywords": {"start": "/go"}})
    assert config.keyword(START) == "/go"
    assert config.keyword(STOP) == DEFAULT_KEYWORDS[STOP]


def test_from_mapping_reads_the_switches():
    config = ControlConfig.from_mapping(
        {"enabled": False, "requireStartCommand": False}
    )
    assert config.enabled is False
    assert config.require_start_command is False


def test_the_binary_now_comes_from_the_integrations_block(tmp_path):
    """issue-109: `ghBinary` was removed; one `integrations` block replaces it.

    The removed key is not quietly honoured here — a config that still declares
    it never reaches this code, because `load_cli_config` refuses it outright.
    """
    import yaml

    from the_loop import cli_config

    path = tmp_path / "cli-config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": "0.2.0",
                "integrations": {"github": {"cli": {"binary": "/usr/bin/gh"}}},
                "webhooks": {"ghWebhook": {"routing": {"control": {"enabled": True}}}},
            }
        ),
        encoding="utf-8",
    )
    data = cli_config.load_cli_config(path)
    section = data["webhooks"]["ghWebhook"]["routing"]["control"]
    assert ControlConfig.from_mapping(section).gh_binary == "/usr/bin/gh"


def test_an_empty_keyword_disables_only_that_command():
    config = ControlConfig.from_mapping({"keywords": {"stop": ""}})
    assert parse_command("the-loop:stop-execution now", config).command is None
    assert parse_command("the-loop:pause-execution", config).command == PAUSE


# -- parse_command --------------------------------------------------------------


@pytest.mark.parametrize("command", COMMANDS)
def test_each_declared_keyword_is_recognised(command):
    body = f"please {DEFAULT_KEYWORDS[command]} when you get a chance"
    assert parse_command(body, ControlConfig()).command == command


def test_a_comment_without_a_keyword_is_not_a_command():
    result = parse_command("could you rebase this on main?", ControlConfig())
    assert result.command is None and not result.ambiguous
    assert not result


@pytest.mark.parametrize(
    "body",
    [
        "the-loop:start-execution",
        "the-loop:start-execution.",
        "**the-loop:start-execution**",
        "line one\nthe-loop:start-execution\nline three",
        "(the-loop:start-execution)",
        "THE-LOOP:START-EXECUTION",
    ],
)
def test_keyword_matches_as_a_whole_token_case_insensitively(body):
    assert parse_command(body, ControlConfig()).command == START


@pytest.mark.parametrize(
    "body",
    [
        "xthe-loop:start-executionx",
        "the-loop:start-execution-later",
        "athe-loop:start-execution",
        "the-loop:start-execution:now",
    ],
)
def test_a_keyword_glued_to_other_word_characters_does_not_match(body):
    assert parse_command(body, ControlConfig()).command is None


def test_the_same_command_twice_is_not_ambiguous():
    body = "the-loop:start-execution — I mean it, the-loop:start-execution"
    assert parse_command(body, ControlConfig()).command == START


def test_two_different_commands_are_refused_as_ambiguous():
    body = "the-loop:start-execution ... actually the-loop:stop-execution"
    result = parse_command(body, ControlConfig())
    assert result.ambiguous is True
    assert result.command is None
    assert set(result.matched) == {START, STOP}
    assert result  # truthy: the caller must NOT fall through to forwarding


def test_disabled_control_recognises_nothing():
    config = ControlConfig(enabled=False)
    assert parse_command("the-loop:stop-execution", config).command is None


def test_an_empty_body_is_not_a_command():
    assert parse_command(None, ControlConfig()).command is None
    assert parse_command("", ControlConfig()).command is None


# -- command_comment ------------------------------------------------------------


def test_the_cli_comment_carries_the_same_keyword_a_human_would_type():
    body = command_comment(PAUSE, ControlConfig(), actor="operator")
    assert DEFAULT_KEYWORDS[PAUSE] in body
    assert parse_command(body, ControlConfig()).command == PAUSE


def test_the_cli_comment_is_marked_as_the_loops_own():
    # Without the marker both ingress paths would read it back and re-apply the
    # command forever (the issue-104 contract).
    body = command_comment(START, ControlConfig(), actor="operator")
    assert SELF_COMMENT_MARKER in body
    assert is_self_authored(body)


def test_the_cli_comment_says_where_it_came_from():
    body = command_comment(STOP, ControlConfig(), actor="operator")
    assert "the-loop CLI" in body
    assert "operator" in body


def test_the_cli_comment_survives_a_custom_keyword():
    config = ControlConfig.from_mapping({"keywords": {"resume": "/resume"}})
    body = command_comment(RESUME, config, actor="")
    assert "/resume" in body
    assert parse_command(body, config).command == RESUME


# -- ControlStore ---------------------------------------------------------------


def test_store_records_and_reads_back_a_command(tmp_path):
    store = ControlStore(tmp_path / "control")
    record = store.record(REF, START, source="cli", actor="operator", note="url")
    assert record.command == START
    read = store.get(WorkItemRef.parse(REF))
    assert read is not None
    assert (read.command, read.source, read.actor, read.note) == (
        START,
        "cli",
        "operator",
        "url",
    )
    assert read.requested_at  # stamped


def test_an_unknown_work_item_has_no_record(tmp_path):
    assert ControlStore(tmp_path / "control").get(REF) is None
    assert ControlStore(tmp_path / "control").start_requested(REF) is False


@pytest.mark.parametrize(
    "command,armed", [(START, True), (RESUME, True), (PAUSE, False), (STOP, False)]
)
def test_start_requested_follows_the_last_command(tmp_path, command, armed):
    store = ControlStore(tmp_path / "control")
    store.record(REF, command)
    assert store.start_requested(REF) is armed


def test_a_stop_durably_disarms_a_previously_started_item(tmp_path):
    store = ControlStore(tmp_path / "control")
    store.record(REF, START)
    store.record(REF, STOP)
    assert store.start_requested(REF) is False
    # …and a fresh store (a daemon restart) reads the same answer off disk.
    assert ControlStore(tmp_path / "control").start_requested(REF) is False


def test_a_start_survives_a_restart(tmp_path):
    ControlStore(tmp_path / "control").record(REF, START)
    assert ControlStore(tmp_path / "control").start_requested(REF) is True


def test_an_unknown_command_is_refused(tmp_path):
    with pytest.raises(ValueError):
        ControlStore(tmp_path / "control").record(REF, "delete-everything")


def test_clear_forgets_the_record(tmp_path):
    store = ControlStore(tmp_path / "control")
    store.record(REF, START)
    assert store.clear(REF) is True
    assert store.get(REF) is None
    assert store.clear(REF) is False  # already gone


def test_an_unreadable_record_is_skipped_not_raised(tmp_path):
    store = ControlStore(tmp_path / "control")
    store.record(REF, START)
    path = next((tmp_path / "control").glob("*.json"))
    path.write_text("{not json")
    assert store.get(REF) is None
    assert store.start_requested(REF) is False  # fails closed


def test_records_are_kept_per_work_item(tmp_path):
    store = ControlStore(tmp_path / "control")
    store.record(REF, START)
    store.record("github:octo/repo#16", STOP)
    assert store.start_requested(REF) is True
    assert store.start_requested("github:octo/repo#16") is False
