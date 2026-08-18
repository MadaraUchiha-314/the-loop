"""Hook registry — the same pattern the CLI already uses for sub-commands.

``the_loop/commands/base.py`` registers a ``Command`` subclass with ``@register``
into a module-level ``_REGISTRY``; dropping a module under ``commands/`` makes a
new sub-command exist. Hooks work identically: decorate a function with
``@hook("name")``, drop it under ``graph/hooks/``, and the graph can name it.

There is deliberately no third-party engine behind any of this (issue-109,
R6b.2/R6b.3): a hook is a plain function, the registry is a dict.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Callable, Dict, Iterator, List

from .contract import HookContext, HookResult

__all__ = [
    "EXTENSION_PREFIX",
    "HookFn",
    "collecting",
    "get_hook",
    "hook",
    "hook_names",
    "is_registered",
]

HookFn = Callable[[HookContext], HookResult]

#: The namespace a REPOSITORY's own hooks live in (issue-248). Reserved in both
#: directions: a shipped hook may not take an ``x-`` name, and a repository hook
#: may not take anything else. The prefix is the whole collision rule — a reader
#: of a chain can tell whose code is about to run, and no repository module can
#: shadow ``validate-artifacts`` by declaring one.
EXTENSION_PREFIX = "x-"

_REGISTRY: Dict[str, HookFn] = {}

#: Where ``@hook`` writes while a repository's module is being executed. Kept
#: per-thread rather than per-process: a daemon loads modules on whichever thread
#: is handling the delivery, and a shared slot would let one repository's
#: registrations land in another's table.
_COLLECTOR = threading.local()


def hook(name: str) -> Callable[[HookFn], HookFn]:
    """Register ``fn`` under ``name``. A duplicate name is a programming error
    raised at import time — exactly as the command registry does.

    The same decorator serves a repository's own hooks (issue-248): inside
    :func:`collecting` the registration lands in that collector instead of the
    process-global registry, and the ``x-`` prefix is required there and refused
    here. One authoring API, two tables.
    """

    def decorate(fn: HookFn) -> HookFn:
        if not name:
            raise ValueError("a hook must have a non-empty name")
        collector = getattr(_COLLECTOR, "table", None)
        if collector is None:
            if name.startswith(EXTENSION_PREFIX):
                raise ValueError(
                    f"hook name {name!r} is reserved: the {EXTENSION_PREFIX!r} "
                    "namespace belongs to repository-provided hooks (issue-248)"
                )
            if name in _REGISTRY:
                raise ValueError(f"duplicate hook name: {name!r}")
            _REGISTRY[name] = fn
            return fn
        if not name.startswith(EXTENSION_PREFIX):
            raise ValueError(
                f"repository hook {name!r} must be named "
                f"{EXTENSION_PREFIX}<something>: the unprefixed namespace is "
                "the-loop's own, so a repository module cannot shadow a shipped hook"
            )
        if name in collector:
            raise ValueError(f"duplicate hook name: {name!r}")
        collector[name] = fn
        return fn

    return decorate


@contextmanager
def collecting() -> Iterator[Dict[str, HookFn]]:
    """Redirect ``@hook`` registrations into a fresh table for the caller.

    This is what keeps a repository's hooks OUT of the process-global registry
    (issue-248, R3.4): the table is handed to the graph compiled for that one
    repository, so two repositories a single daemon serves can both define
    ``x-house-rules`` and each get its own. Not re-entrant — one module load at
    a time, per thread.
    """
    if getattr(_COLLECTOR, "table", None) is not None:
        raise RuntimeError("hook collection is already in progress on this thread")
    table: Dict[str, HookFn] = {}
    _COLLECTOR.table = table
    try:
        yield table
    finally:
        _COLLECTOR.table = None


def get_hook(name: str) -> HookFn:
    """The hook registered under ``name``.

    Raises :class:`KeyError` naming the valid hooks — a graph referencing an
    unregistered hook must fail at **load**, not mid-traversal (R6b.1).
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown hook {name!r}; registered hooks are: "
            f"{', '.join(sorted(_REGISTRY)) or '(none)'}"
        ) from None


def is_registered(name: str) -> bool:
    return name in _REGISTRY


def hook_names() -> List[str]:
    return sorted(_REGISTRY)
