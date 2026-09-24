"""Graphs of the operator's own, and the commands that select them (issue-343).

issue-109 shipped the process as data and deferred *"user-defined graphs and
user-authored hooks"*; issue-248 delivered the hooks half. This module is the
graphs half, in two declarations the owner asked to keep apart (PR #425 review):

* **which graphs exist** — the top-level ``graphs`` list: a name, a YAML file the
  operator wrote, and whether it walks as a guest;
* **which command selects which graph** — ``routing.control.commands``: an
  existing arming command re-pointed (``do: {graph: acme-quick-loop}``) or a new
  word (``triage: {graph: acme-triage-loop}``), which then arms like ``start``.
  A command with no entry keeps selecting what it always did.

Four rules hold it together:

* **Declared by the operator, never by a repository.** Both live in the CLI
  config, beside ``critics[]`` and ``routing.graph.hooks`` (decision-123); a path
  resolves against that file's directory, never against a work item's checkout,
  so no session can rewrite the gates of the graph it is walking.
* **Held to the shipped rules.** The same compiler, the same hook registry (plus
  the operator's ``x-`` hooks), and the same phase vocabulary — the
  ``loop:<phase>`` labels are one list for every repository.
* **Selected by name, from the declaration only.** A recorded loop name picks a
  graph here only when the operator declares it now; anything else reads as the
  default, the rule the agent-writable state file already demanded.
* **Fails at load.** A malformed entry, a reserved or colliding name, a command
  that does not select a loop, a binding to a graph nobody declared, an
  unreadable file — each raises, naming what did it.

Spec: docs/specs/issue-343/  ·  Decision: 136
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from .model import (
    OUTER_PATH_LOOPS,
    PHASE_VOCABULARY,
    SHIPPED_LOOPS,
    Graph,
    GraphConfigError,
    _read_graph_file,
    compile_graph,
)
from .registry import EXTENSION_PREFIX

__all__ = [
    "BINDINGS_KEY",
    "CATALOG_KEY",
    "RESERVED_PREFIX",
    "Binding",
    "Catalog",
    "CustomGraph",
    "compile_custom",
    "config_base",
    "parse_catalog",
    "read_bindings",
    "read_catalog",
]

#: Where the operator declares the graphs, for messages that have to name it.
CATALOG_KEY = "graphs"

#: Where the operator binds commands to graphs.
BINDINGS_KEY = "routing.control.commands"

#: The shipped loops' family name. Reserved so the next loop the-loop ships can
#: never collide with a graph an operator already runs under that name.
RESERVED_PREFIX = "pdlc-"

#: A graph name, and a command word: lowercase, digits and hyphens.
_NAME = re.compile(r"^[a-z][a-z0-9-]*$")

_ENTRY_KEYS = frozenset({"name", "path", "guest"})
_BINDING_KEYS = frozenset({"graph", "keyword"})


def config_base() -> Path:
    """The directory of the CLI config in effect — what a relative ``path`` means.

    ``--config``, then ``$THE_LOOP_CLI_CONFIG``, then ``./.the-loop/``, then
    ``~/.the-loop/``: the same resolution every other reader of the file uses, so
    the graph sits beside the declaration that named it. Made absolute, so a
    config found as ``./.the-loop/cli-config.yaml`` does not leave its graphs
    relative to whatever the process's working directory later becomes — but not
    symlink-resolved: "this file's directory" is where the operator sees the file.
    """
    from .. import cli_config

    return Path(
        os.path.abspath(cli_config.default_cli_config_path().expanduser())
    ).parent


@dataclass(frozen=True)
class CustomGraph:
    """One top-level ``graphs[]`` entry, parsed and validated."""

    name: str
    path: str
    guest: bool = False

    def resolved_path(self, base: Optional[Path] = None) -> Path:
        """``path`` as a file on this machine: ``~`` expanded, an absolute path
        kept, a relative one joined onto ``base`` (the CLI config's directory)."""
        candidate = Path(self.path).expanduser()
        if candidate.is_absolute():
            return candidate
        return (base if base is not None else config_base()) / candidate


@dataclass(frozen=True)
class Catalog:
    """Every graph the operator declared. Empty for everyone who declared none."""

    entries: Tuple[CustomGraph, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.entries

    @property
    def names(self) -> Tuple[str, ...]:
        return tuple(entry.name for entry in self.entries)

    def get(self, name: str) -> Optional[CustomGraph]:
        return next((entry for entry in self.entries if entry.name == name), None)

    def is_guest(self, name: str) -> bool:
        entry = self.get(name)
        return bool(entry and entry.guest)

    def digest(self) -> str:
        payload = [[e.name, e.path, e.guest] for e in self.entries]
        blob = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]


@dataclass(frozen=True)
class Binding:
    """One ``routing.control.commands.<word>`` entry: the graph it selects and,
    for a NEW word, the keyword a person types (``the-loop <word>`` unless set)."""

    word: str
    graph: str
    keyword: str = ""


# -- parsing: which graphs exist ----------------------------------------------


def read_catalog(cli_config: Mapping[str, Any]) -> Catalog:
    """Parse the top-level ``graphs`` list out of an already-loaded CLI config.

    Falls back to ``routing._graphs`` — where the loader fans the list for the
    readers that are handed the routing block alone (:func:`the_loop.cli_config.
    apply_graphs`), exactly as the ``instance`` block travels as ``_instance``.
    """
    if not isinstance(cli_config, Mapping):
        return Catalog()
    raw = cli_config.get("graphs")
    if raw is None:
        routing = cli_config.get("routing")
        if isinstance(routing, Mapping):
            raw = routing.get("_graphs")
    return parse_catalog(raw)


def parse_catalog(raw: Any) -> Catalog:
    """Validate a ``graphs`` list. An **absent** list (``None``) is not malformed —
    it is every operator who has never heard of this feature, and they get an
    empty catalog. A present one is validated whole, and the first fault raises.
    """
    if raw is None:
        return Catalog()
    if not isinstance(raw, list):
        raise GraphConfigError(f"CLI config: `{CATALOG_KEY}` must be a list")
    entries: list[CustomGraph] = []
    for item in raw:
        entry = _read_entry(item)
        if any(existing.name == entry.name for existing in entries):
            raise GraphConfigError(
                f"CLI config: `{CATALOG_KEY}` declares {entry.name!r} twice"
            )
        entries.append(entry)
    return Catalog(entries=tuple(entries))


def _read_entry(item: Any) -> CustomGraph:
    if not isinstance(item, Mapping):
        raise GraphConfigError(
            f"CLI config: `{CATALOG_KEY}` entry {item!r} must be a mapping of "
            "`name`, `path`, and optionally `guest`"
        )
    unknown = sorted(str(key) for key in item if key not in _ENTRY_KEYS)
    if unknown:
        raise GraphConfigError(
            f"CLI config: `{CATALOG_KEY}` entry {dict(item)!r} has unknown "
            f"key(s) {', '.join(unknown)}"
            + (
                " — a command selects a graph under `routing.control.commands`"
                if "commands" in unknown
                else ""
            )
        )
    raw_name, raw_path = item.get("name"), item.get("path")
    if not isinstance(raw_name, str) or not isinstance(raw_path, str):
        raise GraphConfigError(
            f"CLI config: `{CATALOG_KEY}` entry {dict(item)!r} needs both a "
            "`name` and a `path`, each a string"
        )
    name, path = raw_name.strip(), raw_path.strip()
    if not name or not path:
        raise GraphConfigError(
            f"CLI config: `{CATALOG_KEY}` entry {dict(item)!r} needs both a "
            "`name` and a `path`"
        )
    if not _NAME.match(name):
        raise GraphConfigError(
            f"CLI config: `{CATALOG_KEY}` name {name!r} must be lowercase letters, "
            "digits and hyphens, starting with a letter"
        )
    if name in SHIPPED_LOOPS or name.startswith(RESERVED_PREFIX):
        raise GraphConfigError(
            f"CLI config: `{CATALOG_KEY}` name {name!r} is reserved: "
            f"{RESERVED_PREFIX}* names belong to the loops the-loop ships"
        )
    guest = item.get("guest", False)
    if not isinstance(guest, bool):
        raise GraphConfigError(
            f"CLI config: `{CATALOG_KEY}` entry {name!r} has a `guest` that is "
            "not true or false"
        )
    return CustomGraph(name=name, path=path, guest=guest)


# -- parsing: which command selects which graph --------------------------------


def read_bindings(block: Any, catalog: Catalog) -> Dict[str, Binding]:
    """Parse ``routing.control.commands`` against the declared ``catalog``.

    Each key is a command word: one of the arming commands that may spawn a
    session (re-pointed), or a new word (which arms like ``start``). Each value
    names the ``graph`` it selects — a shipped outer-path loop or a declared one —
    and, for a new word only, an optional ``keyword``. A word that means
    something else, a graph nobody declared, or a keyword on a built-in command
    (those live in ``routing.control.keywords``) is refused.
    """
    from ..control import COMMANDS, SPAWN_COMMANDS

    if block is None:
        return {}
    if not isinstance(block, Mapping):
        raise GraphConfigError(
            f"CLI config: `{BINDINGS_KEY}` must be a mapping of command → "
            "{graph, keyword}"
        )
    known = (*OUTER_PATH_LOOPS, *catalog.names)
    bindings: Dict[str, Binding] = {}
    for raw_word, value in block.items():
        word = str(raw_word or "").strip()
        where = f"CLI config: `{BINDINGS_KEY}.{word}`"
        if not _NAME.match(word):
            raise GraphConfigError(
                f"CLI config: `{BINDINGS_KEY}` command {raw_word!r} must be "
                "lowercase letters, digits and hyphens, starting with a letter"
            )
        if word in COMMANDS and word not in SPAWN_COMMANDS:
            raise GraphConfigError(
                f"{where}: {word!r} is a control command that does not select a "
                f"loop; only {', '.join(SPAWN_COMMANDS)} can be re-pointed, or "
                "name a new command"
            )
        if word not in COMMANDS and word in _reserved_words():
            raise GraphConfigError(
                f"{where}: {word!r} is one of the-loop's own verbs (`the-loop "
                f"{word} …`), so a comment quoting that command would arm a work "
                "item; choose another word"
            )
        if not isinstance(value, Mapping):
            raise GraphConfigError(
                f"{where} must be a mapping with a `graph` and, for a new "
                "command, an optional `keyword`"
            )
        unknown = sorted(str(key) for key in value if key not in _BINDING_KEYS)
        if unknown:
            raise GraphConfigError(f"{where} has unknown key(s) {', '.join(unknown)}")
        graph = value.get("graph")
        if not isinstance(graph, str) or not graph.strip():
            raise GraphConfigError(f"{where} needs a `graph`")
        graph = graph.strip()
        if graph not in known:
            raise GraphConfigError(
                f"{where} names graph {graph!r}, which is neither a shipped loop "
                f"({', '.join(OUTER_PATH_LOOPS)}) nor declared under `{CATALOG_KEY}`"
            )
        keyword = value.get("keyword")
        if keyword is not None:
            if word in COMMANDS:
                raise GraphConfigError(
                    f"{where}: a built-in command's keyword is set under "
                    f"`routing.control.keywords.{word}`, not here"
                )
            if not isinstance(keyword, str) or not keyword.strip():
                raise GraphConfigError(f"{where}: `keyword` must be a non-empty string")
            keyword = " ".join(keyword.split())
        bindings[word] = Binding(word=word, graph=graph, keyword=keyword or "")
    return bindings


def _reserved_words() -> frozenset:
    """Words that already follow ``the-loop`` somewhere else: the CLI's own
    sub-commands (``the-loop graph complete …``, ``the-loop check …``) and the
    Slack command's non-control verbs. A comment QUOTING one of those — a session
    reporting what it ran — must never read as an arming command."""
    from ..commands import iter_commands

    return frozenset(c.name for c in iter_commands()) | {"new", "help", "standing"}


# -- compiling ----------------------------------------------------------------


def _is_extension_name(name: str) -> bool:
    return name.startswith(EXTENSION_PREFIX)


def compile_custom(entry: CustomGraph, target: Optional[Path] = None) -> Graph:
    """Read and compile ``entry``'s file, held to every rule a shipped loop is.

    ``x-`` hook names are accepted here and left for :func:`load_graph` to bind
    against the declared modules — compiling never executes a module, which is
    what lets ``the-loop graph loops`` check a graph without running any code.
    """
    from . import hooks  # noqa: F401 — the shipped registry, before any name resolves

    path = target if target is not None else entry.resolved_path()
    data = dict(_read_graph_file(path, entry.name))
    written = data.get("name")
    if written not in (None, "") and str(written) != entry.name:
        raise GraphConfigError(
            f"the graph at {path} names itself {written!r}, but is declared as "
            f"{entry.name!r} in `{CATALOG_KEY}`; make them agree or drop the "
            "file's `name`"
        )
    data["name"] = entry.name
    try:
        graph = compile_graph(data, known=_is_extension_name)
    except GraphConfigError as exc:
        raise GraphConfigError(
            f"the {entry.name} loop ({path}) does not compile: {exc}"
        ) from None
    for node in graph.ordered():
        if node.phase and node.phase not in PHASE_VOCABULARY:
            raise GraphConfigError(
                f"the {entry.name} loop ({path}): node {node.id!r} declares phase "
                f"{node.phase!r}, which is not one of the-loop's phases "
                f"({', '.join(PHASE_VOCABULARY)}) — the loop:<phase> labels are "
                "one vocabulary for every graph"
            )
    return graph
