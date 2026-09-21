"""The listener's own split check — inbound silence made visible (issue-413).

When a second Socket Mode consumer holds the app-level token, Slack load-balances
envelopes across the open connections and roughly half of everything inbound
lands somewhere else: mentions, button presses, select-menu picks, slash
commands. On this instance the loss leaves **no trace at all** — no
``channel.dropped``, no ``channel.*`` record, nothing to grep. The envelope was
never offered to this process.

``the-loop doctor slack`` (issue-393 F2) measures the split correctly, but only
when an operator types it, and its answer dies with the command. This module is
that measurement moved into the listener's own loop, with somewhere to put the
answer:

* :class:`SplitWatch` posts a few fixed-format nonce heartbeats into the
  configured channel at connect and on each reconcile deadline, and counts how
  many its **own** socket handler hears back inside a short window. Inside the
  listener the doctor's indirection through the event log is unnecessary: the
  handler that sees the heartbeat is the process that posted it, so the receipt
  is a set in memory.
* A shortfall emits ``channel.split_suspected`` at ``warning`` — on the first
  short check and then once every :data:`ESCALATE_EVERY`, so a persistent split
  is a periodic warning and not a storm — and a clean check after a short one
  emits ``channel.split_cleared`` and resets the ladder.
* Every check writes :class:`SplitState` to ``<root>/local/slack-split.json``,
  which is what ``the-loop status``, ``the-loop channels status`` and
  ``/the-loop status`` read. A finding that does not outlive its process cannot
  reach a surface the operator was already looking at.

A shortfall is **evidence, not proof**: Slack exposes no API that lists an app's
connections, so every sentence this module prints says so. Nothing here raises:
a diagnostic that ends the listener is strictly worse than one that never ran.

Ids, counts and timestamps only — never a token, never message text.

Spec: docs/specs/issue-413/design.md.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .. import eventlog
from .slack import (
    DEFAULT_SPLIT_CHECK_BEATS,
    MAX_SPLIT_CHECK_BEATS,
    SPLIT_CAVEAT,
    SPLIT_REMEDY,
    SlackChannelConfig,
    heartbeat_text,
)

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "DEFAULT_BEATS",
    "DEFAULT_WINDOW_SECONDS",
    "ESCALATE_EVERY",
    "MAX_BEATS",
    "RETAINED",
    "SPLIT_CAVEAT",
    "SPLIT_REMEDY",
    "SplitState",
    "SplitWatch",
    "read_state",
    "split_lines",
    "split_state_path",
    "summary_line",
]

#: How many heartbeats one check posts, and the ceiling an operator may
#: configure. Both live in :mod:`.slack` beside the config that carries them.
DEFAULT_BEATS = DEFAULT_SPLIT_CHECK_BEATS
MAX_BEATS = MAX_SPLIT_CHECK_BEATS
#: How long to wait for the echoes. Socket Mode delivery is sub-second.
DEFAULT_WINDOW_SECONDS = 5.0
#: After the first warning, one more every this many consecutive short checks.
ESCALATE_EVERY = 6
#: How many verdicts the rolling window keeps. Under a real split each check is
#: a coin toss — the incident that filed issue-413 read 2/3 → 1/3 → 3/3 → 1/3 —
#: so the report must not be one check's verdict. Eight is two hours at the
#: default cadence.
RETAINED = 8
#: What a check can conclude. Never anything stronger.
VERDICTS = ("ok", "split-suspected", "unverifiable")

_POLL_SECONDS = 0.05


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# -- the recorded state ---------------------------------------------------------------


@dataclass(frozen=True)
class SplitState:
    """One reading of ``<root>/local/slack-split.json``.

    Carries ids, counts and timestamps. A token, a nonce and message text are
    all absent on purpose: this file is read by ``status``, pasted into tickets,
    and writable by anyone who can write ``state.root``.
    """

    verdict: str = ""
    checked_at: str = ""
    beats: int = 0
    echoed: int = 0
    window_seconds: float = 0.0
    channel: str = ""
    reason: str = ""
    checks: int = 0
    short: int = 0
    consecutive_short: int = 0
    recent: Tuple[str, ...] = ()
    interval_seconds: int = 0

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "SplitState":
        verdict = str(data.get("verdict") or "")
        return cls(
            verdict=verdict if verdict in VERDICTS else "",
            checked_at=str(data.get("checkedAt") or ""),
            beats=_int(data.get("beats")),
            echoed=_int(data.get("echoed")),
            window_seconds=_float(data.get("windowSeconds")),
            channel=str(data.get("channel") or ""),
            reason=str(data.get("reason") or ""),
            checks=_int(data.get("checks")),
            short=_int(data.get("short")),
            consecutive_short=_int(data.get("consecutiveShort")),
            recent=tuple(
                str(item)
                for item in (data.get("recent") or ())
                if str(item) in VERDICTS
            )[-RETAINED:],
            interval_seconds=_int(data.get("intervalSeconds")),
        )

    def to_mapping(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "checkedAt": self.checked_at,
            "beats": self.beats,
            "echoed": self.echoed,
            "windowSeconds": self.window_seconds,
            "channel": self.channel,
            "reason": self.reason,
            "checks": self.checks,
            "short": self.short,
            "consecutiveShort": self.consecutive_short,
            "recent": list(self.recent),
            "intervalSeconds": self.interval_seconds,
        }

    @property
    def flapping(self) -> bool:
        """Whether any check in the retained window came back short.

        The whole reason the report is not the latest verdict: a real split
        answers `ok` a quarter of the time at two beats, and an operator who
        looks during one of those must still see that the window was not clean.
        """
        return "split-suspected" in self.recent

    @property
    def suspected(self) -> bool:
        return self.verdict == "split-suspected" or self.flapping


def _int(raw: Any) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _float(raw: Any) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def split_state_path(cli_config: Optional[Mapping[str, Any]]) -> str:
    """Where the check's state lives — ``<state.root>/local/slack-split.json``."""
    from ..state import layout_from_config

    return layout_from_config(dict(cli_config or {})).slack_split


