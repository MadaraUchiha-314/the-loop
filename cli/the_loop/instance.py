"""Instance identity and scope: which work items *this* the-loop manages (issue-322).

Before this module every instance of the-loop was the same instance. One
``cli-config.yaml`` describes one set of daemons, and every daemon judged every
labelled event the same way — labelled, authorized, started, spawn — so two
instances watching one repository both spawned for one ``the-loop start``, in two
checkouts, with two dev servers fighting over one port.

An instance now has a **name**, a **mode** that says how new work items reach it,
and a **declared** list of the work items it manages. The three live under the
top-level ``instance`` block of the CLI config (decision-110 D1: an instance *is*
a running CLI config, so the config that names its daemons names its scope) and
reach the dispatcher through :class:`~the_loop.webhook.dispatcher.RoutingConfig`
by the same fan-out ``integrations.github.cli.binary`` already uses.

## The managed set

Derived, never kept (decision-110 D2): a work item is managed when it is declared
here, when the instance holds a live session record for it, or when the instance
holds a control record for it — the records the instance already writes for every
work item it acts on. The dispatcher computes that union per event; this module
only knows the declared third.

## The modes

``open``
    13.3.1: any armed, authorized start is taken. The default, so a lone instance
    that names itself changes nothing.
``addressed``
    A new work item is taken only when the comment names this instance
    (``instance:<name>``, :func:`parse_address`) — the steady state for several
    instances, where every start says which one runs it.
``locked``
    Nothing new is taken, addressed or not. The declared list is the only door.

## The address token

``instance:<name>`` anywhere in a comment body, matched as a whole word with a
case-insensitive prefix; the name must fit :data:`NAME_RE` in full or the token
is not an address at all. Two different names in one body are *ambiguous* and
refuse the whole comment, as two different control keywords do (issue-106). It is
the collaborator ``@login`` argument's discipline (issue-307) applied once more:
what leaves this parser is a grammar-validated token, never body text.

## The decision

:func:`decide` is pure. An explicit address to another instance wins over
everything (decision-110 D5), a managed work item is in scope in every mode, an
open instance claims anything, a locked one claims nothing — an address never
unlocks it — and an addressed one claims exactly what names it.

Spec: docs/specs/issue-322/design.md §1.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Tuple

from .sessions import WorkItemRef

logger = logging.getLogger("the-loop.instance")

__all__ = [
    "ADDRESSED",
    "ADDRESSED_ELSEWHERE",
    "AMBIGUOUS_ADDRESS",
    "CLAIMABLE",
    "IN_SCOPE",
    "INSTANCE_LOCKED",
    "LOCKED",
    "MODES",
    "NAME_RE",
    "OPEN",
    "REFUSALS",
    "UNADDRESSED",
    "Address",
    "InstanceConfig",
    "ScopeDecision",
    "decide",
    "parse_address",
    "parse_declaration",
]

#: The standing-session name grammar (issue-277), reused: the value is interpolated
#: into a tmux argv (``-e THE_LOOP_INSTANCE=…``) and a comment body, so it is kept
#: narrow by construction.
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

OPEN, ADDRESSED, LOCKED = "open", "addressed", "locked"
MODES = (OPEN, ADDRESSED, LOCKED)

#: The two accepting outcomes…
IN_SCOPE, CLAIMABLE = "in-scope", "claimable"
#: …and the four refusing ones, each the reason recorded on the dropped event.
ADDRESSED_ELSEWHERE, UNADDRESSED, INSTANCE_LOCKED, AMBIGUOUS_ADDRESS = (
    "addressed-elsewhere",
    "unaddressed",
    "instance-locked",
    "ambiguous-address",
)
REFUSALS = (ADDRESSED_ELSEWHERE, UNADDRESSED, INSTANCE_LOCKED, AMBIGUOUS_ADDRESS)

# A GitHub issue / pull-request URL as a declaration (R1.1): the host is kept when
# it is not github.com, exactly as `WorkItemRef` keeps it.
_URL_RE = re.compile(
    r"^https?://(?P<host>[^/\s]+)/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)"
    r"/(?:issues|pull)/(?P<number>\d+)/?$"
)
# The token: `instance:` (any case) not glued to a preceding word, `:` or `/`
# (so `myinstance:a` and `http://instance:a` are not tokens), then the candidate
# up to whitespace. The candidate is validated separately against NAME_RE.
_TOKEN_RE = re.compile(r"(?<![\w:/.-])instance:(\S*)", re.IGNORECASE)


def parse_declaration(value: Any) -> Optional[str]:
    """A ``scope.workItems`` entry as a normalised ref, or ``None`` if it is not one.

    Accepts a ``<provider>:[<host>/]<owner>/<repo>#<n>`` ref or a GitHub issue /
    pull-request URL. Never raises and never echoes the value: a config is data an
    operator may have pasted from anywhere, and the caller reports by index.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    match = _URL_RE.match(text)
    if match:
        host = match.group("host")
        prefix = "" if host == "github.com" else f"{host}/"
        text = f"github:{prefix}{match.group('owner')}/{match.group('repo')}#{match.group('number')}"
    try:
        return WorkItemRef.parse(text).ref
    except ValueError:
        return None


