"""Install and upgrade the-loop itself — the CLI and the harness plugin (issue-152).

the-loop ships as two artifacts: this CLI (``the-loopy-one`` on PyPI) and a plugin for
Claude Code. Putting either on a machine meant knowing the harness's marketplace
incantation and typing it *inside* an interactive session, and moving them forward meant
remembering which installer owned the copy you were running (issue-78). issue-143 already
had to teach the daemon to install the plugin before a spawn, because a session without
the plugin has no loop at all; this module is the same capability for a human or a CI job,
with a scope they can choose.

**Both harnesses, by the same mechanism** (issue-157). Cursor was parked on PR #153
because the first cut *hard-coded* a local clone, and as of Cursor 2.5 no CLI install
command was documented — "clone-and-hope with a permanently skipped project scope". It is
back on different terms, and :data:`BINARIES` plus a per-harness planner was the whole
extension point decision-057 promised: the clone is now the **fallback**, reached only
after :func:`probe` asks ``cursor-agent`` and it answers that it has no plugin surface. If
Cursor ships one, the-loop drives it with no release of ours.

Two rules shape everything here:

* **the-loop does not re-implement a harness's installer.** Where a harness exposes a
  plugin surface, we shell out to it and let the harness own fetching, versioning and
  scope. The surface is *asked for* (``<binary> plugin --help``), never assumed from a
  version number. Only when the binary is absent, or has no such surface, do we fall
  back — and only to a route this repository already documents: for Claude Code, the
  settings keys ``/plugin marketplace add`` + ``/plugin install`` write (the same two
  ``routing.harnessPlugins`` writes before a spawn); for Cursor, the local checkout under
  ``~/.cursor/plugins/local/`` that ``docs/guide/installation.md`` prints.
* **A plan, then its execution.** Everything becomes an ordered list of :class:`Step`,
  each carrying the exact argv (or the file it writes). ``--dry-run`` is "build the plan,
  print it, stop" rather than a second code path that could drift, and a step that cannot
  run says so at *plan* time, so a preview shows the skips too.

Security (see ``docs/specs/issue-152/requirements.md`` and
``docs/specs/issue-157/requirements.md`` § Security considerations): installing is code
execution, so the marketplace ``owner/repo`` is validated with ``harness_plugins``' own
pattern before it can reach an argv, a URL or a settings file; every command is an argv
list executed without a shell; the settings fallback goes through
:func:`the_loop.trust.update_json`, the single non-destructive writer; the Cursor fallback
writes exactly one path and never deletes, overwrites or writes inside a directory it did
not create as a checkout; and a scope that cannot be expressed is skipped rather than
widened.

Spec: docs/specs/issue-152/design.md (decision-057) · docs/specs/issue-157/design.md
(decision-064).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .harness_plugins import (
    DEFAULT_MARKETPLACE_REPO,
    MARKETPLACE_NAME,
    PLUGIN_KEY,
    PLUGIN_NAME,
    ClaudePluginStore,
    _REPO_RE,
)
from .trust import ClaudeTrustStore, TrustResult

logger = logging.getLogger("the-loop.install")

__all__ = [
    "COMPONENTS",
    "CURSOR_PLUGIN_PARENT",
    "DEFAULT_MARKETPLACE_REPO",
    "DISTRIBUTION",
    "Env",
    "HarnessSurface",
    "InvalidMarketplace",
    "Step",
    "StepResult",
    "cli_method",
    "cursor_plugin_dir",
    "default_env",
    "execute",
    "exit_code",
    "plan",
    "probe",
    "resolve_components",
    "resolve_marketplace_repo",
]

#: What can be installed. ``cli`` is this package; ``claude`` and ``cursor`` are the same
#: plugin, in the harness that hosts it.
COMPONENTS = ("cli", "claude", "cursor")

#: The harness binaries, by component. A mapping rather than a constant because the
#: plan/report machinery is harness-shaped: a third harness is an entry here plus its own
#: planner, not a new command. It is also what makes a harness *detected* for the default
#: component set, and what triggers marketplace validation in :func:`plan`.
BINARIES: Dict[str, str] = {"claude": "claude", "cursor": "cursor-agent"}

#: Where Cursor keeps locally checked-out plugins, relative to the operator's home. The
#: path lives here rather than inline so the code and ``docs/guide/installation.md``
#: cannot drift: the guide printing this exact command is what makes the clone a
#: *documented* fallback rather than an invented one.
CURSOR_PLUGIN_PARENT = Path(".cursor") / "plugins" / "local"

#: The PyPI distribution name — see decision-019 for why it is not ``the-loop``.
DISTRIBUTION = "the-loopy-one"

#: A help probe is a question, not work: it gets seconds, an install gets minutes.
PROBE_TIMEOUT = 20
STEP_TIMEOUT = 900


class InvalidMarketplace(ValueError):
    """The marketplace ``owner/repo`` is not one — refuses every plugin step."""


def _run(
    argv: Sequence[str], cwd: Optional[Path] = None, timeout: Optional[int] = None
) -> "subprocess.CompletedProcess[str]":
    """Execute ``argv`` with no shell, capturing output.

    The only place this module starts a process. ``shell=False`` (the default) is the
    security property: no configured or user-supplied value can become shell syntax.
    """
    return subprocess.run(  # noqa: S603 - argv list, never a shell string
        list(argv),
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


@dataclass
class Env:
    """The machine, injected so planning is testable without touching one."""

    home: Path = field(default_factory=Path.home)
    which: Callable[[str], Optional[str]] = shutil.which
    executable: str = sys.executable
    package_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent)
    run: Callable[..., "subprocess.CompletedProcess[str]"] = _run


def default_env() -> Env:
    """The real machine this process is running on."""
    return Env()


@dataclass
class HarnessSurface:
    """What a harness binary told us it can do — never what we assumed."""

    binary: str
    path: Optional[str] = None
    has_plugin_cli: bool = False
    supports_scope: bool = False


@dataclass
class Step:
    """One thing that has to happen, with the exact way it will happen.

    Exactly one of ``argv`` (run a command) and ``writer`` (write a config file) is set,
    unless ``state`` is pre-decided — that is a planner saying "this cannot run, and here
    is why" before anything executes, so ``--dry-run`` shows the skip too.
    """

    component: str
    summary: str
    argv: List[str] = field(default_factory=list)
    cwd: Optional[Path] = None
    writer: Optional[Callable[[], TrustResult]] = None
    target: str = ""
    state: str = ""
    detail: str = ""
    #: How this step runs, bound by :func:`plan` from the ``Env`` that planned it. A
    #: step is self-contained on purpose: an ``execute()`` that resolved the machine
    #: itself would run the *real* one against steps planned for another (under test,
    #: that means installing packages and writing the developer's own settings file).
    run: Callable[..., "subprocess.CompletedProcess[str]"] = _run

    def render(self) -> str:
        """The command, or the file this step writes — what the report shows."""
        if self.argv:
            return " ".join(self.argv)
        return self.target


@dataclass
class StepResult:
    """What actually happened to one :class:`Step`."""

    component: str
    summary: str
    outcome: str  # applied | already | skipped | failed | planned
    command: str
    detail: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "component": self.component,
            "summary": self.summary,
            "outcome": self.outcome,
            "command": self.command,
            "detail": self.detail,
        }


# -- resolution ----------------------------------------------------------------


def resolve_components(names: Sequence[str], env: Env) -> List[str]:
    """Which components to act on.

    Nothing named means the CLI plus every harness actually present on ``PATH`` — the
    useful default on a machine the operator is setting up. ``all`` is the explicit
    "every component, detected or not", so a missing harness is reported rather than
    quietly dropped.
    """
    requested = [str(name).strip().lower() for name in names if str(name).strip()]
    if not requested:
        detected = [
            name for name, binary in BINARIES.items() if env.which(binary) is not None
        ]
        return ["cli"] + detected
    if "all" in requested:
        return list(COMPONENTS)
    unknown = [name for name in requested if name not in COMPONENTS]
    if unknown:
        raise ValueError(
            f"unknown component(s): {', '.join(unknown)}; "
            f"choose from {', '.join(COMPONENTS)} or 'all'"
        )
    # De-duplicated, in the canonical order, so the report reads the same every run.
    return [name for name in COMPONENTS if name in requested]


def resolve_marketplace_repo(flag: str, cli_config: Optional[dict] = None) -> str:
    """``--from`` → ``routing.harnessPlugins.marketplaceRepo`` → the shipped default.

    One source of truth with the daemon (issue-143): an operator running a fork points
    that key once and every path — spawn and install alike — follows it.
    """
    if flag and str(flag).strip():
        return str(flag).strip()
    routing = ((cli_config or {}).get("routing") or {}) if cli_config else {}
    configured = (routing.get("harnessPlugins") or {}).get("marketplaceRepo")
    # An empty `marketplaceRepo` means something specific to the daemon — "enable the
    # plugin, I register the marketplace myself" — but there is nothing to install *from*
    # here, so an install falls back to the shipped default rather than refusing. The
    # resolved value is printed in the plan header, so the substitution is never silent.
    if configured is None or not str(configured).strip():
        return DEFAULT_MARKETPLACE_REPO
    return str(configured).strip()


def _validated_repo(repo: str) -> str:
    """``owner/repo``, or refuse.

    Registering a marketplace means running whatever that repository ships, in every
    session at that scope — so this value is checked before it can reach a subprocess,
    a URL or a settings file, with the same pattern ``routing.harnessPlugins`` applies.
    """
    value = str(repo or "").strip()
    if not _REPO_RE.match(value):
        raise InvalidMarketplace(
            f"marketplace repository {value!r} is not of the form owner/repo; "
            "refusing to install a plugin from it"
        )
    return value


# -- probing -------------------------------------------------------------------


def probe(binary: str, env: Env) -> HarnessSurface:
    """Ask ``binary`` whether it manages plugins, and whether it takes a scope.

    Asking is the point (R6.1): Claude Code exposes ``plugin marketplace add|update``,
    ``plugin install|update`` and ``--scope user|project|local`` today, and a harness
    release should move the-loop with it rather than past a pinned version check. A
    binary that is missing, errors, or hangs simply has no surface — the caller falls
    back to a documented route.
    """
    path = env.which(binary)
    surface = HarnessSurface(binary=binary, path=path)
    if not path:
        return surface
    help_text = _capture(env, [path, "plugin", "--help"])
    if help_text is None or "marketplace" not in help_text.lower():
        return surface
    # A marketplace command is not enough: `plugin install` is what we actually drive,
    # and the two do not always ship together. Cursor 2.5 is the live example of the
    # split — operators report `cursor-agent plugin marketplace add` existing while no
    # CLI install command is documented at all — and a future `claude` build could
    # rearrange its subcommands the same way. Probing only the marketplace would make
    # the-loop run an `install` that cannot work and report `failed`, when the honest
    # answer is "no surface" — which is what routes it to the documented fallback.
    install_help = _capture(env, [path, "plugin", "install", "--help"])
    if install_help is None:
        return surface
    surface.has_plugin_cli = True
    surface.supports_scope = "--scope" in install_help
    return surface


def _capture(env: Env, argv: Sequence[str]) -> Optional[str]:
    """``argv``'s output when it succeeded, else ``None`` (never raises)."""
    try:
        result = env.run(list(argv), timeout=PROBE_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("probe %s failed: %s", " ".join(argv), exc)
        return None
    if result.returncode != 0:
        return None
    return f"{result.stdout or ''}{result.stderr or ''}"


# -- the CLI itself ------------------------------------------------------------


def cli_method(env: Env) -> Tuple[str, str]:
    """How the *running* CLI was installed: ``source``/``uv-tool``/``pipx``/``pip``.

    Read off where the package actually lives rather than asked for as a flag — the
    operator forgetting which installer they used is the whole of issue-78.
    """
    package_dir = Path(env.package_dir)
    checkout = package_dir.parent
    pyproject = checkout / "pyproject.toml"
    if pyproject.is_file():
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover - unreadable file, treat as not-a-checkout
            text = ""
        if DISTRIBUTION in text:
            return "source", str(checkout)
    marker = str(package_dir).replace(os.sep, "/")
    if "/uv/tools/" in marker:
        return "uv-tool", str(package_dir)
    if "/pipx/" in marker:
        return "pipx", str(package_dir)
    return "pip", str(package_dir)


def _venv_python(project_dir: Path) -> Optional[Path]:
    """The project's own interpreter, if it has one."""
    for relative in (
        Path(".venv") / "bin" / "python",
        Path(".venv") / "Scripts" / "python.exe",
    ):
        candidate = Path(project_dir) / relative
        if candidate.exists():
            return candidate
    return None


def plan_cli(*, scope: str, upgrade: bool, project_dir: Path, env: Env) -> List[Step]:
    """Install/upgrade this package with the installer that owns it.

    Project scope means the project's **virtualenv**, deliberately not ``uv add`` or an
    edit to ``pyproject.toml``: installing a tool must not rewrite the operator's
    dependency manifest.
    """
    verb = "upgrade" if upgrade else "install"
    summary = f"{verb} the {DISTRIBUTION} CLI"
    if scope == "project":
        python = _venv_python(project_dir)
        if python is None:
            return [
                Step(
                    "cli",
                    summary,
                    state="skipped",
                    detail=(
                        f"no virtualenv at {Path(project_dir) / '.venv'}; create one "
                        "(e.g. `uv venv`), or install for your user with --scope user"
                    ),
                )
            ]
        argv = [str(python), "-m", "pip", "install"]
        if upgrade:
            argv.append("--upgrade")
        return [Step("cli", summary, argv=argv + [DISTRIBUTION])]

    method, detail = cli_method(env)
    if method == "source":
        return [
            Step(
                "cli",
                summary,
                state="skipped",
                detail=(
                    f"running from a source checkout at {detail}; update it with "
                    "`git pull` (and `uv sync`) rather than installing over it"
                ),
            )
        ]
    if method == "uv-tool" and env.which("uv"):
        return [
            Step(
                "cli",
                summary,
                argv=[str(env.which("uv")), "tool", verb, DISTRIBUTION],
            )
        ]
    if method == "pipx" and env.which("pipx"):
        return [Step("cli", summary, argv=[str(env.which("pipx")), verb, DISTRIBUTION])]
    argv = [env.executable, "-m", "pip", "install"]
    if upgrade:
        argv.append("--upgrade")
    return [Step("cli", summary, argv=argv + [DISTRIBUTION])]


# -- the plugin, per harness ---------------------------------------------------


def plan_claude(
    *, scope: str, upgrade: bool, project_dir: Path, repo: str, env: Env
) -> List[Step]:
    """Claude Code: its own plugin CLI when it has one, else the settings keys."""
    surface = probe(BINARIES["claude"], env)
    if surface.has_plugin_cli and surface.path:
        return _harness_cli_steps(
            "claude",
            surface,
            scope=scope,
            upgrade=upgrade,
            project_dir=project_dir,
            repo=repo,
        )

    settings = (
        Path(project_dir) / ".claude" / "settings.json" if scope == "project" else None
    )
    store = ClaudePluginStore(
        ClaudeTrustStore(home=str(env.home)), settings_file=settings
    )
    target = str(store.settings_path())
    reason = (
        "claude not found on PATH"
        if not surface.path
        else "this claude build exposes no `plugin` command"
    )
    return [
        Step(
            "claude",
            f"register {MARKETPLACE_NAME} ({repo}) and enable {PLUGIN_KEY}",
            writer=lambda: store.enable(repo),
            target=target,
            detail=f"{reason}; wrote the plugin settings directly",
        )
    ]


def cursor_plugin_dir(env: Env) -> Path:
    """Where the local-clone fallback puts the plugin.

    ``env.home`` rather than :meth:`Path.home` because every test drives a fake HOME —
    the directory under test would otherwise be the developer's own Cursor installation.
    """
    return Path(env.home) / CURSOR_PLUGIN_PARENT / PLUGIN_NAME


def plan_cursor(
    *, scope: str, upgrade: bool, project_dir: Path, repo: str, env: Env
) -> List[Step]:
    """Cursor: its own plugin CLI when it has one, else the documented local clone.

    The first branch is *literally* the Claude path — same helper, same two commands,
    same ``--scope`` pass-through — which is the point of asking the binary rather than
    reading a docs page: the day ``cursor-agent`` grows ``plugin install``, this takes it
    with no change here. Until then the probe reports no surface (a ``marketplace``
    command without a working ``install`` counts as none, R5.2) and the clone runs.
    """
    surface = probe(BINARIES["cursor"], env)
    if surface.has_plugin_cli and surface.path:
        return _harness_cli_steps(
            "cursor",
            surface,
            scope=scope,
            upgrade=upgrade,
            project_dir=project_dir,
            repo=repo,
        )
    reason = (
        "cursor-agent not found on PATH"
        if not surface.path
        else "this cursor-agent build exposes no usable `plugin` command"
    )
    return _cursor_clone_steps(
        scope=scope, upgrade=upgrade, repo=repo, env=env, reason=reason
    )


def _cursor_clone_steps(
    *, scope: str, upgrade: bool, repo: str, env: Env, reason: str
) -> List[Step]:
    """The fallback route, as one step whose outcome is decided at *plan* time.

    Deciding here rather than during execution is what lets ``--dry-run`` show the skips
    and the ``already``, and it is why nothing below touches the filesystem beyond
    reading it.
    """
    verb = "upgrade" if upgrade else "install"
    summary = f"{verb} the the-loop plugin for cursor"
    directory = cursor_plugin_dir(env)
    url = f"https://github.com/{repo}.git"
    manual = f"git clone {url} {directory}"

    # Cursor's local plugins directory is user-level; nothing documented expresses a
    # project-scoped Cursor plugin. A scope that cannot be honoured is reported, never
    # widened to the whole machine (R3.2/R3.3).
    if scope != "user":
        return [
            Step(
                "cursor",
                summary,
                state="skipped",
                detail=(
                    f"{reason}, and Cursor documents no project-local plugin directory, "
                    "so a project-scoped install cannot be expressed; re-run with "
                    "--scope user, or install it from Cursor with /add-plugin in that "
                    "workspace"
                ),
            )
        ]

    git = env.which("git")
    if not git:
        return [
            Step(
                "cursor",
                summary,
                state="skipped",
                detail=f"{reason}, and git is not on PATH; install git, then: {manual}",
            )
        ]

    if directory.exists():
        # A checkout this command owns is a state the-loop can determine itself, so it
        # answers rather than delegating (R4.3). Anything else in that directory belongs
        # to somebody else: report it and touch nothing (R4.4).
        if not (directory / ".git").is_dir():
            return [
                Step(
                    "cursor",
                    summary,
                    state="skipped",
                    target=str(directory),
                    detail=(
                        f"{directory} exists but is not a git checkout; leaving it "
                        "untouched — move it aside and re-run, or install it from "
                        "Cursor with /add-plugin"
                    ),
                )
            ]
        if not upgrade:
            return [
                Step(
                    "cursor",
                    summary,
                    state="already",
                    target=str(directory),
                    detail=f"{directory} is already a checkout; nothing to do",
                )
            ]
        return [
            Step(
                "cursor",
                f"update the Cursor plugin checkout in {directory}",
                argv=[str(git), "-C", str(directory), "pull", "--ff-only"],
                detail=reason,
            )
        ]

    if upgrade:
        return [
            Step(
                "cursor",
                summary,
                state="skipped",
                detail=(
                    f"nothing to upgrade: no checkout at {directory}; run "
                    "`the-loop install cursor` first"
                ),
            )
        ]
    # `--` closes the question of whether the URL could be read as an option. It cannot
    # — `repo` is validated as owner/repo before the plan exists, and the URL is built
    # around it — but the guarantee is worth one argv element.
    return [
        Step(
            "cursor",
            f"clone {repo} into {directory}",
            argv=[str(git), "clone", "--", url, str(directory)],
            detail=reason,
        )
    ]


def _harness_cli_steps(
    component: str,
    surface: HarnessSurface,
    *,
    scope: str,
    upgrade: bool,
    project_dir: Path,
    repo: str,
) -> List[Step]:
    """The two commands a plugin-aware harness CLI wants, with the scope it accepts."""
    binary = str(surface.path)
    scope_args = ["--scope", scope] if surface.supports_scope else []
    if scope == "project" and not surface.supports_scope:
        return [
            Step(
                component,
                f"install the the-loop plugin for {component}",
                state="skipped",
                detail=(
                    f"`{surface.binary} plugin install` does not accept --scope, so a "
                    "project-scoped install cannot be expressed; re-run with "
                    "--scope user, or install it from the harness UI"
                ),
            )
        ]
    cwd = Path(project_dir) if scope == "project" else None
    if upgrade:
        return [
            Step(
                component,
                f"refresh the {MARKETPLACE_NAME} marketplace",
                argv=[binary, "plugin", "marketplace", "update", MARKETPLACE_NAME],
                cwd=cwd,
            ),
            Step(
                component,
                f"update {PLUGIN_KEY}",
                argv=[binary, "plugin", "update", PLUGIN_KEY] + scope_args,
                cwd=cwd,
            ),
        ]
    return [
        Step(
            component,
            f"register the {MARKETPLACE_NAME} marketplace ({repo})",
            argv=[binary, "plugin", "marketplace", "add", repo] + scope_args,
            cwd=cwd,
        ),
        Step(
            component,
            f"install {PLUGIN_KEY}",
            argv=[binary, "plugin", "install", PLUGIN_KEY] + scope_args,
            cwd=cwd,
        ),
    ]


#: The per-harness planner, by component. Every planner takes the same keyword
#: arguments, so :func:`plan` stays one call and a third harness is a row here.
PLANNERS: Dict[str, Callable[..., List[Step]]] = {
    "claude": plan_claude,
    "cursor": plan_cursor,
}


# -- plan & execute ------------------------------------------------------------


def plan(
    components: Sequence[str],
    *,
    scope: str = "user",
    upgrade: bool = False,
    project_dir: Optional[Path] = None,
    marketplace_repo: str = DEFAULT_MARKETPLACE_REPO,
    env: Optional[Env] = None,
) -> List[Step]:
    """Build the ordered list of steps for ``components``.

    Raises :class:`InvalidMarketplace` when a plugin component is selected and the
    marketplace value is not ``owner/repo`` — before any step exists, so an invalid
    value can never be executed or written.
    """
    env = env or default_env()
    project = Path(project_dir) if project_dir is not None else Path(".")
    wanted = [name for name in COMPONENTS if name in set(components)]
    repo = ""
    if any(name in BINARIES for name in wanted):
        repo = _validated_repo(marketplace_repo)

    steps: List[Step] = []
    for name in wanted:
        if name == "cli":
            steps += plan_cli(
                scope=scope, upgrade=upgrade, project_dir=project, env=env
            )
        else:
            steps += PLANNERS[name](
                scope=scope,
                upgrade=upgrade,
                project_dir=project,
                repo=repo,
                env=env,
            )
    for step in steps:
        step.run = env.run
    return steps


def execute(steps: Sequence[Step], *, dry_run: bool) -> List[StepResult]:
    """Run ``steps`` in order, one result each.

    Steps are independent: a component that fails does not stop the ones after it
    (R1.4), because "my Cursor install failed" is no reason to leave the CLI
    half-upgraded.
    """
    results: List[StepResult] = []
    for step in steps:
        if step.state:
            results.append(
                StepResult(
                    step.component,
                    step.summary,
                    step.state,
                    step.render(),
                    step.detail,
                )
            )
            continue
        if dry_run:
            results.append(
                StepResult(
                    step.component, step.summary, "planned", step.render(), step.detail
                )
            )
            continue
        results.append(_execute_one(step))
    return results


def _execute_one(step: Step) -> StepResult:
    if step.writer is not None:
        result = step.writer()
        if not result.ok:
            return StepResult(
                step.component, step.summary, "failed", step.render(), result.error
            )
        if not result.applied:
            return StepResult(
                step.component,
                step.summary,
                "already",
                step.render(),
                "already registered",
            )
        return StepResult(
            step.component,
            step.summary,
            "applied",
            step.render(),
            "; ".join(result.applied),
        )
    try:
        completed = step.run(step.argv, cwd=step.cwd, timeout=STEP_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        return StepResult(
            step.component, step.summary, "failed", step.render(), str(exc)
        )
    if completed.returncode != 0:
        return StepResult(
            step.component,
            step.summary,
            "failed",
            step.render(),
            f"exit {completed.returncode}: {_last_line(completed)}",
        )
    return StepResult(
        step.component, step.summary, "applied", step.render(), _last_line(completed)
    )


def _last_line(completed: "subprocess.CompletedProcess[str]") -> str:
    """The most informative line a child process left behind."""
    for stream in (completed.stderr, completed.stdout):
        lines = [line.strip() for line in (stream or "").splitlines() if line.strip()]
        if lines:
            return lines[-1]
    return ""


def exit_code(results: Sequence[StepResult]) -> int:
    """1 when any step failed. Skipped is not a failure — it is a reported gap."""
    return 1 if any(result.outcome == "failed" for result in results) else 0