def read_state(path: Any) -> Optional[SplitState]:
    """The recorded state, or ``None`` when it is absent or unreadable.

    ``None`` is the honest answer for a deployment whose listener has not run
    since this shipped, and every surface prints nothing for it: silence about a
    measurement never taken is correct, silence about one that came back short
    is the defect this module exists to fix.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    state = SplitState.from_mapping(data)
    return state if state.verdict else None


# -- rendering ------------------------------------------------------------------------


def summary_line(state: Optional[SplitState]) -> str:
    """The headline a surface prints, or ``""`` when there is nothing to say."""
    if state is None or not state.suspected:
        return ""
    short_in_window = state.recent.count("split-suspected")
    window = (
        f"{short_in_window} of the last {len(state.recent)} checks short"
        if len(state.recent) > 1
        else "the first check was short"
    )
    latest = (
        f"{state.echoed}/{state.beats} heartbeats reached the listener within "
        f"{state.window_seconds:g}s"
        if state.verdict != "unverifiable"
        else f"the last check could not run — {state.reason}"
    )
    return (
        f"inbound may be split across two Socket Mode consumers — {latest} "
        f"({window}, last at {state.checked_at or 'unknown'})"
    )


def split_lines(state: Optional[SplitState]) -> List[str]:
    """The full report: the headline, the caveat and the remedy — or ``[]``."""
    headline = summary_line(state)
    if not headline:
        return []
    return [headline, SPLIT_CAVEAT, SPLIT_REMEDY]


def cadence_line(state: Optional[SplitState], config: SlackChannelConfig) -> str:
    """What ``channels status`` says when there is no finding to report."""
    if not config.split_check_beats:
        return "off (channels.slack.read.splitCheckBeats: 0)"
    every = (
        f"every {config.catch_up_seconds}s"
        if config.catch_up_seconds
        else "at connect only (read.catchUpSeconds: 0)"
    )
    how = f"{config.split_check_beats} heartbeat(s) {every}"
    if state is None:
        return f"{how} — not run yet on this state root"
    if state.verdict == "unverifiable":
        return f"{how} — last check unverifiable: {state.reason}"
    short = state.recent.count("split-suspected")
    window = f"{len(state.recent)} retained, " + (
        f"{short} short" if short else "none short"
    )
    return (
        f"{how} — last check {state.echoed}/{state.beats} at "
        f"{state.checked_at or 'unknown'}, {window}"
    )


# -- the check ------------------------------------------------------------------------


class SplitWatch:
    """Posts the heartbeats, counts what this listener hears, records the answer.

    One instance per listener. :meth:`observe` is called from the SDK's own
    thread the moment a heartbeat arrives; :meth:`run_cycle` runs on the
    listener's tick. The only shared state between them is the seen-nonce set,
    which is guarded.
    """

    def __init__(
        self,
        path: Any,
        *,
        client: Any,
        config: SlackChannelConfig,
        cli_config: Optional[Mapping[str, Any]] = None,
        beats: int = DEFAULT_BEATS,
        window_seconds: Optional[float] = None,
        interval_seconds: int = 0,
        nonce_factory: Optional[Callable[[], str]] = None,
        client_factory: Optional[Callable[[str], Any]] = None,
    ):
        self.path = Path(path)
        self._client = client
        self._config = config
        self._cli_config = dict(cli_config or {})
        self.beats = max(1, min(int(beats), MAX_BEATS))
        # Resolved through the module at call time, not bound in the signature:
        # the window is the one knob a test needs to shrink, and the listener has
        # no argument to pass it down.
        self.window_seconds = max(
            0.1,
            float(DEFAULT_WINDOW_SECONDS if window_seconds is None else window_seconds),
        )
        self.interval_seconds = int(interval_seconds)
        self._nonce = nonce_factory or (lambda: secrets.token_hex(8))
        self._client_factory = client_factory
        self._seen: Set[str] = set()
        self._lock = threading.Lock()
        self._warned = False
        self._state = read_state(self.path) or SplitState()
        self._channel = ""

    # -- construction -----------------------------------------------------------

    @classmethod
    def for_config(
        cls,
        cli_config: Optional[Mapping[str, Any]],
        *,
        client: Any,
        config: Optional[SlackChannelConfig] = None,
        **kwargs: Any,
    ) -> Optional["SplitWatch"]:
        """The watch this deployment asks for, or ``None`` when it asks for none.

        ``None`` means *do nothing and post nothing* — the channel is disabled or
        ``read.splitCheckBeats`` is ``0``. Every other obstacle (no channel, an
        unresolvable name, a client that refuses) is a runtime ``unverifiable``,
        which is recorded rather than skipped: an operator must be able to tell
        "the check says all is well" from "the check never ran".
        """
        config = config or SlackChannelConfig.from_mapping(cli_config)
        if not config.enabled or not config.split_check_beats:
            return None
        return cls(
            split_state_path(cli_config),
            client=client,
            config=config,
            cli_config=cli_config,
            beats=config.split_check_beats,
            interval_seconds=config.catch_up_seconds,
            **kwargs,
        )

    # -- the receipt side -------------------------------------------------------

    def observe(self, nonce: str) -> None:
        """Record a heartbeat this listener received (the socket handler's call)."""
        if not nonce:
            return
        with self._lock:
            self._seen.add(nonce)

    # -- the measuring side -----------------------------------------------------

    def run_cycle(self, stop_event: Optional[threading.Event] = None) -> SplitState:
        """Post, count, tidy up, record. Never raises.

        Returns the state it recorded. A cycle abandoned because the listener is
        stopping returns the previous state and writes nothing — a half-measured
        window is not evidence of anything.
        """
        try:
            return self._run(stop_event)
        except Exception as exc:  # noqa: BLE001 — a diagnostic never fails its caller
            return self._record("unverifiable", 0, f"{type(exc).__name__}: {exc}")

    def _run(self, stop_event: Optional[threading.Event]) -> SplitState:
        channel = self._resolve_channel()
        if not channel:
            return self._record(
                "unverifiable",
                0,
                "no channel to post the heartbeat into — channels.slack.channel is "
                + (
                    "unset"
                    if not self._config.channel
                    else f"{self._config.channel!r}, which resolves to no channel "
                    "this bot can see"
                ),
            )
        if not os.environ.get(self._config.bot_token_env):
            return self._record(
                "unverifiable",
                0,
                f"no bot token — {self._config.bot_token_env} is unset",
            )
        wanted: Set[str] = set()
        posted: List[Tuple[str, str]] = []
        reason = ""
        try:
            for _ in range(self.beats):
                nonce = self._nonce()
                response = self._client.chat_postMessage(
                    channel=channel, text=heartbeat_text(nonce)
                )
                wanted.add(nonce)
                posted.append((nonce, str((response or {}).get("ts") or "")))
        except Exception as exc:  # noqa: BLE001 — a post that fails is unverifiable
            reason = f"could not post the heartbeat: {type(exc).__name__}: {exc}"
        try:
            if reason:
                return self._record("unverifiable", 0, reason)
            aborted = self._wait(wanted, stop_event)
            if aborted:
                return self._state
            echoed = len(self._taken(wanted))
            return self._record(
                "ok" if echoed >= self.beats else "split-suspected", echoed, ""
            )
        finally:
            self._tidy(channel, posted)
            self._forget(wanted)

    def _wait(self, wanted: Set[str], stop_event: Optional[threading.Event]) -> bool:
        """Poll until every nonce is back or the window closes. ``True`` = stopped."""
        deadline = time.monotonic() + self.window_seconds
        while len(self._taken(wanted)) < len(wanted):
            if stop_event is not None and stop_event.is_set():
                return True
            if time.monotonic() >= deadline:
                break
            time.sleep(_POLL_SECONDS)
        return False

    def _taken(self, wanted: Set[str]) -> Set[str]:
        with self._lock:
            return self._seen & wanted

    def _forget(self, wanted: Set[str]) -> None:
        """Drop this cycle's nonces so the set cannot grow for the process's life."""
        with self._lock:
            self._seen -= wanted

    def _tidy(self, channel: str, posted: Sequence[Tuple[str, str]]) -> None:
        """Delete every heartbeat that got a ``ts``. The room keeps no litter, and
        a delete that fails is a debug line — the measurement already happened."""
        for _, ts in posted:
            if not ts:
                continue
            try:
                self._client.chat_delete(channel=channel, ts=ts)
            except Exception as exc:  # noqa: BLE001
                logger.debug("slack split check: could not delete %s: %s", ts, exc)

    def _resolve_channel(self) -> str:
        if self._channel:
            return self._channel
        try:
            from . import doctor

            self._channel = doctor.central_channel(
                self._config, self._cli_config, self._client_factory
            )
        except Exception as exc:  # noqa: BLE001 — unresolved reads as "no channel"
            logger.debug("slack split check: could not resolve the channel: %s", exc)
            self._channel = ""
        return self._channel

    # -- the recording side -----------------------------------------------------

    def _record(self, verdict: str, echoed: int, reason: str) -> SplitState:
        """Fold one check into the state, escalate if it earns it, write it down.

        An ``unverifiable`` check does not touch the ladder or the rolling
        window: a check that could not run is not evidence either way, and
        counting it as clean would clear a real finding.
        """
        previous = self._state
        if verdict == "unverifiable":
            state = SplitState(
                verdict=verdict,
                checked_at=_utcnow(),
                beats=self.beats,
                echoed=0,
                window_seconds=self.window_seconds,
                channel=self._channel,
                reason=reason,
                checks=previous.checks,
                short=previous.short,
                consecutive_short=previous.consecutive_short,
                recent=previous.recent,
                interval_seconds=self.interval_seconds,
            )
            self._state = state
            self._write(state)
            logger.debug("slack split check: unverifiable — %s", reason)
            return state
        is_short = verdict == "split-suspected"
        consecutive = previous.consecutive_short + 1 if is_short else 0
        state = SplitState(
            verdict=verdict,
            checked_at=_utcnow(),
            beats=self.beats,
            echoed=echoed,
            window_seconds=self.window_seconds,
            channel=self._channel,
            reason="",
            checks=previous.checks + 1,
            short=previous.short + (1 if is_short else 0),
            consecutive_short=consecutive,
            recent=(previous.recent + (verdict,))[-RETAINED:],
            interval_seconds=self.interval_seconds,
        )
        self._state = state
        self._announce(state, previous)
        self._write(state)
        return state

    def _announce(self, state: SplitState, previous: SplitState) -> None:
        """The event ladder: the first short check, then one every ESCALATE_EVERY,
        and one `cleared` when a short run ends."""
        if state.verdict == "split-suspected":
            if state.consecutive_short == 1 or (
                state.consecutive_short % ESCALATE_EVERY == 0
            ):
                eventlog.emit(
                    "channel.split_suspected",
                    level="warning",
                    channel="slack",
                    channel_id=state.channel,
                    beats=state.beats,
                    echoed=state.echoed,
                    window_seconds=state.window_seconds,
                    consecutive=state.consecutive_short,
                    remedy=SPLIT_REMEDY,
                )
                logger.warning(
                    "slack: %d/%d heartbeats reached this listener within %gs — %s %s",
                    state.echoed,
                    state.beats,
                    state.window_seconds,
                    SPLIT_CAVEAT,
                    SPLIT_REMEDY,
                )
            return
        if previous.consecutive_short:
            eventlog.emit(
                "channel.split_cleared",
                channel="slack",
                channel_id=state.channel,
                beats=state.beats,
                echoed=state.echoed,
                after=previous.consecutive_short,
            )
            logger.info(
                "slack: %d/%d heartbeats reached this listener — the split check is "
                "clean again after %d short check(s)",
                state.echoed,
                state.beats,
                previous.consecutive_short,
            )

    def _write(self, state: SplitState) -> None:
        """Atomic replace, like the poller heartbeat. A write that fails warns
        once and is swallowed: observability never breaks ingress."""
        payload = json.dumps(state.to_mapping(), indent=2) + "\n"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=str(self.path.parent),
                prefix=self.path.name + ".",
                suffix=".tmp",
                delete=False,
            )
            try:
                with handle:
                    handle.write(payload)
                os.replace(handle.name, self.path)
            except BaseException:
                _unlink(handle.name)
                raise
        except OSError as exc:
            if not self._warned:
                self._warned = True
                logger.warning(
                    "cannot write the slack split state %s: %s", self.path, exc
                )


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:  # pragma: no cover — the replace already consumed it
        pass
