"""The graph: parse, validate, resolve, index, freeze — once, at load.

"Compile" here means exactly those five things (issue-109, R6b.1). The point is
that **every structural failure is a startup failure** — an unknown hook, an
edge pointing at a node that does not exist, a malformed chain entry — rather
than a surprise three nodes into a traversal at 2am.

The shipped graphs live **with the CLI**, as package data beside this module
(R1.1) — the CLI is what executes them, and every hook they name is registered
here. A repository cannot define or override one; a repo-supplied file is ignored
with a warning (R1.4). The **operator** can declare graphs of their own in the
CLI config (top-level ``graphs``, issue-343): compiled by the same code, held
to the same vocabulary, selected only by name from that declaration
(:mod:`the_loop.graph.catalog`).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Collection,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

import yaml

from .registry import HookFn, get_hook, hook_names, is_registered

#: The five shipped loops. The OUTER loop (issue-172, PR #173 review) walks a
#: work item through the PDLC; the INNER loop walks one pull request through
#: the subset of it that delivers a component — in service of the work item.
#: The CONTRIBUTION loop (issue-185) is the path walked when the-loop is
#: invited into an EXISTING, in-progress work item as a contributor: it cannot
#: start without an authorized human's goal and success criteria, and its
#: phases are sized for a scoped intervention. The AD-HOC loop (issue-225) is
#: the smallest of them: a tactical task that runs NO PDLC process at all —
#: work, talk to the requester, stop when they say stop. The REVIEW loop
#: (issue-279) makes the-loop the REVIEWER of a pull request rather than its
#: author: no brief, no review; findings and follow-ups on the thread; no code
#: changed. Same vocabulary, same hooks, same runtime; different node sets,
#: different state files. A pdlc-project-management-loop is anticipated by the
#: naming and deliberately not shipped yet.
PDLC_WORK_ITEM_LOOP = "pdlc-work-item-loop"
PDLC_PR_LOOP = "pdlc-pr-loop"
PDLC_CONTRIBUTION_LOOP = "pdlc-contribution-loop"
PDLC_ADHOC_LOOP = "pdlc-adhoc-loop"
PDLC_REVIEW_LOOP = "pdlc-review-loop"

#: Every loop name :func:`load_graph` accepts. The membership check is a
#: security seam, not bookkeeping: `work-item-state.json` is agent-writable and its
#: `loop` field feeds graph selection (issue-185), so a reader resolving that
#: field must accept only these names and fall back to the default otherwise.
SHIPPED_LOOPS = (
    PDLC_WORK_ITEM_LOOP,
    PDLC_PR_LOOP,
    PDLC_CONTRIBUTION_LOOP,
    PDLC_ADHOC_LOOP,
    PDLC_REVIEW_LOOP,
)

#: The loops a WORK ITEM's outer path may walk — every shipped loop except the
#: inner one, which is addressed by pull-request number and keeps its own state
#: layout (``pr-loops/…``) rather than being named. Membership here is what
#: :func:`resolve_outer_loop` answers, and every reader of the agent-writable
#: ``WorkItemState.loop`` goes through it.
OUTER_PATH_LOOPS = (
    PDLC_WORK_ITEM_LOOP,
    PDLC_CONTRIBUTION_LOOP,
    PDLC_ADHOC_LOOP,
    PDLC_REVIEW_LOOP,
)

#: The loops that run as a GUEST in somebody else's repository — the-loop was
#: invited in (to contribute, issue-185; to review, issue-279), so its machinery
#: stays out of that repository's history: no adoption write, and the spec tree
#: git-excluded when the host never initialized the-loop (PR #187). One named
#: set rather than per-loop comparisons at each call site, so a sixth guest
#: cannot be added without every carve-out following.
GUEST_LOOPS = (PDLC_CONTRIBUTION_LOOP, PDLC_REVIEW_LOOP)

#: Which outer-path loop an arming CONTROL COMMAND selects (issue-185,
#: issue-225, issue-279). Keyed by the command constants in
#: :mod:`the_loop.control` as plain strings, deliberately: ``control`` is a
#: low-level module with no graph imports, and the loop names live here — the
#: module that already decides which of them may be honoured. A test asserts
#: these keys are real commands, so a rename cannot silently orphan the mapping.
#: A command absent from this mapping (``start``, ``resume``, …) selects the
#: default outer loop.
LOOP_FOR_CONTROL_COMMAND: Dict[str, str] = {
    "contribute": PDLC_CONTRIBUTION_LOOP,
    "do": PDLC_ADHOC_LOOP,
    "review": PDLC_REVIEW_LOOP,
}

#: Every phase a node may declare, in walk order (issue-343). The ``loop:<phase>``
#: label vocabulary is one fixed list (decision-123 D3) so a dashboard built on it
#: works for every repository — which is why an operator's own graph is held to it
#: rather than minting labels of its own. A test pins it equal to the union of the
#: shipped loops' phases, so a new shipped phase lands here in the same change.
PHASE_VOCABULARY = (
    "phase-selection",
    "brainstorming",
    "requirements-definition",
    "design",
    "test-planning",
    "tasks-breakdown",
    "implementation",
    "verification",
    "needs-review",
    "complete",
    "cleanup",
)

#: What a node's ``command:`` may say (issue-343): a slash command of the-loop's
#: own (``do-task``) or, namespaced, one of another plugin's (``acme:triage``).
#: Checked for every graph, so the text a session is told to run can never carry
#: whitespace, a path or a second instruction.
_COMMAND = re.compile(r"^[a-z0-9][a-z0-9-]*(:[a-z0-9][a-z0-9-]*)?$")

#: The default shipped graph — the outer loop — package data beside this module
#: (see shipped_graph_path). Named pdlc.yaml before issue-172 split the process
#: into the two loops.
GRAPH_FILENAME = f"{PDLC_WORK_ITEM_LOOP}.yaml"

if TYPE_CHECKING:  # pragma: no cover
    from .catalog import Catalog
    from .extensions import Declaration

logger = logging.getLogger("the-loop.graph")

__all__ = [
    "ALTERNATIVE_SEPARATOR",
    "GUEST_LOOPS",
    "LOOP_FOR_CONTROL_COMMAND",
    "OUTER_PATH_LOOPS",
    "PDLC_ADHOC_LOOP",
    "PDLC_CONTRIBUTION_LOOP",
    "PDLC_PR_LOOP",
    "PDLC_REVIEW_LOOP",
    "PDLC_WORK_ITEM_LOOP",
    "PHASE_VOCABULARY",
    "SHIPPED_LOOPS",
    "ArtifactSlot",
    "Edge",
    "Graph",
    "GraphConfigError",
    "Node",
    "artifact_names",
    "extension_hook_names",
    "load_graph",
    "resolve_outer_loop",
    "resolve_produces",
    "shipped_graph_path",
    "slash_command",
    "validate_produces_entry",
]


def resolve_outer_loop(name: str, declared: Collection[str] = ()) -> str:
    """``name`` when it is a **non-default** outer-path loop, else ``""``.

    The one place that decides whether a recorded loop name may choose a graph.
    It exists because the value routinely arrives from somewhere the-loop does
    not control — ``work-item-state.json`` is agent-writable, and a control record
    is written from a comment — so the check must fail closed and must not be
    re-implemented per reader (it was, three times, before issue-225 added a
    fourth loop and made the copies disagree about what "not the default" means).

    ``""`` covers all four ways a caller has nothing to select with: an empty
    value, the default outer loop itself, the *inner* loop (addressed by
    pull-request number, never by name — selecting it here would walk a pull
    request's graph with a work item's state layout), and anything invented.

    ``declared`` is the operator's own graph names (issue-343,
    the top-level ``graphs``): an exact member selects that graph. It is the
    only way the set grows — a name the operator does not declare *now* reads as
    the default, however it got into the state file.
    """
    value = str(name or "")
    if value and value in tuple(declared) and value not in SHIPPED_LOOPS:
        return value
    if value == PDLC_WORK_ITEM_LOOP or value not in OUTER_PATH_LOOPS:
        return ""
    return value


def slash_command(command: str) -> str:
    """The slash command a node's ``command:`` names, as a session types it.

    A bare name is one of the-loop's own (``do-task`` → ``/the-loop:do-task``);
    a namespaced one is another plugin's, rendered verbatim (``acme:triage`` →
    ``/acme:triage``) — how an operator's graph points a session at its own
    commands (issue-343). The grammar is enforced at compile time, so the
    result is always one token.
    """
    value = str(command or "")
    return f"/{value}" if ":" in value else f"/the-loop:{value}"


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
    #: May a HUMAN declare this node skipped for one work item (issue-177)?
    #: Distinct from ``optional``, which lets the node skip itself when no
    #: artifact was produced — ``skippable`` is a vocabulary entry for the
    #: declared-skips mechanism, and only the shipped graph can grant it.
    skippable: bool = False
    #: Is this node OFF unless a human selects it at ``phase-selection``
    #: (issue-188)? The mirror image of ``skippable``: same gate, same
    #: authorization, same provenance — opposite default. ``optIn`` implies
    #: ``skippable``, so an opt-in node is part of the declared-skip vocabulary
    #: and declares its own ``on: skipped`` edge like every other member; what
    #: differs is that nobody has to act for it to be skipped.
    opt_in: bool = False
    #: One line rendered beside this node's row on the phase-selection
    #: checklist (issue-188). Shipped-graph text, never repo-supplied: a phase a
    #: reader has to guess at is a phase they will not choose.
    description: str = ""
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
            "skippable": self.skippable,
            "optIn": self.opt_in,
            "description": self.description,
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
    #: Which loop this is (issue-172): pdlc-work-item-loop | pdlc-pr-loop.
    #: "" for an anonymous test graph — nothing branches on it being set.
    name: str = ""
    #: Named bundles of skippable nodes (issue-177): one label/token declares
    #: the whole set. Compile-validated — every member is a declared, skippable
    #: node — so no set can smuggle a protected gate into the vocabulary.
    skip_sets: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    #: This REPOSITORY's own hooks (issue-248), by ``x-`` name. Carried on the
    #: compiled graph rather than in the process-global registry because a daemon
    #: walks several repositories in one process, and two of them may legitimately
    #: define the same name. Empty for every repository that declares none.
    extension_hooks: Mapping[str, HookFn] = field(default_factory=dict, repr=False)
    _index: Dict[Tuple[str, str], Edge] = field(default_factory=dict, repr=False)

    def hook_for(self, name: str) -> HookFn:
        """The function ``name`` resolves to **for this graph**.

        This repository's table first, the shipped registry second — and the two
        can never collide, because a repository hook is required to carry the
        ``x-`` prefix and a shipped one is refused it.
        """
        fn = self.extension_hooks.get(name)
        return fn if fn is not None else get_hook(name)

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

    def expand_skip_tokens(
        self, tokens: Sequence[str]
    ) -> Tuple[Dict[str, str], List[str]]:
        """Resolve skip tokens — node ids or skip-set names — against the
        vocabulary (issue-177).

        Returns ``(accepted, rejected)``: accepted maps each skippable node id
        to the token that declared it (first declaration wins, order
        preserved); rejected keeps every token that names nothing skippable —
        an unknown name, a protected node, a typo. The one shared resolver for
        both declaration channels (labels and the CLI verb), so what a label
        may declare and what the verb may declare cannot drift apart.
        """
        accepted: Dict[str, str] = {}
        rejected: List[str] = []
        for raw in tokens:
            token = str(raw).strip()
            if not token:
                continue
            if token in self.skip_sets:
                for node_id in self.skip_sets[token]:
                    accepted.setdefault(node_id, token)
                continue
            node = self.nodes.get(token)
            if node is not None and node.skippable:
                accepted.setdefault(token, token)
            else:
                rejected.append(token)
        return accepted, rejected


def shipped_graph_path(name: str = PDLC_WORK_ITEM_LOOP) -> Path:
    """The named shipped loop, as package data beside this module.

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
    candidate = Path(__file__).resolve().parent / f"{name}.yaml"
    if candidate.is_file():
        return candidate
    raise GraphConfigError(
        f"the shipped graph {name!r} is missing from the installed package "
        f"({candidate}). This is a packaging fault, not a configuration one — "
        "reinstall the-loopy-one."
    )


