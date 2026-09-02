"""Identity in one place — who may direct the-loop, on every channel (issue-309).

Until issue-309 the daemon kept two allow-lists in two blocks: ``routing.authorizedUsers``
(GitHub logins, the prompt-injection guard since issue-63) and
``channels.slack.authorizedUsers`` (Slack member ids, the reply guard since issue-245).
The owner's call on the ticket: *"we should specify authorized users in one place and have
channel specific details in that same blob and not distributed across."*

So ``routing.authorizedUsers`` stays the one list, and each entry is one **person**:

.. code-block:: yaml

    routing:
      authorizedUsers:
        - MadaraUchiha-314              # a bare string is a GitHub login — the ledger's identity
        - github: jc1993                # one person, their id on every channel they act on
          slack: U0456GHIJKL
          name: John                    # optional, for logs and `channels status`

A :class:`Principal` is that entry parsed: a mapping of channel name → native id. Every
consumer reads the ids of *its own* channel through :func:`ids_for` — the router, the
poller, the dispatcher's control seam and the graph's human gates keep reading exactly
the GitHub logins (:func:`github_logins`), and the Slack pipeline reads the Slack ids —
so nothing widens: an entry naming no ``github`` id is a person who may act on the
channels they are named on and on nothing that reads GitHub logins.

Comparison is exact-match on every channel, as it has always been for GitHub logins.
Empty stays fail-closed everywhere: an empty list authorizes nobody on any channel.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

logger = logging.getLogger("the-loop.identity")

__all__ = [
    "LEDGER_CHANNEL",
    "Principal",
    "github_logins",
    "ids_for",
    "parse_authorized_users",
    "principal_for",
]

#: The channel a bare string entry names. GitHub is the ledger (decision-103 D8), and a
#: login is what ``routing.authorizedUsers`` has meant since issue-63.
LEDGER_CHANNEL = "github"

#: The one key of an entry that is not a channel name.
_NAME_KEY = "name"


@dataclass(frozen=True)
class Principal:
    """One person, as the config declares them: a native id per channel."""

    ids: Mapping[str, str] = field(default_factory=dict)
    name: str = ""

    def id_on(self, channel: str) -> str:
        """This person's id on ``channel`` — ``""`` when they are not named there."""
        return str(self.ids.get(channel) or "")

    @property
    def label(self) -> str:
        """A short human label: the name, else the GitHub login, else any id."""
        if self.name:
            return self.name
        if self.ids.get(LEDGER_CHANNEL):
            return str(self.ids[LEDGER_CHANNEL])
        for channel, native in self.ids.items():
            return f"{channel}:{native}"
        return "(nobody)"

    def to_dict(self) -> Dict[str, str]:
        """The envelope's ``actor`` object: every declared id, channel-keyed."""
        return {str(k): str(v) for k, v in self.ids.items() if v}


def parse_authorized_users(raw: Any) -> List[Principal]:
    """The ``routing.authorizedUsers`` list as principals.

    A bare string is a GitHub login. A mapping's keys are channel names and its values
    that channel's native id (``name`` is the one non-channel key). Anything else — a
    number, a list, a mapping with no usable id — is **dropped with a warning**, never
    coerced: an entry the operator wrote and the daemon could not read must be said out
    loud, but it must not authorize anyone by accident either.
    """
    principals: List[Principal] = []
    if raw is None:
        return principals
    if isinstance(raw, (str, Mapping)) or not isinstance(raw, Iterable):
        logger.warning(
            "routing.authorizedUsers is %r, not a list — nobody is authorized",
            type(raw).__name__,
        )
        return principals
    for index, entry in enumerate(raw):
        if isinstance(entry, str):
            if entry.strip():
                principals.append(Principal(ids={LEDGER_CHANNEL: entry.strip()}))
            continue
        if isinstance(entry, Mapping):
            ids: Dict[str, str] = {}
            name = ""
            for key, value in entry.items():
                key_s = str(key).strip()
                if key_s == _NAME_KEY:
                    name = str(value or "").strip()
                    continue
                if not key_s or value is None or isinstance(value, (list, dict)):
                    logger.warning(
                        "routing.authorizedUsers[%d].%s is not a channel id — ignored",
                        index,
                        key_s or "?",
                    )
                    continue
                value_s = str(value).strip()
                if value_s:
                    ids[key_s] = value_s
            if ids:
                principals.append(Principal(ids=ids, name=name))
            else:
                logger.warning(
                    "routing.authorizedUsers[%d] names no channel id — dropped "
                    "(an entry is a GitHub login, or a mapping of channel → id)",
                    index,
                )
            continue
        logger.warning(
            "routing.authorizedUsers[%d] is %r — dropped (an entry is a GitHub "
            "login, or a mapping of channel → id)",
            index,
            type(entry).__name__,
        )
    return principals


def ids_for(principals: Sequence[Principal], channel: str) -> List[str]:
    """Every id declared on ``channel``, in config order, without duplicates."""
    seen: List[str] = []
    for principal in principals:
        native = principal.id_on(channel)
        if native and native not in seen:
            seen.append(native)
    return seen


def github_logins(principals: Sequence[Principal]) -> List[str]:
    """What every GitHub-login consumer reads: :func:`ids_for` on the ledger channel."""
    return ids_for(principals, LEDGER_CHANNEL)


def principal_for(
    principals: Sequence[Principal], channel: str, native_id: str
) -> Optional[Principal]:
    """The person declared with ``native_id`` on ``channel`` — or ``None``.

    Resolved from the **config**, never from a message: this is how the ledger's record
    of a channel event names a person rather than whatever the message claimed.
    """
    if not native_id:
        return None
    for principal in principals:
        if principal.id_on(channel) == native_id:
            return principal
    return None
