"""Channels — the surfaces the-loop holds a conversation on (issue-245, issue-309).

An **integration** (:mod:`the_loop.graph.integrations`) is a transport for
the-loop's own calls; a **channel** is a conversation surface — and, since
issue-309 (decision-103), a **peer on one event bus**: it subscribes to the event
types it wants, may publish the ones it is granted, renders every event itself, and
one channel — the **ledger**, GitHub by default — records everything that originated
elsewhere before any other channel sees it. The work item stays the single source of
truth the ticket's rule names.

Three invariants this package enforces, all inherited rather than invented:

* **The ledger writes first, and outbound is best-effort after it.** A question
  lands on the ticket first; a channel outage changes nothing about the ask's
  outcome.
* **What a channel may raise is a grant**, read from the catalog (:mod:`.events`):
  a reply is session input by default; a gate answer, a control keyword or a new
  work item only by ``publish``, each recorded on the ledger and judged by the
  ledger's own ingress — never around it.
* **Every record carries an envelope.** A reply's record also carries the
  self-authored marker (:func:`the_loop.authz.mark_self_authored`), so both ingress
  paths drop it and the answer is processed exactly once — by the reply path, not
  the event path.

Spec: docs/specs/issue-309/design.md (and issue-245 for the Slack provider).
"""

from .base import (  # noqa: F401
    DEFAULT_EVENTS,
    DEFAULT_PUBLISH,
    Channel,
    ChannelError,
    Event,
    InboundReply,
    Ledger,
    OutboundEvent,
    PostResult,
    PublishResult,
    load_channels,
    load_ledger,
    render,
)
from .bus import broadcast, publish  # noqa: F401

__all__ = [
    "DEFAULT_EVENTS",
    "DEFAULT_PUBLISH",
    "Channel",
    "ChannelError",
    "Event",
    "InboundReply",
    "Ledger",
    "OutboundEvent",
    "PostResult",
    "PublishResult",
    "broadcast",
    "load_channels",
    "load_ledger",
    "publish",
    "render",
]
