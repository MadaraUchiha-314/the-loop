"""Core capability: repo-scoped, read-only queries (issue-161).

``scenarios``, ``instructions`` and ``critics`` are facts *about* a repository
checkout, derived from its files and harness config — pure reads, same as their
CLI commands. ``critic_run`` is the one repo-scoped execution and reuses the
argv-no-shell critic runner unchanged (issue-108).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

from .. import critics as critics_mod
from .. import instructions as instructions_mod
from ..harness_config import load as load_harness_config
from ..scenarios import DEFAULT_GLOBS, collect_scenarios
from .graphs import resolve_repo


def scenarios(repo: str, globs: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Every Gherkin scenario covered by the repo's integration tests.

    Returns the effective globs alongside the scenarios: "none found" is only
    meaningful next to *what was searched*, and the CLI says both.
    """
    root = resolve_repo(repo)
    effective = [str(g) for g in (globs or [])]
    if not effective:
        config = load_harness_config(root)
        effective = [
            str(g)
            for g in ((config.get("testing") or {}).get("integrationTestGlobs")) or []
        ]
    if not effective:
        effective = list(DEFAULT_GLOBS)
    return {
        "repo": str(root),
        "globs": effective,
        "scenarios": [s.as_dict() for s in collect_scenarios(root, effective)],
    }


def instructions(repo: str) -> Dict[str, Any]:
    """Every registered custom-instruction doc and its resolution state.

    ``onMissing`` rides along because it is the policy that *grades* the report
    — the CLI turns it into an exit code, and deriving it from a second,
    caller-side config read would let the two halves disagree.
    """
    root = resolve_repo(repo)
    config = load_harness_config(root)
    docs = instructions_mod.collect_docs(root, config)
    return {
        "repo": str(root),
        "onMissing": instructions_mod.on_missing(config),
        # ``resolvedOk`` is the one rule that decides whether an entry counts
        # as a gap; carrying it means no client re-derives it from ``state``.
        "docs": [{**d.as_dict(), "resolvedOk": d.resolved_ok} for d in docs],
    }


def critics(repo: str) -> List[Dict[str, Any]]:
    """The configured critic harnesses — argv *shapes* only, never their argv.

    Entries name the executable and whether it resolves on PATH, which is what
    an operator (and ``the-loop critic list``) needs; the composed command line
    and anything interpolated into it stay inside the runner.
    """
    root = resolve_repo(repo)
    return [
        {
            "name": c.name,
            "harness": c.harness,
            "model": c.model,
            "binary": c.binary,
            "available": c.available,
            "enabled": c.enabled,
            "error": c.error,
        }
        for c in critics_mod.load_critics(root)
    ]


def spec_dir_for(repo: str, work_item: str) -> str:
    """``<workflow.specDir>/<work item>`` for the ``{specDir}`` placeholder."""
    if not work_item:
        return ""
    root = resolve_repo(repo)
    spec_root = "docs/specs"
    path = critics_mod.config_path(root)
    if path is not None:
        try:
            data = yaml.safe_load(path.read_text()) or {}
            spec_root = ((data.get("workflow") or {}).get("specDir")) or spec_root
        except Exception:  # noqa: BLE001 — a default is fine here
            pass
    return str(root / spec_root / work_item)


def critic_run(
    repo: str,
    name: str,
    prompt: str,
    prompt_file: str,
    work_item: str = "",
    spec_dir: str = "",
    timeout: Optional[float] = None,
    cwd: str = "",
) -> Dict[str, Any]:
    """Run one named critic round; the single JSON envelope, as a dict.

    Both prompt placeholders always resolve, whichever the caller supplied:
    given only a path, the text is read from it; given only text, the round
    gets a scratch file for the length of the run. A caller that has already
    read a file (the CLI does, so relative paths resolve in the operator's own
    working directory) passes **both**, and the path it names is the one
    ``{promptFile}`` interpolates to.

    Raises ``LookupError`` for an unknown critic and lets
    :class:`~the_loop.critics.CriticConfigError` (a ``ValueError``) escape for a
    misconfigured one — nothing ran, so there is no round to report.
    """
    root = resolve_repo(repo)
    critic = critics_mod.find_critic(root, name)  # CriticConfigError (ValueError)
    where = cwd or critic.cwd or str(root)
    with tempfile.TemporaryDirectory(prefix="the-loop-critic-") as scratch:
        if prompt_file and not prompt:
            prompt = Path(prompt_file).read_text()
        elif not prompt_file:
            scratch_file = Path(scratch) / "critic-prompt.md"
            scratch_file.write_text(prompt)
            prompt_file = str(scratch_file)
        values = {
            "prompt": prompt,
            "promptFile": prompt_file,
            "model": critic.model,
            "workItem": work_item,
            "specDir": spec_dir or spec_dir_for(repo, work_item),
            "cwd": where,
        }
        result = critics_mod.run_critic(critic, values, cwd=where, timeout=timeout)
    return result.as_dict()
