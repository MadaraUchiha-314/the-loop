"""Unit tests for the env file the CLI config names (issue-318, T1/T8/T10).

The loader (``the_loop.envfile``), the resolver on the CLI config
(``cli_config.resolve_env_file`` / ``load_env_file``) and the three process entry
points that call it first. Run with: pytest (from the cli/ directory).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from the_loop import cli_config, envfile

NAME = "THE_LOOP_TEST_ENVFILE_TOKEN"
OTHER = "THE_LOOP_TEST_ENVFILE_OTHER"
SECRET = "xoxb-not-a-real-token-0123456789"


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    """No leaked names between tests, and no --config override."""
    for name in (NAME, OTHER, "THE_LOOP_SLACK_BOT_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    cli_config.set_override(None)
    yield
    cli_config.set_override(None)


@pytest.fixture()
def config_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "conf"
    directory.mkdir()
    return directory


def _write_config(directory: Path, body: str) -> Path:
    path = directory / "cli-config.yaml"
    path.write_text(body)
    return path


# -- the grammar (R1.4) ---------------------------------------------------------


def test_the_grammar_reads_plain_export_and_quoted_lines():
    text = "\n".join(
        [
            "# a comment",
            "",
            "PLAIN=value",
            "export EXPORTED=one two",
            'DOUBLE="a \\"quoted\\" value\\nwith\\ta tab\\\\"',
            "SINGLE='literal \\n stays'",
            "TRAILING=value # not part of it",
            "HASH_INSIDE=a#b",
            "EMPTY=",
            "SPACED = padded ",
        ]
    )
    result = envfile.parse(text)
    assert result.values == {
        "PLAIN": "value",
        "EXPORTED": "one two",
        "DOUBLE": 'a "quoted" value\nwith\ta tab\\',
        "SINGLE": "literal \\n stays",
        "TRAILING": "value",
        "HASH_INSIDE": "a#b",
        "EMPTY": "",
        "SPACED": "padded",
    }
    assert result.invalid_lines == ()


def test_the_grammar_does_not_interpolate():
    result = envfile.parse('A=one\nB="${A}"\nC=$A')
    assert result.values == {"A": "one", "B": "${A}", "C": "$A"}


def test_the_grammar_lets_a_later_duplicate_win():
    assert envfile.parse("A=first\nA=second").values == {"A": "second"}


def test_the_grammar_reports_invalid_lines_by_number():
    text = "\n".join(
        [
            "GOOD=1",
            "no equals sign",
            "1BAD=starts with a digit",
            "BAD NAME=has a space",
            'UNTERMINATED="no closing quote',
            "=novalue",
            "ALSO_GOOD=2",
        ]
    )
    result = envfile.parse(text)
    assert result.values == {"GOOD": "1", "ALSO_GOOD": "2"}
    assert result.invalid_lines == (2, 3, 4, 5, 6)


# -- the loader (R1.5, R2.1–R2.5) -----------------------------------------------


def test_the_environment_wins_over_the_file(tmp_path: Path, monkeypatch):
    """A4: a deliberately exported value is never replaced by the file."""
    path = tmp_path / ".env"
    path.write_text(f"{NAME}=from-the-file\n{OTHER}=also-from-the-file\n")
    environ = {NAME: "exported"}
    result = envfile.load(path, environ)
    assert result is not None
    assert environ == {NAME: "exported", OTHER: "also-from-the-file"}
    assert result.loaded == (OTHER,)
    assert result.skipped == (NAME,)


def test_a_missing_file_warns_and_loads_nothing(tmp_path: Path, caplog):
    missing = tmp_path / "absent.env"
    environ: dict = {}
    with caplog.at_level(logging.WARNING, logger="the-loop.env"):
        assert envfile.load(missing, environ) is None
    assert environ == {}
    assert str(missing) in caplog.text
    assert "not a regular file" in caplog.text or "does not exist" in caplog.text


def test_a_directory_is_not_a_regular_file(tmp_path: Path, caplog):
    environ: dict = {}
    with caplog.at_level(logging.WARNING, logger="the-loop.env"):
        assert envfile.load(tmp_path, environ) is None
    assert environ == {}
    assert str(tmp_path) in caplog.text


def test_an_unreadable_file_warns_with_the_error_class(tmp_path: Path, caplog):
    """A file that cannot be decoded is the portable stand-in for one that cannot be
    read: a permission test would pass for root, which is who runs this in CI."""
    path = tmp_path / ".env"
    path.write_bytes(b"\xff\xfe" + f"{NAME}=".encode() + b"\xff\n")
    environ: dict = {}
    with caplog.at_level(logging.WARNING, logger="the-loop.env"):
        assert envfile.load(path, environ) is None
    assert environ == {}
    assert "UnicodeDecodeError" in caplog.text
    assert str(path) in caplog.text


@pytest.mark.skipif(os.name != "posix", reason="file modes are POSIX")
def test_a_file_readable_by_others_is_warned_about_and_still_loaded(
    tmp_path: Path, caplog
):
    """A2: the warning names the mode problem; the values are still loaded."""
    path = tmp_path / ".env"
    path.write_text(f"{NAME}={SECRET}\n")
    path.chmod(0o644)
    environ: dict = {}
    with caplog.at_level(logging.WARNING, logger="the-loop.env"):
        result = envfile.load(path, environ)
    assert result is not None and result.loaded == (NAME,)
    assert environ[NAME] == SECRET
    assert "readable by others" in caplog.text

    caplog.clear()
    path.chmod(0o600)
    with caplog.at_level(logging.WARNING, logger="the-loop.env"):
        envfile.load(path, {})
    assert "readable by others" not in caplog.text


def test_malformed_lines_are_skipped_by_number_and_the_rest_loaded(
    tmp_path: Path, caplog
):
    """A3: a hostile line is skipped, reported by number, and never evaluated."""
    path = tmp_path / ".env"
    path.write_text(f"{NAME}=kept\n$(rm -rf /)\n{OTHER}=also kept\n")
    path.chmod(0o600)
    environ: dict = {}
    with caplog.at_level(logging.WARNING, logger="the-loop.env"):
        result = envfile.load(path, environ)
    assert result is not None
    assert result.invalid_lines == (2,)
    assert environ == {NAME: "kept", OTHER: "also kept"}
    assert "line 2" in caplog.text
    assert "rm -rf" not in caplog.text


def test_a_warning_never_carries_a_value_or_a_line(tmp_path: Path, caplog):
    """A1/R2.5: every log line carries paths, numbers and classes — never a value."""
    path = tmp_path / ".env"
    path.write_text(f"{NAME}={SECRET}\nBROKEN LINE={SECRET}\n")
    path.chmod(0o644)  # provoke the mode warning too
    environ: dict = {}
    with caplog.at_level(logging.DEBUG, logger="the-loop.env"):
        result = envfile.load(path, environ)
    assert result is not None and environ[NAME] == SECRET
    assert SECRET not in caplog.text
    assert "BROKEN LINE" not in caplog.text
    # the count and the path are reported at info; the names only at debug
    info = [r for r in caplog.records if r.levelno == logging.INFO]
    assert info and str(path) in info[0].getMessage() and "1" in info[0].getMessage()
    debug = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert any(NAME in message for message in debug)


# -- the resolver (R1.1, R1.3, R2.6) --------------------------------------------


def test_a_relative_path_resolves_against_the_config_directory(config_dir: Path):
    config_path = _write_config(config_dir, "env:\n  file: secrets/.env\n")
    resolved = cli_config.resolve_env_file(
        {"env": {"file": "secrets/.env"}}, config_path
    )
    assert resolved == config_dir / "secrets" / ".env"


def test_tilde_is_expanded(config_dir: Path, monkeypatch, tmp_path: Path):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("HOME", str(home))
    config_path = _write_config(config_dir, "")
    resolved = cli_config.resolve_env_file(
        {"env": {"file": "~/.the-loop/.env"}}, config_path
    )
    assert resolved == home / ".the-loop" / ".env"


def test_an_absolute_or_parent_path_is_honoured_and_named(
    config_dir: Path, tmp_path: Path, caplog
):
    """A5: the operator's path is used as given; a missing one is named resolved."""
    config_path = _write_config(config_dir, "")
    absolute = tmp_path / "elsewhere" / ".env"
    assert (
        cli_config.resolve_env_file({"env": {"file": str(absolute)}}, config_path)
        == absolute
    )
    parent = cli_config.resolve_env_file(
        {"env": {"file": "../shared.env"}}, config_path
    )
    assert parent == config_dir / ".." / "shared.env"

    config_path.write_text(f"env:\n  file: {absolute}\n")
    with caplog.at_level(logging.WARNING, logger="the-loop.env"):
        assert cli_config.load_env_file(config_path) is None
    assert str(absolute) in caplog.text


