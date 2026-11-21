"""Unit tests for the hook registry (issue-109, R6b.2)."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from the_loop.graph import registry
from the_loop.graph.contract import HookResult


@pytest.fixture(autouse=True)
def _isolate_registry():
    saved = dict(registry._REGISTRY)
    yield
    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved)


def test_register_and_look_up():
    @registry.hook("t-example")
    def _example(ctx):  # pragma: no cover - not invoked
        return HookResult.ok("t-example")

    assert registry.is_registered("t-example")
    assert registry.get_hook("t-example") is _example
    assert "t-example" in registry.hook_names()


def test_duplicate_name_is_refused_at_import():
    @registry.hook("t-dup")
    def _one(ctx):  # pragma: no cover
        return HookResult.ok("t-dup")

    with pytest.raises(ValueError, match="duplicate hook name"):

        @registry.hook("t-dup")
        def _two(ctx):  # pragma: no cover
            return HookResult.ok("t-dup")


def test_empty_name_is_refused():
    with pytest.raises(ValueError, match="non-empty name"):

        @registry.hook("")
        def _anon(ctx):  # pragma: no cover
            return HookResult.ok("")


def test_unknown_hook_names_the_registered_ones():
    with pytest.raises(KeyError, match="unknown hook"):
        registry.get_hook("t-does-not-exist")


# -- reads_event (issue-551, R5.3) -------------------------------------------------


def test_a_hook_reads_no_event_unless_it_says_so():
    @registry.hook("t-quiet")
    def _quiet(ctx):  # pragma: no cover
        return HookResult.ok("t-quiet")

    @registry.hook("t-listens", reads_event=True)
    def _listens(ctx):  # pragma: no cover
        return HookResult.ok("t-listens")

    assert registry.reads_event(_quiet) is False
    assert registry.reads_event(_listens) is True


def test_a_repository_hook_declares_it_with_the_same_decorator():
    with registry.collecting() as table:

        @registry.hook("x-listens", reads_event=True)
        def _listens(ctx):  # pragma: no cover
            return HookResult.ok("x-listens")

    assert registry.reads_event(table["x-listens"]) is True


def _event_readers(package: Path, package_name: str) -> dict[str, bool]:
    """``{hook name: reads ctx.event}`` for every shipped hook, from the source.

    A function reads the event when it touches an ``.event`` attribute, or calls
    — by name, through this package's own ``from .x import y`` lines — one that
    does.
    """
    modules = {p.stem: ast.parse(p.read_text()) for p in package.glob("*.py")}
    reads: dict[tuple[str, str], bool] = {}
    calls: dict[tuple[str, str], set[tuple[str, str]]] = {}
    hooks: dict[str, tuple[str, str]] = {}
    for stem, tree in modules.items():
        local = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        imported = {
            alias.asname or alias.name: (node.module or "", alias.name)
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.level == 1
            for alias in node.names
        }
        for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
            key = (stem, fn.name)
            inner = list(ast.walk(fn))
            reads[key] = any(
                isinstance(n, ast.Attribute) and n.attr == "event" for n in inner
            )
            calls[key] = set()
            for n in inner:
                if not isinstance(n, ast.Name):
                    continue
                if n.id in local:
                    calls[key].add((stem, n.id))
                elif n.id in imported:
                    calls[key].add(imported[n.id])
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "id", "") == "hook":
                    arg = dec.args[0]
                    if isinstance(arg, ast.Constant):
                        name = arg.value
                    else:  # `@hook(NAME)` — the module's own constant
                        assert isinstance(arg, ast.Name)
                        owner = importlib.import_module(f"{package_name}.{stem}")
                        name = getattr(owner, arg.id)
                    hooks[str(name)] = key

    def reaches(key, seen):
        if key in seen or key not in reads:
            return False
        seen.add(key)
        return reads[key] or any(reaches(k, seen) for k in calls[key])

    return {name: reaches(key, set()) for name, key in hooks.items()}


def test_every_shipped_hook_that_reads_the_event_declares_it():
    """A hook that reads ``ctx.event`` undeclared would never be handed one on an
    agent-owned node (issue-551) — and would fail silently, by waiting."""
    from the_loop.graph import hooks as shipped

    found = _event_readers(Path(str(shipped.__file__)).parent, shipped.__name__)

    ours = {
        name
        for name in registry.hook_names()
        if registry.get_hook(name).__module__.startswith(shipped.__name__ + ".")
    }
    assert set(found) == ours, "the scan missed a hook"
    declared = {name: registry.reads_event(registry.get_hook(name)) for name in found}
    assert declared == found
    assert {name for name, reads in found.items() if reads} >= {
        "classify-feedback",
        "quiz-attested",
    }
