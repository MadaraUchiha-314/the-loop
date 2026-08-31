"""Work-item collaborators — the second, narrower answer to "may this text be an input?".

``routing.authorizedUsers`` (:mod:`the_loop.authz`) is a **global** list: a login either
directs every work item this daemon watches, or none of them. That is the right shape for
the operator and the wrong shape for the person who knows one answer on one issue — and
until this module existed the consequence was not that such a person had *less* power, it
was that they were invisible. Both ingress paths dropped their comment before anything read
it, so an agent waiting on a question never heard the reply.

A **work-item collaborator** is a login an authorized user has granted, on **one** work
item, the right to be *input*. The boundary is deliberately one-way, and it is the whole of
the model:

* a work-item collaborator's comment on that work item is delivered to its session as
  agent input, on both ingress paths;
* everything that is an **action** — the control keywords, spawning a session, arming one,
  and every human gate in the graph — keeps consulting ``authorizedUsers`` alone.

*A work-item collaborator supplies input on one work item; an authorized user directs the
loop.*

## Not to be confused with `.the-loop/collaborators.yaml`

Two unrelated things in this repository are called collaborators. That file names the
project's stewards and their *roles* (architect, approver, …) for the **plugin**, and the
CLI daemon never reads it (decision-032, decision-035). What is here is runtime state: a
roster per work item, written by a control command, read on every event.

## Where a roster lives, and why there

The fourth section of the work item's portable record (``<state.root>/portable/<slug>.json``),
beside ``control``, ``poll`` and ``graph`` — for issue-128's reason: "an authorized user
invited Dana onto this item" is true on any machine, so it travels with the work item
rather than with the session handle. Writes go through
:meth:`the_loop.workitem.WorkItemStore.write_section`, which is read-modify-write per
section and atomic per file, so a grant cannot clobber a control command recorded a moment
earlier by the other ingress.

A grant is cleared when the work item ends (closure, ``the-loop cleanup``,
``the-loop sessions reset``), exactly as the control record is: a grant is scoped to the
work item's active life, and the ticket thread plus the event log stay the record that it
was made.

Spec: docs/specs/issue-307/design.md §1.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from .sessions import WorkItemRef
from .state import LegacyLayout
from .workitem import COLLABORATORS, WorkItemStore

logger = logging.getLogger("the-loop.collaborators")

__all__ = [
    "CollaboratorRecord",
    "CollaboratorStore",
    "LOGIN_RE",
    "normalize_login",
    "parse_logins",
]

#: GitHub's own login grammar: 1–39 characters of ``[A-Za-z0-9]`` with single interior
#: hyphens. This regex is the **entire** parser for the one argument a control command has
#: ever carried, and therefore the mitigation for injection through it (abuse case A3): a
#: token that does not match is not sanitised, it is refused. Nothing else from a comment
#: body reaches the roster, a path, an argv, a prompt or a comment.
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")

#: Trailing characters a name may collect from ordinary prose ("…add @dana.") or from
#: markdown ("`the-loop add-collaborator @dana`"), none of which can appear in a login —
#: so trimming them cannot turn one login into another. Note what is **not** here: ``/``
#: and ``\`` are never trimmed, so ``@dana/../etc`` is refused outright rather than
#: quietly becoming ``dana``.
_TRAILING_PUNCTUATION = ".,;:!?)]}>\"'`"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_login(raw: object) -> str:
    """``raw`` as a canonical GitHub login, or ``""`` when it is not one.

    Strips one optional leading ``@`` and case-folds, because GitHub logins are
    case-insensitive and storing ``@Dana`` while looking up ``dana`` would be a silent
    revocation. Returns ``""`` — never a partial match, never a cleaned-up guess — for
    anything else, which is what every caller refuses on.
    """
    text = str(raw or "").strip()
    if text.startswith("@"):
        text = text[1:]
    if not LOGIN_RE.match(text):
        return ""
    return text.lower()


def parse_logins(text: str) -> List[str]:
    """The run of ``@login`` tokens at the head of ``text``, canonicalised.

    Scanning stops at the first token that is not an ``@login``, so ``@a @b please help``
    yields ``["a", "b"]`` and the prose is ignored rather than making the whole comment a
    refusal (R4.3). Order is preserved and duplicates are dropped. Pure and side-effect
    free.
    """
    out: List[str] = []
    for token in re.split(r"[\s,]+", str(text or "").strip()):
        if not token.startswith("@"):
            break
        login = normalize_login(token.rstrip(_TRAILING_PUNCTUATION))
        if not login:
            break
        if login not in out:
            out.append(login)
    return out


@dataclass(frozen=True)
class CollaboratorRecord:
    """One grant: who, granted by whom, when, through which surface."""

    login: str
    added_by: str = ""
    added_at: str = ""
    source: str = "comment"  # comment | cli
    note: str = ""  # the granting comment's url, when there is one

    def to_dict(self) -> Dict[str, Any]:
        return {
            "login": self.login,
            "addedBy": self.added_by,
            "addedAt": self.added_at,
            "source": self.source,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["CollaboratorRecord"]:
        """``data`` as a record, or ``None`` when it does not name a valid login.

        Fails closed on a hand-edited or corrupt entry: an unparsable login grants nobody,
        rather than granting whatever the file happened to contain.
        """
        if not isinstance(data, dict):
            return None
        login = normalize_login(data.get("login"))
        if not login:
            return None
        return cls(
            login=login,
            added_by=str(data.get("addedBy") or ""),
            added_at=str(data.get("addedAt") or ""),
            source=str(data.get("source") or "comment"),
            note=str(data.get("note") or ""),
        )


def _as_ref(work_item: Union[str, WorkItemRef]) -> WorkItemRef:
    if isinstance(work_item, WorkItemRef):
        return work_item
    return WorkItemRef.parse(work_item)


class CollaboratorStore:
    """The ``collaborators`` section of each work item's portable record.

    Constructed exactly as :class:`the_loop.control.ControlStore` is, over the same
    directory, so both daemons read one roster from one place. A store whose directory
    cannot be read degrades to "nobody is a collaborator" — fail closed, the same way an
    unreadable control record degrades to "nothing was armed".
    """

    def __init__(self, root: Union[str, Path], legacy: Optional[LegacyLayout] = None):
        self.store = WorkItemStore(root, legacy=legacy)

    @property
    def root(self) -> Path:
        return self.store.root

    def list(self, work_item: Union[str, WorkItemRef]) -> List[CollaboratorRecord]:
        """The work item's roster, in the order it was granted."""
        section = self.store.section(work_item, COLLABORATORS) or {}
        entries = section.get("users") if isinstance(section, dict) else None
        out: List[CollaboratorRecord] = []
        for entry in entries or []:
            record = CollaboratorRecord.from_dict(entry)
            if record is None:
                logger.warning(
                    "skipping an unreadable collaborator entry for %s", work_item
                )
                continue
            if any(existing.login == record.login for existing in out):
                continue
            out.append(record)
        return out

    def logins(self, work_item: Union[str, WorkItemRef]) -> List[str]:
        """Just the logins, for the membership tests below."""
        return [record.login for record in self.list(work_item)]

    def add(
        self,
        work_item: Union[str, WorkItemRef],
        login: str,
        actor: str = "",
        source: str = "comment",
        note: str = "",
    ) -> bool:
        """Grant ``login`` on ``work_item``. False when it was already granted.

        Raises :class:`ValueError` for anything that is not a GitHub login: a caller that
        has not validated its input must not be able to write one.
        """
        canonical = normalize_login(login)
        if not canonical:
            raise ValueError(f"not a GitHub login: {login!r}")
        item = _as_ref(work_item)
        current = self.list(item)
        if any(record.login == canonical for record in current):
            return False
        current.append(
            CollaboratorRecord(
                login=canonical,
                added_by=actor,
                added_at=_utcnow(),
                source=source,
                note=note,
            )
        )
        self._write(item, current)
        logger.info(
            "granted %s collaborator status on %s (source=%s, by=%s)",
            canonical,
            item.ref,
            source,
            actor or "(unknown)",
        )
        return True

    def remove(self, work_item: Union[str, WorkItemRef], login: str) -> bool:
        """Revoke ``login`` on ``work_item``. False when it was not granted."""
        canonical = normalize_login(login)
        if not canonical:
            raise ValueError(f"not a GitHub login: {login!r}")
        item = _as_ref(work_item)
        current = self.list(item)
        remaining = [record for record in current if record.login != canonical]
        if len(remaining) == len(current):
            return False
        self._write(item, remaining)
        logger.info("revoked %s's collaborator status on %s", canonical, item.ref)
        return True

    def is_collaborator(
        self, actor: Optional[str], work_item: Union[str, WorkItemRef]
    ) -> bool:
        """Whether ``actor`` is granted on this one work item.

        A nameless actor is **never** a collaborator — the asymmetry with
        :func:`the_loop.authz.is_authorized`, which allows an actor-less action because it
        carries status rather than instructions, is deliberate: a grant is about a person.
        """
        canonical = normalize_login(actor)
        if not canonical:
            return False
        return canonical in self.logins(work_item)

    def permits(
        self, actor: Optional[str], work_items: Iterable[Union[str, WorkItemRef]]
    ) -> bool:
        """Whether ``actor`` is granted on **any** of ``work_items``.

        The caller passes the refs the event itself named, and nothing else — which is
        what confines a grant to the work item and the pull requests already routed to its
        session (R3.7), and what stops it reaching any other work item (abuse case A4).
        This method does not widen the set it is given; it only answers about it.
        """
        canonical = normalize_login(actor)
        if not canonical:
            return False
        for item in work_items:
            try:
                if canonical in self.logins(item):
                    return True
            except ValueError:  # an unparsable ref grants nothing
                continue
        return False

    def clear(self, work_item: Union[str, WorkItemRef]) -> bool:
        """Forget a work item's roster (it ended). False if there was none."""
        if self.store.section(work_item, COLLABORATORS) is None:
            return False
        self.store.write_section(work_item, COLLABORATORS, None)
        return True

    def _write(self, item: WorkItemRef, records: Sequence[CollaboratorRecord]) -> None:
        payload = (
            {"users": [record.to_dict() for record in records]} if records else None
        )
        self.store.write_section(item, COLLABORATORS, payload)
