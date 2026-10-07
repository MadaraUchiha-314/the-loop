"""Jira as a ledger and as a subscriber channel (issue-475, design §C7, R4.1, R4.2).

:class:`JiraLedger` records an event on a Jira work item's own ticket, as the
GitHub ledger records it on an issue. It writes the **same body** —
:func:`~the_loop.channels.bodies.ledger_body` picks the shape by event type for
both trackers — and then does the two things only Jira needs: the body carries
the visible Jira self-marker (:func:`~the_loop.authz.mark_self_authored_on_jira`;
the GitHub HTML marker does not survive ADF), and it is converted to ADF or wiki
markup by :class:`~the_loop.jiraapi.JiraClient` (``jiraformat``).

``work-item.create`` with ``channels.ledger: jira`` opens a ticket in the
project the event names (``detail["project"]``), which must be one with a
``repository`` — a mirror-only project is never a work-item source.

Every write goes through the one client, after :func:`~the_loop.jiraapi.
issue_key_for` has placed the ref on the configured site and a configured
project: nothing is sent for a ref that is not.

:class:`JiraChannel` mirrors a work item's progress into a Jira ticket the way
the Slack channel mirrors it into a room — the **room** being a Jira issue an
authorized user declared on the work item (``the-loop add-channel
jira@OPS-12``, issue-375's grammar). It honours ``channels.jira.subscribe`` and
``verbosity`` and differs from Slack in two deliberate ways:

* **no central fallback** — a work item with no declared ``jira@`` room is not
  mirrored (:meth:`JiraChannel.addresses` says so, and the bus skips it);
* **output only** — it is not :class:`~the_loop.channels.base.Conversational`,
  holds no ``publish`` grant and reads nothing: a comment on the mirror ticket
  never reaches a session. Jira as an input is the separate path where the work
  item itself is a Jira ticket.

The room must be in a project listed under ``integrations.jira.projects`` —
with or without a ``repository`` — which is the allow-list of where the-loop may
write. A project without one is **mirror-only**: a room, never a work item.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from ..authz import mark_self_authored_on_jira
from ..jiraapi import JiraApiConfig, JiraApiError, JiraClient, issue_key_for
from ..jiralabels import JiraLabelError, jira_label
from .base import DEFAULT_EVENTS, VERBOSITIES, Event, PostResult, render
from .bodies import issue_body, issue_title, ledger_body

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "JIRA_ROOM",
    "JiraChannel",
    "JiraChannelConfig",
    "JiraLedger",
    "load_jira_channel",
    "origin_projects",
]

#: The collaboration-channel type a Jira room is declared as (``jira@KEY-n``).
JIRA_ROOM = "jira"


def origin_projects(cli_config: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    """``{project key: repository}`` for the projects that are work-item sources.

    A project listed under ``integrations.jira.projects`` without a
    ``repository`` is mirror-only (design §C7): a room, never a source.
    """
    integrations = dict(cli_config or {}).get("integrations") or {}
    jira = integrations.get("jira") if isinstance(integrations, Mapping) else None
    projects = jira.get("projects") if isinstance(jira, Mapping) else None
    out: Dict[str, str] = {}
    for key, entry in (projects if isinstance(projects, Mapping) else {}).items():
        repository = entry.get("repository") if isinstance(entry, Mapping) else None
        if isinstance(repository, str) and repository.strip():
            out[str(key)] = repository.strip()
    return out


class JiraLedger:
    """The ledger on Jira: comments on the work item's ticket, tickets too."""

    name = "jira"

    def __init__(
        self,
        cli_config: Optional[Mapping[str, Any]] = None,
        *,
        client: Optional[JiraClient] = None,
    ):
        self.cli_config: Dict[str, Any] = dict(cli_config or {})
        self.api = (
            client.config
            if client is not None
            else (JiraApiConfig.from_cli_config(self.cli_config))
        )
        self._client = client

    @property
    def client(self) -> JiraClient:
        return self._client or JiraClient.shared(self.api)

    def subscribes(self, event_type: str) -> bool:
        return False  # the ledger is written to, not subscribed

    def may_publish(self, event_type: str) -> bool:
        return False

    def post(self, event: Event) -> PostResult:
        return self.record(event)

    def _failed(self, error: str) -> PostResult:
        return PostResult(channel=self.name, ok=False, error=error)

    def record(self, event: Event) -> PostResult:
        if event.event_type == "work-item.create":
            return self._create(event)
        try:
            key = issue_key_for(event.work_item, self.api)
        except JiraApiError as exc:
            return self._failed(str(exc))
        body = mark_self_authored_on_jira(ledger_body(event, self.cli_config))
        try:
            comment = self.client.add_comment(key, body)
        except JiraApiError as exc:  # best-effort, like every ledger write
            return self._failed(str(exc))
        return PostResult(channel=self.name, ok=True, url=comment.url)

    def _create(self, event: Event) -> PostResult:
        project = str(event.detail.get("project") or "")
        if not project:
            return self._failed("kickoff-disabled: no Jira project")
        if project not in origin_projects(self.cli_config):
            return self._failed(
                f"Jira project {project} has no repository under "
                "integrations.jira.projects, so a ticket there cannot be a work item"
            )
        try:
            labels = [
                jira_label(label)
                for label in str(event.detail.get("labels") or "").split(",")
                if label.strip()
            ]
        except JiraLabelError as exc:
            return self._failed(str(exc))
        try:
            issue = self.client.create_issue(
                project, issue_title(event.text), issue_body(event), labels
            )
        except JiraApiError as exc:
            return self._failed(str(exc))
        return PostResult(
            channel=self.name,
            ok=True,
            url=issue.url,
            ref=f"jira:{self.api.site}/{issue.key}" if issue.key else "",
        )


