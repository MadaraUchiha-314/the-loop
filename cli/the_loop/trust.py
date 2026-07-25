"""Pre-seed a harness's own config so a spawned session starts unattended (issue-90).

``--dangerously-skip-permissions`` does not silence Claude Code's **workspace
trust** dialog, because trust is not a permission rule. Every checkout the
issue-76 workspace machinery creates is a brand-new directory, so an
auto-executed session opens on a modal nobody is there to answer: with
``runner: tmux`` the-loop records ``session.spawned``, pastes the event prompt
into a TUI showing a dialog, and the work item never moves.

This module puts the "already answered" state where the harness reads it, before
the harness starts. Read off the shipped CLI (not guessed):

* config dir — ``$CLAUDE_CONFIG_DIR`` if set, else ``~/.claude``
* user config file — ``<config dir>/.config.json`` when that file exists, else
  ``${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json``
* user settings file — ``<config dir>/settings.json``
* workspace trust — ``projects["<normalised path>"].hasTrustDialogAccepted``
  (plus ``hasCompletedProjectOnboarding``, so removing the dialog does not just
  reveal the onboarding screen behind it)
* bypass-permissions disclaimer — ``skipDangerousModePermissionPrompt`` in the
  settings file; current builds migrate the legacy top-level
  ``bypassPermissionsModeAccepted`` from the config file into it, so both are
  written for forward/backward compatibility

Written narrowly and non-destructively, because this is the operator's own
configuration: only the keys above, merged into whatever is already there,
via a temp file + atomic replace, and **not written at all** when the value is
already correct. A file that does not parse is reported, never overwritten.

**Scope** (`routing.harnessTrust.scope`, owner decision on PR #92) is the one
real choice here, and it hinges on the two keys being read differently:

* the harness's trust lookup walks **up** from the cwd, so a single entry on the
  **workspace root** covers every checkout beneath it — including folders
  the-loop never spawned into. That is the default (``workspace-root``): a
  workspace the operator already dedicated to the-loop is trusted once.
* ``hasCompletedProjectOnboarding`` has **no** ancestor walk (the harness reads
  it from the exact project key), so it is written per spawn directory
  regardless of scope. Root trust alone would silence the trust dialog and leave
  the onboarding screen behind it.

``scope: directory`` keeps trust on the exact spawn directory only — least
privilege, one entry per work item, and the right choice when the workspace root
holds more than the-loop's own checkouts. Either way a root that does not
contain the spawn directory, or one broad enough to be meaningless (``/``, the
home directory itself), degrades to per-directory trust.

Spec: docs/specs/issue-90/design.md (decision-037).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional

logger = logging.getLogger("the-loop.trust")

__all__ = [
    "ClaudeTrustStore",
    "TrustConfig",
    "TrustResult",
    "args_request_bypass",
    "is_too_broad",
    "is_within",
]

# Current home of the bypass-permissions acceptance (user settings file)…
_BYPASS_SETTING = "skipDangerousModePermissionPrompt"
# …and the legacy top-level key older builds still read from the config file.
_BYPASS_LEGACY_KEY = "bypassPermissionsModeAccepted"

# The argv spellings that ask for bypass-permissions mode.
_BYPASS_FLAG = "--dangerously-skip-permissions"
_PERMISSION_MODE_FLAG = "--permission-mode"
_BYPASS_MODE = "bypassPermissions"

# One lock per config file: the dispatcher runs a worker thread per session and
# several may spawn at once, all read-modify-writing the same two files.
_LOCKS: Dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path)
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = _LOCKS[key] = threading.Lock()
        return lock


@dataclass
class TrustConfig:
    """Mirror of ``webhooks.ghWebhook.routing.harnessTrust`` (see config schema)."""

    enabled: bool = True
    # workspace-root (default, owner decision on PR #92): trust the workspace
    # root once, so every checkout under it — including folders the-loop never
    # spawned into — is covered by the harness's ancestor walk. `directory`
    # trusts only the exact spawn directory (least privilege, one entry per
    # work item). Both keep the same per-directory machinery underneath.
    scope: str = "workspace-root"
    # auto: only when the configured harnessArgs ask for bypass mode (the-loop
    # never widens permissions the operator did not request) | always | never.
    accept_bypass_permissions: str = "auto"

    @property
    def roots_allowed(self) -> bool:
        """Whether a caller may hand :meth:`ClaudeTrustStore.trust` a root."""
        return self.scope == "workspace-root"

    @classmethod
    def from_mapping(cls, data: dict) -> "TrustConfig":
        data = data or {}
        mode = str(data.get("acceptBypassPermissions", "auto"))
        scope = str(data.get("scope", "workspace-root"))
        return cls(
            enabled=bool(data.get("enabled", True)),
            scope=scope
            if scope in ("workspace-root", "directory")
            else "workspace-root",
            accept_bypass_permissions=(
                mode if mode in ("auto", "always", "never") else "auto"
            ),
        )


@dataclass
class TrustResult:
    """Outcome of preparing one harness's config for one directory.

    ``ok=True`` with an empty ``applied`` is the no-op case (nothing was needed,
    or the feature is off) — deliberately indistinguishable from success, since
    both mean "the spawn may proceed".
    """

    ok: bool = True
    applied: List[str] = field(default_factory=list)
    error: str = ""

    def merge(self, other: "TrustResult") -> "TrustResult":
        """Combine two steps: all notes, the first error wins."""
        return TrustResult(
            ok=self.ok and other.ok,
            applied=self.applied + other.applied,
            error=self.error or other.error,
        )


def _set_flag(projects: dict, key: str, name: str) -> bool:
    """Set ``projects[key][name] = True``; True when that changed anything."""
    entry = projects.get(key)
    if not isinstance(entry, dict):
        entry = {}
        projects[key] = entry
    if entry.get(name) is True:
        return False
    entry[name] = True
    return True


def _normalised(path: str) -> str:
    """``path`` in the form the harness stores project keys in."""
    return os.path.normpath(os.path.abspath(path))


def is_within(root: str, path: str) -> bool:
    """True when ``path`` is ``root`` or lives underneath it.

    Component-wise (not a string prefix), so ``/ws`` does not "contain"
    ``/ws-other``.
    """
    root_parts = Path(_normalised(root)).parts
    path_parts = Path(_normalised(path)).parts
    return path_parts[: len(root_parts)] == root_parts


def is_too_broad(root: str, home: Optional[str] = None) -> bool:
    """True for a root nobody should blanket-trust: ``/`` or the home dir itself.

    A workspace root is operator-configured, so this is a guard rail rather
    than a boundary — but trusting ``$HOME`` or ``/`` would silently cover every
    repo and dotfile on the machine, which is never what "trust my workspace"
    is meant to mean. Such a root degrades to per-directory trust with a warning
    rather than failing the spawn.
    """
    resolved = Path(_normalised(root))
    if resolved.parent == resolved:  # filesystem root
        return True
    home_dir = home if home is not None else os.path.expanduser("~")
    return bool(home_dir) and resolved == Path(_normalised(home_dir))


def args_request_bypass(args) -> bool:
    """True when ``args`` ask the harness for bypass-permissions mode.

    Recognises ``--dangerously-skip-permissions`` and both spellings of
    ``--permission-mode bypassPermissions``.
    """
    args = [str(a) for a in (args or [])]
    for index, arg in enumerate(args):
        if arg == _BYPASS_FLAG:
            return True
        if arg == f"{_PERMISSION_MODE_FLAG}={_BYPASS_MODE}":
            return True
        if arg == _PERMISSION_MODE_FLAG and args[index + 1 : index + 2] == [
            _BYPASS_MODE
        ]:
            return True
    return False


def _update_json(path: Path, mutate: Callable[[dict], bool]) -> TrustResult:
    """Read ``path``, apply ``mutate``, and write it back only if it changed.

    ``mutate`` returns True when it actually changed the mapping; False means
    the desired state already holds and **nothing is written** — that is what
    keeps the-loop from racing an interactive harness process for the same file
    on every spawn.

    Never overwrites a file it could not read or parse: an unexpected file is
    the operator's, and clobbering it would be worse than the dialog this
    module exists to remove.
    """
    with _lock_for(path):
        data: dict = {}
        if path.exists():
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError as exc:
                return TrustResult(ok=False, error=f"could not read {path}: {exc}")
            try:
                parsed = json.loads(raw or "{}")
            except json.JSONDecodeError as exc:
                return TrustResult(
                    ok=False,
                    error=(
                        f"{path} is not valid JSON ({exc}); leaving it untouched — "
                        "fix or remove it, or set routing.harnessTrust.enabled: false"
                    ),
                )
            if not isinstance(parsed, dict):
                return TrustResult(
                    ok=False,
                    error=(f"{path} does not hold a JSON object; leaving it untouched"),
                )
            data = parsed
        if not mutate(data):
            return TrustResult()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(path, data)
        except OSError as exc:
            return TrustResult(ok=False, error=f"could not write {path}: {exc}")
        return TrustResult(applied=[str(path)])


def _atomic_write_json(path: Path, data: dict) -> None:
    """Serialize ``data`` beside ``path`` and atomically move it into place.

    A file we create is owner-only (``0600``) — it can carry the operator's
    harness state. An existing file keeps the mode it already had.

    ``os.replace`` swaps the *name*, so a symlinked config (a dotfiles repo
    linked to ``~/.claude.json`` is a common setup) would be replaced by a plain
    file, silently detaching it. Resolve the link first and write through it.
    """
    path = Path(os.path.realpath(path))
    mode: Optional[int] = None
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        mode = None
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".the-loop-tmp", dir=str(path.parent)
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.chmod(tmp, mode if mode is not None else 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


class ClaudeTrustStore:
    """Where Claude Code keeps its trust / disclaimer state, and how to set it.

    ``env`` and ``home`` are injectable so tests drive a fake HOME and never
    touch the real ``~/.claude.json``.
    """

    def __init__(
        self,
        env: Optional[Mapping[str, str]] = None,
        home: Optional[str] = None,
    ):
        self._env = os.environ if env is None else env
        self._home = home

    # -- layout -----------------------------------------------------------------

    def home_dir(self) -> Path:
        if self._home:
            return Path(self._home)
        home = self._env.get("HOME") or ""
        return Path(home) if home else Path(os.path.expanduser("~"))

    def config_dir(self) -> Path:
        """``$CLAUDE_CONFIG_DIR`` when set, else ``~/.claude``."""
        override = (self._env.get("CLAUDE_CONFIG_DIR") or "").strip()
        if override:
            return Path(override)
        return self.home_dir() / ".claude"

    def config_path(self) -> Path:
        """The user config file holding ``projects[...]`` (the trust keys).

        Mirrors the CLI: a ``<config dir>/.config.json`` that already exists
        wins; otherwise ``${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json``.
        """
        scoped = self.config_dir() / ".config.json"
        if scoped.exists():
            return scoped
        override = (self._env.get("CLAUDE_CONFIG_DIR") or "").strip()
        base = Path(override) if override else self.home_dir()
        return base / ".claude.json"

    def settings_path(self) -> Path:
        """The user settings file (``<config dir>/settings.json``)."""
        return self.config_dir() / "settings.json"

    @staticmethod
    def project_keys(path: str) -> List[str]:
        """The ``projects`` keys standing for ``path`` — and only ``path``.

        The exact directory, normalised the way the harness normalises a POSIX
        path, plus its realpath when a symlink makes that differ, so an entry
        holds however the harness canonicalises it. Never expands to a parent:
        widening to an ancestor is a decision the *caller* makes by passing a
        ``root`` to :meth:`trust`, never something this function does silently.
        """
        resolved = _normalised(path)
        keys = [resolved]
        real = os.path.normpath(os.path.realpath(path))
        if real != resolved:
            keys.append(real)
        return keys

    # -- writes -----------------------------------------------------------------

    def trust(self, cwd: str, root: Optional[str] = None) -> TrustResult:
        """Mark ``cwd`` usable by the harness without an interactive dialog.

        Two keys, with **different scoping rules**, because the harness reads
        them differently:

        * ``hasTrustDialogAccepted`` — the harness's trust lookup walks *up*
          from the cwd, so an entry on ``root`` covers every directory beneath
          it, including checkouts the-loop never spawned into. Written on
          ``root`` when one is given (``scope: workspace-root``), else on
          ``cwd``.
        * ``hasCompletedProjectOnboarding`` — read from the **exact** project
          key with no ancestor walk, so it is always written on ``cwd``.
          Otherwise removing the trust dialog would just reveal the onboarding
          screen behind it in every fresh checkout.

        A ``root`` that does not actually contain ``cwd`` is ignored (falling
        back to ``cwd``): trusting an unrelated tree is never what the caller
        meant.
        """
        if not str(cwd or "").strip():
            return TrustResult(ok=False, error="no working directory to trust")
        onboarding_keys = self.project_keys(cwd)
        if root and str(root).strip() and is_within(root, cwd):
            trust_keys = self.project_keys(str(root))
        else:
            trust_keys = onboarding_keys

        def mutate(data: dict) -> bool:
            projects = data.get("projects")
            if not isinstance(projects, dict):
                projects = {}
                data["projects"] = projects
            changed = False
            for key in trust_keys:
                changed |= _set_flag(projects, key, "hasTrustDialogAccepted")
            for key in onboarding_keys:
                changed |= _set_flag(projects, key, "hasCompletedProjectOnboarding")
            return changed

        result = _update_json(self.config_path(), mutate)
        if result.applied:
            scope = (
                f"{trust_keys[0]} (and everything under it)"
                if trust_keys is not onboarding_keys
                else trust_keys[0]
            )
            result = TrustResult(applied=[f"trusted {scope} in {self.config_path()}"])
        return result

    def accept_bypass_permissions(self) -> TrustResult:
        """Record the bypass-permissions disclaimer acceptance.

        Writes the current key (user settings) **and** the legacy one (user
        config), so it holds whichever build of the CLI the operator runs.
        """

        def mutate_settings(data: dict) -> bool:
            if data.get(_BYPASS_SETTING) is True:
                return False
            data[_BYPASS_SETTING] = True
            return True

        def mutate_config(data: dict) -> bool:
            if data.get(_BYPASS_LEGACY_KEY) is True:
                return False
            data[_BYPASS_LEGACY_KEY] = True
            return True

        settings = _update_json(self.settings_path(), mutate_settings)
        if settings.applied:
            settings = TrustResult(
                applied=[f"accepted bypass-permissions in {self.settings_path()}"]
            )
        config = _update_json(self.config_path(), mutate_config)
        if config.applied:
            # Its own note, not folded into the settings one: every write this
            # module makes has to show up in the `workspace.trusted` audit trail.
            config = TrustResult(
                applied=[
                    f"accepted bypass-permissions (legacy key) in {self.config_path()}"
                ]
            )
        return settings.merge(config)
