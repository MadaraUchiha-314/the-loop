"""Lifecycle hooks — every event the-loop records is a point an operator may attach
a hook to (issue-344, decision-124).

The graph hooks (:mod:`the_loop.graph.extensions`, issue-248) let an operator append a
check to a **node boundary** of the process graph. That is the right surface for a
gate and the wrong one for everything that happens *between* boundaries: a session
spawning, a work item ending, a control keyword, a PR merging, a channel post. Every
one of those is already an event the CLI records — about 150 types, catalogued in
:data:`the_loop.eventlog.EVENT_TYPES`, printed by ``the-loop events --types``. This
module makes each catalogued event an **attach point**.

What is reused, unchanged: the ``@hook("x-…")`` decorator and its per-thread collector
(:mod:`the_loop.graph.registry`), the module loader with its containment and
load-or-fail rules (:func:`the_loop.graph.extensions.load_module`), the ``x-``
namespace, :class:`~the_loop.graph.contract.HookResult`. What is new:

* **The attach point** is an event name or an ``fnmatch`` pattern (``graph.*``),
  expanded against the catalog at parse — a pattern matching nothing is an error, so
  a typo cannot silently disarm a telemetry hook.
* **The context** is a :class:`LifecycleEvent` — the record the log holds, plus the
  attachment's ``with`` — not a ``HookContext``. A lifecycle hook observes; it has no
  node, no chain, no outcome and no way to move the graph.
* **The resolution root** for a ``path`` module is the CLI config file's directory,
  not a checkout: the declaration is the instance's, and so is the code it names.
* **Dispatch is asynchronous** — one bounded queue, one worker thread, emission
  order — so a webhook delivery or an API request never waits on a hook's HTTP call.
  Records in the ``hooks.*`` domain are never queued, and neither is a record emitted
  *by* a hook (thread identity), which is what keeps a hook from feeding the system.
* **Shipped lifecycle hooks** live in :data:`SHIPPED`, attachable by the operator with
  the same entry as their own. The first is ``forward-event``: the record as JSON,
  POSTed, with a bearer token read from the environment when the hook runs.

Declared under the top-level ``hooks`` block of the operator's CLI config, and only
there (decision-123): a checkout carrying a hook module nobody declared runs nothing.
A declaration that cannot be honoured fails the entry point that loads it — the
receiver, the poller, the service, or the one-shot command — rather than degrading to
"no hooks".

Spec: docs/specs/issue-344/  ·  Decision: 124
"""

from __future__ import annotations

import atexit
import fnmatch
import hashlib
import json
import logging
import os
import queue
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)
from urllib.parse import urlsplit

from .graph.contract import BLOCK, HookResult, Message
from .graph.extensions import ModuleRef, load_module, read_modules
from .graph.registry import EXTENSION_PREFIX

logger = logging.getLogger("the-loop.hooks")

__all__ = [
    "CONFIG_KEY",
    "EXIT_DRAIN_SECONDS",
    "OWN_DOMAIN",
    "SHIPPED",
    "Attachment",
    "Bound",
    "Declaration",
    "HooksConfigError",
    "LifecycleEvent",
    "LifecycleHooks",
    "ShippedHook",
    "active",
    "attach_points",
    "drain",
    "expand",
    "forward_event",
    "install",
    "read_declaration",
    "reset",
    "validate_forward",
]

#: Where the operator declares the hooks, for messages that have to name it.
CONFIG_KEY = "hooks"

#: The hook system's own events. Never an attach point: a hook that fired on
#: ``hooks.failed`` and failed would be the loop this rule exists to prevent.
OWN_DOMAIN = "hooks."

#: How long a normal exit waits for queued records to reach their hooks.
EXIT_DRAIN_SECONDS = 5.0

#: Records the queue holds before dropping *for hooks* (never for the log).
DEFAULT_CAPACITY = 1024


class HooksConfigError(ValueError):
    """The ``hooks`` block could not be honoured. Always names the offending entry."""


