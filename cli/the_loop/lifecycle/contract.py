"""The lifecycle hook contract (issue-344): seven typed points a hook may change.

A **graph hook** (:mod:`the_loop.graph`) is a check at a node boundary — it answers
"is this gate satisfied?". A **lifecycle hook** is something else: code the operator
attaches to the moments a work item's *delivery* turns — a start is accepted, a session
is about to launch, the loop waits on a person, the phase changes, the ticket closes —
and at each of those moments the-loop **asks before it acts**.

The model is sherma's (https://madarauchiha-314.github.io/sherma/hooks.html): one
typed context per point, one method per point on a base class, and the rule that a
method returns ``None`` to pass the context through unchanged or a context to replace
it. Two things are the-loop's own:

* **Facts and decisions.** A context is read-only facts plus a handful of marked
  *decision* fields (``proceed``, ``prompt``, ``announce``, ``question``, ``notify``…).
  The-loop reads back the decisions and nothing else, so a hook — local or remote —
  can change what the moment decides and cannot redirect what the moment is about.
* **Not the event log.** The first attempt at this ticket (PR #357) made every
  event-log type an attach point. An event is a record of something already done; a
  hook on one can never change it. These seven points are chosen by what delivery *is*,
  and adding one is a reviewed edit to this file, held together by a parity test
  against :class:`LifecycleHooks` and the documentation.

Spec: docs/specs/issue-344/  ·  Decision: 137
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, fields
from typing import (
    Any,
    ClassVar,
    Dict,
    List,
    Mapping,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from ..sessions.registry import WorkItemRef

__all__ = [
    "POINTS",
    "Context",
    "DecisionTypeError",
    "InputReceived",
    "LifecycleHooks",
    "WorkItem",
    "PhaseChanged",
    "SessionSpawn",
    "SessionSpawned",
    "WaitingForInput",
    "WorkItemComplete",
    "WorkItemStart",
    "describe",
]


C = TypeVar("C", bound="Context")


class DecisionTypeError(TypeError):
    """A decision was set to a value of the wrong type — refused, never coerced."""


def decision(default: Any) -> Any:
    """A field the-loop reads back after the hooks ran. Everything else is a fact."""
    if isinstance(default, list):
        return field(default_factory=list, metadata={"decision": True})
    return field(default=default, metadata={"decision": True})


#: ``kind`` of a :class:`WorkItem` that is a pull request (the dispatcher's vocabulary).
KIND_PULL_REQUEST = "pull-request"
KIND_ISSUE = "issue"


@dataclass(frozen=True)
class WorkItem:
    """The work item a point is about — the-loop's core entity, as a hook sees it.

    Built by the-loop from its provider-qualified ref (:class:`WorkItemRef`), never by a
    hook: every field is a fact. ``ref`` is the machine's name and keys everything (the
    registry, the state, the events); the rest is that name taken apart, plus what the
    point knows of the item's shape. Travels as one JSON object inside the context.
    """

    #: ``<provider>:[<host>/]<owner>/<repo>#<number>`` — the-loop's name for the item.
    ref: str = ""
    #: The tracker: ``github`` today (``jira`` is reserved for the Jira follow-up).
    provider: str = ""
    #: The tracker's host — ``github.com``, or a GitHub Enterprise host.
    host: str = ""
    owner: str = ""
    repo: str = ""
    #: ``owner/repo``, host-qualified when the host is not the provider's default.
    repository: str = ""
    number: int = 0
    #: ``issue`` | ``pull-request``; ``""`` when the point does not know.
    kind: str = ""
    #: The browser link, derived from the ref; ``""`` when none can be derived.
    url: str = ""
    #: The-loop's id for it — ``issue-<number>``, the spec folder under ``docs/specs/``.
    id: str = ""

    @classmethod
    def from_ref(
        cls, ref: Union[str, WorkItemRef], kind: str = "", id: str = ""
    ) -> "WorkItem":
        """The item a ref names, with what the caller knows of its ``kind`` and ``id``.

        A string that is not a provider-qualified ref — the bare ``issue-N`` a graph verb
        was given — yields an opaque item: ``ref`` and ``id`` kept, the rest empty. A fact
        for the hooks is never a fault for the operation.
        """
        try:
            parsed = ref if isinstance(ref, WorkItemRef) else WorkItemRef.parse(ref)
        except ValueError:
            return cls(ref=str(ref), kind=kind, id=id or str(ref))
        url = parsed.url
        if kind == KIND_PULL_REQUEST and url:
            url = url.replace("/issues/", "/pull/", 1)
        return cls(
            ref=parsed.ref,
            provider=parsed.provider,
            host=parsed.host,
            owner=parsed.owner,
            repo=parsed.repo,
            repository=parsed.path,
            number=parsed.number,
            kind=kind,
            url=url,
            id=id or parsed.spec_id or parsed.ref,
        )

    def to_params(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_params(cls, params: Mapping[str, Any]) -> "WorkItem":
        """A work item from its JSON object: known keys only, each of its declared type
        (``number`` an ``int``, the rest ``str``); absent keys keep their defaults."""
        known = {f.name for f in fields(cls)}
        values: Dict[str, Any] = {}
        for name, value in params.items():
            if name not in known:
                continue
            if name == "number":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise TypeError(
                        f"work_item.number must be int, got {type(value).__name__}"
                    )
            elif not isinstance(value, str):
                raise TypeError(
                    f"work_item.{name} must be str, got {type(value).__name__}"
                )
            values[name] = value
        return cls(**values)

    def __bool__(self) -> bool:
        return bool(self.ref)


#: The Python type each declared field annotation admits.
_TYPES: Dict[str, type] = {
    "str": str,
    "bool": bool,
    "List[str]": list,
    "WorkItem": WorkItem,
}


@dataclass
class Context:
    """The base of every point's context: the work item it is about, and the machinery
    that serialises it, applies decisions from a hook's answer, and names them.

    Not a point itself — instantiating it raises. Every point subclasses it, sets
    :attr:`POINT` and :attr:`FIRES`, and declares its fields.
    """

    #: The point's name — the method on :class:`LifecycleHooks` and the JSON-RPC method.
    POINT: ClassVar[str] = ""
    #: One sentence: when the point fires, for the report and the docs.
    FIRES: ClassVar[str] = ""

    #: The work item the point is about — a fact every point carries, as one object.
    work_item: WorkItem = field(default_factory=WorkItem)

    def __post_init__(self) -> None:
        if not type(self).POINT:
            raise TypeError("Context is abstract; instantiate a point's context")

    # -- introspection ------------------------------------------------------------

    @classmethod
    def decisions(cls) -> Tuple[str, ...]:
        """The fields a hook may change, in declaration order."""
        return tuple(f.name for f in fields(cls) if f.metadata.get("decision"))

    @classmethod
    def facts(cls) -> Tuple[str, ...]:
        return tuple(f.name for f in fields(cls) if not f.metadata.get("decision"))

    # -- serialisation --------------------------------------------------------------

    def to_params(self) -> Dict[str, Any]:
        """Every field as JSON-ready values — what a remote executor receives."""
        out: Dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, WorkItem):
                out[f.name] = value.to_params()
            else:
                out[f.name] = list(value) if isinstance(value, list) else value
        return out

    @classmethod
    def from_params(cls: Type[C], params: Mapping[str, Any]) -> C:
        """Build a context from a mapping, ignoring unknown keys (forward compatibility)
        and filling absent fields with their defaults. A known field of the wrong type
        raises :class:`TypeError` naming it."""
        known = {f.name: f for f in fields(cls)}
        values: Dict[str, Any] = {}
        for name, value in params.items():
            f = known.get(name)
            if f is None:
                continue
            values[name] = _checked(name, str(f.type), value)
        return cls(**values)

    # -- decisions ----------------------------------------------------------------------

    def apply(self, result: Mapping[str, Any]) -> Tuple[str, ...]:
        """Copy the **decision** fields of ``result`` onto this context.

        Facts and unknown keys are ignored — a hook's answer changes what the moment
        decides, never what it is about. Every decision is type-checked **before** any
        is written, so a malformed answer changes nothing (R2.4). Returns the names of
        the decisions whose value actually changed.
        """
        staged: List[Tuple[str, Any]] = []
        for f in fields(self):
            if not f.metadata.get("decision") or f.name not in result:
                continue
            value = _checked(f.name, str(f.type), result[f.name], DecisionTypeError)
            if value != getattr(self, f.name):
                staged.append((f.name, value))
        for name, value in staged:
            setattr(self, name, value)
        return tuple(name for name, _ in staged)

    def copy_decisions_from(self, other: "Context") -> Tuple[str, ...]:
        """Take another context's decisions — what a local hook that returned a
        (possibly rebuilt) context decided. It must be the same point's context."""
        if type(other) is not type(self):
            raise TypeError(
                f"a {type(self).POINT} hook returned a {type(other).__name__}; "
                f"return the {type(self).__name__} it was given, or None"
            )
        return self.apply({name: getattr(other, name) for name in self.decisions()})


