"""The message plan and the one delivery step (issue-549, task 9).

The Slack channel decides *what* an event becomes in three pure stages — the
room policy, placement (:mod:`the_loop.channels.placement`) and the two builders
(:mod:`the_loop.channels.shortform`, :mod:`the_loop.channels.render`) — and
writes the outcome down here as a :class:`MessagePlan`: the top message (the
short form, with its buttons) and the long form's parts, in order, each one
Slack ``markdown`` block.

:func:`deliver` is the only code that turns a plan into Slack calls
(design.md § Architecture, stage 4):

* the top message first, then each part as a thread reply, in order
  (non-functional: order);
* every ``chat.postMessage`` sets ``unfurl_links=False`` and
  ``unfurl_media=False`` (R5). ``chat.update`` takes no such flags; an edit is
  only ever made to a message this step posted with them;
* each posted ``ts`` is handed to ``record`` **before** the next call, so a
  replay of the same event (same event id) posts only what is missing
  (non-functional: idempotent retries);
* a Slack 429 waits for ``Retry-After`` and retries the same message; it never
  skips one. After :data:`RATE_LIMIT_ATTEMPTS` the delivery fails as a whole and
  the outbox replays it later, resuming after the last message that landed.

No disk, no state: the caller passes what was already posted and a recorder.
Logs carry event ids, conversation ids and counts, never message text.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .base import ChannelError

__all__ = [
    "RATE_LIMIT_ATTEMPTS",
    "THREAD_OF_TOP",
    "Delivered",
    "MessagePlan",
    "PlannedMessage",
    "deliver",
    "markdown_block",
    "plan_message",
    "post_message",
    "retry_after",
    "summary_of",
]

logger = logging.getLogger("the-loop.channels")

#: A part's ``thread_ts`` that means "the thread of this plan's top message",
#: resolved once the top message's ``ts`` is known (a declared room, R4.1).
THREAD_OF_TOP = "@top"

#: How many times one message is tried while Slack answers 429. Past it the
#: delivery fails; the outbox replays it and the memory resumes it (never skips).
RATE_LIMIT_ATTEMPTS = 5

#: The wait when a 429 names no ``Retry-After`` (the gateway passes Slack's body,
#: not its headers).
DEFAULT_RETRY_AFTER_S = 1.0

#: The longest single wait honoured, so a malformed header cannot park the worker.
MAX_RETRY_AFTER_S = 60.0


@dataclass(frozen=True)
class PlannedMessage:
    """One Slack message of a plan: its ``text`` fallback (the short form, R2.7),
    its blocks, and where it goes — ``""`` top-level, a thread ``ts``, or
    :data:`THREAD_OF_TOP`."""

    text: str
    blocks: Tuple[Mapping[str, Any], ...]
    thread_ts: str = ""


@dataclass(frozen=True)
class MessagePlan:
    """What one event becomes in one conversation.

    ``top`` is the short message; ``parts`` the long form's thread replies, in
    order (empty in the central channel, R4.2). ``edit_ts`` set means the top
    message edits the message at that ts (the room policy's progress-edit, R6)
    rather than posting a new one; ``edit_parts`` are then the long-form replies
    that message holds today, edited in place, deleted when surplus (R6.2).
    ``short_source`` and ``tables_as_code`` are for the delivery log only.
    """

    event_id: str
    channel: str
    top: PlannedMessage
    parts: Tuple[PlannedMessage, ...] = ()
    edit_ts: str = ""
    edit_parts: Tuple[str, ...] = ()
    short_source: str = ""
    tables_as_code: int = 0


@dataclass(frozen=True)
class Delivered:
    """What a conversation holds for one event after :func:`deliver`: the top
    message's ts and each part's, in order. ``calls`` counts the Slack calls this
    delivery made (zero for a full replay)."""

    channel: str
    top: str = ""
    parts: Tuple[str, ...] = ()
    calls: int = 0
    edited: bool = False


def markdown_block(text: str) -> Dict[str, Any]:
    """One long-form part as Slack's ``markdown`` block: standard markdown, drawn
    by Slack itself (R2.1)."""
    return {"type": "markdown", "text": text}


def plan_message(
    *,
    event_id: str,
    channel: str,
    short_text: str,
    short_blocks: Sequence[Mapping[str, Any]],
    top_thread: str = "",
    parts: Sequence[str] = (),
    parts_thread: str = "",
    edit_ts: str = "",
    edit_parts: Sequence[str] = (),
    short_source: str = "",
    tables_as_code: int = 0,
) -> MessagePlan:
    """The plan: the short message at ``top_thread``, then each of ``parts`` as a
    ``markdown`` block at ``parts_thread``. Every message's ``text`` fallback is
    the short form (R2.7). No ``parts_thread`` means no long form is posted."""
    planned = (
        tuple(
            PlannedMessage(short_text, (markdown_block(part),), parts_thread)
            for part in parts
        )
        if parts_thread
        else ()
    )
    return MessagePlan(
        event_id=event_id,
        channel=channel,
        top=PlannedMessage(
            short_text, tuple(dict(b) for b in short_blocks), top_thread
        ),
        parts=planned,
        edit_ts=edit_ts,
        edit_parts=tuple(str(ts) for ts in edit_parts if ts) if edit_ts else (),
        short_source=short_source,
        tables_as_code=tables_as_code,
    )


def retry_after(exc: BaseException) -> Optional[float]:
    """Seconds to wait when ``exc`` is Slack's 429, else ``None``.

    Reads the SDK's ``SlackApiError`` (``response.status_code``, ``headers``,
    ``data``) and the gateway client's (``response`` is Slack's body as a dict).
    """
    response = getattr(exc, "response", None)
    if response is None:
        return None
    status = getattr(response, "status_code", None)
    data = getattr(response, "data", None)
    if not isinstance(data, Mapping):
        data = response if isinstance(response, Mapping) else {}
    error = str(data.get("error") or "")
    if status != 429 and error not in ("ratelimited", "rate_limited"):
        return None
    headers = getattr(response, "headers", None) or {}
    raw: Any = None
    if isinstance(headers, Mapping):
        raw = headers.get("Retry-After") or headers.get("retry-after")
    try:
        wait = float(raw) if raw is not None else DEFAULT_RETRY_AFTER_S
    except (TypeError, ValueError):
        wait = DEFAULT_RETRY_AFTER_S
    return min(max(wait, 0.0), MAX_RETRY_AFTER_S)


def _ok(response: Any, what: str) -> Mapping[str, Any]:
    if not isinstance(response, Mapping):
        response = getattr(response, "data", None) or {}
    if response.get("ok") is False:
        raise ChannelError(f"slack: {what} failed: {response.get('error') or 'error'}")
    return response


def _with_retry(
    call: Callable[[], Any], what: str, sleep: Callable[[float], None]
) -> Mapping[str, Any]:
    """``call()``; a 429 waits and calls again, up to :data:`RATE_LIMIT_ATTEMPTS`."""
    for attempt in range(1, RATE_LIMIT_ATTEMPTS + 1):
        try:
            return _ok(call(), what)
        except ChannelError:
            raise
        except Exception as exc:  # SlackApiError and transport errors alike
            wait = retry_after(exc)
            if wait is None:
                raise ChannelError(f"slack: {what} failed: {exc}") from None
            if attempt == RATE_LIMIT_ATTEMPTS:
                raise ChannelError(
                    f"slack: {what} still rate-limited after {attempt} attempts"
                ) from None
            logger.info("slack: %s rate-limited; retrying in %.1fs", what, wait)
            sleep(wait)
    raise ChannelError(f"slack: {what} failed")  # pragma: no cover — loop returns


def post_message(
    client: Any,
    *,
    channel: str,
    text: str,
    blocks: Optional[Sequence[Mapping[str, Any]]] = None,
    thread_ts: str = "",
) -> Mapping[str, Any]:
    """One ``chat.postMessage`` with link previews off (R5) — the one spelling of a
    post every Slack call site in the channel uses. Raises what the client raises."""
    return client.chat_postMessage(
        channel=channel,
        text=text,
        blocks=list(blocks) if blocks is not None else None,
        thread_ts=thread_ts or None,
        unfurl_links=False,
        unfurl_media=False,
    )


def deliver(
    client: Any,
    plan: MessagePlan,
    *,
    already: Optional[Mapping[str, Any]] = None,
    record: Optional[Callable[[Delivered], None]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Delivered:
    """Post ``plan`` in order, skipping what ``already`` says landed.

    ``already`` is the delivery memory's record for this event id —
    ``{"channel", "top", "parts": [...]}`` — and is honoured only when it is for
    the plan's channel. ``record`` is called with the conversation's state after
    **every** successful call, before the next one. A failure raises
    :class:`ChannelError`; what landed before it stays recorded.
    """
    keep = record or (lambda _delivered: None)
    prior = already if already and already.get("channel") == plan.channel else {}
    top = str(prior.get("top") or "")
    landed: List[str] = [str(ts) for ts in (prior.get("parts") or []) if ts]
    calls = 0
    edited = False
    # The replies an edited message already holds (R6.2), edited in place. When
    # the edit fell back to a fresh post they belong to the old message, and the
    # new one gets its long form posted whole.
    reuse: Tuple[str, ...] = ()

    if not top:
        if plan.edit_ts:
            top, edited = _edit_top(client, plan, sleep)
        else:
            response = _with_retry(
                lambda: post_message(
                    client,
                    channel=plan.channel,
                    text=plan.top.text,
                    blocks=plan.top.blocks,
                    thread_ts=plan.top.thread_ts,
                ),
                "post",
                sleep,
            )
            top = str(response.get("ts") or "")
            if not top and plan.parts:
                raise ChannelError("slack: post failed: no ts returned")
        calls += 1
        keep(Delivered(plan.channel, top, tuple(landed), calls, edited))
    elif plan.edit_ts:
        edited = top == plan.edit_ts  # a replay of an edit already made
    if edited:
        reuse = plan.edit_parts

    for index, part in enumerate(plan.parts):
        if index < len(landed):
            continue  # posted by an earlier attempt at this event
        thread = top if part.thread_ts == THREAD_OF_TOP else part.thread_ts
        ts = ""
        if index < len(reuse):
            ts = _edit_part(client, plan.channel, reuse[index], part)
            calls += 1
        if not ts:
            response = _with_retry(
                lambda: post_message(
                    client,
                    channel=plan.channel,
                    text=part.text,
                    blocks=part.blocks,
                    thread_ts=thread,
                ),
                f"long-form part {index + 1}/{len(plan.parts)}",
                sleep,
            )
            ts = str(response.get("ts") or "")
            calls += 1
        landed.append(ts)
        keep(Delivered(plan.channel, top, tuple(landed), calls, edited))

    # A long form that shrank: the replies past its new end go (R6.2). Best
    # effort — a reply Slack will not delete is left, never re-posted.
    for surplus in reuse[len(plan.parts) :]:
        if surplus in landed:
            continue
        try:
            _ok(client.chat_delete(channel=plan.channel, ts=surplus), "delete")
        except Exception as exc:  # noqa: BLE001 — a surplus reply never fails delivery
            logger.debug("slack: chat.delete of %s failed (%s)", surplus, exc)
        calls += 1

    return Delivered(plan.channel, top, tuple(landed), calls, edited)


def _edit_part(client: Any, channel: str, ts: str, part: PlannedMessage) -> str:
    """Edit the long-form reply at ``ts`` to hold ``part``; ``""`` when it is gone
    or cannot be edited, so the caller posts it fresh instead (R6.3). An edit
    takes no unfurl flags: the reply was posted with them (design.md stage 4)."""
    try:
        _ok(
            client.chat_update(
                channel=channel, ts=ts, text=part.text, blocks=list(part.blocks)
            ),
            "edit",
        )
        return ts
    except Exception as exc:  # noqa: BLE001 — a stale reply is recoverable
        logger.debug("slack: chat.update of reply %s failed (%s); posting", ts, exc)
        return ""


def _edit_top(
    client: Any, plan: MessagePlan, sleep: Callable[[float], None]
) -> Tuple[str, bool]:
    """Edit the message at ``plan.edit_ts``; if it is gone or cannot be edited,
    post a fresh one and adopt its ts (issue-393 B5: a lost progress message never
    wedges the phase). Returns ``(ts, edited)``."""
    try:
        _ok(
            client.chat_update(
                channel=plan.channel,
                ts=plan.edit_ts,
                text=plan.top.text,
                blocks=list(plan.top.blocks),
            ),
            "edit",
        )
        return plan.edit_ts, True
    except Exception as exc:  # noqa: BLE001 — a stale ts is recoverable
        logger.debug(
            "slack: chat.update at %s failed (%s); posting fresh", plan.edit_ts, exc
        )
    response = _with_retry(
        lambda: post_message(
            client,
            channel=plan.channel,
            text=plan.top.text,
            blocks=plan.top.blocks,
            thread_ts=plan.top.thread_ts,
        ),
        "post",
        sleep,
    )
    return str(response.get("ts") or ""), False


def summary_of(delivered: Delivered) -> Dict[str, Any]:
    """The delivery-memory record for one event: where, the top ts, the parts."""
    return {
        "channel": delivered.channel,
        "top": delivered.top,
        "parts": list(delivered.parts),
    }
