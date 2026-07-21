"""Polling ingress: pull labelled work items and drive the dispatcher.

A pull-based alternative to the webhook receiver for hosts a webhook cannot
reach (issue-34). It reuses the whole webhook routing/dispatch stack; only the
ingress is new, and it is **provider-agnostic** — a ``polling.sources`` config
entry selects a :class:`PollProvider` by name (GitHub ships; the seam admits
others). GitHub is reached solely through a configured provider.
"""

from .base import (  # noqa: F401
    Comment,
    PollProvider,
    ProviderError,
    WorkItem,
    build_provider,
    provider_names,
    register_provider,
)
from .github import (  # noqa: F401
    GhClient,
    GhComment,
    GhError,
    GhItem,
    GitHubPollProvider,
    RepoSpec,
    check_gh_dependency,
    parse_repos,
)
from .poller import PollConfig, Poller, PollState, PollSummary  # noqa: F401

__all__ = [
    "Comment",
    "GhClient",
    "GhComment",
    "GhError",
    "GhItem",
    "GitHubPollProvider",
    "PollConfig",
    "PollProvider",
    "PollState",
    "PollSummary",
    "Poller",
    "ProviderError",
    "RepoSpec",
    "WorkItem",
    "build_provider",
    "check_gh_dependency",
    "parse_repos",
    "provider_names",
    "register_provider",
]