def _checked(name: str, declared: str, value: Any, error: type = TypeError) -> Any:
    """``value`` if it is of the declared type (``bool`` is not an ``int`` here)."""
    expected = _TYPES.get(declared)
    if expected is None:  # pragma: no cover — every field is declared with a known type
        raise error(f"field {name!r} has an undeclared type {declared!r}")
    if expected is WorkItem:
        if isinstance(value, WorkItem):
            return value
        try:
            if isinstance(value, Mapping):
                return WorkItem.from_params(value)
            if isinstance(value, str):
                return WorkItem.from_ref(value)
        except (TypeError, ValueError) as exc:
            raise error(f"{name!r}: {exc}") from exc
    elif expected is bool:
        if isinstance(value, bool):
            return value
    elif expected is str:
        if isinstance(value, str):
            return value
    elif isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    raise error(f"{name!r} must be {declared}, got {type(value).__name__} ({value!r})")


# -- the seven points ----------------------------------------------------------------


@dataclass
class WorkItemStart(Context):
    """A start of this work item's delivery was accepted — an authorized ``the-loop
    start`` (or an arming command, or a label-alone spawn) — and the-loop is about to
    prepare its workspace. Fires **once per arming**, before any session exists.

    Decisions: ``proceed`` — ``False`` refuses the start: the work item is disarmed,
    one marked comment on the ticket names the hook and the ``reason``, the event is
    settled and not retried.
    """

    POINT: ClassVar[str] = "work_item_start"
    FIRES: ClassVar[str] = (
        "once per arming, when a start is accepted and before the workspace is "
        "prepared or any session exists"
    )

    #: The loop the item will walk (``pdlc-work-item-loop``, ``pdlc-adhoc-loop``, one
    #: of the operator's own); ``""`` when the daemon could not resolve it.
    loop: str = ""
    #: The arming command (``start``, ``contribute``, ``do``, ``review``, an operator's
    #: word); ``""`` for a label-alone spawn.
    command: str = ""
    #: The login that armed it (or the event's actor when no command was recorded).
    actor: str = ""
    #: The harness the session will run on (``claude`` | ``cursor``).
    harness: str = ""
    #: This instance's name (``routing.instance.name``), ``""`` when unnamed.
    instance: str = ""
    proceed: bool = decision(True)
    reason: str = decision("")


