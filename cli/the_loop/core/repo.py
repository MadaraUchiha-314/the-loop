"""Core capability: repo-scoped, read-only queries (issue-161).

``scenarios`` and ``instructions`` are facts *about* a repository checkout, derived
from its files and from what the caller hands in — pure reads, same as their CLI
commands. ``critics`` lists the operator's configured critic harnesses (the CLI
config's ``critics[]``, issue-352), and ``critic_run`` is the one repo-scoped
execution, reusing the argv-no-shell critic runner unchanged (issue-108).

The CLI reads no harness config (issue-352, decision-123). What these functions
used to read from ``.the-loop/harness-config.yaml`` — the integration-test globs,
the registered instruction docs, the critic roster — now arrives as arguments or
from the CLI config, and the skill tells the agent what to pass.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .. import critics as critics_mod
from .. import instructions as instructions_mod
from ..scenarios import DEFAULT_GLOBS, collect_scenarios
from .graphs import resolve_repo


def scenarios(repo: str, globs: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Every Gherkin scenario covered by the repo's integration tests.

    Returns the effective globs alongside the scenarios: "none found" is only
    meaningful next to *what was searched*, and the CLI says both. The globs are
    the caller's (``--glob``, or the harness config's ``testing.integrationTestGlobs``
    read by the agent and passed along), else the built-in defaults.
    """
    root = resolve_repo(repo)
    effective = [str(g) for g in (globs or [])] or list(DEFAULT_GLOBS)
    return {
        "repo": str(root),
        "globs": effective,
        "scenarios": [s.as_dict() for s in collect_scenarios(root, effective)],
    }


def instructions(
    repo: str,
    docs: Optional[Sequence[Any]] = None,
    on_missing: str = instructions_mod.DEFAULT_ON_MISSING,
) -> Dict[str, Any]:
    """Every registered custom-instruction doc and its resolution state.

    ``docs`` are the entries as the harness config's ``customInstructions.docs``
    lists them — a path string, or a ``{path, notes}`` mapping — handed in by the
    caller (the agent, or ``--doc`` on the command line). ``on_missing`` rides
    along because it is the policy that *grades* the report — the CLI turns it
    into an exit code, and carrying it here means no client re-derives it.
    """
    root = resolve_repo(repo)
    entries = [{"path": d} if isinstance(d, str) else d for d in (docs or [])]
    config = {"customInstructions": {"docs": entries, "onMissing": on_missing}}
    resolved = instructions_mod.collect_docs(root, config)
    return {
        "repo": str(root),
        "onMissing": instructions_mod.on_missing(config),
        # ``resolvedOk`` is the one rule that decides whether an entry counts
        # as a gap; carrying it means no client re-derives it from ``state``.
        "docs": [{**d.as_dict(), "resolvedOk": d.resolved_ok} for d in resolved],
    }


def critics(repo: str = "") -> List[Dict[str, Any]]:
    """The configured critic harnesses — argv *shapes* only, never their argv.

    Entries name the executable and whether it resolves on PATH, which is what
    an operator (and ``the-loop critic list``) needs; the composed command line
    and anything interpolated into it stay inside the runner. ``repo`` is kept
    for the route's shape and is not consulted: the roster is the operator's
    CLI config's ``critics[]`` (issue-352), not any repository's.
    """
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
        for c in critics_mod.load_critics()
    ]


def spec_dir_for(repo: str, work_item: str) -> str:
    """``<specDir>/<work item>`` for the ``{specDir}`` placeholder — the CLI
    config's ``routing.graph.specDir``, else ``docs/specs``."""
    if not work_item:
        return ""
    from ..graph.bootstrap import resolve_spec_root

    return str(resolve_repo(repo) / resolve_spec_root() / work_item)


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
    critic = critics_mod.find_critic(name)  # CriticConfigError (ValueError)
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