@dataclass(frozen=True)
class InstanceConfig:
    """Mirror of the top-level ``instance`` block (see the config schema)."""

    name: str = ""
    mode: str = OPEN
    declared: Tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: Optional[Mapping[str, Any]]) -> "InstanceConfig":
        """Build from the block; every unresolvable value **narrows** (R1.4, R1.5).

        A name outside the grammar is unnamed; an unknown mode is ``locked``;
        ``addressed`` without a name is ``locked``; a declaration that does not
        parse is skipped by index. Warned, never raised: an un-edited or mis-edited
        config must not brick a daemon, and the closed reading is the safe one.
        """
        if data is None:
            return cls()
        if not isinstance(data, Mapping):
            logger.warning(
                "instance: not a mapping; using the defaults (unnamed, open)"
            )
            return cls()
        name = data.get("name") or ""
        if not isinstance(name, str) or (name and not NAME_RE.fullmatch(name)):
            logger.warning(
                "instance.name does not fit ^[a-z0-9][a-z0-9-]{0,39}$; treating the "
                "instance as unnamed"
            )
            name = ""
        scope = data.get("scope")
        if scope is None:
            scope = {}
        elif not isinstance(scope, Mapping):
            logger.warning("instance.scope: not a mapping; using the defaults (open)")
            scope = {}
        mode = scope.get("mode") or OPEN
        if not isinstance(mode, str) or mode not in MODES:
            logger.warning(
                "instance.scope.mode is not one of %s; resolving to %r so a typo "
                "cannot widen what this instance takes on",
                "/".join(MODES),
                LOCKED,
            )
            mode = LOCKED
        if mode == ADDRESSED and not name:
            logger.warning(
                "instance.scope.mode is 'addressed' but instance.name is unset — "
                "nothing can address an unnamed instance; resolving to %r",
                LOCKED,
            )
            mode = LOCKED
        declared: List[str] = []
        entries = scope.get("workItems") or []
        if not isinstance(entries, (list, tuple)):
            logger.warning("instance.scope.workItems: not a list; declaring nothing")
            entries = []
        for index, entry in enumerate(entries):
            ref = parse_declaration(entry)
            if ref is None:
                logger.warning(
                    "instance.scope.workItems[%d] is not a work-item ref or GitHub "
                    "URL; skipped",
                    index,
                )
                continue
            if ref not in declared:
                declared.append(ref)
        return cls(name=name, mode=mode, declared=tuple(declared))

    def declares(self, ref: str) -> bool:
        return ref in self.declared

    def to_dict(self) -> dict:
        """The scope as the control plane reports it."""
        return {
            "name": self.name,
            "scope": {"mode": self.mode, "workItems": list(self.declared)},
        }


@dataclass(frozen=True)
class Address:
    """Which instance a comment body names, if any (pure, side-effect free)."""

    name: str = ""
    ambiguous: bool = False
    matched: Tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.name) or self.ambiguous


def parse_address(body: Optional[str]) -> Address:
    """The ``instance:<name>`` token(s) ``body`` carries (R3.1, R3.3, R3.4).

    Every occurrence is read; a candidate outside :data:`NAME_RE` is not an address
    and contributes nothing. One distinct valid name is the address; two or more
    are ambiguous; none is no address.
    """
    if not body:
        return Address()
    names: List[str] = []
    for match in _TOKEN_RE.finditer(body):
        # Trailing sentence punctuation is prose, not name: `(instance:box-2)`.
        candidate = match.group(1).rstrip(").,;:!?]'\"")
        if candidate and NAME_RE.fullmatch(candidate) and candidate not in names:
            names.append(candidate)
    if not names:
        return Address()
    if len(names) > 1:
        return Address(ambiguous=True, matched=tuple(names))
    return Address(name=names[0], matched=(names[0],))


@dataclass(frozen=True)
class ScopeDecision:
    """Whether this instance acts on an event, and the recorded reason if not."""

    outcome: str

    @property
    def accepted(self) -> bool:
        return self.outcome in (IN_SCOPE, CLAIMABLE)


def decide(config: InstanceConfig, address: Address, managed: bool) -> ScopeDecision:
    """The scope decision — design §1's seven-row table, in order.

    ``managed`` is whether any work item the event names is in this instance's
    managed set (declared ∪ session record ∪ control record), computed by the
    caller because the records are the caller's.
    """
    if address.ambiguous:
        return ScopeDecision(AMBIGUOUS_ADDRESS)
    if address.name and address.name != config.name:
        # An explicit address is authoritative (decision-110 D5): the human named
        # the instance, and a managed-set override would let two instances act.
        return ScopeDecision(ADDRESSED_ELSEWHERE)
    if managed:
        return ScopeDecision(IN_SCOPE)
    if config.mode == OPEN:
        return ScopeDecision(CLAIMABLE)
    if config.mode == LOCKED:
        # Before the address check, on purpose: an address never unlocks.
        return ScopeDecision(INSTANCE_LOCKED)
    if address.name and address.name == config.name:
        return ScopeDecision(CLAIMABLE)
    return ScopeDecision(UNADDRESSED)