def test_a_config_without_an_env_block_loads_nothing(config_dir: Path, caplog):
    """T10: a 13.2.0 config behaves exactly as before — nothing resolved, nothing said."""
    config_path = _write_config(
        config_dir, "version: '0.7.0'\nrouting:\n  enabled: false\n"
    )
    with caplog.at_level(logging.DEBUG, logger="the-loop.env"):
        assert cli_config.resolve_env_file({"routing": {}}, config_path) is None
        assert cli_config.resolve_env_file({"env": {}}, config_path) is None
        assert cli_config.resolve_env_file({"env": {"file": ""}}, config_path) is None
        assert cli_config.load_env_file(config_path) is None
    assert caplog.text == ""


def test_a_wrong_type_is_a_warning_not_a_path(config_dir: Path, caplog):
    config_path = _write_config(config_dir, "")
    with caplog.at_level(logging.WARNING, logger="the-loop.env"):
        assert (
            cli_config.resolve_env_file({"env": "not-a-mapping"}, config_path) is None
        )
        assert (
            cli_config.resolve_env_file({"env": {"file": ["a"]}}, config_path) is None
        )
        assert cli_config.resolve_env_file({"env": {"file": 3}}, config_path) is None
    assert caplog.text.count("env.file") >= 2


def test_a_stale_or_broken_config_loads_nothing_and_does_not_raise(
    config_dir: Path, tmp_path: Path
):
    """R2.6: the lenient read — a stale version or a parse error is the command's to
    refuse, not the loader's; `--version` and `migrate-config` keep working."""
    env_path = tmp_path / ".env"
    env_path.write_text(f"{NAME}=loaded\n")
    stale = _write_config(
        config_dir, f"version: '0.1.0'\nghBinary: gh\nenv:\n  file: {env_path}\n"
    )
    assert cli_config.load_env_file(stale) is None
    assert NAME not in os.environ
    broken = _write_config(config_dir, "env: [unclosed\n")
    assert cli_config.load_env_file(broken) is None
    assert cli_config.load_env_file(config_dir / "absent.yaml") is None