# ---------------------------------------------------------------- the channel


@dataclass(frozen=True)
class JiraChannelConfig:
    """``channels.jira``: on/off, what it receives, how much it says. No
    ``publish``: the channel takes no input."""

    enabled: bool = False
    subscribe: Tuple[str, ...] = DEFAULT_EVENTS
    verbosity: str = "normal"

    @classmethod
    def from_mapping(
        cls, cli_config: Optional[Mapping[str, Any]]
    ) -> "JiraChannelConfig":
        """Parse the whole CLI config; a malformed section is disabled, loudly."""
        channels = dict(cli_config or {}).get("channels") or {}
        section = channels.get("jira") if isinstance(channels, Mapping) else None
        if section is None:
            return cls()
        if not isinstance(section, Mapping):
            logger.error(
                "channels.jira: the section is not a mapping — the channel is "
                "disabled (fail closed)"
            )
            return cls()
        if "publish" in section:
            # The schema refuses it; a hand-built mapping is told the same, and
            # the value is never honoured — this channel takes no input.
            logger.error(
                "channels.jira.publish is not an option: the Jira channel takes no "
                "input; the value is ignored"
            )
        verbosity = str(section.get("verbosity", "normal"))
        if verbosity not in VERBOSITIES:
            logger.warning(
                "channels.jira.verbosity %r is not one of %s — resolving to 'normal'",
                verbosity,
                "/".join(VERBOSITIES),
            )
            verbosity = "normal"
        return cls(
            enabled=section.get("enabled") is True,
            subscribe=_subscribe(section.get("subscribe")),
            verbosity=verbosity,
        )


