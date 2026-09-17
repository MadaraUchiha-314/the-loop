"""Collaboration channels — the room a work item is worked in (issue-375).

``channels.slack.channel`` is the operator's **one** channel: every work item this
deployment touches gets a thread in it, and everybody who wants to follow one work
item has to follow all of them. That is the right shape for a small team and the
wrong shape for the work item people spin a room up for — the migration with six
stakeholders, the incident with a ``#tmp-…`` channel and a dozen watchers.

A **collaboration channel** is a channel an authorized user declares on **one** work
item. Two things follow from the declaration, and only these two:

* the work item's conversation lives **there** — the thread root is opened in the
  declared channel instead of the operator's central one, so every update the-loop
  posts about that item lands in the room the people are in;
* every message in that channel is **about that work item**. A top-level message is
  a reply on the item rather than a new issue, and a message in an unbound thread
  there is a reply too — because a dedicated room has one subject.

What it is *not* is a permission. The declaration moves a conversation; it grants
nobody anything. Who may speak is still ``channels.slack``'s principals allow-list,
who may direct the loop is still ``routing.authorizedUsers``, and who may be input
on one work item is still :mod:`the_loop.collaborators`' roster. A channel is a
place, not a person.

## The grammar

``<type>@<target>`` — ``slack@C0123ABCD`` — with ``<type>://<target>`` accepted as
the same declaration and canonicalised to the first form. The type is what makes
this extensible: adding Jira or WhatsApp later is a row in :data:`CHANNEL_TYPES`
and an adapter, not a new grammar. A type with no adapter on this deployment is
**refused at declaration time** rather than stored and silently ignored — a channel
that is declared and does nothing is worse than one that was never accepted.

The target is validated **per type**, and the whole of that validation is a regex:
nothing else from a comment body reaches the roster, a path, an argv or an API
call. Slack's is a conversation id (``C…``/``G…``/``D…``), the same thing
``channels.slack.channel`` requires and for the same reason — the bot's scopes
(``chat:write``, ``*:history``) do not include ``channels:read``, so the-loop
cannot turn ``#tmp-issue-375`` into an id and will not pretend to.

## One channel, one work item

A channel backs **at most one** work item. The reverse lookup is what the Slack
ingress reads to decide whose conversation a message in a room is, so two work
items in one room would make that answer a guess. :meth:`CollaborationChannelStore.
declared_by` refuses to guess: it returns a single ref or nothing, and
:meth:`add` refuses a channel another work item already declares.

## Where a declaration lives

The ``collaborationChannels`` section of the work item's portable record
(``<state.root>/portable/<slug>.json``), beside ``collaborators`` and for the same
reason (issue-128): "an authorized user declared this work item's room" is true on
any machine, so it travels with the work item rather than with the session handle.
It is deliberately **not** the ``channels`` section, which holds the conversation
the-loop *opened* (channel, thread, permalink): that one is written wholesale by
the channel state's own writer, and a declaration parked in it would be clobbered
by the next thread bind.

A declaration is cleared when the work item ends, exactly as the collaborator
roster is — the room outlives the item, the-loop's claim on it does not.

Spec: docs/specs/issue-375/design.md §1.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .sessions import WorkItemRef
from .state import LegacyLayout
from .workitem import COLLABORATION_CHANNELS, WorkItemStore

logger = logging.getLogger("the-loop.workchannels")

__all__ = [
    "CHANNEL_TYPES",
    "ChannelRef",
    "CollaborationChannel",
    "CollaborationChannelStore",
    "SLACK",
    "parse_channel_ref",
    "parse_channel_refs",
]

#: The one channel type the-loop can actually carry a conversation on today.
SLACK = "slack"

#: What a Slack target may be: a conversation id, as ``conversations.info`` and
#: ``chat.postMessage`` take it. ``C`` public, ``G`` private, ``D`` a direct
#: message — the same three prefixes :func:`the_loop.channels.slack.kinds_from_id`
#: recognises. A channel *name* is refused: the bot has no ``channels:read``
#: scope, so nothing here could resolve one, and accepting it would move the
#: failure to the first post.
_SLACK_TARGET_RE = re.compile(r"^[CGD][A-Z0-9]{2,20}$")

#: The declared types, each with the pattern its target must match and a line
#: saying what that target is when it does not. **The extension point**: a new
#: channel type is a row here plus an adapter that knows how to post on it.
CHANNEL_TYPES: Dict[str, Tuple[re.Pattern, str]] = {
    SLACK: (
        _SLACK_TARGET_RE,
        "a Slack conversation id — C… (public), G… (private) or D… (a direct "
        "message), which Slack shows under 'View channel details'. A channel "
        "NAME cannot be used: the-loop's bot has no `channels:read` scope to "
        "resolve one with, and `channels.slack.channel` takes an id for the "
        "same reason",
    ),
}

#: ``<type>@<target>`` or ``<type>://<target>``. The type is matched loosely here
#: — lowercase letters and digits — and then looked up in :data:`CHANNEL_TYPES`,
#: so an unknown type is refused with a message naming the known ones rather than
#: failing to parse at all. The target is matched loosely for the same reason:
#: a per-type refusal can say what that type's target looks like.
_REF_RE = re.compile(
    r"^(?P<type>[a-z][a-z0-9]{0,15})(?:@|://)(?P<target>[^\s@/]{1,64})$"
)

#: Trailing characters a ref collects from prose ("…in slack@C0123.") or markdown
#: ("`the-loop add-channel slack@C0123`"), none of which can appear in a target.
_TRAILING_PUNCTUATION = ".,;:!?)]}>\"'`"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class ChannelRef:
    """One channel, as a type and a target that is valid for it."""

    type: str
    target: str

    @property
    def ref(self) -> str:
        """The canonical spelling — what is stored, printed and compared."""
        return f"{self.type}@{self.target}"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.ref


def parse_channel_ref(raw: object) -> Optional[ChannelRef]:
    """``raw`` as a :class:`ChannelRef`, or ``None`` when it is not one.

    Total and side-effect free: every refusal is ``None``, never a cleaned-up
    guess and never a partial match. :func:`describe_refusal` turns the same
    input into the sentence a human is told, so the two cannot disagree about
    what was wrong.
    """
    text = str(raw or "").strip().rstrip(_TRAILING_PUNCTUATION)
    match = _REF_RE.match(text)
    if not match:
        return None
    kind = match.group("type")
    entry = CHANNEL_TYPES.get(kind)
    if entry is None:
        return None
    if not entry[0].match(match.group("target")):
        return None
    return ChannelRef(type=kind, target=match.group("target"))


def describe_refusal(raw: object) -> str:
    """Why ``raw`` is not a channel ref — the message a refusal carries.

    Three refusals, narrowest last: the shape, the type, the target. A caller
    prints this; nothing branches on it.
    """
    text = str(raw or "").strip().rstrip(_TRAILING_PUNCTUATION)
    known = ", ".join(sorted(CHANNEL_TYPES))
    match = _REF_RE.match(text)
    if not match:
        return (
            f"{text!r} is not a channel: expected <type>@<target> (or "
            f"<type>://<target>), e.g. slack@C0123ABCD. Known types: {known}"
        )
    kind = match.group("type")
    entry = CHANNEL_TYPES.get(kind)
    if entry is None:
        return (
            f"the-loop has no adapter for channel type {kind!r} on this "
            f"deployment; known types: {known}"
        )
    return (
        f"{match.group('target')!r} is not a valid {kind} target: expected {entry[1]}"
    )


def parse_channel_refs(text: str) -> List[ChannelRef]:
    """The run of channel refs at the head of ``text``, canonicalised.

    Scanning stops at the first token that is not one, so
    ``slack@C0123 please watch this`` yields the channel and the prose reaches
    nothing — the rule :func:`the_loop.collaborators.parse_logins` follows, for
    the same reason. Order is preserved and duplicates are dropped.
    """
    out: List[ChannelRef] = []
    for token in re.split(r"[\s,]+", str(text or "").strip()):
        channel = parse_channel_ref(token)
        if channel is None:
            break
        if channel not in out:
            out.append(channel)
    return out


@dataclass(frozen=True)
class CollaborationChannel:
    """One declaration: which channel, declared by whom, when, through which surface."""

    type: str
    target: str
    added_by: str = ""
    added_at: str = ""
    source: str = "comment"  # comment | cli
    note: str = ""  # the declaring comment's url, when there is one

    @property
    def ref(self) -> str:
        return f"{self.type}@{self.target}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ref": self.ref,
            "type": self.type,
            "target": self.target,
            "addedBy": self.added_by,
            "addedAt": self.added_at,
            "source": self.source,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["CollaborationChannel"]:
        """``data`` as a record, or ``None`` when it does not name a valid channel.

        Fails closed on a hand-edited or corrupt entry, and re-validates the
        stored ``ref`` rather than trusting ``type``/``target`` beside it: what
        the ingress routes on is the parsed value, so an entry that would not be
        accepted today is not honoured today.
        """
        if not isinstance(data, dict):
            return None
        channel = parse_channel_ref(data.get("ref"))
        if channel is None:
            return None
        return cls(
            type=channel.type,
            target=channel.target,
            added_by=str(data.get("addedBy") or ""),
            added_at=str(data.get("addedAt") or ""),
            source=str(data.get("source") or "comment"),
            note=str(data.get("note") or ""),
        )


class ChannelTakenError(ValueError):
    """A channel another work item already declares (R3.4).

    A subclass of ``ValueError`` so every caller that already refuses a malformed
    declaration refuses this one too, and carries ``work_item`` so the refusal can
    name who holds the room.
    """

    def __init__(self, channel: ChannelRef, work_item: str):
        super().__init__(
            f"{channel.ref} is already the collaboration channel for {work_item}; "
            "one channel backs one work item, so declare a different channel or "
            "remove it there first"
        )
        self.channel = channel
        self.work_item = work_item


def _as_ref(work_item: Union[str, WorkItemRef]) -> WorkItemRef:
    if isinstance(work_item, WorkItemRef):
        return work_item
    return WorkItemRef.parse(work_item)


class CollaborationChannelStore:
    """The ``collaborationChannels`` section of each work item's portable record.

    Constructed exactly as :class:`the_loop.collaborators.CollaboratorStore` is,
    over the same directory, so the daemons, the CLI and the Slack ingress read one
    set of declarations from one place. A store whose directory cannot be read
    degrades to "nothing is declared" — fail closed, which here means the
    operator's central channel keeps carrying the conversation.
    """

    def __init__(self, root: Union[str, Path], legacy: Optional[LegacyLayout] = None):
        self.store = WorkItemStore(root, legacy=legacy)

    @property
    def root(self) -> Path:
        return self.store.root

    def list(self, work_item: Union[str, WorkItemRef]) -> List[CollaborationChannel]:
        """The work item's declared channels, in the order they were declared."""
        section = self.store.section(work_item, COLLABORATION_CHANNELS) or {}
        entries = section.get("channels") if isinstance(section, dict) else None
        out: List[CollaborationChannel] = []
        for entry in entries or []:
            record = CollaborationChannel.from_dict(entry)
            if record is None:
                logger.warning(
                    "skipping an unreadable channel declaration for %s", work_item
                )
                continue
            if any(existing.type == record.type for existing in out):
                # One channel per type is the invariant `add` maintains; a record
                # that somehow carries two is read as its FIRST, so the answer is
                # at least deterministic while an operator fixes the file.
                continue
            out.append(record)
        return out

    def for_type(
        self, work_item: Union[str, WorkItemRef], channel_type: str = SLACK
    ) -> Optional[CollaborationChannel]:
        """This work item's declared channel of ``channel_type``, or ``None``.

        What the outbound side asks: *where does this work item's conversation
        live?* ``None`` means the operator's central channel, which is what every
        work item had before this existed.
        """
        for record in self.list(work_item):
            if record.type == channel_type:
                return record
        return None

    def declared_by(self, channel: Union[str, ChannelRef]) -> str:
        """The ref of the work item that declared ``channel`` — ``""`` for none.

        The reverse lookup the Slack ingress reads, and the one place the
        one-channel-one-work-item invariant is *enforced at read time*: two
        records naming one channel answer ``""`` (and log), so a message in a
        contested room is left unattributed rather than delivered to whichever
        record sorted first.
        """
        target = (
            channel if isinstance(channel, ChannelRef) else parse_channel_ref(channel)
        )
        if target is None:
            return ""
        found = [ref for ref, _ in self._declarations(target)]
        if len(found) > 1:
            logger.warning(
                "%s is declared by more than one work item (%s); no message there "
                "is attributed until that is resolved",
                target.ref,
                ", ".join(sorted(found)),
            )
            return ""
        return found[0] if found else ""

    def _declarations(
        self, channel: ChannelRef
    ) -> List[Tuple[str, CollaborationChannel]]:
        """Every ``(work item ref, record)`` naming ``channel``, across the store."""
        out: List[Tuple[str, CollaborationChannel]] = []
        try:
            refs = self.store.refs()
        except (OSError, ValueError) as exc:
            logger.warning("could not read the channel declarations: %s", exc)
            return out
        for ref in refs:
            try:
                records = self.list(ref)
            except ValueError:  # an unparsable ref declares nothing
                continue
            for record in records:
                if record.type == channel.type and record.target == channel.target:
                    out.append((ref, record))
        return out

    def targets(self, channel_type: str = SLACK) -> Dict[str, str]:
        """``{target: work item ref}`` for every declared channel of one type.

        What the poll transport reads: the rooms it has to look in beyond the
        operator's own. A contested target is left out entirely, the same answer
        :meth:`declared_by` gives for it.
        """
        found: Dict[str, List[str]] = {}
        try:
            refs = self.store.refs()
        except (OSError, ValueError) as exc:
            logger.warning("could not read the channel declarations: %s", exc)
            return {}
        for ref in refs:
            try:
                records = self.list(ref)
            except ValueError:
                continue
            for record in records:
                if record.type == channel_type:
                    found.setdefault(record.target, []).append(ref)
        return {
            target: owners[0] for target, owners in found.items() if len(owners) == 1
        }

    def add(
        self,
        work_item: Union[str, WorkItemRef],
        channel: Union[str, ChannelRef],
        actor: str = "",
        source: str = "comment",
        note: str = "",
    ) -> Tuple[bool, Optional[CollaborationChannel]]:
        """Declare ``channel`` on ``work_item``.

        Returns ``(changed, replaced)``: ``changed`` is false when this exact
        channel was already declared, and ``replaced`` is the declaration of the
        same *type* this one displaced — one channel per type, so declaring a
        second Slack channel moves the room rather than adding one (R1.7).

        Raises :class:`ValueError` for anything that is not a channel ref, and
        :class:`ChannelTakenError` when another work item already declares it.
        """
        target = (
            channel if isinstance(channel, ChannelRef) else parse_channel_ref(channel)
        )
        if target is None:
            raise ValueError(describe_refusal(channel))
        item = _as_ref(work_item)
        holder = self.declared_by(target)
        if holder and holder != item.ref:
            raise ChannelTakenError(target, holder)
        current = self.list(item)
        if any(
            record.type == target.type and record.target == target.target
            for record in current
        ):
            return False, None
        replaced = next(
            (record for record in current if record.type == target.type), None
        )
        remaining = [record for record in current if record.type != target.type]
        remaining.append(
            CollaborationChannel(
                type=target.type,
                target=target.target,
                added_by=actor,
                added_at=_utcnow(),
                source=source,
                note=note,
            )
        )
        self._write(item, remaining)
        logger.info(
            "declared %s as %s's collaboration channel (source=%s, by=%s%s)",
            target.ref,
            item.ref,
            source,
            actor or "(unknown)",
            f", replacing {replaced.ref}" if replaced else "",
        )
        return True, replaced

    def remove(
        self, work_item: Union[str, WorkItemRef], channel: Union[str, ChannelRef]
    ) -> bool:
        """Undeclare ``channel`` on ``work_item``. False when it was not declared."""
        target = (
            channel if isinstance(channel, ChannelRef) else parse_channel_ref(channel)
        )
        if target is None:
            raise ValueError(describe_refusal(channel))
        item = _as_ref(work_item)
        current = self.list(item)
        remaining = [
            record
            for record in current
            if not (record.type == target.type and record.target == target.target)
        ]
        if len(remaining) == len(current):
            return False
        self._write(item, remaining)
        logger.info("%s is no longer %s's collaboration channel", target.ref, item.ref)
        return True

    def clear(self, work_item: Union[str, WorkItemRef]) -> bool:
        """Forget a work item's declarations (it ended). False if there were none."""
        if self.store.section(work_item, COLLABORATION_CHANNELS) is None:
            return False
        self.store.write_section(work_item, COLLABORATION_CHANNELS, None)
        return True

    def _write(
        self, item: WorkItemRef, records: Sequence[CollaborationChannel]
    ) -> None:
        payload = (
            {"channels": [record.to_dict() for record in records]} if records else None
        )
        self.store.write_section(item, COLLABORATION_CHANNELS, payload)