def _validate_chain(
    node_id: str,
    boundary: str,
    specs: Sequence[Any],
    known: Optional[Callable[[str], bool]] = None,
) -> Tuple[Any, ...]:
    """Validate one chain's entries. ``known`` widens what counts as registered —
    a repository's own table when this is validating an attachment (issue-248) —
    so a shipped entry and an appended one are checked by the same code."""
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
        if not (is_registered(name) or (known is not None and known(name))):
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


def _build_node(
    raw: Mapping[str, Any], known: Optional[Callable[[str], bool]] = None
) -> Node:
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
    command = str(raw.get("command", "") or "")
    if command and not _COMMAND.match(command):
        raise GraphConfigError(
            f"node {node_id!r}: command {command!r} is not a slash-command name; "
            "write `do-task` for one of the-loop's own or `acme:triage` for "
            "another plugin's"
        )
    produces = raw.get("produces") or []
    if isinstance(produces, str):
        produces = [produces]
    for entry in produces:
        validate_produces_entry(node_id, entry)
    opt_in = bool(raw.get("optIn", False))
    if bool(raw.get("required", False)) and opt_in:
        # Checked BEFORE the skippable pair below, and separately: `optIn`
        # implies `skippable`, so the other message would name a marker this
        # author never wrote and send them looking for it in the wrong line.
        raise GraphConfigError(
            f"node {node_id!r} is both required and optIn — a mandatory gate "
            "cannot be off until somebody asks for it (issue-188)"
        )
    if bool(raw.get("required", False)) and bool(raw.get("skippable", False)):
        raise GraphConfigError(
            f"node {node_id!r} is both required and skippable — a mandatory "
            "gate cannot also be in the skip vocabulary (issue-177)"
        )
    return Node(
        id=node_id,
        phase=str(raw.get("phase", "")),
        actor=actor,
        produces=tuple(str(p) for p in produces),
        command=command,
        stage=str(raw.get("stage", "")),
        session=session,
        required=bool(raw.get("required", False)),
        optional=bool(raw.get("optional", False)),
        # `optIn` implies `skippable` (issue-188): an opt-in node is routed
        # around by the same `on: skipped` edge, reported by the same code and
        # authorized at the same gate — only its default differs.
        skippable=bool(raw.get("skippable", False)) or opt_in,
        opt_in=opt_in,
        description=str(raw.get("description", "") or "").strip(),
        max_attempts=int(raw.get("maxAttempts", 3)),
        entry=_validate_chain(node_id, "entry", raw.get("entry") or [], known),
        exit=_validate_chain(node_id, "exit", raw.get("exit") or [], known),
        terminal=bool(raw.get("terminal", False)),
    )


