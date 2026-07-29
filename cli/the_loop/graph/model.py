"""The graph: parse, validate, resolve, index, freeze — once, at load.

"Compile" here means exactly those five things (issue-109, R6b.1). The point is
that **every structural failure is a startup failure** — an unknown hook, an
edge pointing at a node that does not exist, a malformed chain entry — rather
than a surprise three nodes into a traversal at 2am.

The graph ships **with the plugin** (R1.1). A repository cannot define or
override it; a repo-supplied one is ignored with a warning (R1.4). It stays
fully declarative so user-authored graphs can arrive later as a distribution
change rather than a rewrite.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import yaml

from .registry import hook_names, is_registered

logger = logging.getLogger("the-loop.graph")

__all__ = [
    "Edge",
    "Graph",
    "GraphConfigError",
    "Node",
    "load_graph",
    "shipped_graph_path",
]

_ACTORS = frozenset({"agent", "human", "code"})
_SESSION_MODES = frozenset({"new", "inherit"})


class GraphConfigError(ValueError):
    """The graph could not be compiled. Always names the offending element."""


@dataclass(frozen=True)
class Node:
    id: str
    phase: str = ""
    actor: str = "agent"
    produces: Tuple[str, ...] = ()
    command: str = ""
    stage: str = ""
    session: str = "new"
    required: bool = False
    optional: bool = False
    max_attempts: int = 3
    entry: Tuple[Any, ...] = ()
    exit: Tuple[Any, ...] = ()
    terminal: bool = False

    def as_mapping(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "phase": self.phase,
            "actor": self.actor,
            "produces": list(self.produces),
            "command": self.command,
            "stage": self.stage,
            "session": self.session,
            "required": self.required,
            "optional": self.optional,
            "maxAttempts": self.max_attempts,
            "terminal": self.terminal,
        }


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    on: str


@dataclass
class Graph:
    nodes: Dict[str, Node]
    edges: List[Edge]
    start: str
    version: int = 1
    _index: Dict[Tuple[str, str], Edge] = field(default_factory=dict, repr=False)

    def node(self, node_id: str) -> Node:
        try:
            return self.nodes[node_id]
        except KeyError:
            raise GraphConfigError(
                f"unknown node {node_id!r}; declared nodes are: {', '.join(self.nodes)}"
            ) from None

    def edges_from(self, node_id: str) -> List[Edge]:
        return [e for e in self.edges if e.source == node_id]

    def next_node(self, node_id: str, outcome: str) -> Optional[str]:
        """The first declared edge matching ``outcome`` — declaration order wins."""
        edge = self._index.get((node_id, outcome))
        return edge.target if edge else None

    def ordered(self) -> List[Node]:
        """Nodes in declaration order — the order ``check`` reports them in."""
        return list(self.nodes.values())


def shipped_graph_path() -> Path:
    """The graph that ships with the plugin.

    ``CLAUDE_PLUGIN_ROOT`` when the plugin is installed; otherwise the copy in
    this repository, which is what makes the-loop able to run its own loop.
    """
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        candidate = Path(root) / "skills" / "the-loop" / "graph" / "pdlc.yaml"
        if candidate.is_file():
            return candidate
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "skills" / "the-loop" / "graph" / "pdlc.yaml"
        if candidate.is_file():
            return candidate
    raise GraphConfigError(
        "could not locate the shipped graph (skills/the-loop/graph/pdlc.yaml); "
        "set CLAUDE_PLUGIN_ROOT to the plugin install directory"
    )


def _validate_chain(
    node_id: str, boundary: str, specs: Sequence[Any]
) -> Tuple[Any, ...]:
    out: List[Any] = []
    for spec in specs:
        if isinstance(spec, str):
            name, entry = spec, spec
        elif isinstance(spec, Mapping) and "hook" in spec:
            name, entry = str(spec["hook"]), dict(spec)
        else:
            raise GraphConfigError(
                f"node {node_id!r}: malformed {boundary} hook entry {spec!r} — "
                "expected a hook name or {hook: name, with: {...}}"
            )
        if not is_registered(name):
            raise GraphConfigError(
                f"node {node_id!r}: {boundary} references unknown hook {name!r}; "
                f"registered hooks are: {', '.join(hook_names()) or '(none)'}"
            )
        out.append(entry)
    return tuple(out)


def _normalise_edge_keys(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Undo YAML 1.1's boolean coercion of the bare key ``on``.

    ``on:`` in an unquoted YAML mapping parses as the boolean ``True`` — the
    same trap GitHub Actions workflows hit. Graph authors should not have to
    know that, so the loader accepts both forms rather than making a quoted
    ``"on"`` a rule people discover by having their edge silently vanish.
    """
    out: Dict[str, Any] = {}
    for key, value in raw.items():
        if key is True:
            out["on"] = value
        elif key is False:
            out["off"] = value
        else:
            out[str(key)] = value
    return out


