"""Unit tests for the hook registry (issue-109, R6b.2)."""

from __future__ import annotations

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
