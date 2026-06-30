"""Command package. Importing it registers all built-in commands."""

from .base import Command, iter_commands, register  # noqa: F401

# Import command modules for their registration side effects.
from . import gh_webhook  # noqa: F401,E402

__all__ = ["Command", "iter_commands", "register"]
