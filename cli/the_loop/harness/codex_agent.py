"""Codex TUI hosting, exact-conversation resume and JSONL one-shot reviews.

Codex creates its own conversation id. A unique launch marker identifies its
rollout positively; resume never chooses a conversation by recency. Instruction
and Stop-hook setup are independent of workspace trust, and existing operator
configuration and approval/sandbox policy remain authoritative.
"""

from __future__ import annotations

import os
import json
import tempfile
import sys
from pathlib import Path
from typing import List, Optional

from ..codex_support import (
    codex_home,
    conversation_marker,
    native_session_id,
    prepare_instructions,
    rollout_path,
)

from .base import HarnessAdapter
from ..trust import TrustResult, _lock_for, is_too_broad

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class CodexAdapter(HarnessAdapter):
    name = "codex"
    default_binary = "codex"
    #: Long and short (``-m``) both exist on ``codex`` and ``codex exec``; the
    #: long form is used for the same reason as cursor's (issue-360): it is the
    #: one spelling both surfaces document.
    model_flag = "--model"
    #: Codex spells effort as the ``model_reasoning_effort`` config key, set per
    #: run with ``-c`` (its ``--help``'s own example mechanism). Levels the-loop
    #: knows that codex cannot express are simply absent — `models check`
    #: validates each mapping against the installed CLI rather than trusting
    #: this table (decision-124).
    _EFFORT_ARGS = {
        "low": ("-c", "model_reasoning_effort=low"),
        "medium": ("-c", "model_reasoning_effort=medium"),
        "high": ("-c", "model_reasoning_effort=high"),
        "xhigh": ("-c", "model_reasoning_effort=xhigh"),
        "ultra": ("-c", "model_reasoning_effort=ultra"),
    }

    def prepare_environment(self, cwd: str, root: Optional[str] = None) -> TrustResult:
        """Pre-trust ``cwd`` in codex's config so an unattended spawn starts.

        Codex's directory-trust dialog (its issue-90 equivalent) is not a
        permission rule — no CLI flag silences it, ``--dangerously-bypass-…``
        included — and it blocks the TUI on a keypress. Trust lives in
        ``$CODEX_HOME/config.toml`` as ``[projects."<dir>"] trust_level =
        "trusted"``. For a linked worktree codex resolves and trusts the main
        repository root (the dialog says so in as many words), so that root is
        written too. Writes are append-only, atomic, and skipped when an entry
        for the directory already exists — an operator's own ``trust_level``
        is never rewritten.
        """
        result = (
            prepare_instructions(cwd, hook_home=codex_home())
            if self.plugins.enabled
            else TrustResult()
        )
        if not self.trust.enabled:
            return result
        keys = [os.path.normpath(os.path.abspath(cwd))]
        real = os.path.normpath(os.path.realpath(cwd))
        if real not in keys:
            keys.append(real)
        main_root = _worktree_main_root(cwd)
        if main_root and main_root not in keys:
            keys.append(main_root)
        if root and self.trust.roots_allowed:
            rootkey = os.path.normpath(os.path.realpath(root))
            if (
                rootkey not in keys
                and not is_too_broad(rootkey)
                and (real + os.sep).startswith(rootkey + os.sep)
            ):
                keys.append(rootkey)
        return result.merge(_trust_in_codex_config(keys))

    def _oneshot_argv(self, prompt: str) -> List[str]:
        # JSONL retains token usage; shared extraction reads the final message.
        # `--skip-git-repo-check` keeps probes runnable outside a repository.
        return ["exec", "--skip-git-repo-check", "--json"] + self.extra_args + [prompt]

    def interactive_argv(self, prompt: str, session_id: str) -> List[str]:
        # Record the launch marker in the first user prompt for id discovery.
        return self._launch_args() + [prompt + "\n\n" + conversation_marker(session_id)]

    def interactive_resume_argv(self, prompt: str, session_id: str) -> List[str]:
        # The caller resolves the launch marker to Codex's own UUID first.
        return ["resume"] + self._launch_args() + [session_id, prompt]

    def resolve_session_id(self, cwd: str, session_id: str) -> str:
        path = rollout_path(cwd, session_id)
        return native_session_id(path) if path else ""


def _codex_config_path() -> Path:
    """``$CODEX_HOME/config.toml``, honouring the same override codex does."""
    home = (os.environ.get("CODEX_HOME") or "").strip()
    base = Path(home) if home else Path.home() / ".codex"
    return base / "config.toml"


def _worktree_main_root(cwd: str) -> str:
    """The main repository root when ``cwd`` is inside a linked worktree, else "".

    Read from the worktree's ``.git`` *file* (``gitdir: <main>/.git/worktrees/<n>``)
    rather than asked of git, so preparing an environment never runs a binary.
    """
    probe = Path(os.path.realpath(cwd))
    for directory in (probe, *probe.parents):
        gitfile = directory / ".git"
        if gitfile.is_dir():
            return ""  # an ordinary checkout: cwd's own entry already covers it
        if gitfile.is_file():
            try:
                content = gitfile.read_text(encoding="utf-8").strip()
            except OSError:
                return ""
            if not content.startswith("gitdir:"):
                return ""
            gitdir = Path(content[len("gitdir:") :].strip())
            if not gitdir.is_absolute():
                gitdir = (directory / gitdir).resolve()
            parts = gitdir.parts
            for i in range(len(parts) - 1):
                if parts[i] == ".git" and parts[i + 1] == "worktrees":
                    return os.path.normpath(str(Path(*parts[:i])) or os.sep)
            return ""  # a .git file without a worktrees segment: not linked
    return ""


def _trust_in_codex_config(keys: List[str]) -> TrustResult:
    """Preserve valid TOML and operator choices; serialize concurrent writes."""
    path = _codex_config_path().resolve()
    with _lock_for(path):
        return _write_trust(path, keys)


def _write_trust(path: Path, keys: List[str]) -> TrustResult:
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        projects = tomllib.loads(text).get("projects", {})
        if not isinstance(projects, dict):
            raise ValueError("projects must be a TOML table")
    except (OSError, ValueError) as exc:
        return TrustResult(ok=False, error=f"could not read {path}: {exc}")
    missing = [key for key in dict.fromkeys(keys) if key not in projects]
    additions = [
        f'\n[projects.{json.dumps(key, ensure_ascii=False)}]\ntrust_level = "trusted"\n'
        for key in missing
    ]
    if not additions:
        return TrustResult()
    tmp = ""
    try:
        updated = text + "".join(additions)
        tomllib.loads(updated)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".config-toml-")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(updated)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except (OSError, ValueError) as exc:
        return TrustResult(ok=False, error=f"could not write {path}: {exc}")
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
    return TrustResult(applied=[f"trusted {key} in {path}" for key in missing])
