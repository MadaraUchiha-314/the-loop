"""The integration contract and transport resolution."""

from __future__ import annotations

import logging
from typing import Any, Dict, FrozenSet, Mapping, Protocol

logger = logging.getLogger("the-loop.graph.integrations")

__all__ = [
    "Integration",
    "IntegrationError",
    "OperationUnsupported",
    "TransportUnavailable",
    "resolve",
]


class IntegrationError(RuntimeError):
    """A call could not be made."""


class TransportUnavailable(IntegrationError):
    """No transport could be resolved. Always names *every* remedy."""


class OperationUnsupported(IntegrationError):
    """This provider does not implement the requested operation."""


class Integration(Protocol):
    """Every provider looks the same to a hook."""

    name: str
    transport: str
    operations: FrozenSet[str]

    def call(self, op: str, **params: Any) -> Dict[str, Any]: ...


def resolve(target: str, config: Mapping[str, Any]) -> "Integration":
    """Build the configured provider for ``target``.

    There is one GitHub transport since issue-442 — PyGithub under the token
    ``integrations.github.api.tokenEnv`` names — so ``auto`` and ``api`` build
    it, a missing token fails closed naming the variables, and the retired
    ``cli`` is refused by name rather than silently served another way: a
    configured choice that quietly degrades is worse than an error.
    """
    section = dict((config.get("integrations") or {}).get(target) or {})
    transport = str(section.get("transport", "auto"))

    if target == "github":
        from ...ghapi import GitHubApiConfig
        from .github import GitHubProvider

        if transport == "cli":
            # Retired by issue-442 (decision-139): the daemon reaches GitHub
            # through PyGithub under a token, never through a `gh` binary. The
            # config gate refuses the key at start; a hand-built mapping is
            # refused here, by name, rather than silently served another way.
            raise TransportUnavailable(
                "github: the `cli` transport was retired (issue-442) — the daemon "
                "reaches GitHub with the token `integrations.github.api.tokenEnv` "
                "names; remove `integrations.github.transport` and "
                "`integrations.github.cli` (`the-loop migrate-config`)"
            )
        if transport not in ("auto", "api"):
            raise TransportUnavailable(
                f"github: unknown transport {transport!r}; expected auto or api"
            )
        api = GitHubApiConfig.from_cli_config(config)
        if not api.token():
            raise TransportUnavailable(
                f"github: {api.missing_token_reason} — the daemon's own GitHub "
                "calls need a token (integrations.github.api.tokenEnv)"
            )
        return GitHubProvider(api)

    if target == "slack":
        # Slack converged on the channels layer (issue-245, owner's call on
        # PR #267): the incoming-webhook integration is gone, and the `notify`
        # hook broadcasts through `channels.slack` instead. Kept as a named
        # refusal so an embedder still calling `resolve("slack", …)` learns the
        # replacement instead of getting a generic unknown-target error.
        raise TransportUnavailable(
            "slack is no longer an integration — the incoming webhook was "
            "removed in favour of the channels layer (issue-245). Configure "
            "channels.slack (the bot) instead; `the-loop migrate-config` "
            "retires an old integrations.slack section."
        )

    raise TransportUnavailable(f"no integration registered for target {target!r}")
