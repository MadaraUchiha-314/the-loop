"""The kickoff target: which repository a top-level Slack message becomes an issue in.

Issue-341. Until 13.11.1 the answer was one config value, ``kickoff.repo``, and an
empty one disabled the path — because *inferring* a repository from prose has no
sensible answer. This module does not infer one. It reads a **selector** off the
first line and resolves it against the closed set the operator already declared
(:mod:`the_loop.repos`), which is the same set a slash command's target is bounded to:

    slim-gym: flaky teardown in the batch runner

Three shapes are accepted — a bare repository name, ``owner/repo``, and the
``host/owner/repo`` the writer already parses (issue-311) — and the outcome is one of
five, never a guess (decision-120):

``resolved``        the prefix named exactly one declared repository
``fallback``        no prefix was read; ``kickoff.repo`` takes it, provided the
                    operator declared it (issue-348)
``unknown-repo``    a *qualified* prefix named nothing declared — refused
``ambiguous-repo``  a *bare* prefix named several — refused, candidates listed
``no-target``       no prefix and no ``kickoff.repo`` — refused, a prefix asked for
``empty-message``   the prefix resolved but nothing was left to open — refused

A **bare** word that matches nothing is deliberately *not* a refusal (decision-120
D3): ``fix: flaky teardown`` is an ordinary English first line, and every configured
install must keep behaving as it did. ``owner/repo:`` has no reading as prose, so
that is where refusing starts.

Nothing here does I/O, and nothing of the member's text ever becomes a repository:
what a resolution yields is :attr:`DeclaredRepo.declared` — a string from the
operator's own config.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

from ..repos import DeclaredRepo, declared_repositories, parse_repo_path

__all__ = [
    "CANDIDATE_LIMIT",
    "KickoffTarget",
    "PREFIX_RE",
    "refusal_text",
    "resolve_target",
]

#: One to three ``/``-separated segments, each starting alphanumeric, then ``:``.
#: A grammar that cannot express ``../``, ``$(…)``, ``;`` or a scheme's ``//`` —
#: so a metacharacter is not "rejected", it is never read as a prefix at all.
_SEGMENT = r"[A-Za-z0-9][A-Za-z0-9._-]*"
PREFIX_RE = re.compile(
    rf"^[ \t]*(?P<prefix>{_SEGMENT}(?:/{_SEGMENT}){{0,2}})[ \t]*:[ \t]*(?P<rest>.*)$"
)

#: How many declared repositories a refusal names before "…and N more".
CANDIDATE_LIMIT = 12


@dataclass(frozen=True)
class KickoffTarget:
    """Where a kickoff goes, and what it is composed from."""

    outcome: str
    repo: str = ""  #: the DECLARED slug to create in — never the member's text
    text: str = ""  #: the message the issue is composed from (prefix stripped)
    prefix: str = ""  #: what was read, for the refusal's wording
    candidates: Tuple[str, ...] = ()  #: what the member could have named

    @property
    def ok(self) -> bool:
        return self.outcome in ("resolved", "fallback")


def _strip_prefix(text: str, rest: str) -> str:
    """The message with its first line replaced by ``rest`` (R1.3)."""
    lines = text.splitlines()
    tail = lines[1:] if len(lines) > 1 else []
    return "\n".join([rest.rstrip()] + tail) if rest.strip() or tail else rest.strip()


def _matches(
    prefix: str, declared: Tuple[DeclaredRepo, ...], cli_config
) -> List[DeclaredRepo]:
    """The declared repositories ``prefix`` names — qualified by key, bare by name."""
    wanted = prefix.lower()
    if "/" in prefix:
        try:
            key = parse_repo_path(prefix, cli_config).key
        except ValueError:
            return []
        return [entry for entry in declared if entry.key == key]
    return [entry for entry in declared if entry.repo.lower() == wanted]


def resolve_target(
    text: str, config, cli_config: Optional[Mapping] = None
) -> KickoffTarget:
    """Where this kickoff message goes. Never raises; never infers."""
    declared = declared_repositories(cli_config)
    names = tuple(entry.declared for entry in declared)
    # The fallback is `kickoff.repo` VERBATIM, not its entry in the declared set:
    # 13.11.1 handed this string to the writer as it stood, and a message with no
    # prefix must keep behaving exactly as it did (R3.1).
    fallback = (config.kickoff_repo or "").strip()

    def without_prefix() -> KickoffTarget:
        if not fallback:
            return KickoffTarget("no-target", text=text, candidates=names)
        # The fallback is bounded by the same declaration as everything else
        # (issue-348, R4.3): `kickoff.repo` points AT a declared repository, it does
        # not declare one. An instance that declared nothing is bounded by nothing,
        # exactly as its receiver is — so the check only bites once there is a set
        # to be outside of.
        if declared and not _matches(fallback, declared, cli_config):
            return KickoffTarget(
                "unknown-repo", text=text, prefix=fallback, candidates=names
            )
        return KickoffTarget("fallback", repo=fallback, text=text, candidates=names)

    lines = text.splitlines()
    match = PREFIX_RE.match(lines[0]) if lines else None
    if not match:
        return without_prefix()
    prefix = match["prefix"]
    found = _matches(prefix, declared, cli_config)
    if len(found) == 1:
        stripped = _strip_prefix(text, match["rest"])
        if not stripped.strip():
            # A prefix and nothing else is not a work item — and having reached a
            # named repository, the member gets told so rather than dropped.
            return KickoffTarget(
                "empty-message", text=text, prefix=prefix, candidates=names
            )
        return KickoffTarget(
            "resolved",
            repo=found[0].declared,
            text=stripped,
            prefix=prefix,
            candidates=names,
        )
    if len(found) > 1:
        return KickoffTarget(
            "ambiguous-repo",
            text=text,
            prefix=prefix,
            candidates=tuple(entry.declared for entry in found),
        )
    if "/" in prefix:
        # A qualified name has no reading as prose: refuse rather than let the
        # fallback absorb a repository the member explicitly named (A2).
        return KickoffTarget("unknown-repo", text=text, prefix=prefix, candidates=names)
    return without_prefix()  # a bare word that matches nothing is not a prefix


def _candidate_list(candidates: Tuple[str, ...]) -> str:
    shown = [f"`{name}`" for name in candidates[:CANDIDATE_LIMIT]]
    extra = len(candidates) - len(shown)
    return ", ".join(shown) + (f" …and {extra} more" if extra > 0 else "")


def refusal_text(target: KickoffTarget) -> str:
    """What the thread is told. Fixed words, the prefix quoted, the declared names —
    no token, no other config value, and nothing else of the member's message (A5)."""
    if not target.candidates:
        where = (
            "I know no repositories — set the top-level `repositories` in the "
            "CLI config, then try again."
        )
    else:
        where = f"I know: {_candidate_list(target.candidates)}."
    if target.outcome == "empty-message":
        return (
            f"`{target.prefix}` is a repository I know, but the message said "
            "nothing else — put the title after the prefix and I'll open it."
        )
    if target.outcome == "ambiguous-repo":
        return (
            f"`{target.prefix}` names more than one repository I know — say which "
            f"owner: {_candidate_list(target.candidates)}. Nothing was created."
        )
    if target.outcome == "unknown-repo":
        return (
            f"I don't know a repository called `{target.prefix}`, so nothing was "
            f"created. Start your message with one I do know, or drop the prefix. "
            f"{where}"
        )
    return (
        "This channel has no default repository, so a kickoff has to name one: "
        f"start your message with `<repo>: `. {where}"
    )