@dataclass
class SessionSpawn(Context):
    """A harness session is about to be launched for this work item or one of its pull
    requests — the first spawn, a pull request's own session, or a respawn after a dead
    one — with the prompt rendered and the adapter resolved.

    Decisions: ``prompt`` — the text the harness boots on, replaced by what the hook
    returns; ``proceed`` — ``False`` prevents the launch (a pull request's session then
    falls back to delivery into the work item's session).
    """

    POINT: ClassVar[str] = "session_spawn"
    FIRES: ClassVar[str] = (
        "before every harness launch — a first spawn, a pull request's own session, a "
        "respawn — with the prompt rendered"
    )

    #: The conversation being launched: the work item itself, or one of its pull requests.
    endpoint: WorkItem = field(default_factory=WorkItem)
    harness: str = ""
    #: The checkout the session runs in.
    cwd: str = ""
    #: The frozen model and effort (``""`` when the work item chose none).
    model: str = ""
    effort: str = ""
    #: The harness argv the launch adds.
    harness_args: List[str] = field(default_factory=list)
    #: True when this replaces a session found dead.
    respawn: bool = False
    loop: str = ""
    prompt: str = decision("")
    proceed: bool = decision(True)
    reason: str = decision("")


@dataclass
class SessionSpawned(Context):
    """A harness session was launched and registered. Fires before the-loop posts its
    "session exists, attach here" comment.

    Decisions: ``announce`` — ``False`` skips that comment.
    """

    POINT: ClassVar[str] = "session_spawned"
    FIRES: ClassVar[str] = (
        "after the session is registered and before the-loop announces it on the ticket"
    )

    endpoint: WorkItem = field(default_factory=WorkItem)
    harness: str = ""
    harness_session_id: str = ""
    tmux_target: str = ""
    cwd: str = ""
    model: str = ""
    effort: str = ""
    harness_args: List[str] = field(default_factory=list)
    respawn: bool = False
    announce: bool = decision(True)


