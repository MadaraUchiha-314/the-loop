"""Unit tests for the execution-control vocabulary and its record (issue-106).

Pure pieces only: config parsing, keyword matching (boundaries, case,
ambiguity), the CLI's paper-trail comment body, and the durable
:class:`ControlStore`. Dispatcher/poller behaviour lives in
``test_control_integration.py``.
"""

import pytest

from the_loop.authz import SELF_COMMENT_MARKER, is_self_authored
from the_loop.migrations import CURRENT_CONFIG_VERSION
from the_loop.control import (
    ADD_COLLABORATOR,
    COLLABORATOR_COMMANDS,
    COMMANDS,
    DEFAULT_KEYWORDS,
    REMOVE_COLLABORATOR,
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
    assert config.keyword(START) == "the-loop start"
    assert config.keyword(STOP) == "the-loop stop"
    assert config.keyword(PAUSE) == "the-loop pause"
    assert config.keyword(RESUME) == "the-loop resume"
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
                "version": CURRENT_CONFIG_VERSION,
                "integrations": {"github": {"cli": {"binary": "/usr/bin/gh"}}},
                "routing": {"control": {"enabled": True}},
            }
        ),
        encoding="utf-8",
    )
    data = cli_config.load_cli_config(path)
    section = data["routing"]["control"]
    assert ControlConfig.from_mapping(section).gh_binary == "/usr/bin/gh"


def test_an_empty_keyword_disables_only_that_command():
    config = ControlConfig.from_mapping({"keywords": {"stop": ""}})
    assert parse_command("the-loop stop now", config).command is None
    assert parse_command("the-loop pause", config).command == PAUSE


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
        "the-loop start",
        "the-loop start.",
        "**the-loop start**",
        "line one\nthe-loop start\nline three",
        "(the-loop start)",
        "THE-LOOP START",
    ],
)
def test_keyword_matches_as_a_whole_token_case_insensitively(body):
    assert parse_command(body, ControlConfig()).command == START


@pytest.mark.parametrize(
    "body",
    [
        "xthe-loop start",
        "the-loop startx",
        "the-loop startlater",
        "the-loop start:now",
    ],
)
def test_a_keyword_glued_to_other_word_characters_does_not_match(body):
    assert parse_command(body, ControlConfig()).command is None


def test_the_same_command_twice_is_not_ambiguous():
    body = "the-loop start — I mean it, the-loop start"
    assert parse_command(body, ControlConfig()).command == START


def test_two_different_commands_are_refused_as_ambiguous():
    body = "the-loop start ... actually the-loop stop"
    result = parse_command(body, ControlConfig())
    assert result.ambiguous is True
    assert result.command is None
    assert set(result.matched) == {START, STOP}
    assert result  # truthy: the caller must NOT fall through to forwarding


def test_disabled_control_recognises_nothing():
    config = ControlConfig(enabled=False)
    assert parse_command("the-loop stop", config).command is None


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
    # Corrupt THIS work item's record, resolved by path — not `next(glob("*.json"))`.
    # The directory also holds the derived `index.json` (issue-130), so the glob
    # returned whichever of the two the filesystem listed first: locally the record,
    # on CI the index. Corrupting the index left the record intact and `get()`
    # rightly returned it, failing an assertion about a file the test never touched.
    path = store.store.path_for(REF)
    path.write_text("{not json")
    assert store.get(REF) is None
    assert store.start_requested(REF) is False  # fails closed


def test_records_are_kept_per_work_item(tmp_path):
    store = ControlStore(tmp_path / "control")
    store.record(REF, START)
    store.record("github:octo/repo#16", STOP)
    assert store.start_requested(REF) is True
    assert store.start_requested("github:octo/repo#16") is False


# -- the two commands that carry an argument (issue-307) ------------------------


def test_the_collaborator_keywords_are_declared_like_every_other():
    config = ControlConfig()
    assert config.keyword(ADD_COLLABORATOR) == "the-loop add-collaborator"
    assert config.keyword(REMOVE_COLLABORATOR) == "the-loop remove-collaborator"
    assert set(COLLABORATOR_COMMANDS) <= set(COMMANDS)


def test_a_collaborator_command_carries_the_login_it_named():
    result = parse_command("the-loop add-collaborator @Dana", ControlConfig())
    assert result.command == ADD_COLLABORATOR
    assert result.subjects == ["dana"]


def test_several_logins_and_a_repeated_keyword_all_count():
    body = (
        "please the-loop add-collaborator @a @b — they know this area\n"
        "and the-loop add-collaborator @c too"
    )
    result = parse_command(body, ControlConfig())
    assert result.command == ADD_COLLABORATOR
    assert result.subjects == ["a", "b", "c"]


def test_a_keyword_with_nobody_named_is_the_command_and_no_subjects():
    """The caller refuses it (`missing-collaborator`); the parser only reports."""
    result = parse_command("the-loop remove-collaborator soon", ControlConfig())
    assert result.command == REMOVE_COLLABORATOR
    assert result.subjects == []


def test_nothing_but_a_login_reaches_the_caller():
    """A3: prose, paths and argv fragments after the keyword are not subjects."""
    body = "the-loop add-collaborator @dana/../etc --permission-mode bypass"
    assert parse_command(body, ControlConfig()).subjects == []
    body = "the-loop add-collaborator @dana rm -rf /"
    assert parse_command(body, ControlConfig()).subjects == ["dana"]


def test_the_keywords_match_as_whole_tokens():
    config = ControlConfig()
    assert parse_command("the-loop add-collaborators @a", config).command is None
    assert parse_command("xthe-loop add-collaborator @a", config).command is None
    assert parse_command("`the-loop add-collaborator @a`", config).subjects == ["a"]
    assert parse_command("THE-LOOP ADD-COLLABORATOR @A", config).subjects == ["a"]


def test_a_collaborator_keyword_beside_another_command_is_ambiguous():
    result = parse_command(
        "the-loop add-collaborator @dana and the-loop stop", ControlConfig()
    )
    assert result.ambiguous and result.command is None


def test_an_emptied_collaborator_keyword_disables_that_command():
    config = ControlConfig.from_mapping({"keywords": {"add-collaborator": ""}})
    assert parse_command("the-loop add-collaborator @a", config).command is None
    assert (
        parse_command("the-loop remove-collaborator @a", config).command
        == REMOVE_COLLABORATOR
    )


def test_the_paper_trail_comment_carries_the_login_and_the_right_invocation():
    body = command_comment(
        ADD_COLLABORATOR,
        ControlConfig(),
        actor="octocat",
        subject="dana",
        invocation="the-loop add-collaborator",
    )
    assert body.startswith("the-loop add-collaborator @dana")
    assert "`the-loop add-collaborator`" in body
    assert is_self_authored(body)  # the daemon must not read it back


def test_a_collaborator_command_is_not_a_control_record(tmp_path):
    """They arm nothing, so `start_requested` must not learn about them."""
    store = ControlStore(tmp_path / "control")
    store.record(REF, START)
    assert store.start_requested(REF) is True
    store.record(REF, STOP)
    assert store.start_requested(REF) is False
