"""Executors — what a declared entry becomes once loaded (issue-344, R4.1, R3.5).

An :class:`Executor` answers one point with ``None``, a context or a mapping of
decisions. :class:`LocalExecutor` wraps a :class:`~the_loop.lifecycle.contract.LifecycleHooks`
instance imported into this process; :class:`~the_loop.lifecycle.remote.RemoteExecutor`
speaks JSON-RPC to one the operator hosts. :func:`load` turns a validated
:class:`~the_loop.lifecycle.declaration.Declaration` into the ordered list of them —
and fails, naming the entry, on anything it cannot honour.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import inspect
import logging
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from .contract import POINTS, Context, LifecycleHooks
from .declaration import CONFIG_KEY, Declaration, Entry, HooksConfigError

logger = logging.getLogger("the-loop.lifecycle")

__all__ = ["Executor", "LocalExecutor", "clear_module_cache", "load"]


class Executor:
    """One declared hook, ready to run. Subclasses implement :meth:`handles` and
    :meth:`call`; the runner owns ordering, recording and failure semantics."""

    def __init__(self, name: str, on: Tuple[str, ...] = (), required: bool = False):
        self.name = name
        self.on = tuple(on)
        self.required = required

    def handles(self, point: str) -> bool:  # pragma: no cover — abstract
        raise NotImplementedError

    def call(
        self, point: str, ctx: Context
    ) -> Optional[Union[Context, Mapping[str, Any]]]:  # pragma: no cover — abstract
        raise NotImplementedError

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": type(self).__name__,
            "on": [p for p in POINTS if self.handles(p)],
            "required": self.required,
        }


class LocalExecutor(Executor):
    """A ``LifecycleHooks`` subclass running in this process, synchronously.

    Handles the points the class overrides; an ``on`` narrows that set and never
    widens it — a method the class does not define is not run.
    """

    def __init__(
        self,
        name: str,
        hooks: LifecycleHooks,
        on: Tuple[str, ...] = (),
        required: bool = False,
    ):
        super().__init__(name, on, required)
        self.hooks = hooks

    def handles(self, point: str) -> bool:
        if self.on and point not in self.on:
            return False
        return self.hooks.handles(point)

    def call(
        self, point: str, ctx: Context
    ) -> Optional[Union[Context, Mapping[str, Any]]]:
        return getattr(self.hooks, point)(ctx)


# -- loading ---------------------------------------------------------------------------

#: Modules already executed from a ``path``, keyed by the resolved file. A daemon
#: declaring the same file under two names executes it once, and an edited file is
#: picked up on the next start (R3.7), exactly as graph hook modules are.
_MODULE_CACHE: Dict[str, ModuleType] = {}


def clear_module_cache() -> None:
    """Forget every loaded path module. For tests."""
    _MODULE_CACHE.clear()


def load(declaration: Declaration, base_dir: Union[str, Path]) -> List[Executor]:
    """Every enabled entry as an executor, in declaration order.

    ``base_dir`` is the CLI config file's directory — what a relative ``path``
    resolves against. Imports happen here and only here.
    """
    from .remote import RemoteExecutor

    executors: List[Executor] = []
    for entry in declaration.entries:
        if not entry.enabled:
            continue
        if entry.kind == "url":
            executors.append(
                RemoteExecutor(
                    name=entry.name,
                    url=entry.url,
                    on=entry.on,
                    required=entry.required,
                    token_env=entry.token_env,
                    headers=dict(entry.headers),
                    timeout=entry.timeout,
                )
            )
            continue
        module = _import(entry, Path(base_dir))
        hooks = _select(module, entry)
        executors.append(
            LocalExecutor(entry.name, hooks, on=entry.on, required=entry.required)
        )
    return executors


def _where(entry: Entry) -> str:
    return f"the hook {entry.name!r} declared in `{CONFIG_KEY}` ({entry.target})"


def _import(entry: Entry, base_dir: Path) -> ModuleType:
    if entry.kind == "module":
        try:
            return importlib.import_module(entry.module)
        except HooksConfigError:
            raise
        except BaseException as exc:  # noqa: BLE001 — every failure names the entry
            raise HooksConfigError(
                f"{_where(entry)} could not be imported: {exc.__class__.__name__}: {exc}"
            ) from None
    target = entry.resolved_path(base_dir)
    if not target.is_file():
        raise HooksConfigError(
            f"{_where(entry)} names a file that does not exist ({target}); a relative "
            "`path` resolves against the CLI config file's directory"
        )
    key = str(target)
    cached = _MODULE_CACHE.get(key)
    if cached is not None:
        return cached
    name = "the_loop_lifecycle_hooks_" + hashlib.sha256(key.encode()).hexdigest()[:16]
    spec = importlib.util.spec_from_file_location(name, target)
    if spec is None or spec.loader is None:
        raise HooksConfigError(
            f"{_where(entry)}: {target} could not be loaded as a module"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException as exc:  # noqa: BLE001 — every failure names the entry
        sys.modules.pop(name, None)
        raise HooksConfigError(
            f"{_where(entry)} raised while loading: {exc.__class__.__name__}: {exc}"
        ) from None
    _MODULE_CACHE[key] = module
    return module


def _select(module: ModuleType, entry: Entry) -> LifecycleHooks:
    """The executor the module provides: the named attribute, else its one subclass."""
    if entry.executor:
        candidate = getattr(module, entry.executor, None)
        if candidate is None:
            raise HooksConfigError(
                f"{_where(entry)} names `executor: {entry.executor}`, which the module "
                "does not define"
            )
    else:
        own = [
            obj
            for _, obj in inspect.getmembers(module, inspect.isclass)
            if issubclass(obj, LifecycleHooks)
            and obj is not LifecycleHooks
            and obj.__module__ == module.__name__
        ]
        if len(own) != 1:
            names = ", ".join(sorted(c.__name__ for c in own)) or "none"
            raise HooksConfigError(
                f"{_where(entry)} must define exactly one LifecycleHooks subclass, or "
                f"name one with `executor:`; found {names}"
            )
        candidate = own[0]
    if isinstance(candidate, LifecycleHooks):
        if entry.params:
            raise HooksConfigError(
                f"{_where(entry)}: `executor: {entry.executor}` is an instance, so "
                "`with` has nothing to construct; drop one of the two"
            )
        return candidate
    if not (inspect.isclass(candidate) and issubclass(candidate, LifecycleHooks)):
        raise HooksConfigError(
            f"{_where(entry)}: `{entry.executor}` is neither a LifecycleHooks subclass "
            "nor an instance of one"
        )
    try:
        return candidate(**dict(entry.params))
    except BaseException as exc:  # noqa: BLE001 — every failure names the entry
        raise HooksConfigError(
            f"{_where(entry)} could not be constructed with `with` "
            f"{dict(entry.params)!r}: {exc.__class__.__name__}: {exc}"
        ) from None