@dataclass
class WaitingForInput(Context):
    """The loop is about to wait on a person: an agent asked a question (``the-loop
    ask``, ``kind = question``) or the graph entered a human gate (``kind = gate``).

    Decisions: ``question`` and ``summary`` — the text published for an agent's
    question; for a gate the request text is the graph's, so both are empty and a
    change is ignored.
    """

    POINT: ClassVar[str] = "waiting_for_input"
    FIRES: ClassVar[str] = (
        "before an agent's question is posted, and when a human gate is entered"
    )

    #: ``question`` (an agent's ``the-loop ask``) or ``gate`` (a human node entered).
    kind: str = ""
    #: The graph node, for a gate.
    node: str = ""
    #: Who is asking: the local actor for a question, ``""`` for a gate.
    actor: str = ""
    loop: str = ""
    question: str = decision("")
    summary: str = decision("")


@dataclass
class InputReceived(Context):
    """A person's input reached the loop — an answer to the session (``the-loop reply``,
    the API, a channel), a comment or review about to be delivered into the session, or
    a control command (``start``, ``stop``, ``execute``…) — and the-loop is about to act
    on it. The counterpart of ``waiting_for_input``: fires before the delivery, before a
    human gate reads the comment, before the command runs.

    Decisions: ``text`` — what is delivered: an answer as-is, a comment's body as the
    session is shown it; ignored for a command. ``proceed`` — ``False`` drops the input:
    an answer is refused to its caller, a comment is not delivered (one marked comment on
    the ticket names the ``reason``, the event is settled), a command is rejected
    (``control.rejected``, reason ``input-refused``).
    """

    POINT: ClassVar[str] = "input_received"
    FIRES: ClassVar[str] = (
        "when a person's input reaches the loop — an answer, a comment or review to "
        "deliver, a control command — before the-loop acts on it"
    )

    #: ``answer`` (a reply to the session) | ``comment`` (a comment or review to deliver)
    #: | ``command`` (a control word).
    kind: str = ""
    #: The login that wrote it, or the actor the verb was given.
    actor: str = ""
    #: ``comment`` (the ticket or pull request, by webhook or poll) | ``verb`` (the-loop's
    #: own reply and control verbs: the CLI, the API, a channel).
    source: str = ""
    #: The control word, for a command (``start``, ``stop``, ``pause``, ``execute``…).
    command: str = ""
    #: The GitHub event, for a comment (``issue_comment``, ``pull_request_review``…).
    event: str = ""
    #: The conversation the input lands in: the work item's, or a pull request's; empty
    #: for a command.
    endpoint: WorkItem = field(default_factory=WorkItem)
    loop: str = ""
    text: str = decision("")
    proceed: bool = decision(True)
    reason: str = decision("")


