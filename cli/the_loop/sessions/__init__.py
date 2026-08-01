"""Session registry: work item ↔ harness session linkage (issue-15, R2)."""

from .registry import (  # noqa: F401
    DEFAULT_GITHUB_HOST,
    LIVE_STATUSES,
    RegistryError,
    Session,
    SessionRegistry,
    WorkItemRef,
    host_from_url,
)

__all__ = [
    "DEFAULT_GITHUB_HOST",
    "LIVE_STATUSES",
    "RegistryError",
    "Session",
    "SessionRegistry",
    "WorkItemRef",
    "host_from_url",
]
