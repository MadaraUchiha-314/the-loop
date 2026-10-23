"""Outbound Slack for the instances: a pass-through to the Slack Web API with the bot
token the gateway already holds (issue-519, R2, R3, R6).

An instance behind a gateway reads Slack through it but, until this module, still needed
the app's bot token in its own environment to write anything back. The gateway's Socket
Mode ingress cannot start without that same token, so the secret was on the gateway and
on every instance at once. Now an instance with no token sends each Slack Web API call it
would have made — method name and parameters — to ``POST /api/v1/gateway/slack/call``,
and the gateway makes the call and returns Slack's answer verbatim.

Three checks, nothing more (the owner's design review: a pass-through, no state):
posting is on (``slack.post.enabled``), the token is set, and the method is one of the
fourteen the instance calls. The gateway stores nothing, retries nothing and never falls
back to another credential; a call it cannot make is an answer the instance turns into
one failed post. Message text never reaches the event log — ``gateway.slack_call``
carries the method, the channel and the outcome.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .. import eventlog
from ..channels import attachments

__all__ = ["SLACK_METHODS", "ProxyResult", "SlackProxy"]

logger = logging.getLogger("the-loop.gateway.slack-proxy")

#: Exactly the Slack Web API methods the instance calls today (requirements R2.2,
#: plus `chat.getPermalink`, which the first enumeration missed — the record's link). A
#: flat set — not channel logic — so the gateway is not a generic bot-token oracle for
#: ``admin.*`` or ``conversations.invite``. A new call site on the instance is one name
#: here, reviewed as such. Every one of them accepts a JSON body.
SLACK_METHODS = frozenset(
    {
        "chat.postMessage",
        "chat.update",
        "chat.postEphemeral",
        "chat.delete",
        "chat.getPermalink",
        "reactions.add",
        "views.open",
        "conversations.info",
        "conversations.list",
        "conversations.replies",
        "conversations.history",
        "users.list",
        "files.info",
        "auth.test",
    }
)

#: Why the gateway cannot post, as ``503 posting-unavailable`` says it (R2.3, R6.1).
REASON_DISABLED = "disabled"
REASON_NO_TOKEN = "no-token"
REASON_NO_SOCKET = "socket-unconfigured"


@dataclass(frozen=True)
class ProxyResult:
    """What a route returns: Slack's status and body as they came (R2.4), or the
    gateway's own refusal (``{"error": …}``); for a download, the bytes and their type."""

    status: int
    body: Any
    headers: Dict[str, str] = field(default_factory=dict)
    media_type: str = "application/json"


def _default_web_client(token: str):
    """The SDK client with **no retry handler** (critic review, round 1): the SDK's
    default retries a connection error once, which could post a message twice when Slack
    accepted the first attempt before the connection reset. One call here is one HTTP
    attempt; a transport failure is `502 slack-unreachable` for the instance to handle."""
    from slack_sdk import WebClient  # type: ignore[import-not-found]

    return WebClient(token=token, retry_handlers=[])


