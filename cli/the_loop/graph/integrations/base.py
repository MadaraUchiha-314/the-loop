"""The integration contract and transport resolution."""

from __future__ import annotations

import logging
import os
import shutil
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


def _has_token(env_names) -> bool:
    return any(os.environ.get(n) for n in env_names)


def resolve(target: str, config: Mapping[str, Any]) -> "Integration":
    """Build the configured provider for ``target``.

    ``transport: auto`` resolves in a documented order — a configured API token
    first, then an installed CLI binary — and when neither is available it fails
    closed naming **both** remedies. An explicit transport is honoured verbatim
    and fails rather than silently falling back: a configured choice that
    quietly degrades is worse than an error.
    """
    section = dict((config.get("integrations") or {}).get(target) or {})
    transport = str(section.get("transport", "auto"))

    if target == "github":
        from .github import GitHubApi, GitHubCli

        api_cfg = dict(section.get("api") or {})
        cli_cfg = dict(section.get("cli") or {})
        token_envs = api_cfg.get("tokenEnv") or ["GH_TOKEN", "GITHUB_TOKEN"]
        if isinstance(token_envs, str):
            token_envs = [token_envs]
        binary = str(cli_cfg.get("binary", "gh"))

        if transport == "api":
            return GitHubApi(
                token_envs, str(api_cfg.get("baseUrl", "https://api.github.com"))
            )
        if transport == "cli":
            return GitHubCli(binary)
        if transport != "auto":
            raise TransportUnavailable(
                f"github: unknown transport {transport!r}; expected auto, api or cli"
            )
        if _has_token(token_envs):
            return GitHubApi(
                token_envs, str(api_cfg.get("baseUrl", "https://api.github.com"))
            )
        if shutil.which(binary):
            return GitHubCli(binary)
        raise TransportUnavailable(
            "github: no transport available — set one of "
            f"{', '.join(token_envs)} to use the API transport, or install "
            f"{binary!r} to use the CLI transport"
        )

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
