"""Unit tests for ``the-loop install`` / ``the-loop upgrade`` (issue-152).

Planning is pure — it takes the machine as an argument (:class:`the_loop.install.Env`)
— so almost everything here asserts on the argv a given (component, scope, upgrade,
probe result) produces, without a subprocess ever running. The few tests that do execute
steps drive fakes.

Same rule as ``test_trust.py`` / ``test_harness_plugins.py``: every test that can reach a
settings file drives a **fake HOME** under ``tmp_path``, because the file under test would
otherwise be the developer's real ``~/.claude/settings.json``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from the_loop import install
from the_loop.harness_plugins import MARKETPLACE_NAME, PLUGIN_KEY


# -- fakes ---------------------------------------------------------------------


class FakeRunner:
    """Records argv, and replays canned results keyed by a command fragment."""

    def __init__(
        self, results: Optional[Dict[str, subprocess.CompletedProcess]] = None
    ):
        self.calls: List[Dict[str, object]] = []
        self._results = results or {}

    def __call__(self, argv, cwd=None, timeout=None):
        self.calls.append({"argv": list(argv), "cwd": cwd})
        for fragment, result in self._results.items():
            if fragment in " ".join(argv):
                return result
        return subprocess.CompletedProcess(argv, 0, "", "")

    @property
    def argvs(self) -> List[List[str]]:
        return [call["argv"] for call in self.calls]  # type: ignore[misc]


def completed(
    code: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["fake"], code, stdout, stderr)


def env_for(
    home: Path,
    *,
    binaries=("claude", "git", "uv"),
    package_dir: Optional[Path] = None,
    executable: str = "/usr/bin/python3",
    runner: Optional[FakeRunner] = None,
) -> install.Env:
    """An :class:`~the_loop.install.Env` describing an imaginary machine."""
    available = set(binaries)
    return install.Env(
        home=home,
        which=lambda name: f"/usr/bin/{name}" if name in available else None,
        executable=executable,
        package_dir=package_dir or (home / "lib" / "site-packages" / "the_loop"),
        run=runner or FakeRunner(),
    )


def summaries(steps) -> List[str]:
    return [step.summary for step in steps]


def argv_of(steps) -> List[List[str]]:
    return [list(step.argv) for step in steps if step.argv]


# -- the marketplace source (R7, Security §1) ----------------------------------


def test_marketplace_repo_prefers_the_flag_then_config_then_the_default():
    assert install.resolve_marketplace_repo("me/fork", {"routing": {}}) == "me/fork"
    assert (
        install.resolve_marketplace_repo(
            "", {"routing": {"harnessPlugins": {"marketplaceRepo": "team/loop"}}}
        )
        == "team/loop"
    )
    assert install.resolve_marketplace_repo("", {}) == install.DEFAULT_MARKETPLACE_REPO

    # An empty configured value means "I register the marketplace myself" to the daemon;
    # an install has nothing to install *from*, so it falls back to the shipped default.
    assert (
        install.resolve_marketplace_repo(
            "", {"routing": {"harnessPlugins": {"marketplaceRepo": ""}}}
        )
        == install.DEFAULT_MARKETPLACE_REPO
    )


@pytest.mark.parametrize(
    "value",
    [
        "not-a-repo",
        "owner/repo; rm -rf /",
        "https://github.com/owner/repo",
        "owner/repo/extra",
        "$(whoami)/repo",
    ],
)
def test_an_invalid_marketplace_repo_refuses_the_plugin_steps(tmp_path, value):
    """It never reaches an argv, a URL or a settings file — it stops the plan."""
    with pytest.raises(install.InvalidMarketplace) as excinfo:
        install.plan(["claude"], marketplace_repo=value, env=env_for(tmp_path / "home"))
    assert value in str(excinfo.value)


def test_an_invalid_marketplace_repo_does_not_block_the_cli_component(tmp_path):
    """Only the plugin steps depend on it, so `install cli` still plans."""
    steps = install.plan(
        ["cli"], marketplace_repo="nonsense", env=env_for(tmp_path / "home")
    )
    assert steps and all(step.component == "cli" for step in steps)


# -- how the running CLI was installed (R2.2, R2.3, R3.2) ----------------------


@pytest.mark.parametrize(
    "package_dir, expected",
    [
        (
            "/home/u/.local/share/uv/tools/the-loopy-one/lib/python3.12/site-packages/the_loop",
            "uv-tool",
        ),
        (
            "/home/u/.local/pipx/venvs/the-loopy-one/lib/python3.12/site-packages/the_loop",
            "pipx",
        ),
        ("/usr/lib/python3.12/site-packages/the_loop", "pip"),
    ],
)
def test_cli_method_is_read_off_the_running_package(tmp_path, package_dir, expected):
    env = env_for(tmp_path / "home", package_dir=Path(package_dir))
    assert install.cli_method(env)[0] == expected


def test_cli_method_detects_a_source_checkout(tmp_path):
    checkout = tmp_path / "the-loop" / "cli"
    (checkout / "the_loop").mkdir(parents=True)
    checkout.joinpath("pyproject.toml").write_text(
        'name = "the-loopy-one"\n', encoding="utf-8"
    )
    env = env_for(tmp_path / "home", package_dir=checkout / "the_loop")
    method, detail = install.cli_method(env)
    assert method == "source"
    assert str(checkout) in detail


@pytest.mark.parametrize(
    "method_dir, upgrade, expected",
    [
        (
            "/x/uv/tools/the-loopy-one/lib/py/site-packages/the_loop",
            False,
            ["/usr/bin/uv", "tool", "install", "the-loopy-one"],
        ),
        (
            "/x/uv/tools/the-loopy-one/lib/py/site-packages/the_loop",
            True,
            ["/usr/bin/uv", "tool", "upgrade", "the-loopy-one"],
        ),
        (
            "/x/pipx/venvs/the-loopy-one/lib/py/site-packages/the_loop",
            True,
            ["/usr/bin/pipx", "upgrade", "the-loopy-one"],
        ),
    ],
)
def test_cli_steps_use_the_method_that_owns_the_running_copy(
    tmp_path, method_dir, upgrade, expected
):
    env = env_for(
        tmp_path / "home",
        binaries=("uv", "pipx"),
        package_dir=Path(method_dir),
    )
    steps = install.plan(["cli"], upgrade=upgrade, env=env)
    assert argv_of(steps) == [expected]


def test_cli_pip_method_installs_with_the_running_interpreter(tmp_path):
    env = env_for(tmp_path / "home", binaries=(), executable="/opt/py/bin/python")
    steps = install.plan(["cli"], upgrade=True, env=env)
    assert argv_of(steps) == [
        ["/opt/py/bin/python", "-m", "pip", "install", "--upgrade", "the-loopy-one"]
    ]


def test_a_source_checkout_is_skipped_not_installed_over(tmp_path):
    checkout = tmp_path / "the-loop" / "cli"
    (checkout / "the_loop").mkdir(parents=True)
    checkout.joinpath("pyproject.toml").write_text(
        'name = "the-loopy-one"\n', encoding="utf-8"
    )
    env = env_for(tmp_path / "home", package_dir=checkout / "the_loop")
    steps = install.plan(["cli"], upgrade=True, env=env)
    assert [step.state for step in steps] == ["skipped"]
    assert not argv_of(steps)
    assert "source checkout" in steps[0].detail


def test_project_scope_installs_the_cli_into_the_projects_virtualenv(tmp_path):
    project = tmp_path / "repo"
    venv_python = project / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")
    steps = install.plan(
        ["cli"], scope="project", project_dir=project, env=env_for(tmp_path / "home")
    )
    assert argv_of(steps) == [
        [str(venv_python), "-m", "pip", "install", "the-loopy-one"]
    ]


def test_project_scope_without_a_virtualenv_is_skipped_not_widened(tmp_path):
    """R3.4: never quietly install at a scope other than the one asked for."""
    steps = install.plan(
        ["cli"],
        scope="project",
        project_dir=tmp_path / "repo",
        env=env_for(tmp_path / "home"),
    )
    assert [step.state for step in steps] == ["skipped"]
    assert "--scope user" in steps[0].detail


# -- probing a harness (R6.1) --------------------------------------------------


def test_probe_reads_the_surface_off_the_binary(tmp_path):
    runner = FakeRunner(
        {
            "plugin install --help": completed(0, "Options:\n  -s, --scope <scope>\n"),
            "plugin --help": completed(
                0, "Commands:\n  marketplace  Manage\n  install\n"
            ),
        }
    )
    surface = install.probe("claude", env_for(tmp_path / "home", runner=runner))
    assert surface.has_plugin_cli and surface.supports_scope
    assert runner.argvs[0] == ["/usr/bin/claude", "plugin", "--help"]


def test_probe_reports_no_surface_when_the_help_fails(tmp_path):
    runner = FakeRunner({"plugin": completed(1, "", "unknown command")})
    surface = install.probe("claude", env_for(tmp_path / "home", runner=runner))
    assert not surface.has_plugin_cli and not surface.supports_scope


def test_probe_needs_an_install_command_not_just_a_marketplace(tmp_path):
    """A binary with `plugin marketplace add` but no `plugin install` has no surface.

    The split is real — Cursor 2.5 is the documented example (issue-157) — and probing
    only the marketplace would make the-loop run an install that cannot work and report
    `failed`. The honest answer is "no surface", which routes to the settings fallback.
    """
    runner = FakeRunner(
        {
            "plugin install --help": completed(1, "", "unknown command: install"),
            "plugin --help": completed(
                0, "Commands:\n  marketplace  Manage marketplaces"
            ),
        }
    )
    env = env_for(tmp_path / "home", runner=runner)
    surface = install.probe("claude", env)
    assert not surface.has_plugin_cli and not surface.supports_scope

    steps = install.plan(["claude"], marketplace_repo="me/loop", env=env)
    assert not argv_of(steps)
    assert install.execute(steps, dry_run=False)[0].outcome == "applied"
    assert (tmp_path / "home" / ".claude" / "settings.json").is_file()


def test_probe_reports_a_missing_binary(tmp_path):
    surface = install.probe("claude", env_for(tmp_path / "home", binaries=()))
    assert surface.path is None and not surface.has_plugin_cli


def test_probe_survives_a_hanging_binary(tmp_path):
    def hang(argv, cwd=None, timeout=None):
        raise subprocess.TimeoutExpired(argv, timeout or 1)

    env = env_for(tmp_path / "home")
    env.run = hang  # type: ignore[assignment]
    assert not install.probe("claude", env).has_plugin_cli


# -- Claude Code (R1.1, R2.4, R3.1-R3.3, R6.2) ---------------------------------


def _claude_env(tmp_path, *, scope_flag=True, runner=None):
    runner = runner or FakeRunner(
        {
            "plugin install --help": completed(
                0, "  -s, --scope <scope>" if scope_flag else "  -h, --help"
            ),
            "plugin --help": completed(0, "  marketplace  Manage marketplaces"),
        }
    )
    return env_for(tmp_path / "home", runner=runner), runner


def test_claude_install_uses_the_harness_cli_with_the_scope(tmp_path):
    env, _ = _claude_env(tmp_path)
    steps = install.plan(["claude"], marketplace_repo="me/loop", env=env)
    assert argv_of(steps) == [
        [
            "/usr/bin/claude",
            "plugin",
            "marketplace",
            "add",
            "me/loop",
            "--scope",
            "user",
        ],
        ["/usr/bin/claude", "plugin", "install", PLUGIN_KEY, "--scope", "user"],
    ]


def test_claude_upgrade_refreshes_the_marketplace_first(tmp_path):
    env, _ = _claude_env(tmp_path)
    steps = install.plan(["claude"], upgrade=True, env=env)
    assert argv_of(steps) == [
        ["/usr/bin/claude", "plugin", "marketplace", "update", MARKETPLACE_NAME],
        ["/usr/bin/claude", "plugin", "update", PLUGIN_KEY, "--scope", "user"],
    ]


def test_claude_project_scope_runs_in_the_project_directory(tmp_path):
    env, _ = _claude_env(tmp_path)
    project = tmp_path / "repo"
    project.mkdir()
    steps = install.plan(["claude"], scope="project", project_dir=project, env=env)
    assert all(step.cwd == project for step in steps)
    assert all("--scope" in step.argv and "project" in step.argv for step in steps)


def test_claude_scope_is_omitted_when_the_binary_does_not_accept_it(tmp_path):
    env, _ = _claude_env(tmp_path, scope_flag=False)
    steps = install.plan(["claude"], env=env)
    assert all("--scope" not in step.argv for step in steps)


def test_claude_project_scope_is_skipped_when_the_binary_cannot_express_it(tmp_path):
    """A scope that cannot be honoured is skipped, never widened to the user."""
    env, _ = _claude_env(tmp_path, scope_flag=False)
    project = tmp_path / "repo"
    project.mkdir()
    steps = install.plan(["claude"], scope="project", project_dir=project, env=env)
    assert [step.state for step in steps] == ["skipped"]


def test_claude_falls_back_to_the_settings_file_without_a_plugin_cli(tmp_path):
    env = env_for(tmp_path / "home", binaries=("git",))
    steps = install.plan(["claude"], marketplace_repo="me/loop", env=env)
    assert not argv_of(steps)
    results = install.execute(steps, dry_run=False)
    assert [r.outcome for r in results] == ["applied"]
    settings = json.loads(
        (tmp_path / "home" / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert (
        settings["extraKnownMarketplaces"][MARKETPLACE_NAME]["source"]["repo"]
        == "me/loop"
    )
    assert settings["enabledPlugins"][PLUGIN_KEY] is True


def test_the_claude_fallback_at_project_scope_writes_the_project_settings(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()
    env = env_for(tmp_path / "home", binaries=())
    steps = install.plan(["claude"], scope="project", project_dir=project, env=env)
    install.execute(steps, dry_run=False)
    assert (project / ".claude" / "settings.json").is_file()
    assert not (tmp_path / "home" / ".claude" / "settings.json").exists()


def test_the_claude_fallback_is_idempotent(tmp_path):
    env = env_for(tmp_path / "home", binaries=())
    install.execute(install.plan(["claude"], env=env), dry_run=False)
    again = install.execute(install.plan(["claude"], env=env), dry_run=False)
    assert [r.outcome for r in again] == ["already"]


# -- components, outcomes, dry-run, exit code (R1.3, R1.4, R4, R5) -------------


def test_components_default_to_the_cli_plus_detected_harnesses(tmp_path):
    env = env_for(tmp_path / "home", binaries=("claude", "git"))
    assert install.resolve_components([], env) == ["cli", "claude"]


def test_an_undetected_harness_is_not_in_the_default_set(tmp_path):
    env = env_for(tmp_path / "home", binaries=("git",))
    assert install.resolve_components([], env) == ["cli"]


def test_components_all_selects_every_component_even_when_undetected(tmp_path):
    env = env_for(tmp_path / "home", binaries=())
    assert install.resolve_components(["all"], env) == ["cli", "claude"]


def test_cursor_is_not_a_component_yet(tmp_path):
    """Parked on the owner's call (PR #153); tracked as issue-157."""
    with pytest.raises(ValueError):
        install.resolve_components(["cursor"], env_for(tmp_path / "home"))


