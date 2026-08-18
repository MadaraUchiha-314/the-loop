"""A repository's own hooks: declared in its harness config, run at the-loop's
boundaries (issue-248).

issue-109 shipped ten hooks and deferred *"user-defined graphs and user-authored
hooks"* to a later work item, on the stated grounds that "the declarative form and
the registry exist so it can arrive safely". This module is the **hooks** half of
that arrival, and only that half: the process graph is still the-loop's — a
repository cannot declare a node, an edge or a loop — but it can now append a check
of its own to a boundary the shipped graph already declares.

Four rules hold the whole design, and three of them are restrictions:

* **Declared in the harness config** (``graph.hooks``). A hook gating *this
  project's* artifacts is a property of the project, not of the operator's machine
  (decision-044), which is where ``reviews.critics[]`` already lives — and, like
  that entry, it is executable configuration in a repo-tracked file: review one
  like code (decision-043).
* **Append-only.** An attachment goes on the END of the node's shipped chain, so
  every shipped hook runs — and short-circuits — first. The strongest thing a
  repository hook can do to the loop is *stop* it.
* **``x-`` namespace, resolved per repository.** The prefix says whose code is
  about to run and makes shadowing a shipped hook impossible; the per-repository
  table means two repositories one daemon serves can both define ``x-house-rules``
  without seeing each other's.
* **No routing.** An attached hook's ``data["outcome"]`` is dropped by
  :func:`~the_loop.graph.chain.run_chain`, so no repository hook can classify a
  human gate or choose an edge.

Everything here fails at **load**: a module that is missing, unreadable, raises,
registers nothing or registers the wrong name stops the graph from compiling and
says which declaration did it. A gate the repository asked for must either run or
be loudly absent — degrading to "no hooks" is how a compliance check silently
stops running.

Spec: docs/specs/issue-248/  ·  Decision: 096
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import logging
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from .model import Graph, GraphConfigError, _validate_chain
from .registry import EXTENSION_PREFIX, HookFn, collecting

logger = logging.getLogger("the-loop.graph")

__all__ = [
    "Attachment",
    "Declaration",
    "ModuleRef",
    "apply",
    "load_modules",
    "read_declaration",
]

#: Where a repository declares its hooks, for messages that have to name it.
CONFIG_KEY = "graph.hooks"

#: The boundaries a repository may attach to — the node's own two.
BOUNDARIES = ("entry", "exit")

#: A dotted module name, and nothing that could be a path or an expression.
_DOTTED = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


@dataclass(frozen=True)
class ModuleRef:
    """One ``graph.hooks.modules[]`` entry: a file in the repository, or an
    installed module. Exactly one of the two, checked at parse time."""

    path: str = ""
    dotted: str = ""

    def label(self) -> str:
        return self.path or self.dotted


@dataclass(frozen=True)
class Attachment:
    """One ``graph.hooks.attach[]`` entry — a hook, a node, a boundary, params."""

    hook: str
    node: str
    boundary: str = "exit"
    params: Mapping[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        rendered = f"{self.hook} → {self.node} ({self.boundary})"
        return f"{rendered} with: {dict(self.params)}" if self.params else rendered


@dataclass(frozen=True)
class Declaration:
    """What a repository declared, parsed and validated — but not yet executed.

    Kept separate from loading on purpose: ``the-loop graph hooks`` reports this
    and stops, which is how an operator inspects a repository's declarations
    without running any of its code (R5.1).
    """

    modules: Tuple[ModuleRef, ...] = ()
    attachments: Tuple[Attachment, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.modules and not self.attachments

    def digest(self) -> str:
        """A stable fingerprint, so the compiled-graph cache is keyed by what the
        repository declared rather than by the shipped file alone."""
        payload = {
            "modules": [[m.path, m.dotted] for m in self.modules],
            "attach": [
                [a.hook, a.node, a.boundary, a.params] for a in self.attachments
            ],
        }
        blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]


# -- parsing (reads YAML; imports nothing) ------------------------------------


def read_declaration(harness: Mapping[str, Any]) -> Declaration:
    """Parse ``graph.hooks`` out of an already-loaded harness config.

    A malformed block raises rather than resolving to "no hooks" — the whole point
    of R4.4. An **absent** block is not malformed: it returns an empty declaration,
    which is what every repository that has never heard of this feature gets.
    """
    if not isinstance(harness, Mapping):
        return Declaration()
    block = harness.get("graph") or {}
    if not isinstance(block, Mapping):
        raise GraphConfigError("harness config: `graph` must be a mapping")
    raw = block.get("hooks") or {}
    if not raw:
        return Declaration()
    if not isinstance(raw, Mapping):
        raise GraphConfigError(
            f"harness config: `{CONFIG_KEY}` must be a mapping with `modules` "
            "and `attach` lists"
        )
    return Declaration(
        modules=_read_modules(raw.get("modules")),
        attachments=_read_attachments(raw.get("attach")),
    )


def _entries(value: Any, key: str) -> Sequence[Any]:
    if not value:
        return ()
    if isinstance(value, Mapping) or isinstance(value, str):
        raise GraphConfigError(f"harness config: `{CONFIG_KEY}.{key}` must be a list")
    if not isinstance(value, Sequence):
        raise GraphConfigError(f"harness config: `{CONFIG_KEY}.{key}` must be a list")
    return value


def _read_modules(value: Any) -> Tuple[ModuleRef, ...]:
    refs: list[ModuleRef] = []
    for entry in _entries(value, "modules"):
        if not isinstance(entry, Mapping):
            raise GraphConfigError(
                f"harness config: `{CONFIG_KEY}.modules` entry {entry!r} must be a "
                "mapping — write `- path: .the-loop/hooks/mine.py` or "
                "`- module: acme.hooks`, never a bare string, because a bare string "
                "cannot say which of the two it is"
            )
        path = str(entry.get("path") or "").strip()
        dotted = str(entry.get("module") or "").strip()
        if bool(path) == bool(dotted):
            raise GraphConfigError(
                f"harness config: `{CONFIG_KEY}.modules` entry {dict(entry)!r} must "
                "name exactly one of `path` (a .py file in this repository) or "
                "`module` (an installed dotted name)"
            )
        if dotted and not _DOTTED.match(dotted):
            raise GraphConfigError(
                f"harness config: `{CONFIG_KEY}.modules` module {dotted!r} is not an "
                "importable dotted name"
            )
        refs.append(ModuleRef(path=path, dotted=dotted))
    return tuple(refs)


def _read_attachments(value: Any) -> Tuple[Attachment, ...]:
    attachments: list[Attachment] = []
    for entry in _entries(value, "attach"):
        if not isinstance(entry, Mapping):
            raise GraphConfigError(
                f"harness config: `{CONFIG_KEY}.attach` entry {entry!r} must be a "
                "mapping of `hook`, `node`, and optionally `boundary` and `with`"
            )
        name = str(entry.get("hook") or "").strip()
        node = str(entry.get("node") or "").strip()
        boundary = str(entry.get("boundary") or "exit").strip()
        params = entry.get("with")
        params = {} if params is None else params
        if not name or not node:
            raise GraphConfigError(
                f"harness config: `{CONFIG_KEY}.attach` entry {dict(entry)!r} needs "
                "both a `hook` and a `node`"
            )
        if not name.startswith(EXTENSION_PREFIX):
            raise GraphConfigError(
                f"harness config: `{CONFIG_KEY}.attach` may only name a repository "
                f"hook, and those are named {EXTENSION_PREFIX}<something>; {name!r} "
                "is not one. Attaching a SHIPPED hook to another node would be "
                "editing the-loop's process, which a repository cannot do"
            )
        if boundary not in BOUNDARIES:
            raise GraphConfigError(
                f"harness config: `{CONFIG_KEY}.attach` entry for {name!r} names "
                f"boundary {boundary!r}; it must be one of {list(BOUNDARIES)}"
            )
        if not isinstance(params, Mapping):
            raise GraphConfigError(
                f"harness config: `{CONFIG_KEY}.attach` entry for {name!r} has a "
                "`with` that is not a mapping"
            )
        attachments.append(
            Attachment(hook=name, node=node, boundary=boundary, params=dict(params))
        )
    return tuple(attachments)


# -- loading (executes the repository's code) ---------------------------------

#: Hooks already collected from a module, keyed by its resolved source. A daemon
#: walking twenty work items in one repository imports each module once; the entry
#: also makes the load deterministic when a module is already in ``sys.modules``,
#: where the decorators would otherwise not run a second time.
_MODULE_CACHE: Dict[str, Dict[str, HookFn]] = {}


def clear_module_cache() -> None:
    """Forget every loaded module. For tests, and for a process that reloads."""
    _MODULE_CACHE.clear()


def load_modules(repo: Path, declaration: Declaration) -> Dict[str, HookFn]:
    """Execute the declared modules and return this repository's hook table."""
    table: Dict[str, HookFn] = {}
    for ref in declaration.modules:
        for name, fn in _load_one(repo, ref).items():
            if name in table:
                raise GraphConfigError(
                    f"two hook modules of this repository register {name!r}; "
                    f"the second is {ref.label()!r}"
                )
            table[name] = fn
    return table