# -- the context ---------------------------------------------------------------


@dataclass(frozen=True)
class LifecycleEvent:
    """One recorded event, as a lifecycle hook sees it.

    The envelope the log writes (``event``, ``level``, ``ts``, ``source``, ``pid``)
    plus the per-event ``fields`` — documented per type in the catalog — plus the
    attachment's ``with`` as ``params`` and the instance's name. :meth:`record` is
    the whole line the log holds, which is what a forwarder sends.
    """

    event: str
    level: str = "info"
    ts: str = ""
    source: str = ""
    pid: int = 0
    fields: Mapping[str, Any] = field(default_factory=dict)
    params: Mapping[str, Any] = field(default_factory=dict)
    instance: str = ""

    @property
    def work_item(self) -> str:
        """The work item the event concerns, or ``""`` — the field most hooks want."""
        value = self.fields.get("work_item")
        return str(value) if value else ""

    def record(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "ts": self.ts,
            "source": self.source,
            "event": self.event,
            "level": self.level,
            "pid": self.pid,
        }
        out.update(self.fields)
        return out

    @classmethod
    def from_record(
        cls, record: Mapping[str, Any], params: Mapping[str, Any], instance: str
    ) -> "LifecycleEvent":
        fields = {
            k: v
            for k, v in record.items()
            if k not in ("ts", "source", "event", "level", "pid")
        }
        return cls(
            event=str(record.get("event", "")),
            level=str(record.get("level", "info")),
            ts=str(record.get("ts", "")),
            source=str(record.get("source", "")),
            pid=int(record.get("pid") or 0),
            fields=fields,
            params=dict(params),
            instance=instance,
        )


LifecycleFn = Callable[[LifecycleEvent], Optional[HookResult]]


# -- the catalog view ------------------------------------------------------------


def attach_points() -> Tuple[str, ...]:
    """Every event type a hook may attach to: the catalog, minus ``hooks.*``."""
    from .eventlog import EVENT_TYPES

    return tuple(
        sorted(name for name in EVENT_TYPES if not name.startswith(OWN_DOMAIN))
    )


def expand(patterns: Sequence[str], universe: Sequence[str] = ()) -> Tuple[str, ...]:
    """The catalogued events ``patterns`` match, in catalog order, each once.

    Raises :class:`HooksConfigError` for a pattern that matches nothing — the load
    is where a typo has to surface, not the day the telemetry is missed.
    """
    names = tuple(universe) or attach_points()
    matched: List[str] = []
    for pattern in patterns:
        hits = [n for n in names if fnmatch.fnmatchcase(n, pattern)]
        if not hits:
            raise HooksConfigError(
                f"`{CONFIG_KEY}.lifecycle` pattern {pattern!r} matches no event type; "
                "`the-loop events --types` lists the attach points "
                f"({OWN_DOMAIN}* excluded)"
            )
        matched.extend(h for h in hits if h not in matched)
    return tuple(matched)


# -- the shipped table -------------------------------------------------------------


@dataclass(frozen=True)
class ShippedHook:
    """A lifecycle hook the-loop ships: the function and its parameter check."""

    fn: LifecycleFn
    validate: Callable[[Mapping[str, Any]], None]
    description: str = ""


_SCHEMES = ("http", "https")


def validate_forward(params: Mapping[str, Any]) -> None:
    """``forward-event``'s parameters, checked at parse — before any import."""
    url = params.get("url")
    if not isinstance(url, str) or not url.strip():
        raise HooksConfigError(
            "`forward-event` needs `with: {url: …}` — where the record is POSTed to"
        )
    scheme = urlsplit(url.strip()).scheme.lower()
    if scheme not in _SCHEMES:
        raise HooksConfigError(
            f"`forward-event` url {url!r} must be http or https, not {scheme or 'a bare'!r}"
            " — the forwarder opens a network connection, never a file"
        )
    token_env = params.get("tokenEnv")
    if token_env is not None and (not isinstance(token_env, str) or not token_env):
        raise HooksConfigError(
            "`forward-event` `tokenEnv` must be the NAME of an environment variable "
            "(a non-empty string); the value is read when the hook runs"
        )
    headers = params.get("headers")
    if headers is not None:
        if not isinstance(headers, Mapping) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in headers.items()
        ):
            raise HooksConfigError(
                "`forward-event` `headers` must be a mapping of string to string"
            )
    timeout = params.get("timeoutSeconds")
    if timeout is not None and (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or timeout <= 0
    ):
        raise HooksConfigError(
            "`forward-event` `timeoutSeconds` must be a positive number"
        )


