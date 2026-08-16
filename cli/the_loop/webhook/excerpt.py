"""The event excerpt: what a session is told about the event it just received.

A pure ``(event, payload) -> str`` of the same family as
:mod:`the_loop.webhook.router`'s extractors — no I/O, unit-testable per event
type — moved out of :mod:`the_loop.webhook.dispatcher` in issue-243.

**A field allow-list, not a payload subset.** Until issue-243 this copied whole
container objects (``comment``, ``issue``, ``sender``, …) out of the webhook
payload and cut the result at 4,000 characters. Measured on an ordinary comment,
that delivered a 61-character instruction inside a 4,014-character excerpt whose
cut landed mid-string, so the "JSON" a session received did not parse
(``docs/specs/issue-243/evidence/baseline.md``). A comment needs its **body** and
its **address**; its URL already names the issue or pull request it lives on.

Three properties come from the allow-list shape, and they are why it is not a
deny-list of noisy keys:

* GitHub adds fields to these objects routinely, and an allow-list does not
  re-inflate when it does.
* Free text is capped **per field**, before the dump, so truncation can never
  take a URL, an anchor, or the JSON's own structure.
* Every attacker-controlled string that reaches an agent's prompt is one of a
  fixed, named few — the trust boundary is narrower than it was, and visible
  here in one table.

Nothing *acts* on this text. Routing, authorization, control parsing, reaction
targeting and head-ref resolution all read the full ``RoutedEvent.payload``; this
is the prose a model reads, and it fails **safe** (an unrecognised shape costs
context, never the delivery of an event a human already authorized).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional, Tuple

from .router import event_actor

#: Per-field cap on free text (a body, a description, a check-run summary). The
#: field alone is truncated, so the surrounding JSON stays parseable (R3.1/R3.2).
TEXT_MAX_CHARS = 3_500

#: Defensive backstop on the whole rendered excerpt. With the caps above, only a
#: pathological payload (hundreds of labels) can reach it.
EXCERPT_MAX_CHARS = 4_000

_TRUNCATED = "… (truncated)"

#: Fields carried per container, **in emission order**. Order is a guarantee, not
#: cosmetics: an inline comment's ``path``/``line`` precede its ``body`` so the
#: anchor that makes the instruction actionable is never the thing a cap takes
#: (issue-246).
_CONTAINERS: Dict[str, Tuple[str, ...]] = {
    "comment": ("path", "line", "body", "html_url"),
    "review": ("state", "body", "html_url"),
    "issue": ("number", "title", "state", "html_url"),
    "pull_request": ("number", "title", "state", "draft", "merged", "html_url"),
    "label": ("name",),
    "workflow_run": (
        "name",
        "event",
        "status",
        "conclusion",
        "head_branch",
        "html_url",
    ),
    "check_run": (
        "name",
        "status",
        "conclusion",
        "output",
        "html_url",
        "details_url",
    ),
    "check_suite": ("status", "conclusion", "head_branch", "head_sha"),
}

#: Which containers each event is *about*. An ``issue_comment`` deliberately
#: drops the ``issue``: the comment's own URL names it, and the prompt's first
#: line already names the work item.
_EVENT_CONTAINERS: Dict[str, Tuple[str, ...]] = {
    "issue_comment": ("comment",),
    "pull_request_review_comment": ("comment",),
    "pull_request_review": ("review",),
    "issues": ("issue", "label"),
    "pull_request": ("pull_request", "label"),
    "pull_request_review_thread": ("pull_request",),
    "workflow_run": ("workflow_run",),
    "check_run": ("check_run",),
    "check_suite": ("check_suite",),
}

#: Events whose data sits at the payload root rather than in a container.
_ROOT_FIELDS: Dict[str, Tuple[str, ...]] = {
    "status": ("state", "context", "description", "target_url"),
}

#: Fields whose value is free text an untrusted actor wrote: capped (R3.1).
_TEXT_FIELDS = frozenset({"body", "description", "summary"})

#: Nested objects carried whole, distilled by the same rules.
_NESTED: Dict[str, Tuple[str, ...]] = {
    "output": ("title", "summary"),
}

#: Containers whose ``user`` means "who wrote this". An ``issue``'s user is
#: whoever *opened* it, which is not who acted — those events carry a top-level
#: ``actor`` instead, so nobody reads an opener as the person to reply to.
_AUTHORED = frozenset({"comment", "review"})

#: Events whose acting login is not the author of any carried object — a
#: lifecycle action is taken by the ``sender``.
_ACTOR_EVENTS = frozenset({"issues", "pull_request", "pull_request_review_thread"})


def _text(value: str, budget: int) -> str:
    """``value`` capped at ``budget``, with the marker inside the string (R3.1)."""
    if len(value) <= budget:
        return value
    return value[:budget] + _TRUNCATED


def _field(name: str, value: Any, budget: int) -> Any:
    """One carried value, capped or recursed as its name requires."""
    if isinstance(value, str) and name in _TEXT_FIELDS:
        return _text(value, budget)
    if name in _NESTED and isinstance(value, Mapping):
        return _pick(value, _NESTED[name], budget)
    return value


def _pick(obj: Mapping, fields: Tuple[str, ...], budget: int) -> Dict[str, Any]:
    """``fields`` of ``obj``, in order, skipping what is absent or ``None``."""
    picked: Dict[str, Any] = {}
    for name in fields:
        value = obj.get(name)
        if value is None:
            continue  # an explicit "line": null says nothing absence does not
        picked[name] = _field(name, value, budget)
    return picked


def _author(obj: Mapping) -> Optional[str]:
    """``obj``'s author as a bare login (R1.5) — never GitHub's user object."""
    user = obj.get("user")
    if not isinstance(user, Mapping):
        return None
    login = user.get("login")
    return login if isinstance(login, str) and login else None


def _container(payload: Mapping, key: str, budget: int) -> Optional[Dict[str, Any]]:
    """The distilled ``key`` container of ``payload``, or ``None`` if it has none.

    A missing, ``None`` or wrong-typed container yields ``None`` rather than
    raising: a payload shape the-loop has not seen must not cost an authorized
    event its delivery (R2.7).
    """
    obj = payload.get(key)
    if not isinstance(obj, Mapping):
        return None
    distilled = _pick(obj, _CONTAINERS[key], budget)
    if key in _AUTHORED:
        author = _author(obj)
        if author:
            distilled["author"] = author
    return distilled or None


def _containers_for(event: str, payload: Mapping) -> Tuple[str, ...]:
    """Which containers to read for ``event``.

    An event with no rule of its own — an operator's extra ``routing.events``
    entry, or the legacy no-event call — reads every container it happens to
    carry, so it is distilled rather than dumped raw (R2.6).
    """
    named = _EVENT_CONTAINERS.get(event)
    if named is not None:
        return named
    return tuple(key for key in _CONTAINERS if key in payload)


def _distil(event: str, payload: Mapping, budget: int) -> Dict[str, Any]:
    """The whole excerpt as a structure, with free text capped at ``budget``."""
    distilled: Dict[str, Any] = {}

    root = _ROOT_FIELDS.get(event)
    if root:
        distilled.update(_pick(payload, root, budget))

    if event in _ACTOR_EVENTS:
        # The lifecycle actor is the sender, and `event_actor` is already the one
        # definition of "who is responsible for this event" — the same one
        # authorization judges by.
        actor = event_actor(event, dict(payload))
        if actor:
            distilled["actor"] = actor

    for key in _containers_for(event, payload):
        carried = _container(payload, key, budget)
        if carried:
            distilled[key] = carried
    return distilled


def event_excerpt(event: str, payload: dict) -> str:
    """The distilled, JSON-formatted summary of ``event`` for a prompt.

    Total by construction: it raises nothing, and renders ``"{}"`` for a payload
    it recognises nothing in.
    """
    if not isinstance(payload, Mapping):
        return "{}"

    budget = TEXT_MAX_CHARS
    text = json.dumps(_distil(event, payload, budget), indent=2, default=str)
    # JSON escaping inflates what a cap measured in *characters* renders as — a
    # body of newlines doubles. Halve the text budget until the rendered excerpt
    # fits, so the size limit is enforced by shortening prose rather than by
    # cutting the document in half (which is exactly what made the old excerpt
    # unparseable). Terminates: the budget strictly decreases toward zero, and
    # the structure around the text is a few hundred characters at most.
    while len(text) > EXCERPT_MAX_CHARS and budget > 0:
        budget //= 2
        text = json.dumps(_distil(event, payload, budget), indent=2, default=str)
    if len(text) > EXCERPT_MAX_CHARS:  # no free text left to give: a pathological shape
        text = text[:EXCERPT_MAX_CHARS] + "\n" + _TRUNCATED
    return text


def payload_excerpt(payload: dict) -> str:
    """Distil without an event name — the shape callers outside the-loop import."""
    return event_excerpt("", payload)
