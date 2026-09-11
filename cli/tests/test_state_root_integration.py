"""One configuration resolves to one state root, in every process (issue-339).

`state.root` used to be a **relative** path, so the daemon and the CLI resolved it
against their own working directories and silently addressed different files — two
heartbeats, two registries, two event logs. On the reporter's box that hid a dead poller
for 17 hours while `status` reported a live one as down, off a two-day-old file.

These scenarios pin the property the bug violated: the same config file, read from two
places, names the same directory.

Spec: docs/specs/issue-339/design.md §D1, §D2 · Testing plan rows T2, T8, T10.
"""

from pathlib import Path

import pytest

from the_loop import cli_config
from the_loop.state import layout_from_config, rival_roots

PATHS = (
    "root",
    "portable_dir",
    "portable_index",
    "local_dir",
    "event_log",
    "pidfile",
    "poll_pidfile",
    "poll_status",
    "poller_log",
    "self_diagnosis",
    "channels_dir",
    "standing_dir",
)


@pytest.fixture(autouse=True)
def _no_leaked_override():
    cli_config.set_override(None)
    yield
    cli_config.set_override(None)


def _write_config(directory: Path, body: str = "version: '0.7.0'\n") -> Path:
    config_dir = directory / ".the-loop"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "cli-config.yaml"
    path.write_text(body)
    return path


def _layout_paths(config: dict) -> dict:
    layout = layout_from_config(config)
    return {name: getattr(layout, name) for name in PATHS}


def test_one_config_file_two_working_directories_one_state_root(tmp_path, monkeypatch):
    """
    Feature: one configuration resolves to one state root
      Scenario: one config file, two working directories, one state root
        Given a CLI config at <repo>/.the-loop/cli-config.yaml with no state.root
        When it is loaded from <repo>, and again from an unrelated directory
        Then every generated path resolves to the same absolute location under <repo>

    Requirement: docs/specs/issue-339/bugfix.md R1.1, R1.2, R1.4
    """
    repo = tmp_path / "repo"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    path = _write_config(repo)

    monkeypatch.chdir(repo)
    from_repo = _layout_paths(cli_config.load_cli_config(path))
    monkeypatch.chdir(elsewhere)
    from_elsewhere = _layout_paths(cli_config.load_cli_config(path))

    assert from_repo == from_elsewhere
    assert Path(from_repo["root"]).is_absolute()
    assert Path(from_repo["poll_status"]) == repo / ".the-loop" / "poll-status.json"


def test_a_relative_root_is_anchored_on_the_config_not_the_cwd(tmp_path, monkeypatch):
    """
    Feature: one configuration resolves to one state root
      Scenario: a relative state.root follows the config file, not the caller
        Given a config at <repo>/.the-loop/cli-config.yaml with state.root: var/state
        When it is loaded from an unrelated working directory
        Then the root is <repo>/var/state and no directory under the caller is named

    Requirement: docs/specs/issue-339/bugfix.md R1.2, R1.4
    """
    repo = tmp_path / "repo"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    path = _write_config(repo, "version: '0.7.0'\nstate:\n  root: var/state\n")

    monkeypatch.chdir(elsewhere)
    layout = layout_from_config(cli_config.load_cli_config(path))

    assert Path(layout.root) == repo / "var" / "state"


def test_migration_an_explicit_root_keeps_the_directory_it_always_had(
    tmp_path, monkeypatch
):
    """
    Feature: one configuration resolves to one state root
      Scenario: an explicit state.root resolves to the directory it always resolved to
        Given a config carrying the pre-fix idiom state.root: .the-loop
        When it is loaded from the base directory, as a working setup always did
        Then the resolved root is the same <repo>/.the-loop it named before the fix

    Requirement: docs/specs/issue-339/bugfix.md R1.2 (no silent state move)
    """
    repo = tmp_path / "repo"
    path = _write_config(repo, "version: '0.7.0'\nstate:\n  root: .the-loop\n")

    monkeypatch.chdir(repo)
    before_fix = Path(".the-loop").resolve()  # what a cwd-relative root named here
    layout = layout_from_config(cli_config.load_cli_config(path))

    assert Path(layout.root).resolve() == before_fix


