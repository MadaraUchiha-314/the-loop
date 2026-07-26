"""Session registry: work item ↔ harness session linkage (issue-15, R2)."""

from .pauses import (  # noqa: F401
    DEFAULT_PAUSE_FILE,
    SOURCE_LOCAL,
    PauseRecord,
    PauseState,
    PauseStore,
)
from .registry import (  # noqa: F401
    RegistryError,
    Session,
    SessionRegistry,
    WorkItemRef,
)

__all__ = [
    "DEFAULT_PAUSE_FILE",
    "PauseRecord",
    "PauseState",
    "PauseStore",
    "RegistryError",
    "SOURCE_LOCAL",
    "Session",
    "SessionRegistry",
    "WorkItemRef",
]