def test_an_unknown_component_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        install.resolve_components(["emacs"], env_for(tmp_path / "home"))


def test_dry_run_executes_nothing_and_reports_the_plan(tmp_path):
    runner = FakeRunner(
        {
            "plugin install --help": completed(0, "--scope"),
            "plugin --help": completed(0, "marketplace"),
        }
    )
    env = env_for(tmp_path / "home", runner=runner)
    steps = install.plan(["claude"], env=env)
    before = len(runner.calls)
    results = install.execute(steps, dry_run=True)
    assert len(runner.calls) == before  # the probe ran at plan time; nothing since
    assert [r.outcome for r in results] == ["planned", "planned"]
    assert not (tmp_path / "home" / ".claude").exists()


def test_a_failing_step_is_reported_and_exits_non_zero(tmp_path):
    runner = FakeRunner(
        {
            "plugin install --help": completed(0, "--scope"),
            "plugin --help": completed(0, "marketplace"),
            "plugin install the-loop": completed(2, "", "boom: no such marketplace"),
        }
    )
    env = env_for(tmp_path / "home", runner=runner)
    results = install.execute(install.plan(["claude"], env=env), dry_run=False)
    assert [r.outcome for r in results] == ["applied", "failed"]
    assert "boom" in results[-1].detail
    assert install.exit_code(results) == 1


