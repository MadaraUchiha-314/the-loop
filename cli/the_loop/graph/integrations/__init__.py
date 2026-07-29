"""Integrations — how the-loop's OWN calls reach GitHub, Slack and Jira.

Two call planes, and only one of them is governed here (issue-109, decision-042):

* the **control plane** — the calls the-loop's hooks make. Deterministic,
  auditable, credentialed, and **configurable** per integration.
* the **work plane** — the calls the *agent* makes from inside its session.
  Unconstrained: CLI, MCP, API, whatever the harness has. the-loop does not
  police it, because the agent is already trusted to write code and policing it
  would break the session-takeover property the tmux runner exists for.

Transport is a choice, not a mandate: ``api`` and ``cli`` where both are
meaningful, ``sdk`` where an official one exists. Providers **declare the
operations they implement**, and the runtime checks that declaration at load
time — a graph needing an operation the configured transport lacks fails at
startup, naming the operation and both fixes, not three nodes deep.
"""

from .base import (  # noqa: F401
    Integration,
    IntegrationError,
    OperationUnsupported,
    TransportUnavailable,
    resolve,
)

__all__ = [
    "Integration",
    "IntegrationError",
    "OperationUnsupported",
    "TransportUnavailable",
    "resolve",
]
