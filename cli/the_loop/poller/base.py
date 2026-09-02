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
from typing import Dict, List, Optional, Type, TypeVar

from ..sessions import WorkItemRef, host_from_url
from ..webhook.router import RoutedEvent


class ProviderError(Exception):
    """A provider failed to talk to its backing system (network, auth, parse)."""


@dataclass(frozen=True)
class Comment:
    """A provider-agnostic comment on a work item.

    "Comment" is the *role*, not the API object: anything a human leaves on a
    work item carrying an instruction is one. On GitHub that is three distinct
    objects — a conversation comment, a pull-request review body, and an inline
    review-thread comment (issue-246) — and the poller core treats all three
    identically, because the four fields below are everything it reads.
    """

    id: str  # stable, unique per comment — the cross-poll dedup key
    body: str
    author: str
    created_at: str
    url: str
    # Provider-specific extras the provider needs in order to build the right
    # event for this comment (e.g. GitHub's kind and a review comment's
    # file/line anchor), carried here rather than widening the neutral shape —
    # the same contract, and the same warning, as ``WorkItem.raw``: the core
    # never reads it, and only the provider that wrote it may.
    raw: Dict = field(default_factory=dict)


@dataclass(frozen=True)
class Closure:
    """Why a work item is no longer open — provider-neutral (issue-94).

    A poll source lists only *open* work items, so an item that ends simply
    vanishes from the listing. This is the answer to the follow-up question the
    poller then asks about a session whose item disappeared: has it actually
    ended, and how?
    """

    state: str  # "closed" | "merged"
    kind: str = ""  # provider vocabulary, e.g. "issue" | "pull-request"
    title: str = ""
    url: str = ""

    @property
    def merged(self) -> bool:
        return self.state == "merged"


@dataclass
class WorkItem:
    """A provider-agnostic unit of work discovered by a poll source.

    ``provider``/``owner``/``repo``/``number`` map onto the existing
    provider-qualified :class:`WorkItemRef`
    (``<provider>:[<host>/]<owner>/<repo>#<n>``, the host coming from ``url``),
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
    def host(self) -> str:
        """Which host this item lives on, read off its own URL (issue-130 review).

        A polled GitHub Enterprise item is identified as such here, exactly as
        the webhook path identifies one from the repository's ``html_url`` — the
        two must agree, because this ref keys the poll ledger while the router's
        keys the routing.
        """
        return host_from_url(self.url)

    @property
    def ref(self) -> str:
        return WorkItemRef(
            provider=self.provider,
            owner=self.owner,
            repo=self.repo,
            number=self.number,
            host=self.host,
        ).ref


#: How many cycles a scope with a *permanent* condition stays skipped before the
#: provider re-probes it once (issue-315) — one hour at the default interval.
#: The core's policy, honoured by every provider that quarantines; a config
#: reload or a restart rebuilds the provider and re-probes at once.
REPROBE_EVERY_CYCLES = 60


@dataclass(frozen=True)
class ScopeFailure:
    """One scope of a source that could not be polled this cycle (issue-315).

    A *scope* is the provider's own unit of listing — a repository for GitHub,
    a project for a Jira provider — and the core never learns what one is
    beyond the string. ``permanent`` marks a condition no retry changes
    (configuration drift, e.g. a repository with Issues turned off), which the
    core surfaces once at warning level instead of as an error every cycle.
    The provider decides, because only it can read its backing system's
    vocabulary.
    """

    scope: str
    error: str  # what failed — or, for a skipped scope, why it is skipped
    permanent: bool = False


@dataclass
class Listing:
    """What one discovery pass over a source found — and what it could not ask.

    ``items`` are the work items from every scope that answered. ``failures``
    are this cycle's listing failures, one per scope and listing that failed;
    ``skipped`` are scopes deliberately not asked because of a standing
    permanent condition; ``recovered`` are scopes a re-probe brought back;
    ``polled`` are the scopes that answered, fully or partly. A scope in
    ``failures`` or ``skipped`` is *degraded*: nothing in it is reconciled as
    closed, because a listing that did not happen proves nothing ended
    (issue-159's rule, now per scope).
    """

    items: List[WorkItem] = field(default_factory=list)
    failures: List[ScopeFailure] = field(default_factory=list)
    skipped: List[ScopeFailure] = field(default_factory=list)
    recovered: List[str] = field(default_factory=list)
    polled: List[str] = field(default_factory=list)

    @property
    def degraded(self) -> set:
        return {f.scope for f in self.failures} | {s.scope for s in self.skipped}


class PollProvider:
    """Contract a poll source implements. One instance per configured source.

    Subclasses set ``name`` and implement discovery + event construction. The
    instance is constructed from a ``polling.sources`` entry via
    :meth:`from_source`, already bound to its scope and resolved label.
    """

    name: str = ""

    @classmethod
    def from_source(cls, source: dict, *, default_label: str) -> "PollProvider":
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

    def listing(self) -> Listing:
        """Discover the labelled work items, scope by scope (issue-315).

        What the poller core calls. The default wraps :meth:`list_work_items`
        all-or-nothing, so a provider that has not learned scopes keeps its
        behaviour: a :class:`ProviderError` raised here means the provider
        could not be asked at all — no scopes configured, its binary missing —
        and fails the whole source, exactly as before. A provider that *can*
        isolate its scopes overrides this, reports each failed scope in the
        :class:`Listing`, and reserves the exception for that whole-source case.
        """
        return Listing(items=self.list_work_items())

    def scope_of(self, ref: WorkItemRef) -> str:
        """The scope ``ref`` lives in, spelled as :class:`ScopeFailure` spells it.

        ``""`` when this provider has no scopes, or ``ref`` is not its. The core
        uses it to keep a degraded scope's sessions out of closure
        reconciliation (issue-315).
        """
        return ""

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

    # -- closure reconciliation (issue-94, opt-in) -----------------------------
    #
    # A provider opts into "did this work item end?" by implementing all three.
    # The defaults say "I don't answer closure questions", and ``owns``
    # returning False is what makes the poller skip reconciliation entirely for
    # such a provider — no other core change needed.

    def owns(self, ref: WorkItemRef) -> bool:
        """Whether ``ref`` falls inside this source's configured scope."""
        return False

    def closure(self, ref: WorkItemRef) -> Optional[Closure]:
        """Ask the backing system whether ``ref`` has ended.

        ``None`` means "still open" (or "this provider does not answer"), and is
        the only safe answer under doubt — the poller never closes a session on
        an unknown state. Raise :class:`ProviderError` when the backing system
        could not be reached, so the caller can retry on a later cycle.
        """
        return None

    def closure_event(self, ref: WorkItemRef, closure: Closure) -> RoutedEvent:
        """A close event for ``ref``, shaped like the webhook one it mirrors."""
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


def build_provider(source: dict, *, default_label: str) -> PollProvider:
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
    return cls.from_source(source, default_label=default_label)
