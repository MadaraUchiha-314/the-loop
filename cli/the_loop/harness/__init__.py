"""Harness adapters: trigger Claude Code / Cursor sessions via their CLIs.

CLI-only by decision (docs/decisions/decision-016.md): both vendors' official
programmatic surface reachable from a zero-dependency Python process is their
CLI, invoked as a subprocess.
"""

from .base import HarnessAdapter, Usage, hosts_sessions  # noqa: F401
from .claude_code import ClaudeCodeAdapter  # noqa: F401
from .cursor_agent import CursorAgentAdapter  # noqa: F401

__all__ = [
    "ADAPTER_TYPES",
    "ClaudeCodeAdapter",
    "CursorAgentAdapter",
    "HarnessAdapter",
    "Usage",
    "hosting_harnesses",
    "hosts_sessions",
]

#: Every harness this build of the-loop has an adapter for, by name. What
#: :func:`build_adapters` instantiates, and what the `phase-selection` gate asks
#: which harnesses may be offered (issue-440) without building one.
ADAPTER_TYPES = {
    "claude": ClaudeCodeAdapter,
    "cursor": CursorAgentAdapter,
}


def hosting_harnesses():
    """The harness names whose adapter can host a work item's session."""
    return [name for name, cls in ADAPTER_TYPES.items() if hosts_sessions(cls)]


def build_adapters(harness_args=None, trust=None, plugins=None):
    """Adapters keyed by harness name, with per-harness extra CLI args.

    ``trust`` is the ``routing.harnessTrust`` policy (issue-90) and ``plugins``
    the ``routing.harnessPlugins`` one (issue-143); adapters use them to decide
    what to pre-seed in their harness's own config before a spawn.
    """
    harness_args = harness_args or {}
    return {
        name: cls(extra_args=harness_args.get(name) or [], trust=trust, plugins=plugins)
        for name, cls in ADAPTER_TYPES.items()
    }
