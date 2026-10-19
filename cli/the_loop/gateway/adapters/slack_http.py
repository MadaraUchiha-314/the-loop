"""Slack's HTTP routes on the gateway (issue-496, R6.4, R7.2; abuse case 2).

``POST /slack/events``, ``/slack/interactions`` and ``/slack/commands`` under Slack's own
contract: ``X-Slack-Signature`` is ``v0=`` + HMAC-SHA256 of ``v0:<timestamp>:<body>``
with the signing secret, verified in constant time, and a timestamp more than 300 s from
now is a replay (401, nothing stored). The ``url_verification`` challenge is answered
without storing. Everything else is stored, then answered 200 inside Slack's three
seconds. Behind ``slack.http.enabled``; served only while the signing secret is set.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from ..config import GatewayConfig
from .ingest import Ingest

__all__ = ["REPLAY_WINDOW_S", "build_slack_http_router", "verify_slack_signature"]

logger = logging.getLogger("the-loop.gateway.slack-http")

REPLAY_WINDOW_S = 300


def verify_slack_signature(
    secret: str,
    timestamp: str,
    body: bytes,
    signature: Optional[str],
    *,
    now: Optional[float] = None,
) -> str:
    """``""`` when valid, else the refusal reason (``replay-window`` | ``bad-signature``)."""
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return "bad-signature"
    if abs((time.time() if now is None else now) - ts) > REPLAY_WINDOW_S:
        return "replay-window"
    if not signature or not signature.startswith("v0="):
        return "bad-signature"
    base = b"v0:" + str(ts).encode() + b":" + body
    expected = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    return "" if hmac.compare_digest(expected, signature) else "bad-signature"


def build_slack_http_router(ingest: Ingest, config: GatewayConfig) -> APIRouter:
    router = APIRouter()
    del config  # the live config is read from the ingest's state at request time

    async def _accept(request: Request, kind: str) -> Any:
        live = ingest.state.config.slack
        secret = (
            os.environ.get(live.http.signing_secret_env)
            if live is not None and live.http.enabled
            else None
        )
        if not secret:
            return JSONResponse(status_code=404, content={"status": "not found"})
        body = await request.body()
        reason = verify_slack_signature(
            secret,
            request.headers.get("X-Slack-Request-Timestamp", ""),
            body,
            request.headers.get("X-Slack-Signature"),
        )
        if reason:
            ingest._dropped("slack", kind, "-", reason)
            return JSONResponse(status_code=401, content={"status": reason})
        payload = _payload(kind, body, request.headers.get("content-type", ""))
        if payload is None:
            return JSONResponse(status_code=400, content={"status": "invalid payload"})
        if kind == "events_api" and payload.get("type") == "url_verification":
            return PlainTextResponse(str(payload.get("challenge") or ""))
        delivery_id = str(
            payload.get("event_id")
            or payload.get("trigger_id")
            or f"http-{int(time.time() * 1000)}"
        )
        try:
            outcome = ingest.accept(
                "slack",
                "webhook",
                kind,
                delivery_id,
                request.headers,
                body,
                payload=payload,
            )
        except Exception:  # noqa: BLE001 — a 5xx makes Slack retry
            logger.exception("gateway: storing Slack HTTP delivery failed")
            return JSONResponse(status_code=500, content={"status": "store failed"})
        if outcome.status == "invalid":
            return JSONResponse(status_code=400, content={"status": "invalid payload"})
        return JSONResponse(status_code=200, content={"ok": True})

    @router.post("/slack/events", operation_id="slackEvents")
    async def events(request: Request) -> Any:
        return await _accept(request, "events_api")

    @router.post("/slack/interactions", operation_id="slackInteractions")
    async def interactions(request: Request) -> Any:
        return await _accept(request, "interactive")

    @router.post("/slack/commands", operation_id="slackCommands")
    async def commands(request: Request) -> Any:
        return await _accept(request, "slash_commands")

    return router


def _payload(kind: str, body: bytes, content_type: str) -> Optional[Dict[str, Any]]:
    """Slack posts events as JSON, interactions as a form with a `payload` field, and
    slash commands as a plain form — one object out, whichever came in."""
    text = body.decode("utf-8", "replace")
    if "json" in content_type or (text.startswith("{") and kind == "events_api"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None
    form = {k: v[0] for k, v in parse_qs(text, keep_blank_values=True).items()}
    if kind == "interactive":
        try:
            data = json.loads(form.get("payload") or "")
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None
    return form or None