def compile_graph(
    data: Mapping[str, Any], known: Optional[Callable[[str], bool]] = None
) -> Graph:
    """Compile a parsed mapping into a frozen, indexed :class:`Graph`.

    ``known`` widens which hook names count as registered — an operator's graph
    passes a predicate accepting ``x-`` names, which :func:`load_graph` then
    resolves against the declared modules (issue-343). ``None`` — every shipped
    graph — accepts the shipped registry alone.
    """
    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise GraphConfigError("the graph declares no nodes")

    nodes: Dict[str, Node] = {}
    for raw in raw_nodes:
        if not isinstance(raw, Mapping):
            raise GraphConfigError(f"node entries must be mappings; found {raw!r}")
        node = _build_node(raw, known)
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

    # Declared skips (issue-177): routing around a skippable node is authored
    # in the graph, never inferred — a skippable node without its `on: skipped`
    # edge would leave the runtime guessing at 2am, so it fails at load.
    for node in nodes.values():
        if node.skippable and (node.id, "skipped") not in index:
            raise GraphConfigError(
                f"node {node.id!r} is skippable but declares no edge for the "
                "outcome 'skipped'; add '{from: "
                f"{node.id}, to: <next>, on: skipped}}'"
            )

    skip_sets: Dict[str, Tuple[str, ...]] = {}
    raw_sets = data.get("skipSets") or {}
    if not isinstance(raw_sets, Mapping):
        raise GraphConfigError("skipSets must be a mapping of name -> node list")
    for set_name, members in raw_sets.items():
        if not isinstance(members, Sequence) or isinstance(members, str):
            raise GraphConfigError(f"skip set {set_name!r} must be a list of node ids")
        resolved: List[str] = []
        for member in members:
            member_id = str(member)
            node = nodes.get(member_id)
            if node is None or not node.skippable:
                raise GraphConfigError(
                    f"skip set {set_name!r} names {member_id!r}, which is not "
                    "a declared skippable node — a set cannot widen the skip "
                    "vocabulary (issue-177)"
                )
            if node.opt_in:
                # A skip set declares phases *away*, and an opt-in phase is
                # already away. Naming one here would make a token that reads
                # as "drop these" silently a no-op for one of its members
                # (issue-188).
                raise GraphConfigError(
                    f"skip set {set_name!r} names {member_id!r}, which is an "
                    "opt-in node — it does not run unless it is selected, so "
                    "declaring it skipped says nothing (issue-188)"
                )
            resolved.append(member_id)
        skip_sets[str(set_name)] = tuple(resolved)

    return Graph(
        nodes=nodes,
        edges=edges,
        start=start,
        version=int(data.get("version", 1)),
        name=str(data.get("name", "")),
        skip_sets=skip_sets,
        _index=index,
    )


