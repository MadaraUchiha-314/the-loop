"""the-loop's process graph: nodes with entry/exit hook chains (issue-109).

Two runtime concepts and one contract:

* a **node** is a step of the PDLC — a place the work item *is*;
* a **hook** is a unit of work with a fixed signature, chained at a boundary;
* :class:`~the_loop.graph.contract.HookResult` is what decides movement.

A node is complete when its exit hooks all pass, waiting when one returns
``wait``, blocked when one returns ``block``. No prose is ever parsed.

Spec: ``docs/specs/issue-109/``; decisions 041 and 042.
"""

from .chain import ChainOutcome, run_chain  # noqa: F401
from .contract import (  # noqa: F401
    BLOCK,
    PASS,
    SKIP,
    WAIT,
    HookContext,
    HookResult,
    Message,
    WorkItem,
)
from .extensions import Declaration, read_declaration  # noqa: F401
from .model import Graph, GraphConfigError, Node, load_graph  # noqa: F401
from .registry import EXTENSION_PREFIX, get_hook, hook, hook_names  # noqa: F401
from .runtime import NodeReport, Runtime, StatusReport, force  # noqa: F401
from .state import GraphState  # noqa: F401

__all__ = [
    "BLOCK",
    "EXTENSION_PREFIX",
    "PASS",
    "SKIP",
    "WAIT",
    "ChainOutcome",
    "Declaration",
    "Graph",
    "GraphConfigError",
    "GraphState",
    "HookContext",
    "HookResult",
    "Message",
    "Node",
    "NodeReport",
    "Runtime",
    "StatusReport",
    "WorkItem",
    "force",
    "get_hook",
    "hook",
    "hook_names",
    "load_graph",
    "read_declaration",
    "run_chain",
]
