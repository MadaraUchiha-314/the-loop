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
from the_loop.harness_plugins import MARKETPLACE_NAME, PLUGIN_KEY, PLUGIN_NAME


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


# -- Cursor (issue-157: R1-R5) -------------------------------------------------


def _cursor_env(
    tmp_path,
    *,
    surface: bool = True,
    install_help: bool = True,
    scope_flag: bool = True,
    git: bool = True,
):
    """A machine with `cursor-agent` answering the probe however the test needs.

    ``surface``/``install_help`` are the two halves of :func:`the_loop.install.probe`:
    a binary can advertise ``plugin marketplace`` and still have no working
    ``plugin install`` (Cursor 2.5 is the documented example), and that combination has
    to route to the fallback rather than to a command that cannot work.
    """
    runner = FakeRunner(
        {
            "plugin install --help": completed(
                0 if install_help else 1,
                "  -s, --scope <scope>" if scope_flag else "  -h, --help",
            ),
            "plugin --help": completed(
                0 if surface else 1, "  marketplace  Manage marketplaces"
            ),
        }
    )
    binaries = ["cursor-agent"] + (["git"] if git else [])
    return env_for(tmp_path / "home", binaries=tuple(binaries), runner=runner), runner


def _clone_dir(tmp_path) -> Path:
    return install.cursor_plugin_dir(env_for(tmp_path / "home"))


def _make_checkout(tmp_path) -> Path:
    """A directory that looks like a checkout this command created."""
    directory = _clone_dir(tmp_path)
    (directory / ".git").mkdir(parents=True)
    return directory


def test_cursor_is_an_accepted_component(tmp_path):
    """R2.4 — no longer rejected as unknown (it was, until issue-157)."""
    env = env_for(tmp_path / "home")
    assert install.resolve_components(["cursor"], env) == ["cursor"]


def test_cursor_joins_the_default_set_when_its_binary_is_present(tmp_path):
    """R2.1/R2.2 — detected on PATH, and only then."""
    present = env_for(tmp_path / "home", binaries=("claude", "cursor-agent"))
    assert install.resolve_components([], present) == ["cli", "claude", "cursor"]

    absent = env_for(tmp_path / "home", binaries=("claude",))
    assert install.resolve_components([], absent) == ["cli", "claude"]


def test_cursor_drives_its_own_plugin_cli_when_the_binary_has_one(tmp_path):
    """R1.1/R5.1 — the same two steps Claude gets, off what the binary reported."""
    env, _ = _cursor_env(tmp_path)
    steps = install.plan(["cursor"], marketplace_repo="me/loop", env=env)
    assert argv_of(steps) == [
        [
            "/usr/bin/cursor-agent",
            "plugin",
            "marketplace",
            "add",
            "me/loop",
            "--scope",
            "user",
        ],
        ["/usr/bin/cursor-agent", "plugin", "install", PLUGIN_KEY, "--scope", "user"],
    ]


def test_cursor_upgrade_via_its_plugin_cli_refreshes_the_marketplace_first(tmp_path):
    """R1.2 — the R2.4 rule of issue-152 applies to every harness that has a CLI."""
    env, _ = _cursor_env(tmp_path)
    steps = install.plan(["cursor"], upgrade=True, env=env)
    assert argv_of(steps) == [
        ["/usr/bin/cursor-agent", "plugin", "marketplace", "update", MARKETPLACE_NAME],
        ["/usr/bin/cursor-agent", "plugin", "update", PLUGIN_KEY, "--scope", "user"],
    ]


def test_cursor_project_scope_passes_through_a_scope_the_binary_accepts(tmp_path):
    """R3.1 — the moment cursor-agent expresses scope, the-loop stops skipping."""
    env, _ = _cursor_env(tmp_path)
    project = tmp_path / "repo"
    project.mkdir()
    steps = install.plan(["cursor"], scope="project", project_dir=project, env=env)
    assert all(step.cwd == project for step in steps)
    assert all("--scope" in step.argv and "project" in step.argv for step in steps)


