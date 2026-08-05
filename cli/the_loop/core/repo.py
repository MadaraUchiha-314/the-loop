"""Core capability: repo-scoped, read-only queries (issue-161).

``scenarios``, ``instructions`` and ``critics`` are facts *about* a repository
checkout, derived from its files and harness config — pure reads, same as their
CLI commands. ``critic_run`` is the one repo-scoped execution and reuses the
argv-no-shell critic runner unchanged (issue-108).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import critics as critics_mod
from .. import instructions as instructions_mod
from ..harness_config import load as load_harness_config
from ..scenarios import DEFAULT_GLOBS, collect_scenarios
from .graphs import resolve_repo


def scenarios(repo: str) -> List[Dict[str, Any]]:
    """Every Gherkin scenario covered by the repo's integration tests."""
    root = resolve_repo(repo)
    config = load_harness_config(root)
    globs = ((config.get("testing") or {}).get("integrationTestGlobs")) or list(
        DEFAULT_GLOBS
    )
    return [s.as_dict() for s in collect_scenarios(root, [str(g) for g in globs])]


def instructions(repo: str) -> List[Dict[str, Any]]:
    """Every registered custom-instruction doc and its resolution state."""
    root = resolve_repo(repo)
    config = load_harness_config(root)
    return [d.as_dict() for d in instructions_mod.collect_docs(root, config)]


def critics(repo: str) -> List[Dict[str, Any]]:
    """The configured critic harnesses (never their secrets — entries carry
    argv shapes only)."""
    root = resolve_repo(repo)
    return [
        {"name": c.name, "harness": c.harness, "model": c.model}
        for c in critics_mod.load_critics(root)
    ]


def critic_run(
    repo: str,
    name: str,
    prompt: str,
    prompt_file: str,
    work_item: str = "",
    spec_dir: str = "",
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Run one named critic round; the single JSON envelope, as a dict.

    Raises ``LookupError`` for an unknown critic and lets
    :class:`~the_loop.critics.CriticConfigError` (a ``ValueError``) escape for a
    misconfigured one — nothing ran, so there is no round to report.
    """
    root = resolve_repo(repo)
    critic = critics_mod.find_critic(root, name)  # CriticConfigError (ValueError)
    values = {
        "prompt": prompt,
        "promptFile": prompt_file,
        "model": critic.model,
        "workItem": work_item,
        "specDir": spec_dir,
        "cwd": str(root),
    }
    result = critics_mod.run_critic(critic, values, cwd=str(root), timeout=timeout)
    return result.as_dict()
