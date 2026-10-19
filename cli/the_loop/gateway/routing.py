"""Which instances consume an event — decided on write (issue-496, R5.2).

:func:`consumers_for` is called by every adapter between ``resolve_ref`` and
``store.append``. The order is the requirement's (R5.2):

1. the **claimants** of the subject plus the claimants of each linked subject — a pull
   request's linked ticket through bindings (R5.3, R5.4), de-duplicated;
2. when that set is empty, the one instance that **registered the event's actor**
   (R5.5) — how the first event about a work item reaches the instance of the user who
   caused it;
3. when both are empty, ``[]``: the event is **held** on ``unassigned`` and routed later
   by ``store.claim`` or ``store.bind`` (R2.2, R5.7).

Routing reads three small tables and the adapter writes the ``deliveries`` rows in the
same transaction as the ``events`` row (``store.append``), so the provider's
acknowledgement implies the fan-out is durable. The gateway module tree imports neither
``webhook/dispatcher.py`` nor ``authz.py``: nothing here judges a human.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .store import Store

__all__ = ["Routing", "consumers_for"]


@dataclass(frozen=True)
class Routing:
    consumers: Tuple[str, ...]
    by: str  # claim | actor | hold


def consumers_for(
    subject: str,
    linked: Sequence[str],
    actor: Optional[Tuple[str, str]],
    store: Store,
) -> Routing:
    """The instances that consume ``subject`` now, and why (``claim`` / ``actor`` /
    ``hold``). ``actor`` is ``(provider, login)``; ``linked`` is the other subjects the
    event also concerns (a PR's ticket)."""
    seen: List[str] = []
    for name in (subject, *linked):
        if not name:
            continue
        for claim in store.claimants(name):
            if claim.instance not in seen:
                seen.append(claim.instance)
    if seen:
        return Routing(tuple(seen), "claim")
    if actor is not None and actor[1]:
        instance = store.instance_for_actor(actor[0], actor[1])
        if instance:
            return Routing((instance,), "actor")
    return Routing((), "hold")
