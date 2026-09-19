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

## Two ids, one person (issue-389)

A collaborator may be known by a GitHub login, by a Slack member id, or by both — at
least one. The login is what the ticket ingress matches a comment's author against;
the member id is what the Slack ingress matches a message's ``user`` against. Neither
is ever derived from the other: an entry with only a login says nothing about Slack,
and one with only a Slack id is invisible to :meth:`CollaboratorStore.is_collaborator`
and :meth:`CollaboratorStore.permits`, which keep their meaning (a login is on the
roster, or it is not). A handle (``@dana``) is **never** stored: the CLI resolves it
to an id through the directory before anything is written, and the ticket grammar
accepts only ``slack:U…`` — so an entry that names an unresolvable id authorizes
nobody rather than whoever holds a handle today (abuse case A11).

Spec: docs/specs/issue-307/design.md §1; docs/specs/issue-389/design.md §5.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .sessions import WorkItemRef
from .state import LegacyLayout
from .workitem import COLLABORATORS, WorkItemStore

logger = logging.getLogger("the-loop.collaborators")

__all__ = [
    "CollaboratorRecord",
    "CollaboratorStore",
    "LOGIN_RE",
    "SLACK_TOKEN_PREFIX",
    "Subjects",
    "normalize_login",
    "normalize_slack_id",
    "parse_logins",
    "parse_subjects",
    "slack_token",
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

#: How a Slack member id is spelled as a command argument: ``slack:U0456GHIJ``. The
#: prefix is what tells the parser an id from a login, and it is matched
#: case-insensitively (the keywords are); the id itself is not — a member id is
#: uppercase, and a lowercase token is a name, which the ticket path refuses to look
#: up (issue-389 §5).
SLACK_TOKEN_PREFIX = "slack:"


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


def normalize_slack_id(raw: object) -> str:
    """``raw`` as a Slack member id (``U…``/``W…``), or ``""`` when it is not one.

    The Slack counterpart of :func:`normalize_login`, and as strict: a handle, a
    conversation id or a lowercase token is ``""``, never a guess. Ids are compared
    as Slack issues them, so nothing is case-folded.
    """
    from .channels.directory import is_member_id

    text = str(raw or "").strip()
    return text if is_member_id(text) else ""


def slack_token(member_id: str) -> str:
    """``member_id`` spelled as the command argument: ``slack:U0456GHIJ``."""
    return f"{SLACK_TOKEN_PREFIX}{member_id}"


@dataclass(frozen=True)
class Subjects:
    """What a collaborator command named: logins and Slack member ids, each in order.

    Both lists are canonical and duplicate-free; either may be empty. Falsy when both
    are, which is what a caller refuses on (``missing-collaborator``).
    """

    logins: List[str] = field(default_factory=list)
    slack: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.logins or self.slack)


def parse_subjects(text: str) -> Subjects:
    """The run of ``@login`` and ``slack:U…`` tokens at the head of ``text``.

    The two kinds may come in any order. Scanning stops at the first token that is
    neither, so ``@a slack:U0456GHIJ @b please help`` yields both people and the
    prose is ignored rather than making the whole comment a refusal (issue-307
    R4.3). A ``slack:`` token whose value is not a member id — a handle, a lowercase
    id — is not a subject **and** ends the run: the ticket path resolves nothing, so
    a token that would need resolving is refused outright (issue-389 A11). Order is
    preserved and duplicates are dropped. Pure and side-effect free.
    """
    logins: List[str] = []
    slack: List[str] = []
    for token in re.split(r"[\s,]+", str(text or "").strip()):
        token = token.rstrip(_TRAILING_PUNCTUATION)
        if token.startswith("@"):
            login = normalize_login(token)
            if not login:
                break
            if login not in logins:
                logins.append(login)
        elif token[: len(SLACK_TOKEN_PREFIX)].lower() == SLACK_TOKEN_PREFIX:
            member = normalize_slack_id(token[len(SLACK_TOKEN_PREFIX) :])
            if not member:
                break
            if member not in slack:
                slack.append(member)
        else:
            break
    return Subjects(logins=logins, slack=slack)