@dataclass
class PhaseChanged(Context):
    """The graph moved the work item's phase — the ``loop:<phase>`` label changed, or a
    terminal node was reached. Fires before the channels are told.

    Decisions: ``notify`` — ``False`` skips the ``phase.*`` lifecycle publish to the
    channels for this transition.
    """

    POINT: ClassVar[str] = "phase_changed"
    FIRES: ClassVar[str] = (
        "when the phase label changes or a terminal node is reached, before the "
        "channels are told"
    )

    loop: str = ""
    from_node: str = ""
    to_node: str = ""
    from_phase: str = ""
    to_phase: str = ""
    #: The outcome that routed the edge (``pass``, ``approved``…); ``""`` at the start.
    outcome: str = ""
    #: The entered node's actor (``agent`` | ``human``).
    actor: str = ""
    #: True when the entered node is terminal — the loop is complete.
    terminal: bool = False
    notify: bool = decision(True)


@dataclass
class WorkItemComplete(Context):
    """The ticket or pull request that *is* this work item closed or merged. Fires
    before the closure is announced on the channels.

    Decisions: ``announce`` — ``False`` skips the ``work-item.closed`` publish.
    """

    POINT: ClassVar[str] = "work_item_complete"
    FIRES: ClassVar[str] = (
        "when the ticket or pull request that is the work item closes, before the "
        "closure is announced"
    )

    #: ``merged`` | ``closed``.
    state: str = ""
    #: ``issue`` | ``pull-request``.
    kind: str = ""
    #: The dispatcher's reason (``pr-merged``, ``issue-closed``…).
    reason: str = ""
    #: ``webhook`` | ``poll``.
    source: str = ""
    actor: str = ""
    loop: str = ""
    announce: bool = decision(True)


#: The catalog — the only names a declaration's ``on`` may use, in lifecycle order.
POINTS: Dict[str, Type[Context]] = {
    cls.POINT: cls
    for cls in (
        WorkItemStart,
        SessionSpawn,
        SessionSpawned,
        WaitingForInput,
        InputReceived,
        PhaseChanged,
        WorkItemComplete,
    )
}


class LifecycleHooks:
    """Subclass this and override the points you care about.

    Each method receives that point's context. Return ``None`` to pass it through
    unchanged, or return the context (edited in place, or a rebuilt one of the same
    type) to change its **decisions** — the-loop reads back nothing else. Executors
    run in the order the CLI config declares them; each sees the decisions of the ones
    before it. A method that raises is recorded (``hooks.failed``) and skipped; the
    operation proceeds unless the entry is ``required`` and the point has ``proceed``.

    The same class runs in-process (``module:``/``path:`` in the CLI config) or behind
    :class:`~the_loop.lifecycle.remote.HookServer` (``url:``), unchanged.
    """

    def work_item_start(self, ctx: WorkItemStart) -> Optional[WorkItemStart]:
        return None

    def session_spawn(self, ctx: SessionSpawn) -> Optional[SessionSpawn]:
        return None

    def session_spawned(self, ctx: SessionSpawned) -> Optional[SessionSpawned]:
        return None

    def waiting_for_input(self, ctx: WaitingForInput) -> Optional[WaitingForInput]:
        return None

    def input_received(self, ctx: InputReceived) -> Optional[InputReceived]:
        return None

    def phase_changed(self, ctx: PhaseChanged) -> Optional[PhaseChanged]:
        return None

    def work_item_complete(self, ctx: WorkItemComplete) -> Optional[WorkItemComplete]:
        return None

    def handles(self, point: str) -> bool:
        """Whether this class overrides ``point`` — what a local executor runs by default."""
        if point not in POINTS:
            return False
        return getattr(type(self), point) is not getattr(LifecycleHooks, point)


def describe() -> List[Dict[str, Any]]:
    """The catalog as rows — for ``the-loop hooks points`` and the docs."""
    rows = []
    for point, cls in POINTS.items():
        doc = (cls.__doc__ or "").strip().split("\n\n")[0]
        rows.append(
            {
                "point": point,
                "context": cls.__name__,
                "fires": cls.FIRES,
                "facts": list(cls.facts()),
                "decisions": list(cls.decisions()),
                "summary": " ".join(doc.split()),
            }
        )
    return rows


def _replace(ctx: Context, **changes: Any) -> Context:  # pragma: no cover — helper
    return dataclasses.replace(ctx, **changes)
