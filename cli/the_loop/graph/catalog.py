"""Graphs of the operator's own, declared in the CLI config (issue-343).

issue-109 shipped the process as data and deferred *"user-defined graphs and
user-authored hooks"*; issue-248 delivered the hooks half. This module is the
graphs half: ``routing.graph.graphs`` names YAML files the operator wrote, and the
arming commands that select each one — an existing command (``do``), overriding
the loop it selects, or a new word (``triage``), which then arms like ``start``.

Four rules hold it together:

* **Declared by the operator, never by a repository.** The list lives in the CLI
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
  that does not select a loop, an unreadable file — each raises, naming what did
  it. Nothing degrades to "no custom graphs".

Spec: docs/specs/issue-343/  ·  Decision: 136
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from .model import (
    PHASE_VOCABULARY,
    SHIPPED_LOOPS,
    Graph,
    GraphConfigError,
    _read_graph_file,
    compile_graph,
)
from .registry import EXTENSION_PREFIX

__all__ = [
    "CATALOG_KEY",
    "RESERVED_PREFIX",
    "Catalog",
    "CustomGraph",
    "compile_custom",
    "config_base",
    "read_catalog",
]

#: Where the operator declares the graphs, for messages that have to name it.
CATALOG_KEY = "routing.graph.graphs"

#: The shipped loops' family name. Reserved so the next loop the-loop ships can
#: never collide with a graph an operator already runs under that name.
RESERVED_PREFIX = "pdlc-"

#: A graph name, and a command word: lowercase, digits and hyphens.
_NAME = re.compile(r"^[a-z][a-z0-9-]*$")

_ENTRY_KEYS = frozenset({"name", "path", "commands", "guest"})


def config_base() -> Path:
    """The directory of the CLI config in effect — what a relative ``path`` means.

    ``--config``, then ``$THE_LOOP_CLI_CONFIG``, then ``./.the-loop/``, then
    ``~/.the-loop/``: the same resolution every other reader of the file uses, so
    the graph sits beside the declaration that named it. Made absolute, so a
    config found as ``./.the-loop/cli-config.yaml`` does not leave its graphs
    relative to whatever the process's working directory later becomes.
    """
    from .. import cli_config

    return cli_config.default_cli_config_path().expanduser().resolve().parent


@dataclass(frozen=True)
class CustomGraph:
    """One ``routing.graph.graphs[]`` entry, parsed and validated."""

    name: str
    path: str
    commands: Tuple[str, ...] = ()
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

    @property
    def bindings(self) -> Dict[str, str]:
        """Command word → the loop it selects, overrides and new words alike."""
        return {word: entry.name for entry in self.entries for word in entry.commands}

    def get(self, name: str) -> Optional[CustomGraph]:
        return next((entry for entry in self.entries if entry.name == name), None)

    def is_guest(self, name: str) -> bool:
        entry = self.get(name)
        return bool(entry and entry.guest)

    def digest(self) -> str:
        payload = [[e.name, e.path, list(e.commands), e.guest] for e in self.entries]
        blob = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]


# -- parsing ------------------------------------------------------------------


def read_catalog(cli_config: Mapping[str, Any]) -> Catalog:
    """Parse ``routing.graph.graphs`` out of an already-loaded CLI config.

    An **absent** list is not malformed — it is every operator who has never
    heard of this feature, and they get an empty catalog. A present one is
    validated whole, and the first fault raises.
    """
    if not isinstance(cli_config, Mapping):
        return Catalog()
    routing = cli_config.get("routing") or {}
    if not isinstance(routing, Mapping):
        raise GraphConfigError("CLI config: `routing` must be a mapping")
    block = routing.get("graph") or {}
    if not isinstance(block, Mapping):
        raise GraphConfigError("CLI config: `routing.graph` must be a mapping")
    raw = block.get("graphs")
    if not raw:
        return Catalog()
    if isinstance(raw, (str, Mapping)) or not isinstance(raw, list):
        raise GraphConfigError(f"CLI config: `{CATALOG_KEY}` must be a list")

    entries: list[CustomGraph] = []
    bound: Dict[str, str] = {}
    for item in raw:
        entry = _read_entry(item)
        if any(existing.name == entry.name for existing in entries):
            raise GraphConfigError(
                f"CLI config: `{CATALOG_KEY}` declares {entry.name!r} twice"
            )
        for word in entry.commands:
            if word in bound:
                raise GraphConfigError(
                    f"CLI config: `{CATALOG_KEY}` binds the command {word!r} to "
                    f"both {bound[word]!r} and {entry.name!r}; a command selects "
                    "one loop"
                )
            bound[word] = entry.name
        entries.append(entry)
    return Catalog(entries=tuple(entries))


def _read_entry(item: Any) -> CustomGraph:
    if not isinstance(item, Mapping):
        raise GraphConfigError(
            f"CLI config: `{CATALOG_KEY}` entry {item!r} must be a mapping of "
            "`name`, `path`, and optionally `commands` and `guest`"
        )
    unknown = sorted(str(key) for key in item if key not in _ENTRY_KEYS)
    if unknown:
        raise GraphConfigError(
            f"CLI config: `{CATALOG_KEY}` entry {dict(item)!r} has unknown "
            f"key(s) {', '.join(unknown)}"
        )
    name = str(item.get("name") or "").strip()
    path = str(item.get("path") or "").strip()
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
    return CustomGraph(
        name=name, path=path, commands=_read_commands(name, item), guest=guest
    )


def _read_commands(name: str, item: Mapping[str, Any]) -> Tuple[str, ...]:
    """The words that select ``name``: an arming command it overrides, or a new
    word that becomes one. A word that means something else is refused."""
    from ..control import COMMANDS, SPAWN_COMMANDS

    raw = item.get("commands")
    if raw is None:
        return ()
    if isinstance(raw, (str, Mapping)) or not isinstance(raw, list):
        raise GraphConfigError(
            f"CLI config: `{CATALOG_KEY}` entry {name!r}: `commands` must be a list"
        )
    words: list[str] = []
    for value in raw:
        word = str(value or "").strip()
        if not _NAME.match(word):
            raise GraphConfigError(
                f"CLI config: `{CATALOG_KEY}` entry {name!r}: command {value!r} "
                "must be lowercase letters, digits and hyphens, starting with a "
                "letter"
            )
        if word in COMMANDS and word not in SPAWN_COMMANDS:
            raise GraphConfigError(
                f"CLI config: `{CATALOG_KEY}` entry {name!r}: {word!r} is a control "
                "command that does not select a loop; only "
                f"{', '.join(SPAWN_COMMANDS)} can be overridden, or name a new "
                "command"
            )
        if word not in words:
            words.append(word)
    return tuple(words)


# -- compiling ----------------------------------------------------------------


def _is_extension_name(name: str) -> bool:
    return name.startswith(EXTENSION_PREFIX)


def compile_custom(entry: CustomGraph, target: Optional[Path] = None) -> Graph:
    """Read and compile ``entry``'s file, held to every rule a shipped loop is.

    ``x-`` hook names are accepted here and left for :func:`load_graph` to bind
    against the declared modules — compiling never executes a module, which is
    what lets ``the-loop graph loops`` check a graph without running any code.
    """
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