def parse_logins(text: str) -> List[str]:
    """The ``@login`` tokens :func:`parse_subjects` finds at the head of ``text``.

    Kept for the callers that only want logins (the Slack slash command's argument
    check, and any reader of a comment's author): the same scan, minus the ids.
    """
    return parse_subjects(text).logins


@dataclass(frozen=True)
class CollaboratorRecord:
    """One grant: who, granted by whom, when, through which surface.

    ``login`` and ``slack`` are the two ids a person may be known by (issue-389); at
    least one is set. ``slack`` is a member id as Slack issues it — never a handle.
    """

    login: str = ""
    slack: str = ""
    added_by: str = ""
    added_at: str = ""
    source: str = "comment"  # comment | cli
    note: str = ""  # the granting comment's url, when there is one

    @property
    def label(self) -> str:
        """How a human should see the entry: ``@dana``, ``slack:U…``, or both."""
        parts = []
        if self.login:
            parts.append(f"@{self.login}")
        if self.slack:
            parts.append(slack_token(self.slack))
        return " ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"login": self.login}
        if self.slack:
            # Emitted only when set, so a roster written before the field existed
            # reads back byte-for-byte the same and a reader of the file sees the
            # id only on the entries that carry one.
            out["slack"] = self.slack
        out.update(
            {
                "addedBy": self.added_by,
                "addedAt": self.added_at,
                "source": self.source,
                "note": self.note,
            }
        )
        return out

    @classmethod
    def from_dict(cls, data: Any) -> Optional["CollaboratorRecord"]:
        """``data`` as a record, or ``None`` when it does not name a valid id.

        Fails closed on a hand-edited or corrupt entry, and on **every** part of
        one: a login that is not a login, a ``slack`` that is not a member id, or
        neither id at all, skips the whole entry rather than honouring the half
        that parsed (abuse case A11). What is refused grants nobody, rather than
        whatever the file happened to contain.
        """
        if not isinstance(data, dict):
            return None
        raw_login = str(data.get("login") or "").strip()
        raw_slack = str(data.get("slack") or "").strip()
        login = normalize_login(raw_login) if raw_login else ""
        slack = normalize_slack_id(raw_slack) if raw_slack else ""
        if (raw_login and not login) or (raw_slack and not slack):
            logger.warning(
                "skipping a collaborator entry whose %s is not one: %r",
                "login" if raw_login and not login else "slack id",
                raw_login if raw_login and not login else raw_slack,
            )
            return None
        if not login and not slack:
            logger.warning("skipping a collaborator entry that names no id at all")
            return None
        return cls(
            login=login,
            slack=slack,
            added_by=str(data.get("addedBy") or ""),
            added_at=str(data.get("addedAt") or ""),
            source=str(data.get("source") or "comment"),
            note=str(data.get("note") or ""),
        )


def _as_ref(work_item: Union[str, WorkItemRef]) -> WorkItemRef:
    if isinstance(work_item, WorkItemRef):
        return work_item
    return WorkItemRef.parse(work_item)


def _validated(login: str, slack: str) -> Tuple[str, str]:
    """``(login, slack)`` canonicalised, or :class:`ValueError` — at least one."""
    canonical_login = normalize_login(login) if login else ""
    if login and not canonical_login:
        raise ValueError(f"not a GitHub login: {login!r}")
    canonical_slack = normalize_slack_id(slack) if slack else ""
    if slack and not canonical_slack:
        raise ValueError(
            f"not a Slack member id: {slack!r} (expected U… or W…; a handle must be "
            "resolved to its id first)"
        )
    if not canonical_login and not canonical_slack:
        raise ValueError("a collaborator needs a GitHub login or a Slack member id")
    return canonical_login, canonical_slack


