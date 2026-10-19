"""Core capability: progress — a session's non-blocking status line (issue-340).

``the-loop ask`` is the only mid-flight signal a session has, and it *blocks*: the
session stops and waits for a human. Every other event fires at a boundary — a
gate, a block, the end — so a session that runs for hours is silent, and a person
on a phone cannot tell hard work from a stuck loop from a dead poller.

:func:`progress_session` is the verb's core: the agent says where it is, the
session keeps working, and the line becomes a ``session.progress`` event every
channel that subscribes to it hears. Three rules keep it from becoming noise:

* **Opt-in per work item.** Only a work item that carries the configured label
  (``progress.label``, default ``the-loop: progress``) emits anything. The label is
  read from the tracker at call time, so adding or removing it takes effect on the
  next report — no config edit, no restart. Without the label the verb is a
  successful no-op, which is why an agent can call it unconditionally.
* **Rate-limited.** At most one report per work item per ``progress.minIntervalSeconds``.
  A report that arrives sooner is coalesced away and says when the next is welcome;
  the agent's next call is then the newest one. The clock is the event log, the
  source of truth for what was emitted (decision-025) — no second store to drift.
* **Short by construction.** One or two lines, cut at ``progress.maxChars``. It is a
  signal, not a record: it is never written on the ticket (the full detail goes
  there already), so the event is not ``recorded`` in the catalog.

Core never prints: the verb returns ``messages`` and an ``exitCode`` like every other
session verb, so the CLI, the HTTP API and the SDK share one implementation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional

from .. import eventlog
from ..workitem import WorkItemRef
from . import events as core_events

logger = logging.getLogger("the-loop.progress")

__all__ = [
    "DEFAULT_LABEL",
    "DEFAULT_MAX_CHARS",
    "DEFAULT_MIN_INTERVAL_SECONDS",
    "MAX_LINES",
    "ProgressConfig",
    "progress_session",
    "shorten",
]

DEFAULT_LABEL = "the-loop: progress"
DEFAULT_MIN_INTERVAL_SECONDS = 300
DEFAULT_MAX_CHARS = 280
#: A report is "one or two lines": what is happening now, and what is next.
MAX_LINES = 2


class ProgressConfig:
    """The CLI config's ``progress`` block, read the way the daemon reads it.

    A malformed value falls back to its default rather than refusing — a typo in an
    optional signal must never stop an agent reporting — and the schema is where a
    wrong type is rejected loudly.
    """

    def __init__(
        self,
        label: str = DEFAULT_LABEL,
        min_interval_seconds: int = DEFAULT_MIN_INTERVAL_SECONDS,
        max_chars: int = DEFAULT_MAX_CHARS,
    ):
        self.label = label
        self.min_interval_seconds = min_interval_seconds
        self.max_chars = max_chars

    @property
    def enabled(self) -> bool:
        """An empty ``label`` turns the whole feature off."""
        return bool(self.label)

    @classmethod
    def from_config(cls, config: Optional[Mapping[str, Any]]) -> "ProgressConfig":
        block = (config or {}).get("progress")
        if not isinstance(block, Mapping):
            return cls()
        label = block.get("label", DEFAULT_LABEL)
        return cls(
            label=label.strip() if isinstance(label, str) else DEFAULT_LABEL,
            min_interval_seconds=_non_negative(
                block.get("minIntervalSeconds"), DEFAULT_MIN_INTERVAL_SECONDS
            ),
            max_chars=max(
                1, _non_negative(block.get("maxChars"), DEFAULT_MAX_CHARS) or 1
            ),
        )


def _non_negative(value: Any, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return default
    return value


def shorten(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """The report as the room will carry it: its first :data:`MAX_LINES` non-empty
    lines, whitespace collapsed within each, cut at ``max_chars`` with an ellipsis."""
    lines = [" ".join(line.split()) for line in (text or "").splitlines()]
    kept = [line for line in lines if line][:MAX_LINES]
    out = "\n".join(kept)
    if len(out) > max_chars:
        out = out[: max(1, max_chars - 1)].rstrip() + "…"
    return out


def _labels_of(ref: WorkItemRef, config: Optional[Mapping[str, Any]]) -> List[str]:
    """The label names the work item's own tracker says it carries right now."""
    if ref.provider == "jira":
        from . import tickets

        api = tickets._jira_api(config)
        _item, key = tickets._jira_ref(ref.ref, api)
        return list(tickets._jira_client(config, None).labels(key))
    from . import github_ops

    item = github_ops._trusted(github_ops._github_ref(ref.ref), config)
    client = github_ops._client(config, None)
    return list(
        client.labels_of(
            item.owner, item.repo, item.number, host=github_ops._host(item)
        )
    )