def test_an_absolute_root_is_used_verbatim(tmp_path):
    """
    Feature: one configuration resolves to one state root
      Scenario: an absolute state.root is the operator's, untouched
        Given a config whose state.root is an absolute path
        When it is loaded
        Then that path is used exactly as written

    Requirement: docs/specs/issue-339/bugfix.md R1.3
    """
    repo = tmp_path / "repo"
    elsewhere = tmp_path / "srv" / "the-loop"
    path = _write_config(repo, f"version: '0.7.0'\nstate:\n  root: {elsewhere}\n")

    layout = layout_from_config(cli_config.load_cli_config(path))

    assert Path(layout.root) == elsewhere


def test_a_missing_config_file_still_resolves_an_absolute_root(tmp_path, monkeypatch):
    """
    Feature: one configuration resolves to one state root
      Scenario: a fresh install, with no config file anywhere
        Given no cli-config.yaml at the resolved path
        When the config is loaded from two different working directories
        Then both name the same absolute root beside the path that would be read

    Requirement: docs/specs/issue-339/bugfix.md R1.1, R1.4
    """
    home = tmp_path / "home"
    path = home / ".the-loop" / "cli-config.yaml"  # never created
    monkeypatch.chdir(tmp_path)
    first = layout_from_config(cli_config.load_cli_config(path))
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")
    second = layout_from_config(cli_config.load_cli_config(path))

    assert Path(first.root) == Path(second.root) == home / ".the-loop"


def test_security_the_spawn_environment_carries_only_the_resolved_path(
    tmp_path, monkeypatch
):
    """
    Feature: a spawned daemon reads the config its parent resolved
      Scenario: nothing caller-supplied reaches THE_LOOP_CLI_CONFIG (abuse case AC1)
        Given a --config override the operator set on this invocation
        When the environment for a spawned child is built
        Then the variable is that absolute path and the rest of the environment is intact

    Requirement: docs/specs/issue-339/bugfix.md R1.5, AC1
    """
    repo = tmp_path / "repo"
    path = _write_config(repo)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNRELATED", "kept")
    cli_config.set_override(path)

    env = cli_config.child_env()

    assert env[cli_config.CLI_CONFIG_ENV] == str(path)
    assert Path(env[cli_config.CLI_CONFIG_ENV]).is_absolute()
    assert env["UNRELATED"] == "kept"


def test_the_child_environment_absolutizes_a_cwd_relative_resolution(
    tmp_path, monkeypatch
):
    """
    Feature: a spawned daemon reads the config its parent resolved
      Scenario: the cwd branch is absolutized before it is handed to a child
        Given the config was found as ./.the-loop/cli-config.yaml
        When the environment for a child (which may have another cwd) is built
        Then the variable holds the absolute path, not the relative one

    Requirement: docs/specs/issue-339/bugfix.md R1.5
    """
    repo = tmp_path / "repo"
    _write_config(repo)
    monkeypatch.chdir(repo)
    monkeypatch.delenv(cli_config.CLI_CONFIG_ENV, raising=False)

    assert cli_config.default_cli_config_path() == Path(".the-loop/cli-config.yaml")
    env = cli_config.child_env()

    assert (
        Path(env[cli_config.CLI_CONFIG_ENV]) == repo / ".the-loop" / "cli-config.yaml"
    )


