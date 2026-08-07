"""Core capability: the process graph, repo-scoped (issue-161).

``check``/``status`` are pure reads (the ``the-loop check`` contract — no
network, no subprocess, no mutation — now holds of these functions; a client's
hop to the service is transport). The mutating verbs are the same runtime verbs
the graph command exposes; ``force`` requires a human-attributed reason and is
deliberately absent from the MCP surface (design §Security).

Every verb takes an optional ``pr`` (issue-172): a pull-request number selects
that PR's **inner loop** (``pdlc-pr-loop``, state under the work item's
``pr-loops/pr-<n>/``); ``None`` — the default and the whole pre-issue-172
surface — is the work item's outer ``pdlc-work-item-loop``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ..graph.bootstrap import build_runtime
from ..graph import runtime as graph_runtime


def resolve_repo(repo: str) -> Path:
    """Validate a repo path at the trust boundary: it must exist and be a
    directory (abuse case 3 — no core call on unvetted input)."""
    path = Path(repo).expanduser()
    if not path.is_dir():
        raise ValueError(f"repo path is not a directory: {repo}")
    return path.resolve()


def _runtime(repo: str, pr: Optional[int] = None):
    return build_runtime(resolve_repo(repo), pr_number=pr)


def check(
    repo: str, work_item: str, recompute: bool = False, pr: Optional[int] = None
) -> Dict[str, Any]:
    """`the-loop check` for one work item: the status report as a dict."""
    return _runtime(repo, pr).status(work_item, recompute=recompute).as_dict()


def complete(
    repo: str,
    work_item: str,
    node: str = "",
    actor: str = "",
    ref: str = "",
    pr: Optional[int] = None,
) -> Dict[str, Any]:
    """A completion claim for the current (or named) node — issue-148 semantics."""
    return _runtime(repo, pr).complete(work_item, ref=ref, node=node, actor=actor)


def advance(
    repo: str, work_item: str, ref: str = "", pr: Optional[int] = None
) -> Dict[str, Any]:
    """Evaluate the current node's exit chain and take the matching edge."""
    return _runtime(repo, pr).advance(work_item, ref=ref).as_dict()


def force(
    repo: str,
    work_item: str,
    to_node: str,
    reason: str,
    actor: str = "",
    ref: str = "",
    pr: Optional[int] = None,
) -> Dict[str, Any]:
    """The authorized-operator escape hatch. Requires a reason; never forges a
    verdict. Not exposed over MCP (design §Security)."""
    runtime = _runtime(repo, pr)
    result = graph_runtime.force(
        runtime, work_item, to_node, reason, actor=actor, ref=ref
    )
    return {
        "workItem": result.work_item,
        "fromNode": result.from_node,
        "toNode": result.to_node,
        "reason": result.reason,
        "warnings": list(result.warnings),
    }


def show(repo: str, pr: Optional[int] = None) -> Dict[str, Any]:
    """The process graph this repo runs on: its nodes and edges, as data.

    A read of *which* graph is in force — the shipped one, or the override the
    repo configures — so it belongs on the same surface as the reports derived
    from it rather than being re-resolved by each client. With ``pr`` set it is
    the inner ``pdlc-pr-loop`` instead.
    """
    runtime = _runtime(repo, pr)
    graph = runtime.graph
    return {
        "version": graph.version,
        "name": graph.name,
        "start": graph.start,
        # Where this repo keeps its specs — the directory `check --all` walks,
        # so a client never has to build a runtime just to learn the layout.
        "specRoot": runtime.spec_root,
        "nodes": [n.as_mapping() for n in graph.ordered()],
        "edges": [{"from": e.source, "to": e.target, "on": e.on} for e in graph.edges],
    }