class SlackProxy:
    """The calls, against the live config of ``state`` so a reload is seen at once."""

    def __init__(
        self,
        state: Any,
        *,
        web_client_factory: Optional[Callable[[str], Any]] = None,
        fetch: Optional[Callable[..., Tuple[str, bytes]]] = None,
    ) -> None:
        self.state = state
        self._web_client_factory = web_client_factory or _default_web_client
        self._fetch = fetch or attachments.fetch_url

    # -- the three checks ----------------------------------------------------------------------

    def available(self) -> Tuple[bool, str]:
        """``(True, "")`` when the gateway can post, else ``(False, <reason>)`` — read
        from the live config and the environment at call time (R2.3, R6.3)."""
        slack = self.state.config.slack
        if slack is None:
            return False, REASON_NO_SOCKET
        if not slack.post.enabled:
            return False, REASON_DISABLED
        if not os.environ.get(slack.socket.bot_token_env):
            return False, REASON_NO_TOKEN
        return True, ""

    def _token(self) -> str:
        slack = self.state.config.slack
        return (os.environ.get(slack.socket.bot_token_env) or "") if slack else ""

    def _unavailable(self, instance: str, what: str, reason: str) -> ProxyResult:
        eventlog.emit(
            "gateway.refused",
            level="warning",
            instance=instance,
            reason="posting-unavailable",
            detail=reason,
            **{what: None},
        )
        return ProxyResult(503, {"error": "posting-unavailable", "reason": reason})

    # -- the call ---------------------------------------------------------------------------------

    def call(
        self, instance: str, method: str, params: Mapping[str, Any]
    ) -> ProxyResult:
        """One Slack Web API call for ``instance``: Slack's status, body and
        ``Retry-After`` come back as they are — an ``ok: false`` included — so the
        instance sees what a local client would (R2.1, R2.4). A method outside
        :data:`SLACK_METHODS` is ``422`` and nothing is sent (abuse case 1); a transport
        failure is ``502 slack-unreachable``."""
        ok, reason = self.available()
        if not ok:
            return self._unavailable(instance, "method", reason)
        if method not in SLACK_METHODS:
            eventlog.emit(
                "gateway.refused",
                level="warning",
                instance=instance,
                reason="method-not-allowed",
                method=method[:64],
            )
            return ProxyResult(
                422,
                {
                    "error": "method-not-allowed",
                    "method": method[:64],
                    "detail": "not a Slack Web API method the-loop calls",
                },
            )
        if "token" in params:
            # slack_sdk pops a `token` key out of the JSON body and uses it in place of
            # the client's: a peer could make this gateway call Slack with a credential of
            # its own, under this gateway's name in the log (security review, issue-519).
            # The call is made with the gateway's token or not at all.
            eventlog.emit(
                "gateway.refused",
                level="warning",
                instance=instance,
                reason="param-not-allowed",
                method=method,
                param="token",
            )
            return ProxyResult(
                422,
                {
                    "error": "param-not-allowed",
                    "param": "token",
                    "detail": "the gateway posts with its own token only",
                },
            )
        channel = params.get("channel")
        channel = str(channel)[:40] if isinstance(channel, str) else None
        status, body, headers = self._api_call(method, dict(params))
        eventlog.emit(
            "gateway.slack_call",
            level="info" if 200 <= status < 300 else "warning",
            instance=instance,
            method=method,
            channel=channel,
            status=status,
            ok=bool(isinstance(body, Mapping) and body.get("ok")),
        )
        return ProxyResult(status, body, headers)

    def _api_call(
        self, method: str, params: Dict[str, Any]
    ) -> Tuple[int, Any, Dict[str, str]]:
        try:
            from slack_sdk.errors import SlackApiError  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001 — the SDK is a declared dependency; be safe
            SlackApiError = ()  # type: ignore[assignment,misc]
        client = self._web_client_factory(self._token())
        try:
            response = client.api_call(method, json=params)
        except SlackApiError as exc:  # Slack answered, ok: false (a 429 included)
            response = getattr(exc, "response", None)
            return (
                int(getattr(response, "status_code", 200) or 200),
                _data_of(response, fallback={"ok": False, "error": str(exc)[:200]}),
                _retry_after(response),
            )
        except Exception as exc:  # noqa: BLE001 — transport: SlackClientError, OSError…
            logger.warning(
                "gateway: slack %s not reached: %s", method, type(exc).__name__
            )
            return (
                502,
                {
                    "error": "slack-unreachable",
                    "detail": f"{type(exc).__name__}: {str(exc)[:200]}",
                },
                {},
            )
        return (
            int(getattr(response, "status_code", 200) or 200),
            _data_of(response, fallback={"ok": True}),
            _retry_after(response),
        )

    # -- the download ----------------------------------------------------------------------------

    def download(self, instance: str, url: str) -> ProxyResult:
        """A message's file for ``instance``, fetched with the bot token under the
        instance's own rules — Slack's hosts only, every redirect re-checked, the 25 MiB
        cap (R3.1). An off-host or non-https URL is refused before any request (R3.2)."""
        ok, reason = self.available()
        if not ok:
            return self._unavailable(instance, "url", reason)
        host = attachments._url_host(url)  # noqa: SLF001 — the one host rule, shared
        if not attachments._host_allowed(host, attachments.SLACK_HOSTS):  # noqa: SLF001
            return self._download_failed(instance, host, "off-host", 422)
        try:
            media_type, data = self._fetch(
                url,
                credential=self._token(),
                allowed_hosts=attachments.SLACK_HOSTS,
                max_bytes=attachments.MAX_BYTES,
            )
        except attachments.FetchError as exc:
            status = {"off-host": 422, "over-cap": 413}.get(exc.reason, 502)
            return self._download_failed(instance, host, exc.reason, status, exc.detail)
        eventlog.emit(
            "gateway.slack_download",
            instance=instance,
            host=host,
            status=200,
            size=len(data),
        )
        return ProxyResult(200, data, {}, media_type or "application/octet-stream")

    def _download_failed(
        self, instance: str, host: str, reason: str, status: int, detail: str = ""
    ) -> ProxyResult:
        eventlog.emit(
            "gateway.slack_download",
            level="warning",
            instance=instance,
            host=host or None,
            status=status,
            reason=reason,
        )
        body: Dict[str, Any] = {"error": reason}
        if detail:
            body["detail"] = detail[:200]
        return ProxyResult(status, body)


def _data_of(response: Any, *, fallback: Mapping[str, Any]) -> Any:
    data = getattr(response, "data", None)
    if isinstance(data, Mapping):
        return dict(data)
    if isinstance(data, (bytes, bytearray)):
        return {"ok": False, "error": "non-json-response"}
    return dict(fallback)


def _retry_after(response: Any) -> Dict[str, str]:
    headers = getattr(response, "headers", None) or {}
    try:
        value = headers.get("Retry-After") or headers.get("retry-after")
    except AttributeError:
        value = None
    return {"Retry-After": str(value)} if value else {}
