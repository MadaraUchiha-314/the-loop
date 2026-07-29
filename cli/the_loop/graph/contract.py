"""The hook contract — the one type every hook returns (issue-109, R2).

Everything the-loop does at a node boundary is a hook: validating artifacts,
linting them, syncing a label, requesting a review, notifying Slack, classifying
a reviewer's reply. They all share one signature::

    def hook(ctx: HookContext) -> HookResult: ...

and one output type. :class:`HookResult` is what decides whether a work item
moves, which is the direct answer to the question issue-109 opens with — *how
does the CLI know a step is complete versus waiting for the user?*

    A node is complete when its exit hooks all ``pass``. It is waiting when one
    returns ``wait``. It is blocked when one returns ``block``.

No prose is ever parsed. Spec: docs/specs/issue-109/design.md § The hook contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

__all__ = [
    "BLOCK",
    "PASS",
    "SKIP",
    "STATUSES",
    "WAIT",
    "HookContext",
    "HookResult",
    "Message",
    "WorkItem",
]

PASS = "pass"
BLOCK = "block"
WAIT = "wait"
SKIP = "skip"

#: Every status a hook may return. A value outside this set is a programming
#: error, not a runtime condition — the chain executor rejects it.
STATUSES = frozenset({PASS, BLOCK, WAIT, SKIP})


@dataclass(frozen=True)
class Message:
    """One finding, addressed to whoever has to act on it.

    ``text`` is composed by the-loop from its own vocabulary plus paths and hook
    names — **never** from untrusted payload text (R3.6), because a blocking
    result is rendered straight back into the agent's next input.
    """

    text: str
    path: str = ""
    severity: str = "error"  # error | warning | info

    def render(self) -> str:
        return f"{self.text} ({self.path})" if self.path else self.text


@dataclass(frozen=True)
class WorkItem:
    """The work item a chain is running for."""

    ref: str  # e.g. github:owner/repo#109
    id: str  # e.g. issue-109
    spec_dir: Path
    tags: Sequence[str] = ()
    risk_tier: int = 3

    @property
    def slug(self) -> str:
        return self.id


@dataclass
class HookContext:
    """Everything a hook may see — and nothing more.

    ``config`` carries secret *handles* (env var names), never secret values
    (R2.7), so a hook cannot accidentally log a credential it was never given.
    """

    work_item: WorkItem
    node: Mapping[str, Any]
    boundary: str  # entry | exit
    repo: Path
    artifacts: Mapping[str, Path] = field(default_factory=dict)
    session: Optional[Mapping[str, Any]] = None
    event: Optional[Mapping[str, Any]] = None
    results: List["HookResult"] = field(default_factory=list)
    config: Mapping[str, Any] = field(default_factory=dict)
    params: Mapping[str, Any] = field(default_factory=dict)

    @property
    def node_id(self) -> str:
        return str(self.node.get("id", ""))


@dataclass
class HookResult:
    """The contract. ``status`` is what moves — or does not move — the work item."""

    status: str
    hook: str
    messages: List[Message] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    retriable: bool = True

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(
                f"{self.hook!r} returned unknown status {self.status!r}; "
                f"expected one of {sorted(STATUSES)}"
            )

    # -- constructors, so hooks read declaratively ---------------------------

    @classmethod
    def ok(cls, hook: str, **data: Any) -> "HookResult":
        return cls(status=PASS, hook=hook, data=dict(data))

    @classmethod
    def blocked(
        cls,
        hook: str,
        messages: Sequence[Message],
        retriable: bool = True,
        **data: Any,
    ) -> "HookResult":
        """Block the chain. ``messages`` is a **list** on purpose: a validating
        hook reports *every* unmet requirement at once so the agent gets the
        complete picture in one round instead of discovering them one at a
        time (R3.5)."""
        return cls(
            status=BLOCK,
            hook=hook,
            messages=list(messages),
            retriable=retriable,
            data=dict(data),
        )

    @classmethod
    def waiting(cls, hook: str, reason: str = "", **data: Any) -> "HookResult":
        msgs = [Message(text=reason, severity="info")] if reason else []
        return cls(status=WAIT, hook=hook, messages=msgs, data=dict(data))

    @classmethod
    def skipped(cls, hook: str, reason: str = "") -> "HookResult":
        msgs = [Message(text=reason, severity="info")] if reason else []
        return cls(status=SKIP, hook=hook, messages=msgs)

    # -- queries --------------------------------------------------------------

    @property
    def outcome(self) -> str:
        """The value edges route on: an explicit ``data['outcome']`` when a hook
        produced one (a gate classification), else the status itself."""
        return str(self.data.get("outcome") or self.status)

    def render(self) -> str:
        return "\n".join(f"- {m.render()}" for m in self.messages)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "hook": self.hook,
            "outcome": self.outcome,
            "messages": [
                {"text": m.text, "path": m.path, "severity": m.severity}
                for m in self.messages
            ],
            "data": self.data,
            "retriable": self.retriable,
        }