def test_status_refuses_to_guess_between_two_roots(tmp_path, monkeypatch):
    """
    Feature: the-loop names the files it read
      Scenario: a second state root also holds a heartbeat
        Given the resolved root, and another candidate root holding poll-status.json
        When the rival roots are computed
        Then the other one is named and the resolved one is not

    Requirement: docs/specs/issue-339/bugfix.md R4.2
    """
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    path = _write_config(repo)
    (home / ".the-loop").mkdir(parents=True)
    (home / ".the-loop" / "poll-status.json").write_text("{}")
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(repo)

    layout = layout_from_config(cli_config.load_cli_config(path))
    rivals = rival_roots(layout)

    assert rivals == (str(home / ".the-loop"),)


def test_no_rival_when_the_only_heartbeat_is_the_resolved_roots(tmp_path, monkeypatch):
    """
    Feature: the-loop names the files it read
      Scenario: one root, one heartbeat, nothing to warn about
        Given the resolved root holds the only poll-status.json
        When the rival roots are computed
        Then there are none

    Requirement: docs/specs/issue-339/bugfix.md R4.2
    """
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    (home / ".the-loop").mkdir(parents=True)
    path = _write_config(repo)
    (repo / ".the-loop" / "poll-status.json").write_text("{}")
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(repo)

    layout = layout_from_config(cli_config.load_cli_config(path))

    assert rival_roots(layout) == ()


def test_status_prints_its_config_its_root_and_a_rival_without_changing_exit_code(
    tmp_path, monkeypatch, capsys
):
    """
    Feature: the-loop names the files it read
      Scenario: status names its config, its root and a rival root without changing its
                exit code
        Given a config whose services are all disabled, and a second root holding a
              heartbeat
        When `the-loop status` runs from an unrelated working directory
        Then it prints the config it read, the root it resolved and the rival it found
        And the exit code is still the one the enabled services decide

    Requirement: docs/specs/issue-339/bugfix.md R4.1, R4.2, R4.3
    """
    from the_loop.cli import main

    repo = tmp_path / "repo"
    home = tmp_path / "home"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    path = _write_config(
        repo,
        "version: '0.7.0'\nservice:\n  enabled: false\nstandingSessions:\n  enabled: false\n",
    )
    (home / ".the-loop").mkdir(parents=True)
    (home / ".the-loop" / "poll-status.json").write_text("{}")
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(elsewhere)

    code = main(["--config", str(path), "status"])
    out = capsys.readouterr().out

    assert code == 0  # nothing enabled is down; a rival root is an observation (R4.3)
    assert f"config      {path}" in out
    assert f"state       {repo / '.the-loop'}" in out
    assert f"conflict    {home / '.the-loop'} also holds a poller heartbeat" in out


def test_the_lifecycle_verbs_anchor_the_root_with_no_config_file_at_all(
    tmp_path, monkeypatch
):
    """
    Feature: one configuration resolves to one state root
      Scenario: a fresh install runs `start` before writing a config
        Given no cli-config.yaml at the path `the-loop` would read
        When the lifecycle verbs load their config
        Then the state root is still the absolute one the daemon they spawn resolves,
             not one relative to whatever directory the command was run from

    Requirement: docs/specs/issue-339/bugfix.md R1.1, R1.4
    """
    from the_loop.commands import lifecycle_cmd

    home = tmp_path / "home"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv(cli_config.CLI_CONFIG_ENV, raising=False)
    monkeypatch.chdir(elsewhere)

    config = lifecycle_cmd._load_config()

    assert Path(layout_from_config(config).root) == home / ".the-loop"


def test_rival_roots_survives_an_environment_with_no_home(tmp_path, monkeypatch):
    """
    Feature: the-loop names the files it read
      Scenario: a daemon running under a unit with no HOME
        Given Path.home() cannot be resolved
        When the rival roots are computed
        Then the home candidate is dropped and the answer is still given

    Requirement: docs/specs/issue-339/bugfix.md R4.2 (an observation never fails status)
    """

    def _no_home():
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", _no_home)
    monkeypatch.chdir(tmp_path)

    assert rival_roots(layout_from_config({"state": {"root": str(tmp_path)}})) == ()
