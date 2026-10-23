"""The instance's gateway-backed Slack client (issue-519, R3.3, R4.2, R4.4).

An instance behind a gateway with no bot token of its own gets this in place of the
SDK's ``WebClient``: the same method names, each one ``POST /api/v1/gateway/slack/call``
with the method and its parameters, made by the gateway with the token it already holds
for Socket Mode. The answer maps to what the SDK would have given — a ``dict`` for
``ok: true``, the SDK's own ``SlackApiError`` for ``ok: false`` — so every call site, the
stale-``ts`` fallback and the best-effort reactions behave exactly as with a local token.
A gateway that is unreachable or refuses is one :class:`GatewayPostingError` (a
``ChannelError``): the post fails, and nothing here reads a token or retries.

``fetch`` has :func:`the_loop.channels.attachments.fetch_url`'s shape so the attachment
fetcher takes it unchanged; the gateway holds the credential, so the argument is ignored.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .attachments import MAX_BYTES, TIMEOUT_SECONDS, FetchError
from .base import ChannelError

__all__ = ["CALL_PATH", "DOWNLOAD_PATH", "GatewayPostingError", "GatewaySlackClient"]

logger = logging.getLogger("the-loop.channels")

CALL_PATH = "/api/v1/gateway/slack/call"
DOWNLOAD_PATH = "/api/v1/gateway/slack/download"
#: One call's budget: the gateway answers Slack's own latency plus a loopback hop.
CALL_TIMEOUT_S = 10.0

#: ``(url, timeout) -> (status, content type, bytes)`` — the download leg, bytes not JSON.
Download = Callable[[str, float], Tuple[int, str, bytes]]


class GatewayPostingError(ChannelError):
    """The gateway could not make the call — unreachable, refused, or not posting. The
    caller's post fails; there is no second credential to fall back to (R4.4)."""