_CACHE: Dict[Tuple[str, str, str, str], Graph] = {}


def load_graph(
    path: Optional[Path] = None,
    repo: Optional[Path] = None,
    name: str = PDLC_WORK_ITEM_LOOP,
    declaration: Optional["Declaration"] = None,
    catalog: Optional["Catalog"] = None,
) -> Graph:
    """Load and compile a loop. Cached — compiled once per declaration.

    ``name`` selects which loop when no explicit ``path`` is given: one of the
    shipped loops (package data beside this module), or — issue-343 — a graph the
    operator declared in the top-level ``graphs``, passed here as ``catalog``.
    Both kinds are compiled by the same code and executed by the same runtime; a
    name that is neither is a :class:`GraphConfigError`, never a fallback.

    ``declaration`` is the operator's ``routing.graph.hooks`` block, already
    parsed (issue-248, re-homed in issue-352): its modules are executed and its
    hooks appended to the nodes it named, with any ``path`` entry resolved
    against ``repo`` — the checkout the loop is walked in. That is why the cache
    key carries the repository and the declaration's digest. ``None`` — every
    caller that has no CLI config at hand — compiles the file alone.
    ``repo`` without a declaration still warns about a repository-supplied graph
    file, which the-loop ignores.
    """
    from . import hooks  # noqa: F401 — registers the built-ins before resolution
    from .extensions import Declaration, apply

    declared = declaration if declaration is not None else Declaration()
    custom = (
        catalog.get(name)
        if catalog is not None and not path and name not in SHIPPED_LOOPS
        else None
    )
    if repo is not None:
        _warn_on_repo_graph(repo, catalog.names if catalog is not None else ())
    if path:
        target = Path(path)
    elif custom is not None:
        target = custom.resolved_path()
    elif name in SHIPPED_LOOPS:
        target = shipped_graph_path(name)
    else:
        raise GraphConfigError(
            f"loop {name!r} is neither one of the-loop's shipped loops "
            f"({', '.join(SHIPPED_LOOPS)}) nor declared in the CLI config's "
            "top-level `graphs`"
        )
    key = (
        str(target),
        custom.name if custom is not None else "",
        str(repo or ""),
        declared.digest(),
    )
    if key in _CACHE:
        return _CACHE[key]
    if custom is not None:
        from .catalog import compile_custom

        graph = compile_custom(custom, target)
        graph = _resolve_extensions(graph, repo, declared)
        logger.info("loaded %s, the operator's own graph, from %s", custom.name, target)
    else:
        graph = compile_graph(_read_graph_file(target))
    if repo is not None and not declared.empty:
        graph = apply(graph, Path(repo), declared)
    _CACHE[key] = graph
    return graph


