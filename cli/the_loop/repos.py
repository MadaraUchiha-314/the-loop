"""The repositories this instance of the-loop works with — one declaration, one builder.

The list is the top-level ``repositories`` key of the CLI config, and **every** ingress
reads it: the ``gh-webhook`` receiver bounds a delivery by it (issue-348), the poller
takes its scopes from it, the ``/the-loop`` slash command bounds its target to it
(issue-334, decision-116 D4), and a Slack kickoff prefix resolves against it (issue-341,
decision-120 D1). Until issue-348 the list lived in ``polling.sources[].repos``, named
after the one ingress that happened to read it — which is how the receiver came to be
bounded by nothing of the kind.

Every read is best-effort in the **fail-closed direction**: an unreadable section or a
malformed entry contributes nothing, so a fault can only shrink the set — it can never
hand an ingress a repository the operator did not declare.

An entry is kept as the operator wrote it (:attr:`DeclaredRepo.declared`) as well as
normalized to a comparable :attr:`~DeclaredRepo.key`, because the string that reaches
``gh --repo`` must stay their own grammar (``owner/repo`` on github.com, a host in front
on Enterprise — issue-311) while the comparison needs one shape.

This module imports no ingress and no channel, which is what lets the webhook router —
stdlib-only and I/O-free — ask it the same question the poller does.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Set, Tuple

from .ghhost import github_host
from .sessions.registry import is_github_host, is_github_name

logger = logging.getLogger("the-loop.repos")

__all__ = [
    "DeclaredRepo",
    "REPOSITORIES_KEY",
    "declared_repositories",
    "parse_repo_path",
    "repository_bounds",
    "repository_keys",
]

#: The one key that declares them. Named here so a message can quote it without
#: five modules spelling it out.
REPOSITORIES_KEY = "repositories"


@dataclass(frozen=True)
class DeclaredRepo:
    """A repository the operator declared, with the slug they declared it as."""

    declared: str
    host: str
    owner: str
    repo: str
    source: str = REPOSITORIES_KEY  # where it was declared — one place since issue-348

    @property
    def key(self) -> str:
        """``host/owner/repo``, lowercased — the comparable shape."""
        return f"{self.host}/{self.owner}/{self.repo}".lower()


def parse_repo_path(
    path: str, cli_config: Optional[Mapping], *, source: str = REPOSITORIES_KEY
) -> DeclaredRepo:
    """``[host/]owner/repo`` → a :class:`DeclaredRepo`; ``ValueError`` for anything
    else. The host defaults to this instance's (``ghhost.github_host``), and every
    segment goes through the one grammar for a host and a GitHub name — before a
    value can become a candidate, let alone an argument."""
    parts = (path or "").strip().split("/")
    if len(parts) == 2:
        host, owner, repo = "", parts[0], parts[1]
    elif len(parts) == 3:
        host, owner, repo = parts
    else:
        raise ValueError(f"{path!r} is not `[host/]owner/repo`")
    host = host or github_host(cli_config)
    if not (is_github_host(host) and is_github_name(owner) and is_github_name(repo)):
        raise ValueError(f"{host}/{owner}/{repo} is not a GitHub repository path")
    return DeclaredRepo(
        declared=(path or "").strip(), host=host, owner=owner, repo=repo, source=source
    )


def _declared_paths(cli_config: Optional[Mapping]) -> List[str]:
    """The raw strings under ``repositories``, or nothing at all.

    A section that is not a list is not half-read: a mapping's keys are not
    repositories, and guessing what the operator meant is how a bound widens.
    """
    entries = (cli_config or {}).get(REPOSITORIES_KEY)
    if entries is None:
        return []
    if not isinstance(entries, (list, tuple)):
        logger.debug("`%s` is not a list — no repository is declared", REPOSITORIES_KEY)
        return []
    return [str(entry) for entry in entries]


def declared_repositories(cli_config: Optional[Mapping]) -> Tuple[DeclaredRepo, ...]:
    """Every repository this instance is configured for, in declaration order.

    Deduplicated by :attr:`~DeclaredRepo.key`, first writing wins — so the slug an
    operator wrote first is the one that reaches ``gh``.
    """
    config: Mapping[str, Any] = dict(cli_config or {})
    declared: List[DeclaredRepo] = []
    seen: Set[str] = set()
    for path in _declared_paths(config):
        try:
            entry = parse_repo_path(path, config)
        except Exception as exc:  # noqa: BLE001 — a malformed entry is not a candidate
            logger.debug("declared repository %r skipped: %s", path, exc)
            continue
        if entry.key in seen:
            continue
        seen.add(entry.key)
        declared.append(entry)
    return tuple(declared)


def repository_keys(cli_config: Optional[Mapping]) -> Set[str]:
    """:func:`declared_repositories` as comparable keys — what a bounds check wants."""
    return {entry.key for entry in declared_repositories(cli_config)}


def repository_bounds(cli_config: Optional[Mapping]) -> Optional[Set[str]]:
    """The keys, or ``None`` when the operator declared nothing.

    An ingress has to tell *"declared nothing"* from *"declared, and this is not in
    it"* — the first accepts everything, the second accepts one repository — and an
    empty set says both. So the distinction is made here, once, rather than in every
    caller that would otherwise have to remember which one an empty set is.
    """
    keys = repository_keys(cli_config)
    return keys or None
