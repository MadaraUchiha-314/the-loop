"""GitHub polling ingress: pull labelled issues/PRs and drive the dispatcher.

A pull-based alternative to the webhook receiver for hosts a webhook cannot
reach (issue-34). It reuses the whole webhook routing/dispatch stack; only the
ingress (``gh`` polling + cross-poll dedup) is new.
"""

from .github import (  # noqa: F401
    GhClient,
    GhComment,
    GhError,
    GhItem,
    RepoSpec,
    check_gh_dependency,
    parse_repos,
)
from .poller import PollConfig, Poller, PollState, PollSummary  # noqa: F401

__all__ = [
    "GhClient",
    "GhComment",
    "GhError",
    "GhItem",
    "PollConfig",
    "PollState",
    "PollSummary",
    "Poller",
    "RepoSpec",
    "check_gh_dependency",
    "parse_repos",
]
