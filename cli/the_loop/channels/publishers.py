"""What the ledger's ingress publishes: the comments it saw (issue-309, R6.1).

Both ingresses — the webhook router and the poller — already decide, per comment,
whether it is the agent's own (marker-stamped, dropped before authorization) or a
human's the loop may act on (an authorized user's, or a work-item collaborator's).
Those two decisions are exactly the two ledger-origin events of the catalog:

* ``comment.agent`` — the agent's artifacts: the requirements summary, the phase
  checklist, a review note. A Slack channel subscribed to this alone gets what
  the agent wrote and no human's words.
* ``comment.human`` — the thread. Only comments the ingress *accepted*: a stranger's
  comment is never relayed anywhere, fail closed.

A comment carrying an **envelope** is a record the bus already made (a reply, a
gate answer, the ask) — the channel that raised it has it — and is never
re-published: that is loop prevention across channels (A10). The publisher is a
callable the daemons build over their config holder, so a reload is honoured and a
router built without one (tests, embedders) publishes nothing.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Mapping, Optional

from .base import Event
from .envelope import has_envelope

logger = logging.getLogger("the-loop.channels")

__all__ = ["Publisher", "comment_publisher", "publish_comment"]

#: ``(kind, work_item_ref, author, body, url) -> None``; ``kind`` is ``agent``/``human``.
Publisher = Callable[[str, str, str, str, str], None]

_TYPES = {"agent": "comment.agent", "human": "comment.human"}


def publish_comment(
    kind: str,
    work_item: str,
    author: str,
    body: str,
    url: str,
    cli_config: Optional[Mapping[str, Any]],
) -> bool:
    """Publish one ledger comment as its catalog event. Never raises; never records."""
    event_type = _TYPES.get(kind)
    if not event_type or not body or not body.strip():
        return False
    if has_envelope(body):
        return False  # the bus made this record; its source channel has it
    from .bus import publish

    try:
        result = publish(
            Event(
                event_type=event_type,
                work_item=work_item,
                text=body,
                url=url or "",
                detail={"author": author} if author else {},
                source="github",
            ),
            cli_config,
            record=False,
        )
    except Exception:  # noqa: BLE001 — a channel bug never touches ingress
        logger.exception("publishing %s for %s raised", event_type, work_item)
        return False
    return result.delivered


def comment_publisher(config_getter: Callable[[], Mapping[str, Any]]) -> Publisher:
    """A :data:`Publisher` reading the CLI config afresh on every call — the
    daemons' reloadable form. A getter that raises publishes nothing."""

    def publish(kind: str, work_item: str, author: str, body: str, url: str) -> None:
        try:
            cli_config = dict(config_getter() or {})
        except Exception:  # noqa: BLE001 — a half-saved config is not ingress's problem
            logger.debug("comment publisher: could not read the CLI config")
            return
        if not cli_config.get("channels"):
            return  # nothing to fan out to; do not even build the event
        publish_comment(kind, work_item, author, body, url, cli_config)

    return publish