def _read_graph_file(target: Path, label: str = "") -> Mapping[str, Any]:
    """``target`` parsed as a YAML mapping, or a :class:`GraphConfigError` that
    names it — and, for an operator's graph, which declaration pointed there."""
    where = f"the graph at {target}" + (f" (declared as {label!r})" if label else "")
    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise GraphConfigError(f"could not read {where}: {exc}") from None
    except yaml.YAMLError as exc:
        raise GraphConfigError(f"{where} is not valid YAML: {exc}") from None
    if not isinstance(data, Mapping):
        raise GraphConfigError(f"{where} must be a mapping")
    return data


def extension_hook_names(graph: Graph) -> List[str]:
    """Every ``x-`` hook ``graph``'s own chains name, sorted (issue-343).

    Only an operator's graph can have any — the shipped registry refuses the
    prefix — and they are what :func:`load_graph` resolves against the declared
    modules, and what ``the-loop graph loops`` lists without importing one.
    """
    from .registry import EXTENSION_PREFIX

    names = set()
    for node in graph.nodes.values():
        for spec in tuple(node.entry) + tuple(node.exit):
            name = spec if isinstance(spec, str) else str(spec.get("hook", ""))
            if name.startswith(EXTENSION_PREFIX):
                names.add(name)
    return sorted(names)