def forward_event(event: LifecycleEvent) -> HookResult:
    """POST the record as JSON to ``params.url``. Best-effort: one attempt, no retry.

    The bearer token is read from the environment **when the hook runs**, by the
    name ``params.tokenEnv`` carries; an unset variable sends nothing and fails,
    never sends unauthenticated. The failure names the variable, never a value.
    """
    params = event.params
    url = str(params["url"]).strip()
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    headers.update(dict(params.get("headers") or {}))
    token_env = params.get("tokenEnv")
    if token_env:
        token = os.environ.get(str(token_env))
        if not token:
            return _failed(
                f"environment variable {token_env} is unset; nothing was sent"
            )
        headers["Authorization"] = f"Bearer {token}"
    timeout = float(params.get("timeoutSeconds") or 5)
    body = json.dumps(event.record(), separators=(",", ":"), default=str).encode()
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 — scheme checked at parse
            status = int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        return _failed(f"{url} answered HTTP {exc.code}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return _failed(f"{url}: {exc.__class__.__name__}: {exc}")
    if status >= 300:
        return _failed(f"{url} answered HTTP {status}")
    return HookResult.ok("forward-event", status=status)


def _failed(text: str) -> HookResult:
    return HookResult.blocked("forward-event", [Message(text=text)], retriable=False)


SHIPPED: Dict[str, ShippedHook] = {
    "forward-event": ShippedHook(
        forward_event,
        validate_forward,
        "POST the event record as JSON to `with.url` (bearer token from the "
        "environment variable `with.tokenEnv` names, read when the hook runs).",
    ),
}


# -- the declaration (reads YAML; imports nothing) ---------------------------------


@dataclass(frozen=True)
class Attachment:
    """One ``hooks.lifecycle[]`` entry: a hook, its patterns, its params, and the
    catalogued events the patterns expanded to at parse."""

    hook: str
    patterns: Tuple[str, ...]
    params: Mapping[str, Any] = field(default_factory=dict)
    events: Tuple[str, ...] = ()

    @property
    def shipped(self) -> bool:
        return not self.hook.startswith(EXTENSION_PREFIX)

    def render(self) -> str:
        rendered = (
            f"{self.hook} → {len(self.events)} event(s) [{', '.join(self.patterns)}]"
        )
        return f"{rendered}  with: {dict(self.params)}" if self.params else rendered


@dataclass(frozen=True)
class Declaration:
    """The parsed ``hooks`` block. Empty when the block is absent."""

    modules: Tuple[ModuleRef, ...] = ()
    attachments: Tuple[Attachment, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.modules and not self.attachments

    def digest(self) -> str:
        payload = {
            "modules": [(m.path, m.dotted) for m in self.modules],
            "attach": [
                (a.hook, list(a.patterns), json.dumps(dict(a.params), sort_keys=True))
                for a in self.attachments
            ],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def read_declaration(cli_config: Mapping[str, Any]) -> Declaration:
    """Parse the top-level ``hooks`` block. Imports nothing.

    A malformed block raises rather than resolving to "no hooks"; an **absent** one
    is what every operator who has never heard of the feature gets, and is empty.
    """
    if not isinstance(cli_config, Mapping):
        return Declaration()
    raw = cli_config.get(CONFIG_KEY)
    if raw is None:
        return Declaration()
    if not isinstance(raw, Mapping):
        raise HooksConfigError(
            f"CLI config: `{CONFIG_KEY}` must be a mapping with `modules` and "
            "`lifecycle` lists"
        )
    unknown = sorted(set(raw) - {"modules", "lifecycle"})
    if unknown:
        raise HooksConfigError(
            f"CLI config: `{CONFIG_KEY}` has unknown key(s) {unknown}; "
            "it takes `modules` and `lifecycle`"
        )
    modules = read_modules(raw.get("modules"), CONFIG_KEY, HooksConfigError)
    return Declaration(
        modules=modules, attachments=_read_attachments(raw.get("lifecycle"))
    )


def _read_attachments(value: Any) -> Tuple[Attachment, ...]:
    if not value:
        return ()
    if isinstance(value, (Mapping, str)) or not isinstance(value, Sequence):
        raise HooksConfigError(f"CLI config: `{CONFIG_KEY}.lifecycle` must be a list")
    universe = attach_points()
    out: List[Attachment] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            raise HooksConfigError(
                f"CLI config: `{CONFIG_KEY}.lifecycle` entry {entry!r} must be a "
                "mapping of `hook`, `on`, and optionally `with`"
            )
        name = str(entry.get("hook") or "").strip()
        # YAML 1.1 parses a bare `on:` key as the boolean True — the GitHub Actions
        # trap, and the one graph/model.py's `_normalise_edge_keys` already undoes
        # for edges. Accept both spellings so nobody has to know.
        raw_on = entry["on"] if "on" in entry else entry.get(True)
        patterns = _patterns(raw_on, name or repr(dict(entry)))
        params = entry.get("with")
        params = {} if params is None else params
        if not name:
            raise HooksConfigError(
                f"CLI config: `{CONFIG_KEY}.lifecycle` entry {dict(entry)!r} needs a "
                "`hook`"
            )
        if not name.startswith(EXTENSION_PREFIX) and name not in SHIPPED:
            raise HooksConfigError(
                f"CLI config: `{CONFIG_KEY}.lifecycle` names {name!r}, which is neither "
                f"a hook of your own ({EXTENSION_PREFIX}<something>, registered by a "
                f"declared module) nor a shipped lifecycle hook "
                f"({', '.join(sorted(SHIPPED))})"
            )
        if not isinstance(params, Mapping):
            raise HooksConfigError(
                f"CLI config: `{CONFIG_KEY}.lifecycle` entry for {name!r} has a `with` "
                "that is not a mapping"
            )
        if name in SHIPPED:
            SHIPPED[name].validate(params)
        out.append(
            Attachment(
                hook=name,
                patterns=patterns,
                params=dict(params),
                events=expand(patterns, universe),
            )
        )
    return tuple(out)


def _patterns(value: Any, label: str) -> Tuple[str, ...]:
    if isinstance(value, str):
        value = [value] if value.strip() else []
    if not value or not isinstance(value, Sequence) or isinstance(value, Mapping):
        raise HooksConfigError(
            f"CLI config: `{CONFIG_KEY}.lifecycle` entry {label} needs `on`: an event "
            "type or fnmatch pattern, or a list of them"
        )
    patterns = tuple(str(p).strip() for p in value)
    if any(not p for p in patterns):
        raise HooksConfigError(
            f"CLI config: `{CONFIG_KEY}.lifecycle` entry {label} has an empty `on` entry"
        )
    return patterns


# -- the runtime -----------------------------------------------------------------


@dataclass(frozen=True)
class Bound:
    """One resolved attachment: the function that runs and the params it gets."""

    name: str
    fn: LifecycleFn
    params: Mapping[str, Any]


class LifecycleHooks:
    """Load a declaration, index it by event, and run the hooks off one thread."""

    def __init__(
        self,
        declaration: Declaration,
        root: Path,
        instance: str = "",
        capacity: int = DEFAULT_CAPACITY,
    ) -> None:
        self.declaration = declaration
        self.root = Path(root)
        self.instance = instance
        self.capacity = capacity
        self.index: Dict[str, Tuple[Bound, ...]] = {}
        self.table: Dict[str, LifecycleFn] = {}
        self._queue: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue(
            maxsize=capacity
        )
        self._worker: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._idle = threading.Condition(self._lock)
        self._outstanding = 0
        self._dropping = False
        self.dropped = 0

    # -- load ----------------------------------------------------------------

    def load(self) -> "LifecycleHooks":
        table: Dict[str, LifecycleFn] = {}
        for ref in self.declaration.modules:
            loaded = load_module(
                self.root,
                ref,
                CONFIG_KEY,
                HooksConfigError,
                "the CLI config's directory",
            )
            for name, fn in loaded.items():
                if name in table:
                    raise HooksConfigError(
                        f"two `{CONFIG_KEY}.modules` register {name!r}; the second is "
                        f"{ref.label()!r}"
                    )
                table[name] = fn  # type: ignore[assignment]
        index: Dict[str, List[Bound]] = {}
        for attachment in self.declaration.attachments:
            fn = self._resolve(attachment, table)
            bound = Bound(attachment.hook, fn, dict(attachment.params))
            for event in attachment.events:
                index.setdefault(event, []).append(bound)
        self.table = table
        self.index = {k: tuple(v) for k, v in index.items()}
        unattached = sorted(set(table) - {a.hook for a in self.declaration.attachments})
        if unattached:
            logger.warning(
                "%s: registered but attached to no event, so %s will never run; add an "
                "entry under `%s.lifecycle`",
                ", ".join(unattached),
                "they" if len(unattached) > 1 else "it",
                CONFIG_KEY,
            )
        return self

    @staticmethod
    def _resolve(
        attachment: Attachment, table: Mapping[str, LifecycleFn]
    ) -> LifecycleFn:
        if attachment.hook in table:
            return table[attachment.hook]
        shipped = SHIPPED.get(attachment.hook)
        if shipped is not None and not attachment.hook.startswith(EXTENSION_PREFIX):
            return shipped.fn
        raise HooksConfigError(
            f"`{CONFIG_KEY}.lifecycle` names {attachment.hook!r}, which no declared "
            f"module registered; registered hooks are: "
            f"{', '.join(sorted(table)) or '(none)'}"
        )

    @property
    def events(self) -> Tuple[str, ...]:
        return tuple(sorted(self.index))

    # -- dispatch (the emitting thread) --------------------------------------------

    def dispatch(self, record: Mapping[str, Any]) -> bool:
        """Queue ``record`` for its hooks. Never blocks, never raises.

        Returns whether it was queued. Not queued: a record of the hook system's
        own domain, one no attachment matches, or one emitted **on the worker
        thread** — i.e. by a hook, directly or through anything the-loop does on its
        behalf — which is the re-entrancy guard.
        """
        event = str(record.get("event", ""))
        if event.startswith(OWN_DOMAIN) or event not in self.index:
            return False
        worker = self._worker
        if worker is not None and threading.current_thread() is worker:
            return False
        with self._lock:
            try:
                self._queue.put_nowait(dict(record))
            except queue.Full:
                self.dropped += 1
                first = not self._dropping
                self._dropping = True
                queued = False
            else:
                self._outstanding += 1
                self._dropping = False
                first = False
                queued = True
                self._ensure_worker()
        if first:
            # Its own domain, so it is written and never queued — no recursion.
            _emit("hooks.dropped", "warning", on=event, capacity=self.capacity)
        return queued

    def _ensure_worker(self) -> None:
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(
                target=self._run, name="the-loop-hooks", daemon=True
            )
            self._worker.start()

    # -- the worker --------------------------------------------------------------

    def _run(self) -> None:
        while True:
            record = self._queue.get()
            if record is None:
                self._queue.task_done()
                return
            try:
                self._deliver(record)
            finally:
                self._queue.task_done()
                with self._lock:
                    self._outstanding -= 1
                    if self._outstanding <= 0:
                        self._idle.notify_all()

    def _deliver(self, record: Mapping[str, Any]) -> None:
        event = str(record.get("event", ""))
        for bound in self.index.get(event, ()):
            context = LifecycleEvent.from_record(record, bound.params, self.instance)
            try:
                result = bound.fn(context)
            except BaseException as exc:  # noqa: BLE001 — a hook never stops the-loop
                _emit(
                    "hooks.failed",
                    "warning",
                    hook=bound.name,
                    on=event,
                    error=f"{exc.__class__.__name__}: {exc}",
                )
                continue
            if isinstance(result, HookResult):
                if result.status == BLOCK:
                    _emit(
                        "hooks.failed",
                        "warning",
                        hook=bound.name,
                        on=event,
                        error="; ".join(m.render() for m in result.messages)
                        or "blocked",
                    )
                elif result.messages:
                    logger.debug("%s on %s: %s", bound.name, event, result.render())

    # -- lifetime ------------------------------------------------------------

    def drain(self, timeout: float = EXIT_DRAIN_SECONDS) -> bool:
        """Wait until every queued record has been handled, or ``timeout``."""
        with self._idle:
            return self._idle.wait_for(lambda: self._outstanding <= 0, timeout=timeout)

    def close(self, timeout: float = EXIT_DRAIN_SECONDS) -> None:
        drained = self.drain(timeout)
        worker = self._worker
        if worker is not None and worker.is_alive():
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
            if drained:
                worker.join(timeout=timeout)


# -- process-wide install (what the event log calls) -------------------------------

_active: Optional[LifecycleHooks] = None
_digest: str = ""
_atexit_registered = False


def _emit(name: str, level: str, **fields: Any) -> None:
    from . import eventlog

    eventlog.emit(name, level=level, **fields)


def _instance_name(cli_config: Mapping[str, Any]) -> str:
    instance = cli_config.get("instance")
    if isinstance(instance, Mapping):
        return str(instance.get("name") or "")
    return ""


def install(
    cli_config: Mapping[str, Any], config_path: Union[str, Path, None]
) -> Optional[LifecycleHooks]:
    """Load the ``hooks`` block and register the runtime as an event-log sink.

    Returns ``None`` — and registers nothing — for an empty declaration. Idempotent
    for an unchanged declaration; a changed one replaces the runtime. Raises
    :class:`HooksConfigError` for anything that cannot be honoured, and the caller
    (an entry point) lets it propagate: nothing degrades to "no hooks".
    """
    global _active, _digest, _atexit_registered
    from . import eventlog

    declaration = read_declaration(cli_config)
    if declaration.empty:
        reset()
        return None
    digest = declaration.digest()
    if _active is not None and digest == _digest:
        return _active
    root = Path(config_path).resolve().parent if config_path else Path.cwd()
    runtime = LifecycleHooks(declaration, root, _instance_name(cli_config)).load()
    if _active is not None:
        eventlog.remove_sink(_active.dispatch)
        _active.close(0.0)
    _active, _digest = runtime, digest
    eventlog.add_sink(runtime.dispatch)
    if not _atexit_registered:
        atexit.register(drain, EXIT_DRAIN_SECONDS)
        _atexit_registered = True
    _emit(
        "hooks.loaded",
        "info",
        modules=len(declaration.modules),
        attachments=len(declaration.attachments),
        events=len(runtime.events),
    )
    return runtime


def active() -> Optional[LifecycleHooks]:
    return _active


def drain(timeout: float = EXIT_DRAIN_SECONDS) -> bool:
    """Wait for the installed runtime to finish what it has queued (exit, tests)."""
    return _active.drain(timeout) if _active is not None else True


def reset() -> None:
    """Forget the installed runtime (tests; and an empty re-install)."""
    global _active, _digest
    if _active is not None:
        from . import eventlog

        eventlog.remove_sink(_active.dispatch)
        _active.close(0.0)
    _active, _digest = None, ""
