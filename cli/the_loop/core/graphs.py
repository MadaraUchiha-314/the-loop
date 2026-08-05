"""Core capability: the process graph, repo-scoped (issue-161).

``check``/``status`` are pure reads (the ``the-loop check`` contract — no
network, no subprocess, no mutation — now holds of these functions; a client's
hop to the service is transport). The mutating verbs are the same runtime verbs
the graph command exposes; ``force`` requires a human-attributed reason and is
deliberately absent from the MCP surface (design §Security).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ..graph.bootstrap import build_runtime
from ..graph import runtime as graph_runtime


def resolve_repo(repo: str) -> Path:
    """Validate a repo path at the trust boundary: it must exist and be a
    directory (abuse case 3 — no core call on unvetted input)."""
    path = Path(repo).expanduser()
    if not path.is_dir():
        raise ValueError(f"repo path is not a directory: {repo}")
    return path.resolve()


def check(repo: str, work_item: str, recompute: bool = False) -> Dict[str, Any]:
    """`the-loop check` for one work item: the status report as a dict."""
    runtime = build_runtime(resolve_repo(repo))
    return runtime.status(work_item, recompute=recompute).as_dict()


def complete(
    repo: str, work_item: str, node: str = "", actor: str = ""
) -> Dict[str, Any]:
    """A completion claim for the current (or named) node — issue-148 semantics."""
    runtime = build_runtime(resolve_repo(repo))
    return runtime.complete(work_item, node=node, actor=actor)


def advance(repo: str, work_item: str) -> Dict[str, Any]:
    """Evaluate the current node's exit chain and take the matching edge."""
    runtime = build_runtime(resolve_repo(repo))
    return runtime.advance(work_item).as_dict()


def force(
    repo: str, work_item: str, to_node: str, reason: str, actor: str = ""
) -> Dict[str, Any]:
    """The authorized-operator escape hatch. Requires a reason; never forges a
    verdict. Not exposed over MCP (design §Security)."""
    runtime = build_runtime(resolve_repo(repo))
    result = graph_runtime.force(runtime, work_item, to_node, reason, actor=actor)
    return {
        "workItem": result.work_item,
        "fromNode": result.from_node,
        "toNode": result.to_node,
        "reason": result.reason,
        "warnings": list(result.warnings),
    }