def _load_one(repo: Path, ref: ModuleRef) -> Dict[str, HookFn]:
    target = _contained(repo, ref.path) if ref.path else None
    key = f"path:{target}" if target is not None else f"module:{ref.dotted}"
    cached = _MODULE_CACHE.get(key)
    if cached is not None:
        return cached
    with collecting() as collected:
        try:
            if target is not None:
                _execute_file(target, key)
            else:
                _import_dotted(ref.dotted)
        except GraphConfigError:
            raise
        except BaseException as exc:  # noqa: BLE001 — every failure names the module
            raise GraphConfigError(
                f"the hook module {ref.label()!r} declared in `{CONFIG_KEY}` could "
                f"not be loaded: {exc.__class__.__name__}: {exc}"
            ) from None
        hooks = dict(collected)
    if not hooks:
        raise GraphConfigError(
            f"the hook module {ref.label()!r} declared in `{CONFIG_KEY}` registered "
            f"no hooks; decorate a function with @hook('{EXTENSION_PREFIX}<name>')"
        )
    _MODULE_CACHE[key] = hooks
    return hooks


def _contained(repo: Path, raw: str) -> Path:
    """Resolve ``raw`` inside ``repo``, or refuse it.

    What a repository declares must be code the repository carries, so its own
    reviewers see it. An absolute path, a ``..`` escape and a symlink out of the
    tree are all the same defect and get the same answer (R5.3).
    """
    candidate = Path(raw)
    if candidate.is_absolute():
        raise GraphConfigError(
            f"`{CONFIG_KEY}.modules` path {raw!r} is absolute; a hook module is "
            "named relative to the repository root, and must live inside it"
        )
    root = Path(repo).resolve()
    target = (root / candidate).resolve()
    if not target.is_relative_to(root):
        raise GraphConfigError(
            f"`{CONFIG_KEY}.modules` path {raw!r} resolves outside the repository "
            f"({target}); a repository may only run hook code it carries"
        )
    if target.suffix != ".py":
        raise GraphConfigError(
            f"`{CONFIG_KEY}.modules` path {raw!r} is not a .py file"
        )
    if not target.is_file():
        raise GraphConfigError(
            f"`{CONFIG_KEY}.modules` path {raw!r} does not exist ({target})"
        )
    return target


