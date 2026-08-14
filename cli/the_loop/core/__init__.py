"""the-loop's core facade — the transport-agnostic capability surface (issue-161).

One module per capability, each a set of plain functions delegating to the
modules that already carry the behaviour (``workitem``, ``eventlog``, ``graph``,
``sessions``, ``scenarios``, ``instructions``, ``critics``, the daemon run
paths). This is the **single implementation** every interface consumes: the CLI
commands, the HTTP API routers and the MCP tools all call these functions and
add only transport, serialization and authn/authz of their own (decision-058).

The facade is importable with no CLI or HTTP context: no argparse, no FastAPI,
no printing — inputs are plain values, outputs are JSON-shaped dicts/lists, and
failures are exceptions the edges translate (``ValueError`` for a caller
mistake, ``LookupError`` for a missing resource).
"""

from . import (  # noqa: F401
    attention,
    config,
    daemons,
    events,
    graphs,
    repo,
    sessions,
    workitems,
)

__all__ = [
    "attention",
    "config",
    "daemons",
    "events",
    "graphs",
    "repo",
    "sessions",
    "workitems",
]
