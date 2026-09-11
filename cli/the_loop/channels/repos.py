"""The repositories this instance is configured for — one set, one builder.

``channels.slack.kickoff.repo`` plus every ``repos`` entry of every ``github``
source in ``polling.sources``. Two inbound shapes ask the same question of it and
must get the same answer: the ``/the-loop`` slash command bounds its target to this
set (issue-334, decision-116 D4), and a kickoff prefix resolves against it
(issue-341, decision-120 D1). Two builders is how two answers diverge.

Every read is best-effort in the **fail-closed direction**: an unreadable section or
a malformed entry contributes nothing, so a fault can only shrink the set — it can
never hand a message a repository the operator did not declare.

An entry is kept as the operator wrote it (:attr:`DeclaredRepo.declared`) as well as
normalized to a comparable :attr:`~DeclaredRepo.key`, because the string that
reaches ``gh --repo`` must stay their own grammar (``owner/repo`` on github.com, a
host in front on Enterprise — issue-311) while the comparison needs one shape.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Set, Tuple

from ..ghhost import github_host
from ..sessions.registry import is_github_host, is_github_name

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "DeclaredRepo",
    "declared_repositories",
    "parse_repo_path",
    "repository_keys",
]


@dataclass(frozen=True)
class DeclaredRepo:
    """A repository the operator declared, with the slug they declared it as."""

    declared: str
    host: str
    owner: str
    repo: str
    source: str = ""  # "kickoff" | "polling" — where it was declared

    @property
    def key(self) -> str:
        """``host/owner/repo``, lowercased — the comparable shape."""
        return f"{self.host}/{self.owner}/{self.repo}".lower()


def parse_repo_path(
    path: str, cli_config: Optional[Mapping], *, source: str = ""
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


def _polled_paths(cli_config: Optional[Mapping]) -> List[str]:
    polling = (cli_config or {}).get("polling") or {}
    sources = polling.get("sources") if isinstance(polling, Mapping) else None
    paths: List[str] = []
    for source in sources if isinstance(sources, list) else []:
        if not isinstance(source, Mapping) or source.get("provider") != "github":
            continue
        entries = source.get("repos") or []
        if not isinstance(entries, (list, tuple)):
            logger.debug("polling source `repos` is not a list — skipped")
            continue
        paths.extend(str(entry) for entry in entries)
    return paths


def declared_repositories(cli_config: Optional[Mapping]) -> Tuple[DeclaredRepo, ...]:
    """Every repository this instance is configured for, in declaration order:
    ``kickoff.repo`` first, then the poll sources. Deduplicated by
    :attr:`~DeclaredRepo.key`, first writing wins."""
    config: Mapping[str, Any] = dict(cli_config or {})
    from .slack import SlackChannelConfig  # local: slack.py reads no repo set

    candidates: List[Tuple[str, str]] = []
    try:
        kickoff = SlackChannelConfig.from_mapping(config).kickoff_repo
    except Exception as exc:  # noqa: BLE001 — a broken section widens nothing
        logger.debug("channels.slack unreadable for the declared set: %s", exc)
        kickoff = ""
    if kickoff:
        candidates.append((kickoff, "kickoff"))
    candidates.extend((path, "polling") for path in _polled_paths(config))

    declared: List[DeclaredRepo] = []
    seen: Set[str] = set()
    for path, source in candidates:
        try:
            entry = parse_repo_path(path, config, source=source)
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
