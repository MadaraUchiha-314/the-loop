"""``the-loop doctor slack`` — the deployment-wide Slack diagnosis (issue-393 F2).

``channels status --probe`` asks Slack about the *app*: what the configured
channel is and which scopes the bot holds. The two probes here ask about the
*deployment* — the questions the e2e run of issue-393 could not answer from any
log:

1. **Is a second Socket Mode consumer holding this app's connection?** (R2.2)
   Slack load-balances an app's events across every open Socket Mode connection,
   so a second the-loop instance — or a stale ``channels listen`` on another host
   — silently halves what each one hears. Slack exposes **no API that lists an
   app's connections**, so the probe measures instead of asking: it posts a few
   fixed-format nonce heartbeats into the configured channel and counts how many
   come back within a window. With two consumers each heartbeat has an even
   chance of landing elsewhere; a shortfall is *evidence* of a split, never
   proof, and every sentence the probe prints says so.

   Who receives the echo depends on what is running here. When this instance's
   own listener holds its runlock, **it** is the receiver — it records each
   heartbeat it hears as a ``channel.heartbeat`` event, and the doctor reads
   the event log back — because opening a second connection beside a running
   listener would itself split the events and measure the doctor, not the
   deployment. When no listener runs here, the doctor opens its **own**
   connection and receives directly.

2. **Does every channel this daemon declares resolve in its own directory?**
   (R2.3) The B1 failure class: a room the bot was invited to that its
   directory never listed, so a name resolved to nothing and every post was
   refused. Each declared name is resolved; each declared id is checked
   against the listing; a miss over a truncated listing says so.

Both probes are best-effort and fail closed: a probe that cannot run answers
``unverifiable`` (never ``ok``), never raises, and prints ids and channel names
only — never a token, never config content (the heartbeat is a marker and a
random nonce).

Spec: docs/specs/issue-393/design.md §Track A (B3 + F2 / R2).
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Set, Tuple

from .. import eventlog
from . import slack as _slack
from .directory import SlackDirectory, is_conversation_id, normalize_name
from .slack import (
    SlackChannelConfig,
    heartbeat_nonce,
    heartbeat_text,
    slack_state_path,
)
from .state import ChannelStores

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "CHANNEL_STATUSES",
    "DEFAULT_BEATS",
    "DEFAULT_WINDOW_SECONDS",
    "VERDICTS",
    "check_declared_channels",
    "consumer_verdict_text",
    "listener_is_running",
    "probe_second_consumer",
]

#: How many heartbeats one probe posts. With two consumers sharing the token,
#: the chance that every one of N heartbeats happens to land here is 1 in 2^N:
#: three beats miss a split one time in eight, which is the balance between a
#: room seeing three transient messages and a doctor that shrugs.
DEFAULT_BEATS = 3
#: How long to wait for the echoes. Socket Mode delivery is sub-second; five
#: seconds covers a slow reconnect without making the operator wait.
DEFAULT_WINDOW_SECONDS = 5.0
#: What :func:`probe_second_consumer` can conclude. Never anything stronger.
VERDICTS = ("ok", "split-suspected", "unverifiable")
#: What :func:`check_declared_channels` says about one declared channel.
CHANNEL_STATUSES = ("ok", "miss", "absent", "invalid", "unverifiable")

_POLL_SECONDS = 0.05


# -- R2.2: the second-consumer heartbeat probe --------------------------------------


def probe_second_consumer(
    cli_config: Optional[Mapping[str, Any]],
    *,
    beats: int = DEFAULT_BEATS,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    client_factory: Optional[Callable[[str], Any]] = None,
    socket_client_factory: Optional[Callable[[str, Any], Any]] = None,
    listener_running: Optional[bool] = None,
    log_path: Optional[str] = None,
    nonce_factory: Optional[Callable[[], str]] = None,
) -> Dict[str, Any]:
    """Post ``beats`` heartbeats and count how many this deployment hears back.

    Returns ``{"verdict", "beats", "echoed", "window_seconds", "receiver",
    "channel", "reason"}``: ``verdict`` is one of :data:`VERDICTS`;
    ``receiver`` is ``listener`` (the running listener's event log was read) or
    ``doctor`` (an own connection was opened); ``reason`` explains an
    ``unverifiable``. Every heartbeat posted is deleted again afterwards,
    best-effort. Never raises. The injection points (``client_factory``,
    ``socket_client_factory``, ``listener_running``, ``log_path``,
    ``nonce_factory``) exist so the probe runs against fakes with no network.
    """
    config = SlackChannelConfig.from_mapping(cli_config)
    beats = max(1, int(beats))
    window = max(0.1, float(window_seconds))
    result: Dict[str, Any] = {
        "verdict": "unverifiable",
        "beats": beats,
        "echoed": 0,
        "window_seconds": window,
        "receiver": "",
        "channel": "",
        "reason": "",
    }
    try:
        return _probe(
            config,
            cli_config,
            result,
            client_factory=client_factory,
            socket_client_factory=socket_client_factory,
            listener_running=listener_running,
            log_path=log_path,
            nonce_factory=nonce_factory,
        )
    except Exception as exc:  # noqa: BLE001 — a diagnostic never fails its caller
        result["verdict"] = "unverifiable"
        result["reason"] = f"{type(exc).__name__}: {exc}"
        return result


def _unverifiable(result: Dict[str, Any], reason: str) -> Dict[str, Any]:
    result["verdict"] = "unverifiable"
    result["reason"] = reason
    return result


def _probe(
    config: SlackChannelConfig,
    cli_config: Optional[Mapping[str, Any]],
    result: Dict[str, Any],
    *,
    client_factory,
    socket_client_factory,
    listener_running,
    log_path,
    nonce_factory,
) -> Dict[str, Any]:
    if not config.enabled:
        return _unverifiable(result, "channels.slack is not enabled")
    bot_token = os.environ.get(config.bot_token_env) or ""
    if not bot_token:
        return _unverifiable(result, f"no bot token — {config.bot_token_env} is unset")
    channel = _central_channel(config, cli_config, client_factory)
    if not channel:
        return _unverifiable(
            result,
            "no channel to post the heartbeat into — channels.slack.channel is "
            + (
                "unset"
                if not config.channel
                else f"{config.channel!r}, which resolves to no channel this bot can see"
            ),
        )
    result["channel"] = channel
    running = (
        bool(listener_running)
        if listener_running is not None
        else listener_is_running(cli_config)
    )
    # Resolved through the module at call time — `slack.build_client` is the one
    # place a test substitutes the SDK client, and a name bound at import would
    # slip past it (and reach the network).
    client = (client_factory or _slack.build_client)(bot_token)
    receiver: _Receiver
    if running:
        path, enabled = _event_log(cli_config, log_path)
        if not enabled:
            return _unverifiable(
                result,
                "a listener is running here but eventLog.enabled is false, so "
                "its receipts cannot be read — enable the event log, or stop the "
                "listener so the doctor can listen itself",
            )
        receiver = _LogReceiver(path)
        result["receiver"] = "listener"
    else:
        app_token = os.environ.get(config.app_token_env) or ""
        if not app_token:
            return _unverifiable(
                result,
                "no listener is running here and no app-level token — "
                f"{config.app_token_env} is unset — so nothing can receive the "
                "heartbeat",
            )
        receiver = _SocketReceiver(
            (socket_client_factory or _default_socket_client)(app_token, client)
        )
        result["receiver"] = "doctor"

    make_nonce = nonce_factory or (lambda: secrets.token_hex(8))
    posted: List[Tuple[str, str]] = []
    seen: Set[str] = set()
    receiver.start()
    try:
        for _ in range(result["beats"]):
            nonce = make_nonce()
            response = client.chat_postMessage(
                channel=channel, text=heartbeat_text(nonce)
            )
            posted.append((nonce, str((response or {}).get("ts") or "")))
        wanted = {nonce for nonce, _ in posted}
        deadline = time.monotonic() + result["window_seconds"]
        seen = receiver.seen() & wanted
        while len(seen) < len(wanted) and time.monotonic() < deadline:
            time.sleep(_POLL_SECONDS)
            seen = receiver.seen() & wanted
    finally:
        # The room should not keep the probe's litter: every heartbeat that
        # got a ts is deleted, and a failure to delete is a debug line, not a
        # verdict — the measurement already happened.
        for _, ts in posted:
            if not ts:
                continue
            try:
                client.chat_delete(channel=channel, ts=ts)
            except Exception as exc:  # noqa: BLE001
                logger.debug("slack doctor: could not delete heartbeat %s: %s", ts, exc)
        receiver.stop()
    result["echoed"] = len(seen)
    result["verdict"] = "ok" if len(seen) == result["beats"] else "split-suspected"
    return result


class _Receiver:
    """What hears the heartbeats: started before the first post, asked for the
    nonces it has seen until the window closes, stopped afterwards."""

    def start(self) -> None:  # pragma: no cover — interface
        raise NotImplementedError

    def seen(self) -> Set[str]:  # pragma: no cover — interface
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover — interface
        raise NotImplementedError


class _SocketReceiver(_Receiver):
    """The doctor's own Socket Mode connection — used only when no listener
    runs here, so the doctor is the one local consumer.

    It acknowledges **only its own heartbeats**. Any other envelope Slack hands
    this connection is a member's real message that the doctor must not eat:
    left un-acknowledged, Slack retries it to whatever consumer remains.
    """

    def __init__(self, client: Any):
        self._client = client
        self._seen: Set[str] = set()
        self._lock = threading.Lock()

    def start(self) -> None:
        self._client.socket_mode_request_listeners.append(self._handle)
        self._client.connect()

    def _handle(self, client: Any, request: Any) -> None:
        if getattr(request, "type", "") != "events_api":
            return
        event = (getattr(request, "payload", None) or {}).get("event") or {}
        nonce = heartbeat_nonce(event) if event.get("type") == "message" else ""
        if not nonce:
            return
        try:
            from slack_sdk.socket_mode.response import (  # type: ignore[import-not-found]
                SocketModeResponse,
            )

            client.send_socket_mode_response(
                SocketModeResponse(envelope_id=request.envelope_id)
            )
        except Exception as exc:  # noqa: BLE001 — the receipt counts either way
            logger.debug("slack doctor: could not ack a heartbeat: %s", exc)
        with self._lock:
            self._seen.add(nonce)

    def seen(self) -> Set[str]:
        with self._lock:
            return set(self._seen)

    def stop(self) -> None:
        try:
            self._client.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("slack doctor: could not close the probe connection: %s", exc)


class _LogReceiver(_Receiver):
    """The running listener, read through the ``channel.heartbeat`` records it
    appends to the event log — only the bytes written after the probe began."""

    def __init__(self, path: str):
        self.path = Path(path)
        self._offset = 0

    def _size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def start(self) -> None:
        self._offset = self._size()

    def seen(self) -> Set[str]:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                handle.seek(self._offset)
                lines = handle.readlines()
        except OSError:
            return set()
        return {
            str(record.get("nonce") or "")
            for record in eventlog.parse_lines(lines, types=["channel.heartbeat"])
            if record.get("nonce")
        }

    def stop(self) -> None:
        return None


def _default_socket_client(app_token: str, web_client: Any):
    from slack_sdk.socket_mode import (  # type: ignore[import-not-found]
        SocketModeClient,
    )

    return SocketModeClient(app_token=app_token, web_client=web_client)


def listener_is_running(cli_config: Optional[Mapping[str, Any]]) -> bool:
    """Whether this instance's Socket Mode listener holds its runlock right now
    — the same lock ``channels listen`` and the service take, so a stale
    pidfile reads as *not running*."""
    try:
        from ..core import daemons as core_daemons
        from ..runlock import RunLock

        lock = RunLock(
            core_daemons._pidfile(core_daemons.SLACK_LISTENER, dict(cli_config or {})),
            name=core_daemons.SLACK_LISTENER,
        )
        return lock.is_held()
    except Exception as exc:  # noqa: BLE001 — unknown reads as "not running"
        logger.debug("slack doctor: could not read the listener lock: %s", exc)
        return False


def _event_log(
    cli_config: Optional[Mapping[str, Any]], override: Optional[str]
) -> Tuple[str, bool]:
    """``(path, enabled)`` of the event log the running listener writes — the
    same resolution :func:`the_loop.eventlog.configure_from_file` makes."""
    from ..state import layout_from_config

    data = dict(cli_config or {})
    cfg = data.get("eventLog") or {}
    path = override or str(cfg.get("path") or layout_from_config(data).event_log)
    return path, bool(cfg.get("enabled", True))


def _central_channel(
    config: SlackChannelConfig,
    cli_config: Optional[Mapping[str, Any]],
    client_factory: Optional[Callable[[str], Any]],
) -> str:
    declared = config.channel
    if not declared:
        return ""
    if is_conversation_id(declared):
        return declared
    return _directory(config, cli_config, client_factory).conversation_id(declared)


def _directory(
    config: SlackChannelConfig,
    cli_config: Optional[Mapping[str, Any]],
    client_factory: Optional[Callable[[str], Any]],
) -> SlackDirectory:
    return SlackDirectory.beside(
        slack_state_path(cli_config),
        token_env=config.bot_token_env,
        client_factory=client_factory,
    )


def consumer_verdict_text(result: Mapping[str, Any]) -> str:
    """The one sentence an operator reads for a probe result — hedged exactly
    as far as the measurement allows, and no further."""
    verdict = result.get("verdict")
    beats = result.get("beats", 0)
    echoed = result.get("echoed", 0)
    window = float(result.get("window_seconds") or 0)
    where = {
        "listener": "the running listener (read back from its event log)",
        "doctor": "the doctor's own Socket Mode connection",
    }.get(str(result.get("receiver") or ""), "the receiver")
    if verdict == "ok":
        return (
            f"{echoed}/{beats} heartbeats reached {where} within {window:g}s — no "
            "second Socket Mode consumer observed. Evidence, not proof: Slack "
            "exposes no API that lists an app's connections, so a consumer that "
            "was idle or reconnecting during the window would not show."
        )
    if verdict == "split-suspected":
        text = (
            f"{echoed}/{beats} heartbeats reached {where} within {window:g}s — "
            "another Socket Mode consumer may hold this app's connection: Slack "
            "splits Socket Mode events across an app's connections, halving "
            "inbound for both. Evidence, not proof (Slack lists no connections): "
            "find every process connected with this app-level token — a second "
            "the-loop instance, a stale `channels listen`, another host — and "
            "stop all but one."
        )
        if result.get("receiver") == "listener":
            text += (
                " A listener started on a build older than this one records no "
                "heartbeat at all — `the-loop restart` on this build first."
            )
        return text
    return f"unverifiable — {result.get('reason') or 'the probe could not run'}"


# -- R2.3: every declared channel against the bot's own directory --------------------


def check_declared_channels(
    cli_config: Optional[Mapping[str, Any]],
    *,
    client_factory: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Resolve every channel this daemon declares in its own directory.

    Returns ``{"channels": [row, ...], "truncated": bool, "reason": str}``.
    Each row is ``{"declared", "owner", "id", "status"}`` with ``status`` one of
    :data:`CHANNEL_STATUSES`: ``ok`` resolved / listed; ``miss`` a name this bot
    can see no channel for (the B1 failure); ``absent`` an id the listing does
    not carry; ``invalid`` neither an id nor a name; ``unverifiable`` no listing
    could be read. ``truncated`` says a miss happened over a listing the page cap
    cut short, so the name may exist beyond it (R1.4). ``reason`` is set when
    nothing could be checked at all. Never raises.
    """
    config = SlackChannelConfig.from_mapping(cli_config)
    result: Dict[str, Any] = {"channels": [], "truncated": False, "reason": ""}
    try:
        path = slack_state_path(cli_config)
        entries: List[Tuple[str, str]] = []
        if config.channel:
            entries.append((config.channel, "channels.slack.channel"))
        targets = ChannelStores.beside(path).declared_targets()
        for target, work_item in sorted(targets.items()):
            entries.append((target, f"declared by {work_item}"))
        if not entries:
            result["reason"] = (
                "nothing declared — channels.slack.channel is unset and no work "
                "item declares a room"
            )
            return result
        if not os.environ.get(config.bot_token_env):
            result["reason"] = (
                f"no bot token — {config.bot_token_env} is unset, so nothing can "
                "be resolved"
            )
            result["channels"] = [
                {
                    "declared": declared,
                    "owner": owner,
                    "id": "",
                    "status": "unverifiable",
                }
                for declared, owner in entries
            ]
            return result
        directory = _directory(config, cli_config, client_factory)
        truncated = False
        for declared, owner in entries:
            row = {
                "declared": declared,
                "owner": owner,
                "id": "",
                "status": "unverifiable",
            }
            if is_conversation_id(declared):
                known = directory.conversation_known(declared)
                row["id"] = declared
                if known:
                    row["status"] = "ok"
                elif known is False:
                    row["status"] = "absent"
                    truncated = truncated or directory.listing_was_truncated()
            elif not normalize_name(declared):
                row["status"] = "invalid"
            else:
                resolved = directory.conversation_id(declared)
                row["id"] = resolved
                if resolved:
                    row["status"] = "ok"
                elif directory.has_conversations():
                    row["status"] = "miss"
                    truncated = truncated or directory.listing_was_truncated()
            result["channels"].append(row)
        result["truncated"] = truncated
        return result
    except Exception as exc:  # noqa: BLE001 — a diagnostic never fails its caller
        result["reason"] = f"{type(exc).__name__}: {exc}"
        return result
