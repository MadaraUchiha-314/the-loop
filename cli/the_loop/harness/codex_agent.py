"""Codex adapter: host the ``codex`` TUI in tmux; run ``codex exec`` for critics.

Codex CLI (issue-449) follows decision-016 like the others: the official CLI is
the programmatic surface. Hosting works, with one honest asymmetry: ``codex``
has no pre-assignable session id in interactive mode (the flag is an open
upstream request, openai/codex#13242), so the id the dispatcher passes into
``interactive_argv`` cannot be handed to the TUI. The session is launched
id-less and the registry's ``harness_session_id`` stays the-loop's own name for
the conversation, not codex's. Respawn therefore resumes by recency —
``codex resume --last`` — scoped by the session's recorded cwd, which is unique
per work item under the workspace's worktree strategy.

Unattended, nothing is taken away (`_UNATTENDED_ARGS` is empty): codex's
approval prompts are governed by sandbox/approval *policy* flags
(``--dangerously-bypass-approvals-and-sandbox``, ``--sandbox``), and policy is
the operator's to declare via ``harnesses[].args`` — the-loop never widens
permissions itself.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import List, Optional

from .base import HarnessAdapter
from ..trust import TrustResult


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
        if not self.trust.enabled:
            return TrustResult()
        keys = [os.path.normpath(os.path.abspath(cwd))]
        real = os.path.normpath(os.path.realpath(cwd))
        if real not in keys:
            keys.append(real)
        main_root = _worktree_main_root(cwd)
        if main_root and main_root not in keys:
            keys.append(main_root)
        if root and self.trust.roots_allowed:
            rootkey = os.path.normpath(os.path.realpath(root))
            if rootkey not in keys and (real + os.sep).startswith(rootkey + os.sep):
                keys.append(rootkey)
        return _trust_in_codex_config(keys)

    def _oneshot_argv(self, prompt: str) -> List[str]:
        # Plain text out, no `--json`: codex's JSON mode is JSONL events, which
        # neither `parse_json_object` nor a critic's `output_format: json`
        # extraction reads; the critic path's text fallback wants the prose.
        # `--skip-git-repo-check` keeps probes runnable outside a repository.
        return ["exec", "--skip-git-repo-check"] + self.extra_args + [prompt]

    def interactive_argv(self, prompt: str, session_id: str) -> List[str]:
        # `session_id` is accepted and dropped: codex mints its own id at
        # launch (see module docstring). Flags first, positional prompt last.
        return self._launch_args() + [prompt]

    def interactive_resume_argv(self, prompt: str, session_id: str) -> List[str]:
        # ponytail: resume-by-recency; swap to `resume <id>` when codex grows a
        # pre-assignable id (openai/codex#13242) or an id-discovery hook lands.
        return ["resume", "--last"] + self._launch_args() + [prompt]


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
            parts = gitdir.parts
            for i in range(len(parts) - 1):
                if parts[i] == ".git" and parts[i + 1] == "worktrees":
                    return os.path.normpath(str(Path(*parts[:i])) or os.sep)
            return ""  # a .git file without a worktrees segment: not linked
    return ""


def _trust_in_codex_config(keys: List[str]) -> TrustResult:
    """Append missing ``[projects."<key>"]`` trust entries, atomically."""
    path = _codex_config_path()
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError as exc:
        return TrustResult(ok=False, error=f"could not read {path}: {exc}")
    additions = [
        f'\n[projects."{key}"]\ntrust_level = "trusted"\n'
        for key in keys
        if f'[projects."{key}"]' not in text
    ]
    if not additions:
        return TrustResult(ok=True)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".config-toml-")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text + "".join(additions))
        os.replace(tmp, path)
    except OSError as exc:
        return TrustResult(ok=False, error=f"could not write {path}: {exc}")
    return TrustResult(
        ok=True, applied=[f"trusted {key} in {path}" for key in keys]
    )
