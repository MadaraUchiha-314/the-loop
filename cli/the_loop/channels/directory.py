"""Slack names, resolved to ids — the directory (issue-375, PR #376 review).

Slack's API takes **ids**: ``chat.postMessage`` wants ``C0123ABCD``, and a member
is ``U0456GHIJ``. People do not. They know the room as ``#tmp-issue-375`` and the
person as ``@dana``, and every place the-loop asked for an id — the collaboration
channel, ``channels.slack.channel``, ``routing.authorizedUsers[].slack`` — asked
them to go and look one up.

This module is the translation layer, and its whole design is one decision:
**resolve once, at the edge, and route on ids.** A name is accepted wherever a
human types one, turned into an id as early as the code can, and never compared
in the hot path — so a rename, an outage or a rate limit can delay a declaration
but can never mis-deliver a message.

## What it costs, and why it is cached

``conversations.list`` and ``users.list`` are Tier-2 methods (about 20 calls a
minute) and paginate the whole workspace. Calling either per message would be
absurd, so the maps live in a JSON file under ``<state.root>/local/`` shared by
every process on this machine, refreshed when a lookup misses and at most once
per :data:`TTL_SECONDS`. A miss on a fresh map is a real "no such name", not a
stale cache, which is what lets a refusal be trusted.

The cache is **local, not portable**: it is a snapshot of one workspace as one
machine last read it, derivable from Slack at any time, and a stale copy carried
elsewhere would answer for a workspace it never read.

## Fail closed, in both directions

Every failure — no token, a transport error, a missing scope, an unknown name,
a name matching nothing — resolves to ``""``. A caller that cannot resolve a
name refuses the thing it was about to do rather than falling back to a default:
a declaration is refused, a post raises, and an allow-list entry matches nobody.
The one asymmetry worth stating is the allow-list's, and it is the safe one: an
unresolvable entry authorizes **fewer** people, never more.

## The caveat this module cannot fix

A conversation id is immutable; a channel name and a member handle are not. An
allow-list entry naming ``@dana`` authorizes *whoever holds that handle now* —
so if dana renames or leaves and somebody else takes it, that person inherits
the grant. The-loop resolves and warns (:meth:`SlackDirectory.user_id` logs when
a handle it had cached now points elsewhere), but the only way to be immune is
to declare the member id. The operator's own documentation says so where the key
is documented; this note is here so nobody has to rediscover it from the code.

A **display name** is worse again — not unique, and settable to anything by the
person themselves — so it is not indexed at all: only the handle resolves.

Spec: docs/specs/issue-375/design.md §8.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "CONVERSATIONS",
    "NAME_RE",
    "TTL_SECONDS",
    "USERS",
    "SlackDirectory",
    "is_conversation_id",
    "is_member_id",
    "normalize_name",
]

#: A Slack **conversation id**: ``C`` public, ``G`` private, ``D`` a direct
#: message. The same three prefixes :func:`the_loop.channels.slack.kinds_from_id`
#: recognises, and deliberately as loose about the rest: that function has read a
#: leading ``C`` as an id since issue-362, so anything it calls an id must stay
#: one here or a configuration that worked yesterday becomes a name lookup today.
#: What separates the two is **case** — Slack folds every channel name and handle
#: to lowercase, so a token with no lowercase letter in it is never a name. The
#: body therefore allows ``-`` and ``_`` as well as ``A-Z0-9``: a real id has
#: neither, but a deployment (or a fixture) that has always called something
#: ``C-OPS`` must keep being understood as naming an id.
_CONVERSATION_ID_RE = re.compile(r"^[CGD][A-Z0-9_-]{1,20}$")

#: A Slack **member id**: ``U`` an ordinary member, ``W`` an Enterprise Grid one.
_MEMBER_ID_RE = re.compile(r"^[UW][A-Z0-9_-]{1,20}$")

#: What a Slack **name** may be — a channel name or a member handle. Slack folds
#: both to lowercase and allows letters, digits, hyphens, underscores, periods
#: and non-ASCII letters; 80 characters is its own limit. Deliberately does NOT
#: match an id's shape, so :func:`normalize_name` and the id checks can never
#: both claim one token.
NAME_RE = re.compile(r"^[^\s@#/\\]{1,80}$")

#: The two maps this directory keeps, and the API method that fills each.
CONVERSATIONS = "conversations"
USERS = "users"

#: How long a map is trusted before a miss refreshes it. An hour is the balance
#: the rate limits force: long enough that a busy daemon reads Slack twice a day,
#: short enough that a channel created this morning is findable this afternoon.
#: A **hit** is served from a map of any age; only a miss pays for a refresh.
TTL_SECONDS = 3600


def is_conversation_id(value: str) -> bool:
    """Whether ``value`` is already a conversation id (no lookup needed)."""
    return bool(_CONVERSATION_ID_RE.match(str(value or "").strip()))


def is_member_id(value: str) -> bool:
    """Whether ``value`` is already a member id (no lookup needed)."""
    return bool(_MEMBER_ID_RE.match(str(value or "").strip()))


def normalize_name(raw: object) -> str:
    """``raw`` as a Slack name — ``#room`` and ``@dana`` lose their sigil.

    Returns ``""`` for anything that is not a name, **including an id**: an id is
    not a name, and a caller that mixes the two would look up ``C0123ABCD`` in a
    map of channel names and get a confident, wrong "no such channel".
    """
    text = str(raw or "").strip().lstrip("#@")
    # The id checks run on the text **as given**, before it is folded: an id is
    # uppercase and a name is not, so upper-casing first would read `dana` as the
    # conversation id `DANA` and answer "that is not a name" about a person.
    if not text or is_conversation_id(text) or is_member_id(text):
        return ""
    lowered = text.lower()
    return lowered if NAME_RE.match(lowered) else ""


def _now() -> float:
    return time.time()


class SlackDirectory:
    """``name -> id`` for one workspace, cached on this machine.

    Constructed per call site rather than shared: it holds no connection, the
    file is the state, and two instances racing to refresh cost one extra API
    call and converge on the same answer.
    """

    def __init__(
        self,
        cli_config: Optional[Mapping[str, Any]] = None,
        client_factory: Optional[Callable[[str], Any]] = None,
        path: Optional[Path] = None,
        token_env: str = "",
    ):
        self.cli_config = dict(cli_config or {})
        self._client_factory = client_factory
        self.path = Path(path) if path else self._default_path()
        #: Which environment variable holds the bot token. Passed explicitly by a
        #: caller that already parsed the channel config (the bot), so a directory
        #: built beside a channel never re-parses one to learn the same fact.
        self.token_env = token_env
        self._client: Any = None

    @classmethod
    def beside(
        cls,
        state_path: Any,
        token_env: str = "",
        client_factory: Optional[Callable[[str], Any]] = None,
    ) -> "SlackDirectory":
        """The directory sharing a root with ``<root>/channels/slack.json``.

        The layout is one root with three directories (decision-046), so the
        channel file's grandparent *is* that root — the derivation
        :meth:`the_loop.channels.state.ChannelStores.beside` already makes, for
        the same reason: a caller that has a channel has everything the cache
        needs, and should not have to carry a config to prove it.
        """
        root = Path(state_path).parent.parent
        return cls(
            path=root / "local" / "slack-directory.json",
            token_env=token_env,
            client_factory=client_factory,
        )

    # -- the two public lookups --------------------------------------------------

    def conversation_id(self, value: str) -> str:
        """``value`` as a conversation id — itself when it already is one.

        ``""`` when it is neither an id nor a name this workspace has, which is
        every caller's signal to refuse rather than to guess.
        """
        text = str(value or "").strip()
        if is_conversation_id(text):
            return text
        name = normalize_name(text)
        if not name:
            return ""
        return self._lookup(CONVERSATIONS, name)

    def user_id(self, value: str) -> str:
        """``value`` as a member id — itself when it already is one.

        Logs a **warning** when a handle this machine had cached now resolves to
        a different member: that is the allow-list hole this module's docstring
        names, and the one thing the-loop can do about it is refuse to let it
        happen quietly. Reached because this lookup — unlike the conversation
        one — re-reads a stale map even on a hit (see :meth:`_lookup`).
        """
        text = str(value or "").strip()
        if is_member_id(text):
            return text
        name = normalize_name(text)
        if not name:
            return ""
        cached = self._cached(USERS).get(name, "")
        resolved = self._lookup(USERS, name, follow=True)
        if cached and resolved and cached != resolved:
            logger.warning(
                "the Slack handle @%s now resolves to %s, not %s — a handle can "
                "change hands, so an allow-list entry naming one follows it. "
                "Declare the member id in routing.authorizedUsers to pin it.",
                name,
                resolved,
                cached,
            )
        return resolved

    # -- the map ------------------------------------------------------------------

    def _lookup(self, kind: str, name: str, follow: bool = False) -> str:
        """``name`` in ``kind``'s map, refreshing once when it is not there.

        A hit is served from a map of any age — a name that resolved yesterday
        resolves today without a call. Only a **miss** pays for a refresh, and
        only one per :data:`TTL_SECONDS`, so a typo in a config file cannot turn
        every message into an API call.

        ``follow`` re-reads a **stale** map even on a hit, which only
        :meth:`user_id` asks for. The two lookups want opposite things from a
        stale answer: a conversation id is stable, so a cached one is simply
        right; a handle can move, and an allow-list that never re-read would
        freeze on whatever the workspace said the first time this machine asked.
        Following costs at most one listing per :data:`TTL_SECONDS`.
        """
        cached = self._cached(kind)
        stale = self._stale(kind)
        if name in cached and not (follow and stale):
            return cached[name]
        if not stale:
            return cached.get(name, "")
        fresh = self._refresh(kind)
        if not fresh:  # the read failed; the cache is still the best answer
            return cached.get(name, "")
        return fresh.get(name, "")

    def _refresh(self, kind: str) -> Dict[str, str]:
        """Re-read ``kind`` from Slack and save it. ``{}`` on any failure."""
        client = self._connect()
        if client is None:
            return {}
        try:
            found = (
                self._read_conversations(client)
                if kind == CONVERSATIONS
                else self._read_users(client)
            )
        except Exception as exc:  # noqa: BLE001 — a directory read never raises
            logger.warning(
                "slack: could not read the %s directory (%s); names cannot be "
                "resolved until this succeeds — is the app missing a scope? "
                "(channels:read / groups:read for channels, users:read for people)",
                kind,
                exc,
            )
            return {}
        self._save(kind, found)
        logger.info("slack: read %d %s for name resolution", len(found), kind)
        return found

    def _read_conversations(self, client) -> Dict[str, str]:
        """``{name: id}`` for every channel the workspace has (paginated).

        Both kinds in one call: a private channel is as declarable as a public
        one, and asking for them separately would double the rate-limit cost to
        answer the same question.
        """
        found: Dict[str, str] = {}
        cursor = ""
        for _ in range(_MAX_PAGES):
            response = client.conversations_list(
                types="public_channel,private_channel",
                exclude_archived=True,
                limit=1000,
                cursor=cursor or None,
            )
            for entry in response.get("channels") or []:
                name = normalize_name(entry.get("name"))
                ident = str(entry.get("id") or "")
                if name and ident and name not in found:
                    found[name] = ident
            cursor = str(
                (response.get("response_metadata") or {}).get("next_cursor") or ""
            )
            if not cursor:
                break
        return found

    def _read_users(self, client) -> Dict[str, str]:
        """``{handle: id}`` for every member (paginated).

        The **handle** (``name``) only — deliberately not the display name. Slack
        guarantees a handle is unique in the workspace and it is what ``@dana``
        addresses; a display name is neither unique nor constrained, and
        ``routing.authorizedUsers`` has warned against it in as many words since
        issue-309 ("never a display name — names are attacker-chosen"). Widening
        the allow-list to a field anyone can set to anything is not what accepting
        handles was asked for, so a display name resolves to nothing at all.
        """
        found: Dict[str, str] = {}
        cursor = ""
        for _ in range(_MAX_PAGES):
            response = client.users_list(limit=200, cursor=cursor or None)
            for entry in response.get("members") or []:
                if entry.get("deleted"):
                    continue
                ident = str(entry.get("id") or "")
                handle = normalize_name(entry.get("name"))
                if handle and ident and handle not in found:
                    found[handle] = ident
            cursor = str(
                (response.get("response_metadata") or {}).get("next_cursor") or ""
            )
            if not cursor:
                break
        return found

    # -- the cache file -------------------------------------------------------------

    def _default_path(self) -> Path:
        from ..state import layout_from_config

        try:
            root = Path(layout_from_config(self.cli_config).local_dir)
        except Exception:  # noqa: BLE001 — a test with no config still resolves ids
            root = Path(".the-loop") / "local"
        return root / "slack-directory.json"

    def _read_file(self) -> Dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _cached(self, kind: str) -> Dict[str, str]:
        entry = self._read_file().get(kind)
        if not isinstance(entry, dict):
            return {}
        names = entry.get("names")
        if not isinstance(names, dict):
            return {}
        return {str(k): str(v) for k, v in names.items()}

    def _stale(self, kind: str) -> bool:
        entry = self._read_file().get(kind)
        if not isinstance(entry, dict):
            return True
        try:
            return _now() - float(entry.get("fetchedAt") or 0) >= TTL_SECONDS
        except (TypeError, ValueError):
            return True

    def _save(self, kind: str, names: Mapping[str, str]) -> None:
        """Replace ``kind``'s map, keeping the other's. Best-effort.

        Read-modify-write on one small file, atomically: the two maps refresh
        independently and a conversations read must not drop the users map that
        another process wrote a moment earlier.
        """
        payload = self._read_file()
        payload[kind] = {
            "names": {str(k): str(v) for k, v in names.items()},
            "fetchedAt": _now(),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(tmp, self.path)
        except OSError as exc:
            logger.debug("slack: could not save the directory cache: %s", exc)

    # -- the client -----------------------------------------------------------------

    def _connect(self):
        """The Slack client, or ``None`` when there is no token or no SDK.

        Built at most once per instance and never raised from: a directory that
        cannot connect answers ``""``, which every caller already handles.
        """
        if self._client is not None:
            return self._client
        try:
            from .slack import SlackChannelConfig, build_client

            env = (
                self.token_env
                or SlackChannelConfig.from_mapping(self.cli_config).bot_token_env
            )
            token = os.environ.get(env, "")
            if not token:
                logger.debug("slack: no bot token (%s); names cannot be resolved", env)
                return None
            factory = self._client_factory or build_client
            self._client = factory(token)
        except Exception as exc:  # noqa: BLE001
            logger.warning("slack: could not build a client for name lookup: %s", exc)
            return None
        return self._client


#: How many pages of a listing to walk before giving up. A thousand channels a
#: page and two hundred members a page, twenty pages: far past any workspace this
#: is used in, and a bound so a malformed cursor cannot spin forever.
_MAX_PAGES = 20