def _subscribe(raw: Any) -> Tuple[str, ...]:
    if raw is None:
        return DEFAULT_EVENTS
    if not isinstance(raw, (list, tuple)):
        logger.warning(
            "channels.jira.subscribe is not a list — using the default %s",
            list(DEFAULT_EVENTS),
        )
        return DEFAULT_EVENTS
    from .events import SUBSCRIBABLE_EVENTS

    events = tuple(str(e) for e in raw)
    unknown = [e for e in events if e not in SUBSCRIBABLE_EVENTS]
    if unknown:
        logger.warning(
            "channels.jira.subscribe names %s, not in the subscribable-event catalog "
            "— kept, but nothing shipped broadcasts them",
            ", ".join(repr(e) for e in unknown),
        )
    return events


class JiraChannel:
    """A subscriber channel whose room is a declared Jira issue. Output only."""

    name = "jira"

    def __init__(
        self,
        config: JiraChannelConfig,
        cli_config: Optional[Mapping[str, Any]] = None,
        *,
        client: Optional[JiraClient] = None,
        store: Optional[Any] = None,
    ):
        self.config = config
        self.cli_config: Dict[str, Any] = dict(cli_config or {})
        self.api = (
            client.config
            if client is not None
            else (JiraApiConfig.from_cli_config(self.cli_config))
        )
        self._client = client
        self._store = store

    @property
    def client(self) -> JiraClient:
        return self._client or JiraClient.shared(self.api)

    @property
    def store(self) -> Any:
        if self._store is None:
            from ..state import layout_from_config, legacy_layout
            from ..workchannels import CollaborationChannelStore

            layout = layout_from_config(self.cli_config)
            self._store = CollaborationChannelStore(
                layout.portable_dir, legacy=legacy_layout(layout)
            )
        return self._store

    def subscribes(self, event_type: str) -> bool:
        return event_type in self.config.subscribe

    def may_publish(self, event_type: str) -> bool:
        return False  # output only: nothing typed on a mirror ticket is input

    def room_for(self, work_item: str) -> str:
        """The issue key of ``work_item``'s declared ``jira@`` room, or ``""``."""
        if not work_item:
            return ""
        try:
            record = self.store.for_type(work_item, JIRA_ROOM)
        except (OSError, ValueError) as exc:
            logger.debug("could not read %s's jira room: %s", work_item, exc)
            return ""
        return record.target if record is not None else ""

    def addresses(self, event: Event) -> bool:
        """Whether this channel has anywhere to put ``event`` — a declared room.

        No central fallback (design §C7): the bus skips the channel for a work
        item with no room, so that is neither a post nor a failure.
        """
        return bool(self.room_for(event.work_item))

    def post(self, event: Event) -> PostResult:
        key = self.room_for(event.work_item)
        if not key:
            return PostResult(
                channel=self.name,
                ok=False,
                error=f"{event.work_item or 'the event'} has no jira@ room declared",
            )
        project = key.rsplit("-", 1)[0]
        if project not in self.api.projects:
            return PostResult(
                channel=self.name,
                ok=False,
                error=f"jira@{key}: project {project} is not configured under "
                "integrations.jira.projects; nothing was sent",
            )
        body = mark_self_authored_on_jira(render(event, self.config.verbosity))
        try:
            comment = self.client.add_comment(key, body)
        except JiraApiError as exc:
            return PostResult(channel=self.name, ok=False, error=str(exc))
        return PostResult(channel=self.name, ok=True, url=comment.url)


def load_jira_channel(
    cli_config: Mapping[str, Any], client_factory: Optional[Callable] = None
) -> Optional[JiraChannel]:
    """The ``channels.jira`` loader (``CHANNEL_PROVIDERS["jira"]``).

    ``None`` when the channel is absent or disabled, and — loudly — when it is
    enabled without ``integrations.jira``: a room needs a site and a credential.
    """
    config = JiraChannelConfig.from_mapping(cli_config)
    if not config.enabled:
        return None
    api = JiraApiConfig.from_cli_config(dict(cli_config))
    if not api.configured:
        logger.error(
            "channels.jira is enabled but integrations.jira is not configured — "
            "the Jira channel is disabled (fail closed)"
        )
        return None
    return JiraChannel(config, cli_config)