def _label_matches(wanted: str, carried: List[str], provider: str) -> bool:
    """Whether the configured label is among ``carried``. Jira cannot hold a space
    or a ``: `` in a label, so the configured spelling is compared in its Jira form."""
    if provider == "jira":
        from ..jiralabels import JiraLabelError, jira_label

        try:
            wanted = jira_label(wanted)
        except JiraLabelError:
            return False
    return wanted.casefold() in {str(label).casefold() for label in carried}


def _seconds_until_next(
    ref: str, interval: int, config: Optional[Mapping[str, Any]]
) -> int:
    """Seconds before ``ref`` may report again; ``0`` when it may report now.

    Read from the event log: the newest ``session.progress`` for the work item.
    With no log (disabled, or nothing emitted yet) there is nothing to wait for.
    """
    if interval <= 0:
        return 0
    from ..state import layout_from_config

    log_path = layout_from_config(dict(config)).event_log if config else None
    now = datetime.now(timezone.utc)
    since = (now - timedelta(seconds=interval)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    recent = core_events.query_events(
        log_path,
        types=["session.progress"],
        work_item=ref,
        since=since + "Z",
        limit=1,
    )
    if not recent:
        return 0
    try:
        last = datetime.strptime(
            str(recent[-1].get("ts", "")), "%Y-%m-%dT%H:%M:%S.%fZ"
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return interval
    return max(1, int(interval - (now - last).total_seconds() + 0.999))


def progress_session(
    ref: str,
    text: str,
    config: Optional[Mapping[str, Any]] = None,
    actor: str = "",
) -> Dict[str, Any]:
    """Report a session's progress on its work item, without blocking it.

    ``ref`` that does not parse, or empty ``text``, is a caller mistake
    (:class:`ValueError`, before anything is read or sent). Everything else is a
    result: ``status`` is ``sent``, ``disabled`` (the feature is off), ``not-opted-in``
    (the work item lacks the label), ``rate-limited`` (``retryAfterSeconds`` says when
    the next report is welcome) or ``label-unreadable`` (the tracker refused the label
    read, exit code 1 — nothing is emitted, so a flaky tracker cannot flood a room).
    """
    from ..channels.base import Event
    from ..channels.bus import publish as bus_publish

    item = WorkItemRef.parse(ref)  # ValueError on a malformed ref
    if not text or not text.strip():
        raise ValueError("the progress report is empty; nothing to say")
    settings = ProgressConfig.from_config(config)
    result: Dict[str, Any] = {
        "workItem": item.ref,
        "status": "",
        "sent": False,
        "exitCode": 0,
        "messages": [],
    }

    def done(status: str, line: str, stream: str = "out", code: int = 0):
        result.update(status=status, exitCode=code)
        result["messages"].append({"stream": stream, "text": line})
        return result

    if not settings.enabled:
        return done(
            "disabled", "progress reports are off (progress.label is empty); not sent"
        )
    try:
        carried = _labels_of(item, config)
    except Exception as exc:  # noqa: BLE001 — a tracker fault is a result, not a crash
        logger.warning("progress: could not read the labels of %s: %s", item.ref, exc)
        return done(
            "label-unreadable",
            f"could not read the labels of {item.ref} ({exc}); nothing was sent",
            stream="err",
            code=1,
        )
    if not _label_matches(settings.label, carried, item.provider):
        return done(
            "not-opted-in",
            f"{item.ref} does not carry the {settings.label!r} label; not sent — "
            "carry on working",
        )
    wait = _seconds_until_next(item.ref, settings.min_interval_seconds, config)
    if wait:
        result["retryAfterSeconds"] = wait
        return done(
            "rate-limited",
            f"too soon after the last report on {item.ref}; not sent — the next one "
            f"is welcome in {wait}s, so report then with where you are by then",
        )
    line = shorten(text, settings.max_chars)
    published = bus_publish(
        Event(
            event_type="session.progress",
            work_item=item.ref,
            text=line,
            detail={"actor": actor} if actor else {},
            source="cli",
        ),
        dict(config or {}),
        record=False,
    )
    channels_posted = sum(1 for posted in published.posts if posted.ok)
    eventlog.emit(
        "session.progress",
        work_item=item.ref,
        text=line,
        actor=actor or None,
        channels_posted=channels_posted,
    )
    result["sent"] = True
    return done(
        "sent",
        f"reported progress on {item.ref}"
        + (
            f" to {channels_posted} channel(s)"
            if channels_posted
            else " (no channel subscribes to session.progress)"
        )
        + " — carry on working",
    )
