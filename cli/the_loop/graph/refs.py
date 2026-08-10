"""Deriving a work-item **ref** from what the repository already declares (issue-194).

The graph names a work item by its spec-directory id (``issue-194``); every
outbound integration call names it by a provider-qualified ref
(``github:octo/repo#194``). :func:`graphlink.spec_id_for` already translates
ref → id for the ingress. This is the other direction, and it exists because
without it ``the-loop graph advance 194`` — the form the docs and the skill show
— handed the bare id to GitHub, where **every** call raised ``malformed work
item ref`` and every hook degraded to a no-op.

Derived, never guessed. The owner and repository come from one place, the
harness config's ``ticketing.github`` (already loaded into the runtime as
``originRepo``), and both halves are validated against GitHub's own name shape
before a ref is built. Anything that does not validate yields ``""`` — the
caller then keeps the bare id, which is exactly the pre-fix behaviour, and the
integration says so out loud. "No ref" is the fail-closed direction; "a ref
pointing somewhere else" is not, and is unreachable.

The ref is spelled by :class:`WorkItemRef` rather than by an f-string here, so
the form this module writes cannot drift from the parser that reads it back.
"""

from __future__ import annotations

import re

from ..sessions import WorkItemRef, is_github_name

__all__ = ["derive_ref", "ref_for"]

#: The spec-directory id of a GitHub-ticketed work item. The ``issue-<n>``
#: convention is GitHub's own — the same one :func:`graphlink.spec_id_for`
#: writes — and the number is the only part of the id that reaches a ref, so it
#: is matched rather than parsed out of arbitrary text.
_ISSUE_ID_RE = re.compile(r"^issue-(\d+)$")


def derive_ref(work_item_id: str, origin_repo: str) -> str:
    """``issue-194`` + ``octo/repo`` → ``github:octo/repo#194``; ``""`` if it cannot.

    ``origin_repo`` is ``<owner>/<repo>`` as :func:`harness_config.origin_repo`
    produces it — empty when the project is not GitHub-ticketed or has not said,
    in which case there is nothing to derive from and nothing is derived.

    Total: every failure path returns ``""``. A caller gets a usable ref or
    nothing, never a partial one and never an exception — this runs on the way
    out to an integration, and a translation helper that raises would turn a
    best-effort comment into a wedged work item.
    """
    match = _ISSUE_ID_RE.match(work_item_id.strip())
    if not match:
        return ""  # not a GitHub-shaped id: another provider's, or a draft
    return ref_for(origin_repo, int(match.group(1)))


def ref_for(repo_slug: str, number: int) -> str:
    """``octo/repo`` + ``7`` → ``github:octo/repo#7``; ``""`` if it cannot.

    The primitive :func:`derive_ref` is built on, and the one an **inner** loop
    needs directly: a pull request's loop is about the pull request, so its ref
    is built from its number and the repository it is in — never from the work
    item's id, which would address the ticket instead (issue-194).
    """
    owner, sep, repo = repo_slug.strip().partition("/")
    if not sep or not owner or not repo:
        return ""  # unset, or not <owner>/<repo>
    if not (is_github_name(owner) and is_github_name(repo)):
        # A host-qualified path (`ghe.example/octo/repo`), a stray separator, a
        # space — anything GitHub itself would not accept as a name. Validated
        # against the same expression `WorkItemRef.url` uses, so "what GitHub
        # accepts" has one definition in the codebase.
        return ""
    if number <= 0:
        return ""
    return WorkItemRef(provider="github", owner=owner, repo=repo, number=number).ref