def _resolve_extensions(
    graph: Graph, repo: Optional[Path], declared: "Declaration"
) -> Graph:
    """Bind the ``x-`` hooks an operator's graph names to the declared modules.

    Deferred at compile time (the compiler accepted any ``x-`` name) and settled
    here, where the repository and the declaration are both in hand: a name no
    declared module registers fails the load, exactly as an unknown shipped hook
    does — a gate the graph asked for either runs or is loudly absent.
    """
    wanted = extension_hook_names(graph)
    if not wanted:
        return graph
    if repo is None or not declared.modules:
        raise GraphConfigError(
            f"the {graph.name} loop names {', '.join(wanted)}, but no module in "
            "`routing.graph.hooks.modules` is loaded for it; declare the module "
            "that registers them"
        )
    from dataclasses import replace

    from .extensions import load_modules

    table = load_modules(Path(repo), declared)
    missing = [name for name in wanted if name not in table]
    if missing:
        raise GraphConfigError(
            f"the {graph.name} loop names {', '.join(missing)}, which no declared "
            f"module registered; registered hooks are: "
            f"{', '.join(sorted(table)) or '(none)'}"
        )
    return replace(graph, extension_hooks=dict(table))


def _warn_on_repo_graph(repo: Path, declared: Sequence[str] = ()) -> None:
    """A repository cannot define the process — say so rather than merging it (R1.4).

    The candidate list is **derived** from :data:`SHIPPED_LOOPS` plus the two
    historical filenames, rather than written out: a hand-maintained copy is how
    the fourth loop shipped with no warning for its own override (issue-225).
    ``declared`` adds the operator's own graph names (issue-343): a repository
    file of that name is not what runs either, and saying so is how the
    difference is found.
    """
    candidates = [repo / ".the-loop" / "graph.yaml", repo / ".the-loop" / "pdlc.yaml"]
    candidates += [
        repo / ".the-loop" / f"{name}.yaml" for name in (*SHIPPED_LOOPS, *declared)
    ]
    for candidate in candidates:
        if candidate.is_file():
            logger.warning(
                "ignoring %s: a repository's graph file cannot be overridden into "
                "the-loop's process; an operator declares their own graphs in the "
                "CLI config's top-level `graphs`",
                candidate,
            )