def test_cursor_falls_back_to_the_documented_local_clone(tmp_path):
    """R4.1/R4.2 — the route docs/guide/installation.md already describes."""
    env, _ = _cursor_env(tmp_path, surface=False)
    steps = install.plan(["cursor"], marketplace_repo="me/loop", env=env)
    assert argv_of(steps) == [
        [
            "/usr/bin/git",
            "clone",
            "--",
            "https://github.com/me/loop.git",
            str(_clone_dir(tmp_path)),
        ]
    ]


def test_cursor_marketplace_without_a_working_install_takes_the_fallback(tmp_path):
    """R5.2 — the split the issue-152 probe was hardened for, now exercised on Cursor."""
    env, _ = _cursor_env(tmp_path, install_help=False)
    steps = install.plan(["cursor"], env=env)
    assert [step.argv[:2] for step in steps] == [["/usr/bin/git", "clone"]]


def test_cursor_probe_failure_falls_back_rather_than_propagating(tmp_path):
    """R5.3 — a hanging binary is 'no surface', not an error."""

    def hang(argv, cwd=None, timeout=None):
        raise subprocess.TimeoutExpired(argv, timeout or 1)

    env, _ = _cursor_env(tmp_path)
    env.run = hang  # type: ignore[assignment]
    steps = install.plan(["cursor"], env=env)
    assert [step.argv[1] for step in steps] == ["clone"]


def test_cursor_upgrade_pulls_the_existing_checkout(tmp_path):
    """R1.2/R4.1 — fast-forward only, so a developer's commits are never merged over."""
    directory = _make_checkout(tmp_path)
    env, _ = _cursor_env(tmp_path, surface=False)
    steps = install.plan(["cursor"], upgrade=True, env=env)
    assert argv_of(steps) == [
        ["/usr/bin/git", "-C", str(directory), "pull", "--ff-only"]
    ]


def test_cursor_install_over_an_existing_checkout_reports_already(tmp_path):
    """R4.3 — a checkout the command owns is a state it can determine itself."""
    directory = _make_checkout(tmp_path)
    env, runner = _cursor_env(tmp_path, surface=False)
    steps = install.plan(["cursor"], env=env)
    before = len(runner.calls)
    results = install.execute(steps, dry_run=False)
    assert [r.outcome for r in results] == ["already"]
    assert str(directory) in results[0].command
    assert len(runner.calls) == before  # nothing was run


def test_cursor_upgrade_without_a_checkout_is_skipped_not_installed(tmp_path):
    """R1.3 — an upgrade never becomes an install behind the operator's back."""
    env, _ = _cursor_env(tmp_path, surface=False)
    steps = install.plan(["cursor"], upgrade=True, env=env)
    assert [step.state for step in steps] == ["skipped"]
    assert "the-loop install cursor" in steps[0].detail
    assert not argv_of(steps)


def test_cursor_leaves_an_occupied_destination_exactly_as_it_found_it(tmp_path):
    """R4.4 / abuse case 2 — never delete, never overwrite, never write inside."""
    directory = _clone_dir(tmp_path)
    directory.mkdir(parents=True)
    occupant = directory / "notes.txt"
    occupant.write_text("someone else's files\n", encoding="utf-8")
    stamp = occupant.stat().st_mtime_ns

    env, runner = _cursor_env(tmp_path, surface=False)
    steps = install.plan(["cursor"], env=env)
    before = len(runner.calls)
    results = install.execute(steps, dry_run=False)

    assert [r.outcome for r in results] == ["skipped"]
    assert str(directory) in results[0].detail
    assert len(runner.calls) == before
    assert occupant.read_text(encoding="utf-8") == "someone else's files\n"
    assert occupant.stat().st_mtime_ns == stamp
    assert list(directory.iterdir()) == [occupant]


def test_cursor_without_git_is_skipped_with_the_manual_command(tmp_path):
    """R4.5 — a missing precondition names the binary and prints the way out."""
    env, _ = _cursor_env(tmp_path, surface=False, git=False)
    steps = install.plan(["cursor"], marketplace_repo="me/loop", env=env)
    assert [step.state for step in steps] == ["skipped"]
    assert "git" in steps[0].detail
    assert "https://github.com/me/loop" in steps[0].detail


