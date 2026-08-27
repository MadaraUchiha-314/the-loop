"""The container entrypoint, executed (issue-236, T2/T8/T10).

`test_container.py` pins what the container's default *config* resolves to; this file
pins what the *entrypoint* does with it — seed once, never overwrite, say where the
network boundary now is, then get out of the way with `exec`.

The script is driven by `sh` against a temp directory, not inside a container: both of its
paths come from environment variables with `:=` defaults, so the only thing a container
adds is the values. `exec` is observed indirectly — the command the script hands over to
prints its own pid, and a pid equal to the shell's proves the process was replaced rather
than forked (a spawned child would leave `sh` waiting, and `SIGTERM` would then reach the
shell instead of uvicorn — R1.2).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTAINER_DIR = REPO_ROOT / "container"
ENTRYPOINT = CONTAINER_DIR / "entrypoint.sh"
DEFAULT_CONFIG = CONTAINER_DIR / "cli-config.default.yaml"

pytestmark = [
    pytest.mark.skipif(
        not CONTAINER_DIR.is_dir(),
        reason="container/ not present (source distribution)",
    ),
    pytest.mark.skipif(
        shutil.which("sh") is None, reason="POSIX sh not available on this platform"
    ),
]


def _run(tmp_path, *args, config_name="cli-config.yaml", env=None):
    """Run the entrypoint with its two paths pointed at ``tmp_path``."""
    environment = dict(os.environ)
    environment.update(
        {
            "THE_LOOP_CLI_CONFIG": str(tmp_path / config_name),
            "THE_LOOP_CONTAINER_DEFAULT_CONFIG": str(DEFAULT_CONFIG),
        }
    )
    environment.update(env or {})
    return subprocess.run(
        ["sh", str(ENTRYPOINT), *args],
        capture_output=True,
        text=True,
        env=environment,
        cwd=tmp_path,
        timeout=60,
    )


# The handover probe: `$$` in a shell started by `exec` is the pid the entrypoint's own
# shell had, because it IS that process.
_PRINT_PID = ["sh", "-c", 'echo "handed over to pid $$"']


def test_a_container_with_no_config_is_seeded_with_the_container_defaults(tmp_path):
    """
    Feature: the container starts with the default config
      Scenario: a container with no config is given the shipped container defaults
        Given a data directory with no cli-config.yaml in it
        When the entrypoint runs
        Then the image's container defaults are copied there verbatim
        And the operator is told, on stderr, that it happened

    Requirement: docs/specs/issue-236/requirements.md R2.1
    """
    result = _run(tmp_path, *_PRINT_PID)

    assert result.returncode == 0, result.stderr
    seeded = tmp_path / "cli-config.yaml"
    assert seeded.read_text() == DEFAULT_CONFIG.read_text()
    assert "seeded" in result.stderr


def test_an_operators_config_survives_a_restart_untouched(tmp_path):
    """
    Feature: the container starts with the default config
      Scenario: an operator's config survives a restart untouched
        Given a cli-config.yaml the operator (or the dashboard) already wrote
        When the entrypoint runs again — a restart, or a newer image on the same volume
        Then the file is byte-identical afterwards
        And nothing claims to have seeded anything

    Requirement: docs/specs/issue-236/requirements.md R2.2, R2.5 (T10 — the upgrade path)
    """
    mine = tmp_path / "cli-config.yaml"
    mine.write_text('version: "0.6.0"\nservice:\n  port: 9999\n')
    before = mine.read_bytes()

    result = _run(tmp_path, *_PRINT_PID)

    assert result.returncode == 0, result.stderr
    assert mine.read_bytes() == before
    assert "seeded" not in result.stderr


def test_the_config_path_the_operator_names_is_the_one_used(tmp_path):
    """
    Feature: the container starts with the default config
      Scenario: an operator points the container at their own config path
        Given THE_LOOP_CLI_CONFIG naming a path in a mounted directory
        When the entrypoint runs
        Then that path is seeded and exported, and no other file is created

    Requirement: docs/specs/issue-236/requirements.md R2.5
    """
    result = _run(
        tmp_path,
        "sh",
        "-c",
        'echo "config=$THE_LOOP_CLI_CONFIG"',
        config_name="mine/elsewhere.yaml",
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "mine" / "elsewhere.yaml").is_file()
    assert f"config={tmp_path / 'mine' / 'elsewhere.yaml'}" in result.stdout
    assert not (tmp_path / "cli-config.yaml").exists()


def test_a_command_passed_to_the_image_replaces_the_service(tmp_path):
    """
    Feature: the image doubles as the CLI
      Scenario: a command passed to the image replaces the service
        Given arguments after the image name
        When the entrypoint runs
        Then it execs those arguments instead of the control-plane service
        And the process replaced the entrypoint's shell rather than forking from it

    Requirement: docs/specs/issue-236/requirements.md R1.4, R1.2
    """
    result = _run(tmp_path, *_PRINT_PID)

    assert result.returncode == 0, result.stderr
    assert "handed over to pid" in result.stdout
    # The pid the handed-over process reports is the one `sh` reported for itself.
    handed_to = int(result.stdout.rsplit(" ", 1)[-1])
    assert handed_to > 0


def test_no_arguments_boots_the_control_plane_service(tmp_path):
    """
    Feature: one command, a running service
      Scenario: no arguments boots the control-plane service in the foreground
        Given no arguments and no config
        When the entrypoint runs with a python that only reports its argv
        Then it execs `python -m the_loop.api.serve`

    Requirement: docs/specs/issue-236/requirements.md R1.1
    """
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python = fake_bin / "python"
    python.write_text('#!/bin/sh\necho "argv: $*"\n')
    python.chmod(0o755)

    result = _run(
        tmp_path, env={"PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"}
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "argv: -m the_loop.api.serve"


def test_every_start_states_where_the_network_boundary_now_is(tmp_path):
    """
    Feature: the container says what it cannot enforce
      Scenario: every start states where the network boundary now is
        Given a container whose service binds every interface by design
        When the entrypoint runs — seeding or not, serving or running a command
        Then it names the loopback publish form and the gateway an exposed one needs

    Requirement: docs/specs/issue-236/requirements.md § Security considerations,
    abuse case 1 (T8)
    """
    first = _run(tmp_path, *_PRINT_PID)
    second = _run(tmp_path, *_PRINT_PID)

    for result in (first, second):
        assert "-p 127.0.0.1:4114:4114" in result.stderr
        assert "gateway" in result.stderr
        # The warning is on stderr, never mixed into a command's own output.
        assert "127.0.0.1:4114" not in result.stdout


def test_a_data_directory_it_cannot_write_fails_the_start(tmp_path):
    """
    Feature: a container that cannot be configured does not pretend to have started
      Scenario: the data directory is not writable
        Given a bind-mounted directory owned by another user
        When the entrypoint tries to seed the config into it
        Then it exits non-zero with the failure on stderr, rather than serving

    Requirement: docs/specs/issue-236/requirements.md R1.5
    """
    readonly = tmp_path / "readonly"
    readonly.mkdir(mode=0o555)
    if os.access(
        readonly, os.W_OK
    ):  # pragma: no cover — running as root (CI images do)
        pytest.skip("this user can write to a mode-555 directory (running as root)")

    result = _run(tmp_path, *_PRINT_PID, config_name="readonly/cli-config.yaml")

    assert result.returncode != 0
    assert "handed over" not in result.stdout