def test_exit_code_is_zero_when_nothing_failed(tmp_path):
    results = [
        install.StepResult("cli", "s", "applied", "", ""),
        install.StepResult("claude", "s", "already", "", ""),
        install.StepResult("cli", "s", "skipped", "", "source checkout"),
    ]
    assert install.exit_code(results) == 0


def test_one_component_failing_does_not_stop_the_others(tmp_path):
    """R1.4: components are independent."""
    runner = FakeRunner({"pip install": completed(1, "", "no network")})
    env = env_for(tmp_path / "home", binaries=(), runner=runner)
    steps = install.plan(["cli", "claude"], env=env)
    results = install.execute(steps, dry_run=False)
    assert [r.component for r in results] == ["cli", "claude"]
    assert results[0].outcome == "failed" and results[1].outcome == "applied"


def test_every_step_is_an_argv_list_never_a_shell_string(tmp_path):
    """Security §2: nothing configured can become shell syntax."""
    runner = FakeRunner(
        {
            "plugin install --help": completed(0, "--scope"),
            "plugin --help": completed(0, "marketplace"),
        }
    )
    env = env_for(tmp_path / "home", runner=runner)
    steps = install.plan(["cli", "claude"], marketplace_repo="me/loop", env=env)
    for step in steps:
        assert isinstance(step.argv, list)
        assert all(isinstance(part, str) for part in step.argv)
