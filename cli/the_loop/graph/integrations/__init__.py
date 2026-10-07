"""Integrations — how the-loop's OWN calls reach GitHub and Jira.

Slack is deliberately NOT here any more (issue-245, owner's call on PR #267):
conversation surfaces live in :mod:`the_loop.channels`, and the graph's
``notify`` hook broadcasts through them. An integration remained the right
shape for one-call transports only.

Two call planes, and only one of them is governed here (issue-109, decision-042):

* the **control plane** — the calls the-loop's hooks make. Deterministic,
  auditable, credentialed, and **configurable** per integration.
* the **work plane** — the calls the *agent* makes from inside its session.
  Unconstrained: CLI, MCP, API, whatever the harness has. the-loop does not
  police it, because the agent is already trusted to write code and policing it
  would break the session-takeover property the tmux runner exists for.

GitHub has one transport since issue-442 — PyGithub under the token
``integrations.github.api.tokenEnv`` names (the ``cli`` transport over the
operator's ``gh`` was retired; decision-139). Jira has one too since issue-475 —
the pycontribs ``jira`` SDK under the credentials ``integrations.jira.api`` names
(decision-142) — with GitHub's operations plus ``transition``. Providers **declare the
operations they implement**, and the runtime checks that declaration at load
time — a graph needing an operation the configured provider lacks fails at
startup, naming the operation, not three nodes deep.
"""

from typing import Any, Mapping

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
    "integration_for",
    "resolve",
]


def integration_for(ref: object, config: Mapping[str, Any]) -> "Integration":
    """The provider for the work item ``ref`` names — by the ref, not by a name
    (issue-475, design §C4).

    ``jira:<site>/<KEY>-<n>`` resolves ``jira``, ``github:…`` resolves
    ``github``. Anything that does not parse as a work-item ref resolves
    ``github``, which is what every caller did before issue-475.

    ``resolve`` is looked up in this module **at call time**, so the seam every
    test patches (``the_loop.graph.integrations.resolve``) applies here too.
    """
    from ...sessions import WorkItemRef

    try:
        provider = WorkItemRef.parse(str(ref)).provider
    except ValueError:
        provider = "github"
    return resolve(provider, config)
