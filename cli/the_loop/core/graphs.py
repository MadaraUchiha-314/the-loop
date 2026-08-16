"""Core capability: the process graph, repo-scoped (issue-161).

``check``/``status`` are pure reads (the ``the-loop check`` contract — no
network, no subprocess, no mutation — now holds of these functions; a client's
hop to the service is transport). The mutating verbs are the same runtime verbs
the graph command exposes; ``force`` requires a human-attributed reason and is
deliberately absent from the MCP surface (design §Security).

Every verb takes an optional ``pr`` (issue-172): a pull-request number selects
that PR's **inner loop** (``pdlc-pr-loop``, state under the work item's
``pr-loops/pr-<n>/``); ``None`` — the default and the whole pre-issue-172
surface — is the work item's outer ``pdlc-work-item-loop``. ``pr_repo``
qualifies that number by repository for a work item spanning several
(issue-183): ``pr-loops/<owner>__<repo>/pr-<n>/``, still under the one spec
directory in the origin repository. It is meaningless without ``pr``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ..graph.bootstrap import build_runtime
from ..graph import runtime as graph_runtime


def repo_resolves(repo: str) -> bool:
    """Does ``repo`` name a directory this process can use?

    The predicate behind :func:`resolve_repo`, factored out rather than copied so
    a caller can ask the boundary's question without catching its exception
    (issue-238). One predicate, one answer: the day these two disagree is the day
    a path one of them rejects reaches core through the other.
    """
    return Path(repo).expanduser().is_dir()


def resolve_repo(repo: str) -> Path:
    """Validate a repo path at the trust boundary: it must exist and be a
    directory (abuse case 3 — no core call on unvetted input)."""
    path = Path(repo).expanduser()
    if not repo_resolves(repo):
        raise ValueError(f"repo path is not a directory: {repo}")
    return path.resolve()


def _recorded_loop(path: Path, work_item: str) -> str:
    """The outer-path loop this work item's state records (issue-185).

    ``""`` — the shipped default — for a fresh item, a pre-issue-185 state
    file, or anything unreadable; only a non-default **outer-path** loop is ever
    returned, because the state file is agent-writable and must not choose
    arbitrary graphs. This is what lets `the-loop check`/`graph` address a
    contribution or an ad-hoc item (issue-225) with no new flags: the recorded
    fact travels with the checkout.
    """
    from .. import harness_config
    from ..graph.model import resolve_outer_loop
    from ..graph.state import GraphState

    try:
        spec_root = harness_config.spec_dir(harness_config.load(path))
        state = GraphState.load(path / spec_root / work_item, work_item)
        recorded = str(getattr(state, "loop", "") or "")
    except Exception:  # noqa: BLE001 — an unreadable state reads as the default
        return ""
    return resolve_outer_loop(recorded)


def _runtime(
    repo: str,
    pr: Optional[int] = None,
    pr_repo: str = "",
    work_item: str = "",
    adopt: bool = False,
):
    """A runtime for ``repo``, adopting it first when the caller changes state.

    ``adopt`` is passed explicitly by the four verbs that write — `complete`,
    `advance`, `force`, `skip` — and by none of the readers (issue-193). It is a
    parameter rather than something inferred from the verb because `check`'s
    purity is what lets CI run the real runtime (issue-109 R8.8); a filesystem
    write hidden behind a call that reads like a lookup would leave that property
    resting on nothing a reviewer can check.

    Adoption runs **before** ``build_runtime`` so ``repoInitialized`` is true on
    the very run that adopted the repository, and never for a contribution: the
    repository the-loop was invited into keeps the-loop out of its history
    (issue-185, PR #187).
    """
    from .. import harness_config
    from ..graph.model import PDLC_CONTRIBUTION_LOOP

    if pr_repo and pr is None:
        raise ValueError("pr_repo names a repository, not a loop: pass pr as well")
    path = resolve_repo(repo)
    loop = _recorded_loop(path, work_item) if pr is None and work_item else ""
    if adopt and loop != PDLC_CONTRIBUTION_LOOP:
        harness_config.scaffold(path)
    return build_runtime(path, pr_number=pr, pr_repo=pr_repo, loop=loop)


def check(
    repo: str,
    work_item: str,
    recompute: bool = False,
    pr: Optional[int] = None,
    pr_repo: str = "",
) -> Dict[str, Any]:
    """`the-loop check` for one work item: the status report as a dict.

    A ``repo`` that does not resolve is **answered, not raised** (issue-238). A
    checkout that has been cleaned up is expected state on the machine that
    cleaned it up, and the only honest report about it is "position unknown" —
    which is what the control plane already renders from the frozen record.
    Calling it a caller error made the dashboard log a 400 per stale session per
    poll tick, forever, in a place no `catch` can suppress.

    Only ``check`` behaves this way, and deliberately: it is the one verb a
    client polls. Somebody asking to *advance* or *force* a repository that is
    not there has made a mistake and wants to be told, so the mutating verbs keep
    :func:`resolve_repo`'s ``ValueError``.

    The early return sits **before** :func:`_runtime`, which is what makes
    "no core call on unvetted input" structural rather than incidental — there is
    no path through this function that reaches the graph with a path the boundary
    rejected. The body names nothing the caller did not already send: no path, no
    error text, so the 200 tells them strictly less than the 400 did.
    """
    if not repo_resolves(repo):
        return {
            "workItem": work_item,
            "currentNode": "",
            "ok": False,
            "parked": None,
            "nodes": [],
            "repoResolved": False,
        }
    return (
        _runtime(repo, pr, pr_repo, work_item)
        .status(work_item, recompute=recompute)
        .as_dict()
    )


def complete(
    repo: str,
    work_item: str,
    node: str = "",
    actor: str = "",
    ref: str = "",
    pr: Optional[int] = None,
    pr_repo: str = "",
) -> Dict[str, Any]:
    """A completion claim for the current (or named) node — issue-148 semantics."""
    return _runtime(repo, pr, pr_repo, work_item, adopt=True).complete(
        work_item, ref=ref, node=node, actor=actor
    )


def advance(
    repo: str,
    work_item: str,
    ref: str = "",
    pr: Optional[int] = None,
    pr_repo: str = "",
) -> Dict[str, Any]:
    """Evaluate the current node's exit chain and take the matching edge."""
    return (
        _runtime(repo, pr, pr_repo, work_item, adopt=True)
        .advance(work_item, ref=ref)
        .as_dict()
    )


def force(
    repo: str,
    work_item: str,
    to_node: str,
    reason: str,
    actor: str = "",
    ref: str = "",
    pr: Optional[int] = None,
    pr_repo: str = "",
) -> Dict[str, Any]:
    """The authorized-operator escape hatch. Requires a reason; never forges a
    verdict. Not exposed over MCP (design §Security)."""
    runtime = _runtime(repo, pr, pr_repo, work_item, adopt=True)
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


def skip(
    repo: str,
    work_item: str,
    nodes: list,
    reason: str,
    actor: str = "",
    ref: str = "",
    pr: Optional[int] = None,
    pr_repo: str = "",
) -> Dict[str, Any]:
    """Declare skips for a work item (issue-177) — the operator channel.

    ``force``'s sibling: human-attributed, reason required, audited on the
    ticket, and deliberately absent from the MCP surface. Tokens outside the
    graph's skip vocabulary, or naming nodes the pointer already reached, come
    back in ``rejected`` rather than taking effect.
    """
    runtime = _runtime(repo, pr, pr_repo, work_item, adopt=True)
    result = graph_runtime.declare_skips(
        runtime,
        work_item,
        [str(n) for n in (nodes or [])],
        reason,
        actor=actor,
        ref=ref,
    )
    return {
        "workItem": result.work_item,
        "declared": list(result.declared),
        "rejected": list(result.rejected),
        "reason": result.reason,
        # Best-effort steps that did not happen — the audit comment (issue-194).
        # A declaration whose paper trail never reached the ticket is still a
        # declaration, and the operator has to be told so they can post it.
        "warnings": list(result.warnings),
    }


def show(repo: str, pr: Optional[int] = None, pr_repo: str = "") -> Dict[str, Any]:
    """The process graph this repo runs on: its nodes and edges, as data.

    A read of *which* graph is in force — the shipped one, or the override the
    repo configures — so it belongs on the same surface as the reports derived
    from it rather than being re-resolved by each client. With ``pr`` set it is
    the inner ``pdlc-pr-loop`` instead.
    """
    runtime = _runtime(repo, pr, pr_repo)
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
