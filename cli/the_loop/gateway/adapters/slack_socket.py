"""One Socket Mode connection per Slack app, on the gateway (issue-496, R1.2, R2.4,
R2.5, R5.9).

The **transport** half of the instance's listener (``channels/slack.py``): connect with
the app-level token, hear every envelope, and acknowledge it — here, **after**
``store.append`` returns (R2.4), so the ack implies the fan-out is durable and a store
failure withholds the ack and Slack redelivers. The classification half stays on the
instance (``slack.dispatch_envelope``, called by the gateway client). The doctor's
heartbeat is the one envelope consumed here: the connection that heard it is the one
the split check is about (``SplitWatch.observe``), and it is never stored.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable, Mapping, Optional

from ...channels.slack import ENVELOPE_TYPES, heartbeat_of
from ..config import GatewayConfig
from .ingest import Ingest

__all__ = ["SlackSocketAdapter", "slack_tokens"]

logger = logging.getLogger("the-loop.gateway.slack-socket")


def slack_tokens(config: GatewayConfig) -> Optional[tuple]:
    """``(app_token, bot_token)`` from the environment, or ``None`` when the socket is
    off or a token is unset (the ingress then does not start: fail-closed)."""
    if config.slack is None or not config.slack.socket.enabled:
        return None
    app = os.environ.get(config.slack.socket.app_token_env) or ""
    bot = os.environ.get(config.slack.socket.bot_token_env) or ""
    if not app or not bot:
        return None
    return app, bot


class SlackSocketAdapter:
    """``start`` opens the one connection; ``handle`` is the request listener."""

    def __init__(
        self,
        ingest: Ingest,
        config: GatewayConfig,
        *,
        client_factory: Optional[Callable[..., Any]] = None,
        web_client_factory: Optional[Callable[[str], Any]] = None,
        watch: Any = None,
    ) -> None:
        self.ingest = ingest
        self.config = config
        self._client_factory = client_factory
        self._web_client_factory = web_client_factory
        self.watch = watch
        self.client: Any = None
        self._lock = threading.Lock()
        self.state = "off"  # off | up | down

    # -- lifecycle ------------------------------------------------------------------------

    def start(self) -> bool:
        tokens = slack_tokens(self.config)
        if tokens is None:
            logger.warning("gateway: Slack Socket Mode not started — tokens unset")
            return False
        app_token, bot_token = tokens
        if self._client_factory is None:
            from slack_sdk.socket_mode import SocketModeClient  # type: ignore[import-not-found]

            from ...channels.slack import build_client

            web_client = (self._web_client_factory or build_client)(bot_token)
            self.client = SocketModeClient(app_token=app_token, web_client=web_client)
        else:
            web_client = (self._web_client_factory or (lambda token: None))(bot_token)
            self.client = self._client_factory(
                app_token=app_token, web_client=web_client
            )
        self.client.socket_mode_request_listeners.append(self.handle)
        self.client.connect()
        self.state = "up"
        logger.info(
            "gateway: Slack Socket Mode connected (one connection for this app)"
        )
        return True

    def stop(self) -> None:
        with self._lock:
            if self.client is not None:
                try:
                    self.client.close()
                finally:
                    self.client = None
            self.state = "off"

    # -- the listener ---------------------------------------------------------------------

    def handle(self, client: Any, request: Any) -> None:
        kind = getattr(request, "type", "")
        if kind not in ENVELOPE_TYPES:
            logger.debug("gateway: ignoring a Socket Mode envelope of type %r", kind)
            return
        payload: Mapping[str, Any] = getattr(request, "payload", None) or {}
        envelope_id = str(getattr(request, "envelope_id", "") or "")
        nonce = heartbeat_of(kind, payload)
        if nonce:
            if self.watch is not None:
                try:
                    self.watch.observe(nonce)
                except Exception:  # noqa: BLE001 — a diagnostic never breaks the ack
                    logger.exception("gateway: split watch raised on a heartbeat")
            self._ack(client, envelope_id)
            return
        try:
            self.ingest.accept(
                "slack", "socket", kind, envelope_id, {}, b"", payload=payload
            )
        except Exception:  # noqa: BLE001 — no ack: Slack redelivers the envelope
            logger.exception(
                "gateway: storing Slack envelope %s failed; not acked", envelope_id
            )
            return
        self._ack(client, envelope_id)

    @staticmethod
    def _ack(client: Any, envelope_id: str) -> None:
        try:
            from slack_sdk.socket_mode.response import (  # type: ignore[import-not-found]
                SocketModeResponse,
            )

            response: Any = SocketModeResponse(envelope_id=envelope_id)
        except Exception:  # noqa: BLE001 — the SDK is absent in a bare test environment
            response = {"envelope_id": envelope_id}
        client.send_socket_mode_response(response)
