"""A minimal, dependency-free GitHub webhook receiver.

Uses only the standard library so the CLI stays very lightweight. The server
verifies the GitHub ``X-Hub-Signature-256`` HMAC (when a secret is configured),
logs each received event, and invokes an optional ``on_event`` callback.
Routing events to harness sessions is composed on top via ``on_event``
(``gh-webhook start --route``; docs/specs/issue-15/design.md).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional

from .. import eventlog

logger = logging.getLogger("the-loop.gh-webhook")

# Per-event callback: (event_name, payload_dict, delivery_id) -> None.
# The delivery id (X-GitHub-Delivery) enables at-most-once routing.
OnEvent = Callable[[str, dict, str], None]


def verify_signature(
    secret: Optional[str], body: bytes, signature_header: Optional[str]
):
    """Verify a GitHub ``X-Hub-Signature-256`` header.

    Returns ``True``/``False`` when a secret is configured, or ``None`` when no
    secret is configured (signature cannot be verified). Uses a constant-time
    comparison.
    """
    if not secret:
        return None
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    expected = "sha256=" + digest
    return hmac.compare_digest(expected, signature_header)


def make_handler(path: str, secret: Optional[str], on_event: Optional[OnEvent] = None):
    """Build a ``BaseHTTPRequestHandler`` subclass bound to the given config."""

    class _Handler(BaseHTTPRequestHandler):
        server_version = "the-loop-gh-webhook/0.1.0"

        def _send(self, code: int, message: str) -> None:
            payload = json.dumps({"status": message}).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):  # noqa: N802 (stdlib naming)
            if self.path.rstrip("/") in ("/health", "/healthz"):
                self._send(200, "ok")
            else:
                self._send(404, "not found")

        def do_POST(self):  # noqa: N802
            if self.path.rstrip("/") != path.rstrip("/"):
                self._send(404, "not found")
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""

            verified = verify_signature(
                secret, body, self.headers.get("X-Hub-Signature-256")
            )
            delivery = self.headers.get("X-GitHub-Delivery", "-")
            event = self.headers.get("X-GitHub-Event", "unknown")
            if verified is False:
                logger.warning("rejected webhook: invalid signature")
                eventlog.emit(
                    "webhook.rejected",
                    level="warning",
                    reason="invalid-signature",
                    gh_event=event,
                    delivery_id=delivery,
                )
                self._send(401, "invalid signature")
                return
            if verified is None:
                logger.warning("webhook signature NOT verified (no secret configured)")

            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
            except json.JSONDecodeError:
                logger.error(
                    "webhook payload was not valid JSON (delivery=%s)", delivery
                )
                eventlog.emit(
                    "webhook.rejected",
                    level="error",
                    reason="invalid-payload",
                    gh_event=event,
                    delivery_id=delivery,
                )
                self._send(400, "invalid payload")
                return

            logger.info("received event=%s delivery=%s", event, delivery)
            eventlog.emit(
                "webhook.received",
                gh_event=event,
                action=payload.get("action"),
                delivery_id=delivery,
                verified=bool(verified),
            )
            if on_event is not None:
                try:
                    on_event(event, payload, delivery)
                except Exception:  # noqa: BLE001 - never let a handler crash the server
                    logger.exception("on_event handler failed for event=%s", event)
            self._send(202, "accepted")

        def log_message(self, format, *args):  # noqa: A002 - match base signature
            logger.debug(format, *args)

    return _Handler


def serve(
    host: str,
    port: int,
    path: str = "/gh-webhook",
    secret: Optional[str] = None,
    on_event: Optional[OnEvent] = None,
) -> ThreadingHTTPServer:
    """Create (but do not start) a threaded HTTP server bound to ``host:port``."""
    handler = make_handler(path=path, secret=secret, on_event=on_event)
    return ThreadingHTTPServer((host, port), handler)
