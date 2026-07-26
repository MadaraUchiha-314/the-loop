"""Unit tests for the consolidated runtime-state layout (issue-98 review).

All daemon state lives under ``.the-loop/state/``; a pre-move path that still
exists keeps being read, and ``the-loop state migrate`` moves it over.
"""

import os

import pytest

from the_loop import state
from the_loop.cli import main

REGISTRY = state.PATHS[0]  # session registry (a directory)
POLL_STATE = next(p for p in state.PATHS if p.current.endswith("poll-state.json"))


@pytest.fixture(autouse=True)
def _in_tmp_cwd(tmp_path, monkeypatch):
    """Every path in this module is cwd-relative, so isolate the cwd."""
    monkeypatch.chdir(tmp_path)
    state._warned.clear()
    yield


def write(path, text="{}"):
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_every_state_path_lives_under_the_state_dir():
    assert state.PATHS
    for path in state.PATHS:
        assert path.current.startswith(state.STATE_DIR + "/")
        assert not path.legacy.startswith(state.STATE_DIR)
        assert path.key and path.description


def test_a_fresh_install_uses_the_new_path():
    assert state.resolve(REGISTRY.current) == REGISTRY.current


def test_a_pre_move_path_is_used_while_it_exists(caplog):
    write(f"{REGISTRY.legacy}/x.json")
    with caplog.at_level("INFO"):
        assert state.resolve(REGISTRY.current) == REGISTRY.legacy
    assert "state migrate" in caplog.text


def test_the_pre_move_note_is_logged_once(caplog):
    write(f"{REGISTRY.legacy}/x.json")
    with caplog.at_level("INFO"):
        state.resolve(REGISTRY.current)
        caplog.clear()
        state.resolve(REGISTRY.current)
    assert caplog.text == ""


def test_the_new_path_wins_when_both_exist():
    write(f"{REGISTRY.legacy}/x.json")
    write(f"{REGISTRY.current}/x.json")
    assert state.resolve(REGISTRY.current) == REGISTRY.current


def test_an_explicitly_configured_path_is_never_second_guessed():
    write(f"{REGISTRY.legacy}/x.json")
    assert state.resolve(REGISTRY.current, "/somewhere/else") == "/somewhere/else"


def test_an_unknown_default_is_returned_as_is():
    assert state.resolve("/not/a/known/state/path") == "/not/a/known/state/path"


def test_plan_reports_each_entry_without_touching_anything():
    write(POLL_STATE.legacy)
    actions = {step.path.key: step.action for step in state.plan()}
    assert actions[POLL_STATE.key] == "would-move"
    assert actions[REGISTRY.key] == "skipped-missing"
    assert os.path.exists(POLL_STATE.legacy)  # untouched


def test_migrate_moves_files_and_directories():
    write(f"{REGISTRY.legacy}/x.json", '{"a": 1}')
    write(POLL_STATE.legacy, '{"items": {}}')
    steps = {step.path.key: step.action for step in state.migrate()}
    assert steps[REGISTRY.key] == "moved"
    assert steps[POLL_STATE.key] == "moved"
    assert os.path.exists(f"{REGISTRY.current}/x.json")
    assert not os.path.exists(REGISTRY.legacy)


def test_migrate_dry_run_writes_nothing():
    write(POLL_STATE.legacy)
    steps = state.migrate(dry_run=True)
    assert any(step.action == "would-move" for step in steps)
    assert os.path.exists(POLL_STATE.legacy)
    assert not os.path.exists(POLL_STATE.current)


def test_migrate_is_idempotent():
    write(POLL_STATE.legacy)
    state.migrate()
    steps = {step.path.key: step.action for step in state.migrate()}
    assert steps[POLL_STATE.key] == "skipped-missing"


def test_migrate_refuses_to_overwrite_state_in_both_layouts():
    write(POLL_STATE.legacy, '{"items": {"old": {}}}')
    write(POLL_STATE.current, '{"items": {"new": {}}}')
    steps = {step.path.key: step.action for step in state.migrate()}
    assert steps[POLL_STATE.key] == "skipped-target-exists"
    from pathlib import Path

    assert "new" in Path(POLL_STATE.current).read_text()  # not clobbered


def test_running_daemons_reports_a_live_pidfile():
    pidfile = next(p for p in state.PATHS if p.current.endswith("poll.pid"))
    write(pidfile.legacy, str(os.getpid()))
    assert any("poll.pid" in entry for entry in state.running_daemons())


def test_running_daemons_ignores_a_stale_or_corrupt_pidfile():
    pidfile = next(p for p in state.PATHS if p.current.endswith("poll.pid"))
    write(pidfile.legacy, "999999999")
    assert state.running_daemons() == []
    write(pidfile.legacy, "not-a-pid")
    assert state.running_daemons() == []


# -- the CLI surface -----------------------------------------------------------


def test_state_paths_lists_every_entry(capsys):
    assert main(["state", "paths"]) == 0
    out = capsys.readouterr().out
    for path in state.PATHS:
        assert path.description in out
    assert state.STATE_DIR in out


def test_state_paths_flags_pre_move_state(capsys):
    write(POLL_STATE.legacy)
    assert main(["state", "paths"]) == 0
    captured = capsys.readouterr()
    assert "pre-move" in captured.out
    assert "state migrate" in captured.err


def test_state_migrate_command_moves_and_reports(capsys):
    write(POLL_STATE.legacy)
    assert main(["state", "migrate"]) == 0
    out = capsys.readouterr().out
    assert "moved" in out and POLL_STATE.current in out
    assert os.path.exists(POLL_STATE.current)


def test_state_migrate_refuses_while_a_daemon_looks_alive(capsys):
    pidfile = next(p for p in state.PATHS if p.current.endswith("poll.pid"))
    write(pidfile.legacy, str(os.getpid()))
    write(POLL_STATE.legacy)
    assert main(["state", "migrate"]) == 1
    assert "looks like it is running" in capsys.readouterr().err
    assert os.path.exists(POLL_STATE.legacy)  # nothing moved

    assert main(["state", "migrate", "--force"]) == 0
    assert os.path.exists(POLL_STATE.current)


def test_state_migrate_dry_run_ignores_a_running_daemon(capsys):
    pidfile = next(p for p in state.PATHS if p.current.endswith("poll.pid"))
    write(pidfile.legacy, str(os.getpid()))
    write(POLL_STATE.legacy)
    assert main(["state", "migrate", "--dry-run"]) == 0
    assert "would move" in capsys.readouterr().out
    assert not os.path.exists(POLL_STATE.current)


def test_state_migrate_with_nothing_to_do(capsys):
    assert main(["state", "migrate"]) == 0
    assert "nothing to migrate" in capsys.readouterr().out
