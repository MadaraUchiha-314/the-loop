"""The graph: parse, validate, resolve, index, freeze — once, at load.

"Compile" here means exactly those five things (issue-109, R6b.1). The point is
that **every structural failure is a startup failure** — an unknown hook, an
edge pointing at a node that does not exist, a malformed chain entry — rather
than a surprise three nodes into a traversal at 2am.

The graph ships **with the CLI**, as package data beside this module (R1.1) —
the CLI is what executes it, and every hook it names is registered here. A
repository cannot define or override it; a repo-supplied one is ignored with a
warning (R1.4). It stays fully declarative so user-authored graphs can arrive
later as a distribution change rather than a rewrite.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import yaml

from .registry import hook_names, is_registered

#: The shipped graph, package data beside this module (see shipped_graph_path).
GRAPH_FILENAME = "pdlc.yaml"

logger = logging.getLogger("the-loop.graph")

__all__ = [
    "ALTERNATIVE_SEPARATOR",
    "ArtifactSlot",
    "Edge",
    "Graph",
    "GraphConfigError",
    "Node",
    "artifact_names",
    "load_graph",
    "resolve_produces",
    "shipped_graph_path",
    "validate_produces_entry",
]

_ACTORS = frozenset({"agent", "human", "code"})
_SESSION_MODES = frozenset({"new", "inherit"})

#: Separates the names one ``produces`` entry accepts:
#: ``requirements.md|bugfix.md`` means *one* artifact that may be called either
#: (issue-124, decision-045). One artifact, several accepted names — not two
#: artifacts, which is why the entry is kept verbatim in :attr:`Node.produces`
#: and only split at resolution time.
ALTERNATIVE_SEPARATOR = "|"


class GraphConfigError(ValueError):
    """The graph could not be compiled. Always names the offending element."""


# -- the ``produces`` name contract -------------------------------------------
#
# One artifact may have several accepted names: a bug's phase-1 spec is called
# ``bugfix.md``, and the-loop has documented that in the skill, the workflow
# reference, the manifest and a bundled template since long before the graph
# existed (issue-124). The graph had no way to say it, so every bug work item
# blocked at phase 1 for the absence of a ``requirements.md`` the documentation
# told it not to write.
#
# The resolver lives here, in the module that already owns ``produces`` and is
# where a structural fault becomes a startup failure, so the two hooks that read
# it cannot drift apart — they used to carry a byte-identical private copy each,
# which is the same defect one level down.


@dataclass(frozen=True)
class ArtifactSlot:
    """One ``produces`` entry, resolved against a work item's spec folder.

    A *slot* is one artifact the node must produce, under any one of the names
    its entry accepts. ``present`` is the subset that exists on disk, in
    declaration order — empty means the node produced nothing, and more than one
    means the folder is ambiguous about which file is the source of truth.
    """

    names: Tuple[str, ...]
    candidates: Tuple[Path, ...]
    present: Tuple[Path, ...]

    @property
    def alternatives(self) -> bool:
        """Does this slot accept more than one name?"""
        return len(self.names) > 1

    def label(self) -> str:
        """The accepted names, for a message: ``requirements.md, bugfix.md``."""
        return ", ".join(self.names)


def artifact_names(entry: object) -> Tuple[str, ...]:
    """The names one ``produces`` entry accepts, in declaration order."""
    return tuple(
        part.strip() for part in str(entry).split(ALTERNATIVE_SEPARATOR) if part.strip()
    )


def validate_produces_entry(node_id: str, entry: object) -> None:
    """Reject a malformed entry at compile time (R1.2).

    ``a||b``, ``|a``, ``a|`` and a bare separator are all authoring slips that
    would otherwise resolve to a silently shorter list of names — a gate quietly
    accepting fewer artifacts than its author wrote. Every structural failure is
    a startup failure, so this raises rather than warns.
    """
    raw = str(entry)
    parts = raw.split(ALTERNATIVE_SEPARATOR)
    if any(not part.strip() for part in parts):
        raise GraphConfigError(
            f"node {node_id!r}: produces entry {raw!r} has an empty alternative; "
            f"write the accepted names as 'first.md{ALTERNATIVE_SEPARATOR}second.md'"
        )


def resolve_produces(produces: object, spec_dir: Path) -> List[ArtifactSlot]:
    """Resolve a node's ``produces`` against ``spec_dir``, one slot per entry.

    The single shared resolver for every hook that reads ``produces``. It never
    *chooses* between present alternatives — that is a policy decision, and the
    hooks make it explicitly (``validate-artifacts`` blocks on ambiguity rather
    than preferring whichever name the graph happened to list first).
    """
    entries: List[Any]
    if not produces:
        entries = []
    elif isinstance(produces, (str, Path)):
        entries = [produces]
    elif isinstance(produces, Sequence):
        entries = list(produces)
    else:
        entries = [produces]

    slots: List[ArtifactSlot] = []
    for entry in entries:
        names = artifact_names(entry)
        candidates = tuple(spec_dir / name for name in names)
        slots.append(
            ArtifactSlot(
                names=names,
                candidates=candidates,
                present=tuple(p for p in candidates if p.is_file()),
            )
        )
    return slots


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
    """The graph that ships with the CLI, as package data beside this module.

    **It belongs to the CLI, not to the plugin.** The plugin is the harness
    integration — skills, commands, hooks that teach an agent the process. The
    graph is *executed*, and the thing that executes it is this package: every
    hook the graph names is registered in ``the_loop.graph.hooks``. A graph
    shipped anywhere else is a graph the runtime may not have.

    It previously lived under ``skills/the-loop/graph/``, which meant
    ``pip install the-loopy-one`` produced a runtime with no process to run —
    ``the-loop check`` failed, advising the operator to set ``CLAUDE_PLUGIN_ROOT``
    to a plugin they had never installed. One copy, in the package, resolved
    relative to this file, so it works identically from a wheel, an editable
    install and a repository checkout.
    """
    candidate = Path(__file__).resolve().parent / GRAPH_FILENAME
    if candidate.is_file():
        return candidate
    raise GraphConfigError(
        f"the shipped graph is missing from the installed package "
        f"({candidate}). This is a packaging fault, not a configuration one — "
        "reinstall the-loopy-one."
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
    for entry in produces:
        validate_produces_entry(node_id, entry)
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
                "ignoring %s: the-loop's process graph ships with the CLI and "
                "cannot be overridden by a repository (user-defined graphs are a "
                "future feature)",
                candidate,
            )
