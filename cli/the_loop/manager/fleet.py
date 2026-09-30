"""The fleet a manager serves: the registry, the probes, the resolvers (issue-374).

A **manager** (``instance.role: manager``) keeps everything a worker does and also
answers for the instances registered under ``instance.manager.instances``. This module is
the client side of that: it knows who the members are (the live config, re-read on every
call so a registration is honoured on the next request — R1.4), whether each one is
*trusted* right now (a **probe**: ``GET /api/v1/instance`` must answer with the
registered name and ``role: worker`` before anything is served from a member or sent to
it — R6.1, decision-138 D5), how to ask every live member one question at once (a
**fan-out**, bounded in workers and in time — R2.9, abuse case 4), and which single
instance a keyed operation is for (the **resolvers** — R2.3, R2.4).

**The manager is its own first member** (R1.3). :attr:`Fleet.local` is a member with
no URL, answered in-process by the core facade rather than over HTTP; it is always
``live`` and first in every list, and registering the manager's own address is refused
by the config reader so the same state is never counted twice.

**A member's answer is data.** Every response is read within the fleet's timeout and
within :data:`MAX_MEMBER_BODY`, parsed as JSON and checked against the shape the
operation promises; anything else is that member's answer dropped, an
``instance.malformed`` event, and — on a keyed operation — a ``502``, never an empty
``200`` (R6.4). Nothing from the caller — no header, no body — is forwarded to a member:
every request is built from the operation's arguments alone (abuse case 1). The stamp a
row carries is always the *registered* name (R6.3).

The transport is injected so the unit tests drive an in-process client per member and
only one integration test opens sockets; the default is ``urllib``, as
:mod:`the_loop.client` already is (decision-138 D10).
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import eventlog
from ..api.errors import Conflict, MemberUnavailable
from ..core.instance import instance_config
from ..instance import NAME_RE, WORKER, InstanceConfig, ManagerConfig, Member

logger = logging.getLogger("the-loop.manager")

__all__ = [
    "LIVE",
    "MAX_MEMBER_BODY",
    "MAX_WORKERS",
    "MISMATCHED",
    "UNREACHABLE",
    "Fleet",
    "Probe",
    "Transport",
    "TransportError",
    "urllib_transport",
]

LIVE, UNREACHABLE, MISMATCHED = "live", "unreachable", "mismatched"

#: How much of a member's response is read before it is dropped as malformed (R6.4).
#: A transcript tail is a few hundred KiB and a work-item list a few KiB; 16 MiB is
#: far above either and small enough to be irrelevant to the process.
MAX_MEMBER_BODY = 16 * 1024 * 1024

#: Simultaneous requests one fan-out makes. Eight is a fleet's worth of members and
#: a bound, not a target: a manager with forty members waits five rounds rather than
#: opening forty sockets against forty single-worker uvicorns at once.
MAX_WORKERS = 8

#: ``(method, url, body, timeout) -> (status, body)``. Raises :class:`TransportError`
#: when no HTTP answer came back at all.
Transport = Callable[[str, str, Optional[bytes], float], Tuple[int, bytes]]


class TransportError(Exception):
    """No HTTP answer: refused, unreachable, timed out, or too large."""


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse every 3xx: a member's answer is data, never a new address.

    ``urlopen``'s default handler would follow a ``Location`` to any host — a
    compromised member could point the manager at a loopback service of the
    manager's own and have its body served as that member's rows. A redirect is
    therefore the member's *error* (its status comes back as is), and the only
    URLs the manager ever opens are the registered ones joined with fixed paths.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 — stdlib hook
        return None


#: One opener for every member request, redirects refused.
_opener = urllib.request.build_opener(_NoRedirects())


def urllib_transport(
    method: str, url: str, body: Optional[bytes], timeout: float
) -> Tuple[int, bytes]:
    """The default transport: stdlib, bounded, no redirects, nothing of the caller's."""
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with _opener.open(request, timeout=timeout) as response:  # noqa: S310 — http(s) URL from the operator's config
            data = response.read(MAX_MEMBER_BODY + 1)
            return response.status, data
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(MAX_MEMBER_BODY + 1)
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        raise TransportError(str(exc)) from exc