def test_cursor_project_scope_is_skipped_never_widened(tmp_path):
    """R3.2/R3.3 / abuse case 4 — no path leads from --scope project to a clone."""
    env, _ = _cursor_env(tmp_path, surface=False)
    project = tmp_path / "repo"
    project.mkdir()
    steps = install.plan(["cursor"], scope="project", project_dir=project, env=env)
    assert [step.state for step in steps] == ["skipped"]
    assert not argv_of(steps)
    assert "--scope user" in steps[0].detail
    assert not _clone_dir(tmp_path).exists()


def test_cursor_dry_run_creates_nothing_and_runs_no_git(tmp_path):
    """R4.6 / abuse case 3 — the same plan, with the execution left out."""
    env, runner = _cursor_env(tmp_path, surface=False)
    steps = install.plan(["cursor"], env=env)
    before = len(runner.calls)
    results = install.execute(steps, dry_run=True)
    assert [r.outcome for r in results] == ["planned"]
    assert len(runner.calls) == before
    assert not _clone_dir(tmp_path).exists()


@pytest.mark.parametrize(
    "value",
    [
        "not-a-repo",
        "owner/repo; rm -rf /",
        "https://github.com/owner/repo",
        "--upload-pack=touch /tmp/pwned",
        "$(whoami)/repo",
    ],
)
def test_an_invalid_marketplace_repo_refuses_the_cursor_steps(tmp_path, value):
    """Abuse case 1 — validated before it can become a URL, let alone an argv."""
    env, runner = _cursor_env(tmp_path, surface=False)
    with pytest.raises(install.InvalidMarketplace) as excinfo:
        install.plan(["cursor"], marketplace_repo=value, env=env)
    assert value in str(excinfo.value)
    assert not any("git" in " ".join(argv) for argv in runner.argvs)


def test_the_clone_url_is_built_only_from_the_validated_repo(tmp_path):
    """Security §1 — the URL has one variable part, and it is `owner/repo`."""
    env, _ = _cursor_env(tmp_path, surface=False)
    steps = install.plan(["cursor"], marketplace_repo="acme/fork", env=env)
    assert "https://github.com/acme/fork.git" in steps[0].argv


def test_the_cursor_clone_lives_under_the_documented_path(tmp_path):
    """The path the installation guide prints, and the one the code uses, are one."""
    home = tmp_path / "home"
    assert install.cursor_plugin_dir(env_for(home)) == (
        home / ".cursor" / "plugins" / "local" / "the-loop"
    )


def test_the_documented_clone_path_is_the_one_the_code_uses():
    """What makes the fallback *documented* rather than invented (R4.1).

    ``CURSOR_PLUGIN_PARENT`` carries a comment claiming the code and
    ``docs/guide/installation.md`` cannot drift apart. Claims in comments do not hold
    themselves up — this is what holds it.
    """
    guide = (
        Path(__file__).resolve().parents[2] / "docs" / "guide" / "installation.md"
    ).read_text(encoding="utf-8")
    documented = f"~/{install.CURSOR_PLUGIN_PARENT.as_posix()}/{PLUGIN_NAME}"
    assert documented in guide, f"{documented} is no longer the route the guide prints"


def test_a_skipped_cursor_does_not_stop_the_other_components(tmp_path):
    """R1.4 — components are independent, whichever one cannot run."""
    env, _ = _cursor_env(tmp_path, surface=False, git=False)
    steps = install.plan(["claude", "cursor"], marketplace_repo="me/loop", env=env)
    results = install.execute(steps, dry_run=False)
    assert [(r.component, r.outcome) for r in results] == [
        ("claude", "applied"),
        ("cursor", "skipped"),
    ]
    assert install.exit_code(results) == 0


# -- components, outcomes, dry-run, exit code (R1.3, R1.4, R4, R5) -------------


def test_components_default_to_the_cli_plus_detected_harnesses(tmp_path):
    env = env_for(tmp_path / "home", binaries=("claude", "git"))
    assert install.resolve_components([], env) == ["cli", "claude"]


def test_an_undetected_harness_is_not_in_the_default_set(tmp_path):
    env = env_for(tmp_path / "home", binaries=("git",))
    assert install.resolve_components([], env) == ["cli"]


def test_components_all_selects_every_component_even_when_undetected(tmp_path):
    env = env_for(tmp_path / "home", binaries=())
    assert install.resolve_components(["all"], env) == ["cli", "claude", "cursor"]


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
