"""Command base class and registry.

Extensibility model: subclass :class:`Command`, decorate it with :func:`register`,
and place the module under ``the_loop/commands/`` (importing it in
``commands/__init__.py``). The CLI discovers all registered commands automatically.
"""

from __future__ import annotations

import argparse
from typing import List


class Command:
    """A the-loop CLI sub-command.

    Subclasses set ``name``/``help`` and implement :meth:`add_arguments` and
    :meth:`run`.
    """

    name: str = ""
    help: str = ""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Register this command's arguments / nested actions on ``parser``."""

    def run(self, args: argparse.Namespace) -> int:
        """Execute the command. Return a process exit code (0 == success)."""
        raise NotImplementedError


_REGISTRY: List[Command] = []


def register(cls):
    """Class decorator that registers a :class:`Command` subclass."""
    instance = cls()
    if not instance.name:
        raise ValueError(f"{cls.__name__} must define a non-empty 'name'")
    if any(c.name == instance.name for c in _REGISTRY):
        raise ValueError(f"duplicate command name: {instance.name!r}")
    _REGISTRY.append(instance)
    return cls


def iter_commands() -> List[Command]:
    """Return all registered commands, sorted by name for stable help output."""
    return sorted(_REGISTRY, key=lambda c: c.name)