def test_load_env_file_sets_the_process_environment(config_dir: Path, tmp_path: Path):
    (config_dir / ".env").write_text(f"{NAME}=loaded\n")
    config_path = _write_config(config_dir, "env:\n  file: .env\n")
    result = cli_config.load_env_file(config_path)
    assert result is not None and result.loaded == (NAME,)
    assert os.environ[NAME] == "loaded"


# -- the entry points (R1.2, R1.6) ----------------------------------------------


class _Stop(Exception):
    pass


def _config_naming_an_env_file(config_dir: Path) -> Path:
    (config_dir / ".env").write_text(f"{NAME}=from-the-file\n")
    return _write_config(config_dir, "env:\n  file: .env\n")


def test_the_cli_loads_the_env_file_before_building_the_parser(
    config_dir: Path, monkeypatch
):
    from the_loop import cli

    config_path = _config_naming_an_env_file(config_dir)
    seen = {}

    def fake_build_parser():
        seen["value"] = os.environ.get(NAME)
        raise _Stop

    monkeypatch.setattr(cli, "build_parser", fake_build_parser)
    with pytest.raises(_Stop):
        cli.main(["--config", str(config_path), "status"])
    assert seen == {"value": "from-the-file"}


def test_the_daemon_entry_loads_the_env_file_before_running(
    config_dir: Path, monkeypatch
):
    from the_loop import daemon_entry
    from the_loop.poller import daemon as poller_daemon

    config_path = _config_naming_an_env_file(config_dir)
    monkeypatch.setenv(cli_config.CLI_CONFIG_ENV, str(config_path))
    seen = {}

    def fake_run(options):
        seen["value"] = os.environ.get(NAME)
        return 0

    monkeypatch.setattr(poller_daemon, "default_options", lambda once=False: None)
    monkeypatch.setattr(poller_daemon, "run", fake_run)
    assert daemon_entry.main(["poller", "--once"]) == 0
    assert seen == {"value": "from-the-file"}


def test_the_service_loads_the_env_file_before_its_config(
    config_dir: Path, monkeypatch
):
    pytest.importorskip("fastapi")
    from the_loop.api import serve

    config_path = _config_naming_an_env_file(config_dir)
    monkeypatch.setenv(cli_config.CLI_CONFIG_ENV, str(config_path))
    seen = {}

    def fake_load(path, strict=False):
        seen["value"] = os.environ.get(NAME)
        raise RuntimeError("stop here")

    monkeypatch.setattr(serve, "load_cli_config", fake_load)
    assert serve.main() == 2
    assert seen == {"value": "from-the-file"}
