"""Provider-agnostic polling contracts (issue-34).

The poller core knows nothing about GitHub. It speaks only this contract; each
ticketing/PR system is a :class:`PollProvider` that a config ``polling.sources``
entry selects by name. A provider knows how to (a) discover the labelled work
items in its configured scope, (b) list an item's comments, and (c) turn an
item/comment into the shared ``RoutedEvent`` the dispatcher already consumes —
so GitHub (or Jira, later) is reached *only* through a configured provider,
never hard-wired into the poller, its config, or the CLI.

Spec: docs/specs/issue-34/design.md §2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Type, TypeVar

from ..sessions import WorkItemRef
from ..webhook.router import RoutedEvent


class ProviderError(Exception):
    """A provider failed to talk to its backing system (network, auth, parse)."""


@dataclass(frozen=True)
class Comment:
    """A provider-agnostic comment on a work item."""

    id: str  # stable, unique per comment — the cross-poll dedup key
    body: str
    author: str
    created_at: str
    url: str


@dataclass
class WorkItem:
    """A provider-agnostic unit of work discovered by a poll source.

    ``provider``/``owner``/``repo``/``number`` map onto the existing
    provider-qualified :class:`WorkItemRef` (``<provider>:<owner>/<repo>#<n>``),
    so the session registry stays the single, provider-neutral identity store.
    ``raw`` carries provider-specific extras a provider needs to build its
    events (e.g. a PR's head branch) without leaking them into the core.
    """

    provider: str
    owner: str
    repo: str
    number: int
    kind: str  # provider vocabulary, e.g. "issue" | "pull-request"
    title: str = ""
    url: str = ""
    author: str = ""  # login that created the item (authorization guard)
    labels: List[str] = field(default_factory=list)
    raw: Dict = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{self.provider}:{self.owner}/{self.repo}#{self.number}"


class PollProvider:
    """Contract a poll source implements. One instance per configured source.

    Subclasses set ``name`` and implement discovery + event construction. The
    instance is constructed from a ``polling.sources`` entry via
    :meth:`from_source`, already bound to its scope and resolved label.
    """

    name: str = ""

    @classmethod
    def from_source(
        cls, source: dict, *, default_label: str, fallback_repos: List[str]
    ) -> "PollProvider":
        """Build a bound provider from one ``polling.sources`` config entry."""
        raise NotImplementedError

    def describe(self) -> str:
        """Short human string for logs (e.g. ``github octo/repo``)."""
        return self.name

    def check_dependencies(self) -> List[str]:
        """Missing native deps (with install hints); empty on the happy path."""
        return []

    def list_work_items(self) -> List[WorkItem]:
        """Discover the labelled work items in this source's scope."""
        raise NotImplementedError

    def list_comments(self, item: WorkItem) -> List[Comment]:
        """All conversation comments currently on ``item``."""
        raise NotImplementedError

    def refs(self, item: WorkItem) -> List[WorkItemRef]:
        """Registry refs an item maps to (itself + any linked items)."""
        raise NotImplementedError

    def presence_event(self, item: WorkItem, refs: List[WorkItemRef]) -> RoutedEvent:
        """A ``labeled=True`` event that spawns a session for ``item``."""
        raise NotImplementedError

    def comment_event(
        self, item: WorkItem, comment: Comment, refs: List[WorkItemRef]
    ) -> RoutedEvent:
        """A ``labeled=False`` event routing ``comment`` to ``item``'s session."""
        raise NotImplementedError


# Provider registry: name -> class. GitHub registers itself on import; new
# providers (e.g. Jira) drop in here with zero core changes.
_PROVIDERS: Dict[str, Type[PollProvider]] = {}

_ProviderT = TypeVar("_ProviderT", bound=PollProvider)


def register_provider(cls: Type[_ProviderT]) -> Type[_ProviderT]:
    if not cls.name:
        raise ValueError(f"{cls.__name__} must set a non-empty provider name")
    _PROVIDERS[cls.name] = cls
    return cls


def provider_names() -> List[str]:
    return sorted(_PROVIDERS)


def build_provider(
    source: dict, *, default_label: str, fallback_repos: List[str]
) -> PollProvider:
    """Resolve a ``polling.sources`` entry to a bound :class:`PollProvider`."""
    name = str((source or {}).get("provider") or "").strip()
    if not name:
        raise ProviderError(
            "a polling source is missing its 'provider' key "
            f"(known providers: {', '.join(provider_names()) or 'none'})"
        )
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ProviderError(
            f"unknown polling provider {name!r} "
            f"(known providers: {', '.join(provider_names()) or 'none'})"
        )
    return cls.from_source(
        source, default_label=default_label, fallback_repos=fallback_repos
    )