@dataclass
class Probe:
    """What the manager last learned about one member, and when."""

    member: Member
    state: str
    at: float
    document: Optional[Dict[str, Any]] = None
    version: str = ""
    detail: str = ""
    probed_at: str = ""

    @property
    def live(self) -> bool:
        return self.state == LIVE

    def row(self) -> Dict[str, Any]:
        """The fleet row (R3.1): the shape a worker's self row has."""
        doc = self.document or {}
        scope = doc.get("scope") or {}
        row: Dict[str, Any] = {
            "name": self.member.name,
            "url": self.member.url,
            "state": self.state,
            "version": self.version if self.live else "",
            "mode": str(scope.get("mode") or "") if self.live else "",
            "managedCount": len(doc.get("managed") or []) if self.live else 0,
            "sessionCount": int(doc.get("sessionCount") or 0) if self.live else 0,
            "probedAt": self.probed_at,
        }
        if not self.live:
            row["detail"] = self.detail
        return row


@dataclass
class _Answer:
    """One member's answer to a fan-out, or why there is none."""

    name: str
    value: Any = None
    error: Optional[Exception] = None


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Fleet:
    """The registry, the probe cache and the resolvers over one live config.

    ``config`` is a callable returning the CLI config *now* — the route class already
    refreshed the holder before the operation ran, so a registration written a moment
    ago is the registry now. ``local_refs`` and ``local_standing`` answer, for the
    manager's own state, the two questions the resolvers ask (which refs, which
    standing names); they are the core facade's, injected so this module imports
    nothing of the stores.
    """

    def __init__(
        self,
        config: Callable[[], Mapping[str, Any]],
        *,
        transport: Transport = urllib_transport,
        local_refs: Optional[Callable[[], Sequence[str]]] = None,
        local_standing: Optional[Callable[[], Sequence[str]]] = None,
        clock: Callable[[], float] = time.monotonic,
        announce: bool = True,
    ) -> None:
        self._config = config
        self._announce_transitions = announce
        self._transport = transport
        self._local_refs = local_refs or (lambda: ())
        self._local_standing = local_standing or (lambda: ())
        self._clock = clock
        self._probes: Dict[Tuple[str, str], Probe] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_config(
        cls,
        config: Optional[Mapping[str, Any]],
        *,
        transport: Transport = urllib_transport,
    ) -> "Fleet":
        """A fleet over a static config — for `status`, which runs with no service.

        One-shot, so it **announces nothing**: a fresh cache has no previous state to
        transition from, and a `status` typed while a member is down would otherwise
        record `instance.unreachable` on every invocation rather than once.
        """
        frozen = dict(config or {})
        return cls(lambda: frozen, transport=transport, announce=False)

    # -- the registry -------------------------------------------------------------

    @property
    def identity(self) -> InstanceConfig:
        return instance_config(dict(self._config()))

    @property
    def config(self) -> ManagerConfig:
        return self.identity.manager

    @property
    def own_name(self) -> str:
        return self.identity.name

    @property
    def local(self) -> Member:
        """The manager itself: no URL, answered in-process, always live (R1.3)."""
        return Member(name=self.own_name, url="")

    def members(self) -> Tuple[Member, ...]:
        return self.config.members

    def is_local(self, member: Member) -> bool:
        return not member.url

    # -- the probe --------------------------------------------------------------------

    def probe(self, member: Member, *, fresh: bool = False) -> Probe:
        """The member's state, from the cache while it is fresh (R6.1).

        ``LIVE`` requires ``GET /api/v1/instance`` to answer a JSON object whose
        ``name`` is the registered name and whose ``role`` is ``worker`` (absent reads
        as ``worker`` — a 19.14.1 member has no ``role``); anything else is
        ``MISMATCHED``, and no answer at all is ``UNREACHABLE``. A change of state
        between two probes is one event; a second failing probe emits nothing.
        """
        if self.is_local(member):
            return Probe(
                member=member, state=LIVE, at=self._clock(), probed_at=_utcnow()
            )
        key = (member.name, member.url)
        interval = self.config.probe_interval_seconds
        with self._lock:
            known = self._probes.get(key)
            if known is not None and not fresh and self._clock() - known.at < interval:
                return known
        probe = self._probe_now(member)
        with self._lock:
            previous = self._probes.get(key)
            self._probes[key] = probe
        self._announce(previous, probe)
        return probe

    def _probe_now(self, member: Member) -> Probe:
        now = self._clock()
        stamp = _utcnow()
        try:
            document = self._get(member, "/api/v1/instance", expect=dict)
        except MemberUnavailable as exc:
            # The row's detail is the transport's reason alone ("connection
            # refused"); the member's name is the row's own column.
            reason = str(exc.__cause__) if exc.__cause__ is not None else str(exc)
            return Probe(
                member=member, state=UNREACHABLE, at=now, detail=reason, probed_at=stamp
            )
        except (ValueError, LookupError, Conflict) as exc:
            # An HTTP error on /api/v1/instance — an older the-loop, or any other
            # app at that address — is "not this instance", never a raised probe:
            # a fleet read must answer with that row, not fail on it.
            return Probe(
                member=member,
                state=MISMATCHED,
                at=now,
                detail=f"does not answer as a the-loop instance: {exc}",
                probed_at=stamp,
                document={"reported": "", "role": ""},
            )
        reported = document.get("name")
        role = document.get("role") or WORKER
        if reported != member.name or role != WORKER:
            shown = (
                reported
                if isinstance(reported, str) and NAME_RE.fullmatch(reported)
                else "(unnamed)"
            )
            detail = (
                f"answers as {shown} with role {role!r}; registered as {member.name}"
                if role != WORKER
                else f"answers as {shown}; registered as {member.name}"
            )
            return Probe(
                member=member,
                state=MISMATCHED,
                at=now,
                detail=detail,
                probed_at=stamp,
                document={"reported": shown, "role": str(role)},
            )
        version = ""
        try:
            health = self._get(member, "/api/v1/health", expect=dict)
            version = str(health.get("version") or "")
        except MemberUnavailable:
            version = ""
        return Probe(
            member=member,
            state=LIVE,
            at=now,
            document=document,
            version=version,
            probed_at=stamp,
        )

    def _announce(self, previous: Optional[Probe], probe: Probe) -> None:
        """One event per transition (R3.4); the names are the registered ones."""
        if not self._announce_transitions:
            return
        before = previous.state if previous is not None else None
        if before == probe.state:
            return
        if probe.state == UNREACHABLE:
            eventlog.emit(
                "instance.unreachable",
                level="error",
                instance=probe.member.name,
                reason=probe.detail,
            )
        elif probe.state == MISMATCHED:
            doc = probe.document or {}
            eventlog.emit(
                "instance.mismatched",
                level="error",
                instance=probe.member.name,
                reported=doc.get("reported", ""),
                role=doc.get("role", ""),
            )
        elif before is not None:
            eventlog.emit("instance.recovered", instance=probe.member.name)

    def probes(self, *, fresh: bool = False) -> List[Probe]:
        """Every registered member's probe, refreshing the stale ones concurrently."""
        members = self.members()
        if not members:
            return []
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(members))) as pool:
            return list(pool.map(lambda m: self.probe(m, fresh=fresh), members))

    def live(self) -> List[Probe]:
        return [probe for probe in self.probes() if probe.live]

    def rows(self) -> List[Dict[str, Any]]:
        """The members' fleet rows (R3.1) — the manager's own row is core's."""
        return [probe.row() for probe in self.probes()]

    def mark_unreachable(self, member: Member, reason: str) -> None:
        """A transport failure outside a probe is the same fact as a failed probe."""
        if self.is_local(member):
            return
        key = (member.name, member.url)
        probe = Probe(
            member=member,
            state=UNREACHABLE,
            at=self._clock(),
            detail=reason,
            probed_at=_utcnow(),
        )
        with self._lock:
            previous = self._probes.get(key)
            self._probes[key] = probe
        self._announce(previous, probe)

    # -- one request ----------------------------------------------------------------------

    def _get(self, member: Member, path: str, *, expect: type = dict) -> Any:
        return self._request(member, "GET", path, expect=expect, operation="probe")

    def call(
        self,
        member: Member,
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
        expect: type = dict,
        operation: str = "",
    ) -> Any:
        """One request to a live member; the member's error is the manager's error.

        A ``400`` is a :class:`ValueError`, a ``404`` a :class:`LookupError`, a ``409``
        a :class:`Conflict`, any other non-2xx a :class:`MemberUnavailable` — so a
        worker's own words reach the caller with the status they had — and a transport
        failure is :class:`MemberUnavailable` and marks the member unreachable.
        """
        if not self.probe(member).live:
            raise MemberUnavailable(
                f"instance {member.name!r} is {self.probe(member).state}: "
                f"{self.probe(member).detail}",
                member.name,
            )
        url = path
        if query:
            filtered = {k: v for k, v in query.items() if v not in (None, "", [], ())}
            if filtered:
                url += "?" + urllib.parse.urlencode(filtered, doseq=True)
        return self._request(
            member, method, url, body=body, expect=expect, operation=operation or path
        )

    def _request(
        self,
        member: Member,
        method: str,
        path: str,
        *,
        body: Optional[Mapping[str, Any]] = None,
        expect: type = dict,
        operation: str = "",
    ) -> Any:
        payload = json.dumps(dict(body)).encode() if body is not None else None
        timeout = self.config.timeout_seconds
        try:
            status, raw = self._transport(method, member.url + path, payload, timeout)
        except TransportError as exc:
            if operation != "probe":
                self.mark_unreachable(member, str(exc))
            raise MemberUnavailable(
                f"instance {member.name!r} did not answer: {exc}", member.name
            ) from exc
        if len(raw) > MAX_MEMBER_BODY:
            self._malformed(member, operation, "body exceeds the bound")
            raise MemberUnavailable(
                f"instance {member.name!r} answered more than {MAX_MEMBER_BODY} bytes",
                member.name,
            )
        try:
            data = json.loads(raw.decode("utf-8") or "null") if raw else None
        except (ValueError, UnicodeDecodeError):
            self._malformed(member, operation, "not JSON")
            raise MemberUnavailable(
                f"instance {member.name!r} answered something that is not JSON",
                member.name,
            )
        if 200 <= status < 300:
            if not isinstance(data, expect):
                self._malformed(member, operation, f"not a JSON {expect.__name__}")
                raise MemberUnavailable(
                    f"instance {member.name!r} answered the wrong shape for {operation}",
                    member.name,
                )
            return data
        detail = ""
        if isinstance(data, dict):
            detail = str(data.get("detail") or "")
        message = f"{member.name}: {detail or f'HTTP {status}'}"
        if status == 400:
            raise ValueError(message)
        if status == 404:
            raise LookupError(message)
        if status == 409:
            candidates = data.get("candidates") if isinstance(data, dict) else None
            raise Conflict(message, candidates or ())
        raise MemberUnavailable(message, member.name)

    def _malformed(self, member: Member, operation: str, reason: str) -> None:
        eventlog.emit(
            "instance.malformed",
            level="error",
            instance=member.name,
            operation=operation,
            reason=reason,
        )

    # -- fan-out -------------------------------------------------------------------------------

    def fan_out(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, Any]] = None,
        expect: type = list,
        operation: str = "",
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Ask every live member the same question at once (R2.2, R2.9).

        Returns ``({name: answer}, [names left out])``: a member whose probe is not
        live, whose call raises, or which does not answer within the fleet's timeout
        is left out — its answer does not exist — and the operation still answers.
        One hung member costs at most ``timeoutSeconds`` of the others' wall time.
        """
        answers: Dict[str, Any] = {}
        left_out: List[str] = []
        probes = self.probes()
        live = [probe.member for probe in probes if probe.live]
        left_out.extend(probe.member.name for probe in probes if not probe.live)
        if not live:
            return answers, left_out
        timeout = self.config.timeout_seconds

        def one(member: Member) -> _Answer:
            try:
                return _Answer(
                    member.name,
                    self.call(
                        member,
                        method,
                        path,
                        query=query,
                        expect=expect,
                        operation=operation,
                    ),
                )
            except Exception as exc:  # noqa: BLE001 — every failure is "left out"
                return _Answer(member.name, error=exc)

        # Not a context manager: `with` would wait for every future on exit, and a
        # member that hangs past the transport's timeout would then hold the whole
        # answer. The pool is released without waiting; a straggler finishes on its
        # own thread and is discarded, bounded by the transport's own timeout.
        pool = ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(live)))
        try:
            futures = {member.name: pool.submit(one, member) for member in live}
            deadline = time.monotonic() + timeout + 1
            for name, future in futures.items():
                try:
                    answer = future.result(
                        timeout=max(0.0, deadline - time.monotonic())
                    )
                except FutureTimeout:
                    left_out.append(name)
                    self.mark_unreachable(
                        self.config.member(name) or Member(name, ""), "timed out"
                    )
                    continue
                if answer.error is not None:
                    logger.warning(
                        "%s left out of %s: %s", name, operation or path, answer.error
                    )
                    left_out.append(name)
                else:
                    answers[name] = answer.value
        finally:
            pool.shutdown(wait=False)
        if left_out:
            eventlog.emit(
                "aggregate.partial",
                level="debug",
                operation=operation or path,
                left_out=sorted(left_out),
            )
        return answers, sorted(set(left_out))

    # -- the resolvers ----------------------------------------------------------------------

    def by_instance(self, name: str) -> Member:
        """The member ``name`` names — the manager itself for its own name (R2.6)."""
        if not name or name == self.own_name:
            return self.local
        member = self.config.member(name)
        if member is None:
            raise LookupError(
                f"no instance named {name!r} is registered with this manager"
            )
        return member

    def _resolve(
        self, key: str, instance: str, holders: Callable[[], List[str]], what: str
    ) -> Member:
        if instance:
            return self.by_instance(instance)
        names = holders()
        if not names:
            raise LookupError(f"no instance manages {what} {key!r}")
        if len(names) > 1:
            raise Conflict(
                f"{what} {key!r} is managed by {len(names)} instances "
                f"({', '.join(names)}); name one with `instance`",
                names,
            )
        return self.by_instance(names[0])

    def by_ref(self, ref: str, instance: str = "") -> Member:
        """The one instance whose managed set holds ``ref`` (R2.3, R2.4).

        The manager's own set comes from its records; a member's from the probe
        document (``managed``), so a keyed read costs no extra round trip while the
        probes are fresh. None → 404; several → 409 naming them, unless ``instance``
        names one.
        """

        def holders_from(probes: List[Probe]) -> List[str]:
            names: List[str] = []
            if ref in set(self._local_refs()):
                names.append(self.own_name)
            for probe in probes:
                if not probe.live:
                    continue
                managed = (probe.document or {}).get("managed") or []
                if any(
                    isinstance(row, dict) and row.get("ref") == ref for row in managed
                ):
                    names.append(probe.member.name)
            return names

        def holders() -> List[str]:
            names = holders_from(self.probes())
            if not names and self.members():
                # A cached probe may predate the member taking the work item: one
                # fresh round before answering "nobody manages it".
                names = holders_from(self.probes(fresh=True))
            return names

        return self._resolve(ref, instance, holders, "work item")

    def by_standing_name(self, name: str, instance: str = "") -> Member:
        """The one instance that lists standing session ``name``."""

        def holders() -> List[str]:
            names: List[str] = []
            if name in set(self._local_standing()):
                names.append(self.own_name)
            answers, _ = self.fan_out(
                "GET", "/api/v1/standing-sessions", expect=list, operation="standing"
            )
            for member_name, rows in answers.items():
                if any(
                    isinstance(row, dict) and row.get("name") == name for row in rows
                ):
                    names.append(member_name)
            return names

        return self._resolve(name, instance, holders, "standing session")
