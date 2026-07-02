"""Session registry: work item ↔ harness session linkage (issue-15, R2)."""

from .registry import (  # noqa: F401
    RegistryError,
    Session,
    SessionRegistry,
    WorkItemRef,
)

__all__ = ["RegistryError", "Session", "SessionRegistry", "WorkItemRef"]