def _execute_file(target: Path, key: str) -> None:
    """Execute ``target`` as a module under a synthetic, collision-proof name."""
    name = "the_loop_repo_hooks_" + hashlib.sha256(key.encode()).hexdigest()[:16]
    spec = importlib.util.spec_from_file_location(name, target)
    if spec is None or spec.loader is None:
        raise GraphConfigError(f"{target} could not be loaded as a Python module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise


def _import_dotted(dotted: str) -> None:
    """Import ``dotted``, re-executing it when it is already imported.

    A module Python has already loaded runs no decorator on a second import, so
    an already-imported module would collect nothing and be reported as "registers
    no hooks". Reloading is what makes the two cases behave the same — which is
    also why a hook module must be safe to execute twice: define hooks, do nothing
    else.
    """
    existing = sys.modules.get(dotted)
    if existing is not None:
        importlib.reload(existing)
        return
    importlib.import_module(dotted)


# -- attaching ----------------------------------------------------------------


def apply(graph: Graph, repo: Path, declaration: Declaration) -> Graph:
    """``graph`` with this repository's hooks loaded and appended to its nodes."""
    if declaration.empty:
        return graph
    table = load_modules(Path(repo), declaration)
    known = table.__contains__
    nodes = dict(graph.nodes)
    for attachment in declaration.attachments:
        if attachment.hook not in table:
            raise GraphConfigError(
                f"`{CONFIG_KEY}.attach` names {attachment.hook!r}, which no declared "
                f"module registered; registered hooks are: "
                f"{', '.join(sorted(table)) or '(none)'}"
            )
        node = nodes.get(attachment.node)
        if node is None:
            raise GraphConfigError(
                f"`{CONFIG_KEY}.attach` names node {attachment.node!r}, which the "
                f"{graph.name or 'loaded'} loop does not declare; its nodes are: "
                f"{', '.join(nodes)}"
            )
        entry: Dict[str, Any] = {"hook": attachment.hook}
        if attachment.params:
            entry["with"] = dict(attachment.params)
        appended = _validate_chain(node.id, attachment.boundary, [entry], known=known)
        chain = tuple(getattr(node, attachment.boundary)) + appended
        nodes[attachment.node] = replace(node, **{attachment.boundary: chain})
    logger.info(
        "loaded %d repository hook(s) from %d module(s) and attached %d of them",
        len(table),
        len(declaration.modules),
        len(declaration.attachments),
    )
    unattached = sorted(set(table) - {a.hook for a in declaration.attachments})
    if unattached:
        # Executed code that gates nothing. Not an error — a hook may be attached
        # in the next commit — but silence here reads as "my check is running".
        logger.warning(
            "%s: registered but attached to no node, so %s will never run; add an "
            "entry under `%s.attach`",
            ", ".join(unattached),
            "they" if len(unattached) > 1 else "it",
            CONFIG_KEY,
        )
    return replace(graph, nodes=nodes, extension_hooks=dict(table))