def _same_person(a: CollaboratorRecord, b: CollaboratorRecord) -> bool:
    """Whether two entries share an id — the roster's identity rule."""
    return bool((a.login and a.login == b.login) or (a.slack and a.slack == b.slack))


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
            if any(_same_person(existing, record) for existing in out):
                # One entry per id: a hand-edited file naming an id twice is read
                # as its FIRST entry, so the answer is at least deterministic.
                continue
            out.append(record)
        return out

    def logins(self, work_item: Union[str, WorkItemRef]) -> List[str]:
        """Just the logins, for the membership tests below (Slack-only entries have
        none and are not here)."""
        return [record.login for record in self.list(work_item) if record.login]

    def slack_ids(self, work_item: Union[str, WorkItemRef]) -> List[str]:
        """Just the Slack member ids — what the Slack ingress matches a message's
        ``user`` against (issue-389 R7.2). Login-only entries are not here."""
        return [record.slack for record in self.list(work_item) if record.slack]

    def add(
        self,
        work_item: Union[str, WorkItemRef],
        login: str = "",
        slack: str = "",
        actor: str = "",
        source: str = "comment",
        note: str = "",
    ) -> bool:
        """Grant ``login`` and/or ``slack`` on ``work_item``. False when nothing changed.

        At least one id. The roster dedupes on **either**: an entry that already
        carries the login or the id is "already granted", and when the call names a
        second id that entry lacks, the id is merged onto it (one person, one entry)
        with the original provenance kept — a change, so True. A second id that a
        *different* person's entry already holds is refused, not reassigned.

        Raises :class:`ValueError` for anything that is not a GitHub login or a Slack
        member id, and for a call naming neither: a caller that has not validated its
        input must not be able to write one. A handle is not an id; resolve it first.
        """
        canonical_login, canonical_slack = _validated(login, slack)
        item = _as_ref(work_item)
        current = self.list(item)
        stamp = CollaboratorRecord(
            login=canonical_login,
            slack=canonical_slack,
            added_by=actor,
            added_at=_utcnow(),
            source=source,
            note=note,
        )
        matches = [record for record in current if _same_person(record, stamp)]
        if not matches:
            current.append(stamp)
            self._write(item, current)
            logger.info(
                "granted %s collaborator status on %s (source=%s, by=%s)",
                stamp.label,
                item.ref,
                source,
                actor or "(unknown)",
            )
            return True
        for record in matches:
            if (
                canonical_login and record.login and record.login != canonical_login
            ) or (canonical_slack and record.slack and record.slack != canonical_slack):
                raise ValueError(
                    f"{stamp.label} conflicts with the existing collaborator "
                    f"{record.label} on {item.ref}; remove one of them first"
                )
        first = matches[0]
        merged = CollaboratorRecord(
            login=first.login or canonical_login,
            slack=first.slack or canonical_slack,
            added_by=first.added_by,
            added_at=first.added_at,
            source=first.source,
            note=first.note,
        )
        if merged == first and len(matches) == 1:
            return False
        remaining = [
            merged if record is first else record
            for record in current
            if record is first or record not in matches
        ]
        self._write(item, remaining)
        logger.info(
            "merged %s onto %s's collaborator entry on %s (source=%s, by=%s)",
            stamp.label,
            first.label,
            item.ref,
            source,
            actor or "(unknown)",
        )
        return True

    def remove(
        self, work_item: Union[str, WorkItemRef], login: str = "", slack: str = ""
    ) -> bool:
        """Revoke on ``work_item`` by either id. False when nothing was granted.

        An entry matching **any** id given is removed whole — a revocation names a
        person, and a person known by two ids is one person.
        """
        canonical_login, canonical_slack = _validated(login, slack)
        item = _as_ref(work_item)
        current = self.list(item)
        probe = CollaboratorRecord(login=canonical_login, slack=canonical_slack)
        remaining = [record for record in current if not _same_person(record, probe)]
        if len(remaining) == len(current):
            return False
        self._write(item, remaining)
        logger.info("revoked %s's collaborator status on %s", probe.label, item.ref)
        return True

    def is_collaborator_slack(
        self, actor_slack_id: Optional[str], work_item: Union[str, WorkItemRef]
    ) -> bool:
        """Whether the Slack member ``actor_slack_id`` is granted on this one work item.

        The Slack ingress's question (issue-389 §5), answered about ids only: a
        handle, a display name or nothing at all is never a collaborator, for the
        reason :meth:`is_collaborator` gives — a grant is about a person, and the
        id on the event is the only thing that names one.
        """
        canonical = normalize_slack_id(actor_slack_id)
        if not canonical:
            return False
        return canonical in self.slack_ids(work_item)

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
