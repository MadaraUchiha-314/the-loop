"""A minimal, dependency-free GitHub (and Jira) webhook receiver.

Uses only the standard library so the CLI stays very lightweight. The server
verifies the GitHub ``X-Hub-Signature-256`` HMAC (when a secret is configured),
logs each received event, and invokes an optional ``on_event`` callback.
Routing events to harness sessions is composed on top via ``on_event``
(``routing.enabled``; docs/specs/issue-15/design.md).

A second route, ``/jira-webhook``, exists only when a Jira webhook secret is
configured (issue-475): a Jira delivery's signature is verified before its body
is parsed, and the body is read for three fields only — a doorbell for
:mod:`.jira`, which re-fetches the issue and the comment.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional

from .. import __version__, eventlog

logger = logging.getLogger("the-loop.gh-webhook")

# Per-event callback: (event_name, payload_dict, delivery_id) -> None.
# The delivery id (X-GitHub-Delivery) enables at-most-once routing.
OnEvent = Callable[[str, dict, str], None]

#: The Jira doorbell's route (issue-475, design §C8) — served only with a secret.
JIRA_PATH = "/jira-webhook"

# Per-delivery Jira callback: (doorbell, X-Atlassian-Webhook-Identifier) -> the
# outcome, logged. The doorbell holds the three fields read from a verified
# body and nothing else (`webhook.jira.read_doorbell`).
OnJira = Callable[[Any, str], str]


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


def make_handler(
    path: str,
    secret: Optional[str],
    on_event: Optional[OnEvent] = None,
    jira_secret: Optional[str] = None,
    on_jira: Optional[OnJira] = None,
):
    """Build a ``BaseHTTPRequestHandler`` subclass bound to the given config.

    ``jira_secret`` turns on the second route, :data:`JIRA_PATH` (issue-475): a
    Jira delivery is verified (``X-Hub-Signature``) before anything else and
    handed to ``on_jira`` as a doorbell. Without a secret the path is a 404 —
    the route does not exist (abuse case 2). The GitHub route is unchanged.
    """

    class _Handler(BaseHTTPRequestHandler):
        server_version = f"the-loop-gh-webhook/{__version__}"

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
            if jira_secret and self.path.rstrip("/") == JIRA_PATH:
                self._jira()
                return
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

        def _jira(self) -> None:
            """A Jira delivery: the signature, then the three doorbell fields.

            Anything but a valid signature is a 401 **before** the body is parsed
            (R6.2, abuse case 1) — logged with the remote address, never the body.
            The webhook GUID is logged, never used as a key: the dedup key is the
            comment's own id, shared with the poller (R6.4).
            """
            from .jira import read_doorbell

            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""
            ident = str(self.headers.get("X-Atlassian-Webhook-Identifier") or "-")
            if (
                verify_signature(jira_secret, body, self.headers.get("X-Hub-Signature"))
                is not True
            ):
                logger.warning(
                    "rejected Jira webhook from %s: missing or invalid signature",
                    self.client_address[0] if self.client_address else "?",
                )
                eventlog.emit(
                    "webhook.rejected",
                    level="warning",
                    reason="invalid-signature",
                    provider="jira",
                    delivery_id=ident,
                )
                self._send(401, "invalid signature")
                return
            try:
                doc = json.loads(body.decode("utf-8")) if body else {}
            except (json.JSONDecodeError, UnicodeDecodeError):
                eventlog.emit(
                    "webhook.rejected",
                    level="error",
                    reason="invalid-payload",
                    provider="jira",
                    delivery_id=ident,
                )
                self._send(400, "invalid payload")
                return
            bell = read_doorbell(doc if isinstance(doc, dict) else {})
            logger.info(
                "received Jira %s for %s (webhook %s)",
                bell.event or "?",
                bell.issue_key or "?",
                ident,
            )
            outcome = "accepted"
            if on_jira is not None:
                try:
                    outcome = on_jira(bell, ident) or outcome
                except Exception:  # noqa: BLE001 - never let a handler crash the server
                    logger.exception("Jira doorbell failed for %s", bell.event)
                    outcome = "error"
            eventlog.emit(
                "webhook.received",
                provider="jira",
                gh_event=bell.event,
                delivery_id=ident,
                verified=True,
                outcome=outcome,
            )
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
    jira_secret: Optional[str] = None,
    on_jira: Optional[OnJira] = None,
) -> ThreadingHTTPServer:
    """Create (but do not start) a threaded HTTP server bound to ``host:port``.

    ``jira_secret``/``on_jira`` add the Jira doorbell route (issue-475); without
    a secret it is not served.
    """
    handler = make_handler(
        path=path,
        secret=secret,
        on_event=on_event,
        jira_secret=jira_secret,
        on_jira=on_jira,
    )
    return ThreadingHTTPServer((host, port), handler)
