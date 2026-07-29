"""Hook registry — the same pattern the CLI already uses for sub-commands.

``the_loop/commands/base.py`` registers a ``Command`` subclass with ``@register``
into a module-level ``_REGISTRY``; dropping a module under ``commands/`` makes a
new sub-command exist. Hooks work identically: decorate a function with
``@hook("name")``, drop it under ``graph/hooks/``, and the graph can name it.

There is deliberately no third-party engine behind any of this (issue-109,
R6b.2/R6b.3): a hook is a plain function, the registry is a dict.
"""

from __future__ import annotations

from typing import Callable, Dict, List

from .contract import HookContext, HookResult

__all__ = ["HookFn", "get_hook", "hook", "hook_names", "is_registered"]

HookFn = Callable[[HookContext], HookResult]

_REGISTRY: Dict[str, HookFn] = {}


def hook(name: str) -> Callable[[HookFn], HookFn]:
    """Register ``fn`` under ``name``. A duplicate name is a programming error
    raised at import time — exactly as the command registry does."""

    def decorate(fn: HookFn) -> HookFn:
        if not name:
            raise ValueError("a hook must have a non-empty name")
        if name in _REGISTRY:
            raise ValueError(f"duplicate hook name: {name!r}")
        _REGISTRY[name] = fn
        return fn

    return decorate


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
