"""Channels — the surfaces the-loop holds a conversation on (issue-245).

An **integration** (:mod:`the_loop.graph.integrations`) is a transport for
the-loop's own calls; a **channel** is a conversation surface: it filters the
event types it wants, renders at its configured verbosity, carries a question
*out* and — for channels that can — carries the answer back *in*. The work item
is never a channel here: it is the substrate every channel mirrors into, the
single source of truth the ticket's rule names.

Two invariants this package enforces, both inherited rather than invented:

* **Outbound is best-effort, after the work item.** A question lands on the
  ticket first; a channel outage changes nothing about the ask's outcome.
* **Inbound is mirrored with the self-authored marker.** A reply given on any
  channel is posted onto the work item as the-loop's own comment
  (:func:`the_loop.authz.mark_self_authored`), so both ingress paths drop it
  and the answer is processed exactly once — by the reply path, not the event
  path.

Spec: docs/specs/issue-245/design.md.
"""

from .base import (  # noqa: F401
    DEFAULT_EVENTS,
    Channel,
    ChannelError,
    InboundReply,
    OutboundEvent,
    PostResult,
    load_channels,
    render,
)

__all__ = [
    "DEFAULT_EVENTS",
    "Channel",
    "ChannelError",
    "InboundReply",
    "OutboundEvent",
    "PostResult",
    "load_channels",
    "render",
]
