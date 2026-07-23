"""Harness adapters: trigger Claude Code / Cursor sessions via their CLIs.

CLI-only by decision (docs/decisions/decision-016.md): both vendors' official
programmatic surface reachable from a zero-dependency Python process is their
CLI, invoked as a subprocess.
"""

from .base import DispatchResult, HarnessAdapter, Usage  # noqa: F401
from .claude_code import ClaudeCodeAdapter  # noqa: F401
from .cursor_agent import CursorAgentAdapter  # noqa: F401

__all__ = [
    "ClaudeCodeAdapter",
    "CursorAgentAdapter",
    "DispatchResult",
    "HarnessAdapter",
    "Usage",
]


def build_adapters(harness_args=None):
    """Adapters keyed by harness name, with per-harness extra CLI args."""
    harness_args = harness_args or {}
    return {
        "claude": ClaudeCodeAdapter(extra_args=harness_args.get("claude") or []),
        "cursor": CursorAgentAdapter(extra_args=harness_args.get("cursor") or []),
    }