class GatewaySlackClient:
    """The fourteen SDK method names the instance uses, each a call to the gateway."""

    def __init__(
        self,
        url: str,
        instance: str,
        peer: str,
        *,
        transport: Optional[Callable[..., Tuple[int, Any]]] = None,
        download: Optional[Download] = None,
        timeout: float = CALL_TIMEOUT_S,
    ) -> None:
        from ..gateway.client import urllib_transport

        self.url = url.rstrip("/")
        self.instance = instance
        self.peer = peer
        self.timeout = timeout
        self._transport = transport or urllib_transport(self.url)
        self._download: Download = download or self._urllib_download

    @classmethod
    def from_cli_config(cls, cli_config: Mapping[str, Any]) -> "GatewaySlackClient":
        """From the instance's `gateway` block, its name and the peer id the hosted
        gateway client persists — the same id, so the gateway's lease check sees one
        peer whether the call comes from the daemon or from `the-loop doctor slack` in
        another process. No file yet (the daemon never ran) sends an empty peer."""
        from .. import cli_config as cli_config_mod
        from ..gateway.client import PEER_FILE
        from ..state import layout_from_config

        block = cli_config_mod.gateway_block(cli_config)
        if block is None:
            raise ValueError("the config has no usable `gateway` block")
        peer = ""
        try:
            path = Path(layout_from_config(dict(cli_config)).local_dir) / PEER_FILE
            data = json.loads(path.read_text(encoding="utf-8"))
            peer = str(data.get("peer") or "")
        except (OSError, ValueError, AttributeError):
            peer = ""
        return cls(block.url, cli_config_mod.instance_name(cli_config), peer)

    # -- the call -----------------------------------------------------------------------------

    def _call(self, method: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        body = {
            "instance": self.instance,
            "peer": self.peer,
            "method": method,
            "params": dict(params),
        }
        try:
            status, answer = self._transport("POST", CALL_PATH, body, self.timeout)
        except Exception as exc:  # noqa: BLE001 — the transport's whole failure set
            raise GatewayPostingError(
                f"slack: gateway unreachable at {self.url} for {method} "
                f"({type(exc).__name__}); the post fails, no local token is tried"
            ) from exc
        if not isinstance(answer, Mapping):
            raise GatewayPostingError(
                f"slack: the gateway at {self.url} answered {method} with status "
                f"{status} and no JSON body"
            )
        if "ok" in answer:
            # Slack's own answer, passed through (R2.4)
            if answer.get("ok"):
                return dict(answer)
            raise _slack_api_error(method, dict(answer))
        error = str(answer.get("error") or f"status {status}")
        detail = answer.get("reason") or answer.get("detail") or answer.get("holder")
        raise GatewayPostingError(
            f"slack: the gateway refused {method} ({status} {error}"
            + (f": {detail}" if detail else "")
            + ")"
        )

    # the SDK's method names (requirements R2.2) — keyword arguments as the SDK takes them
    def chat_postMessage(self, **params: Any) -> Dict[str, Any]:  # noqa: N802
        return self._call("chat.postMessage", params)

    def chat_update(self, **params: Any) -> Dict[str, Any]:
        return self._call("chat.update", params)

    def chat_postEphemeral(self, **params: Any) -> Dict[str, Any]:  # noqa: N802
        return self._call("chat.postEphemeral", params)

    def chat_delete(self, **params: Any) -> Dict[str, Any]:
        return self._call("chat.delete", params)

    def chat_getPermalink(self, **params: Any) -> Dict[str, Any]:  # noqa: N802
        return self._call("chat.getPermalink", params)

    def reactions_add(self, **params: Any) -> Dict[str, Any]:
        return self._call("reactions.add", params)

    def views_open(self, **params: Any) -> Dict[str, Any]:
        return self._call("views.open", params)

    def conversations_info(self, **params: Any) -> Dict[str, Any]:
        return self._call("conversations.info", params)

    def conversations_list(self, **params: Any) -> Dict[str, Any]:
        return self._call("conversations.list", params)

    def conversations_replies(self, **params: Any) -> Dict[str, Any]:
        return self._call("conversations.replies", params)

    def conversations_history(self, **params: Any) -> Dict[str, Any]:
        return self._call("conversations.history", params)

    def users_list(self, **params: Any) -> Dict[str, Any]:
        return self._call("users.list", params)

    def files_info(self, **params: Any) -> Dict[str, Any]:
        return self._call("files.info", params)

    def auth_test(self, **params: Any) -> Dict[str, Any]:
        return self._call("auth.test", params)

    # -- the download -------------------------------------------------------------------------

    def fetch(
        self,
        url: str,
        *,
        credential: str = "",
        allowed_hosts: Any = (),
        max_bytes: int = MAX_BYTES,
        timeout: float = TIMEOUT_SECONDS,
        **_: Any,
    ) -> Tuple[str, bytes]:
        """``fetch_url``'s shape (R3.3): ``(content type, bytes)`` or ``FetchError`` with
        the gateway's reason. ``credential`` is ignored — the gateway holds it — and the
        host rule and the cap are applied by the gateway."""
        try:
            status, media_type, data = self._download(url, timeout)
        except Exception as exc:  # noqa: BLE001
            raise FetchError(
                "transfer-failed", f"gateway unreachable: {type(exc).__name__}"
            )
        if status == 200:
            return media_type or "application/octet-stream", data
        try:
            answer = json.loads(data.decode("utf-8")) if data else {}
        except ValueError:
            answer = {}
        error = str(answer.get("error") or f"status {status}")
        if status == 503:
            # the attachment line's existing word for "no credential could fetch it"
            raise FetchError(
                "no-token", f"gateway posting {answer.get('reason') or 'off'}"
            )
        if error in ("off-host", "over-cap", "transfer-failed"):
            raise FetchError(error, str(answer.get("detail") or ""))
        raise FetchError("transfer-failed", f"gateway {status} {error}")

    def _urllib_download(self, url: str, timeout: float) -> Tuple[int, str, bytes]:
        body = json.dumps(
            {"instance": self.instance, "peer": self.peer, "url": url}
        ).encode("utf-8")
        request = urllib.request.Request(
            self.url + DOWNLOAD_PATH,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 — the configured gateway URL
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    return 413, "application/json", b'{"error": "over-cap"}'
                return (
                    response.status,
                    str(response.headers.get("Content-Type") or ""),
                    data,
                )
        except urllib.error.HTTPError as exc:
            return exc.code, str(exc.headers.get("Content-Type") or ""), exc.read()


def _slack_api_error(method: str, answer: Dict[str, Any]) -> Exception:
    """The SDK's own exception for ``ok: false`` so existing ``except`` paths hold; a
    ``ChannelError`` only if the SDK is somehow absent."""
    error = str(answer.get("error") or "unknown_error")
    try:
        from slack_sdk.errors import SlackApiError  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return ChannelError(f"slack: {method} failed: {error}")
    return SlackApiError(f"slack: {method} failed: {error}", answer)
