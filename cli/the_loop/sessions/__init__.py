"""Session registry: work item ↔ harness session linkage (issue-15, R2)."""

from .pauses import (  # noqa: F401
    DEFAULT_PAUSE_FILE,
    DEFAULT_PAUSED_LABEL,
    SOURCE_LABEL,
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
    "DEFAULT_PAUSED_LABEL",
    "DEFAULT_PAUSE_FILE",
    "PauseRecord",
    "PauseState",
    "PauseStore",
    "RegistryError",
    "SOURCE_LABEL",
    "SOURCE_LOCAL",
    "Session",
    "SessionRegistry",
    "WorkItemRef",
]