def _build_node(raw: Mapping[str, Any]) -> Node:
    node_id = str(raw.get("id") or "").strip()
    if not node_id:
        raise GraphConfigError(
            f"every node needs an id; offending entry: {dict(raw)!r}"
        )
    actor = str(raw.get("actor", "agent"))
    if actor not in _ACTORS:
        raise GraphConfigError(
            f"node {node_id!r}: actor {actor!r} is not one of {sorted(_ACTORS)}"
        )
    session = str(raw.get("session", "new"))
    if session not in _SESSION_MODES:
        raise GraphConfigError(
            f"node {node_id!r}: session {session!r} is not one of {sorted(_SESSION_MODES)}"
        )
    produces = raw.get("produces") or []
    if isinstance(produces, str):
        produces = [produces]
    return Node(
        id=node_id,
        phase=str(raw.get("phase", "")),
        actor=actor,
        produces=tuple(str(p) for p in produces),
        command=str(raw.get("command", "")),
        stage=str(raw.get("stage", "")),
        session=session,
        required=bool(raw.get("required", False)),
        optional=bool(raw.get("optional", False)),
        max_attempts=int(raw.get("maxAttempts", 3)),
        entry=_validate_chain(node_id, "entry", raw.get("entry") or []),
        exit=_validate_chain(node_id, "exit", raw.get("exit") or []),
        terminal=bool(raw.get("terminal", False)),
    )


def compile_graph(data: Mapping[str, Any]) -> Graph:
    """Compile a parsed mapping into a frozen, indexed :class:`Graph`."""
    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise GraphConfigError("the graph declares no nodes")

    nodes: Dict[str, Node] = {}
    for raw in raw_nodes:
        if not isinstance(raw, Mapping):
            raise GraphConfigError(f"node entries must be mappings; found {raw!r}")
        node = _build_node(raw)
        if node.id in nodes:
            raise GraphConfigError(f"duplicate node id {node.id!r}")
        nodes[node.id] = node

    edges: List[Edge] = []
    index: Dict[Tuple[str, str], Edge] = {}
    for raw in data.get("edges") or []:
        if not isinstance(raw, Mapping):
            raise GraphConfigError(f"edge entries must be mappings; found {raw!r}")
        raw = _normalise_edge_keys(raw)
        try:
            source, target, on = str(raw["from"]), str(raw["to"]), str(raw["on"])
        except KeyError as exc:
            raise GraphConfigError(
                f"edge {dict(raw)!r} is missing {exc.args[0]!r}"
            ) from None
        for end, label in ((source, "from"), (target, "to")):
            if end not in nodes:
                raise GraphConfigError(
                    f"edge {label} names undeclared node {end!r}; declared nodes are: "
                    f"{', '.join(nodes)}"
                )
        edge = Edge(source=source, target=target, on=on)
        edges.append(edge)
        # First declared wins; a later duplicate is ambiguity, not an override.
        if (source, on) in index:
            logger.warning(
                "graph declares more than one edge from %s on %r; the first "
                "declared one wins",
                source,
                on,
            )
        else:
            index[(source, on)] = edge

    start = str(data.get("start") or next(iter(nodes)))
    if start not in nodes:
        raise GraphConfigError(f"start node {start!r} is not declared")

    return Graph(
        nodes=nodes,
        edges=edges,
        start=start,
        version=int(data.get("version", 1)),
        _index=index,
    )


_CACHE: Dict[str, Graph] = {}


def load_graph(path: Optional[Path] = None, repo: Optional[Path] = None) -> Graph:
    """Load and compile the shipped graph. Cached per path — compiled once."""
    from . import hooks  # noqa: F401 — registers the built-ins before resolution

    if repo is not None:
        _warn_on_repo_graph(repo)
    target = Path(path) if path else shipped_graph_path()
    key = str(target)
    if key in _CACHE:
        return _CACHE[key]
    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise GraphConfigError(f"could not read the graph at {target}: {exc}") from None
    except yaml.YAMLError as exc:
        raise GraphConfigError(
            f"the graph at {target} is not valid YAML: {exc}"
        ) from None
    if not isinstance(data, Mapping):
        raise GraphConfigError(f"the graph at {target} must be a mapping")
    graph = compile_graph(data)
    _CACHE[key] = graph
    return graph


def _warn_on_repo_graph(repo: Path) -> None:
    """A repository cannot define the process — say so rather than merging it (R1.4)."""
    for candidate in (
        repo / ".the-loop" / "graph.yaml",
        repo / ".the-loop" / "pdlc.yaml",
    ):
        if candidate.is_file():
            logger.warning(
                "ignoring %s: the-loop's process graph ships with the plugin and "
                "cannot be overridden by a repository (user-defined graphs are a "
                "future feature)",
                candidate,
            )
