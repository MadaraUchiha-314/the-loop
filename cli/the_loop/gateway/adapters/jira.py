"""``POST /jira-webhook`` on the gateway (issue-496, R1.4, R6.4; abuse case 1).

The instance doorbell's contract: ``X-Hub-Signature`` (sha256 HMAC) verified before the
body is parsed, ``X-Atlassian-Webhook-Identifier`` kept as the delivery id, a 404 when no
secret is configured — the route does not exist. The three doorbell fields are read with
``webhook/jira.read_doorbell``; the ref is ``jira:<site>/<KEY>`` on a mapped project.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...webhook.server import verify_signature
from ..config import GatewayConfig
from .ingest import Ingest

__all__ = ["JIRA_PATH", "build_jira_router", "jira_secret"]

logger = logging.getLogger("the-loop.gateway.jira")

JIRA_PATH = "/jira-webhook"


def jira_secret(config: GatewayConfig) -> Optional[str]:
    if config.jira is None or not config.jira.webhook.enabled:
        return None
    return os.environ.get(config.jira.webhook.secret_env) or None


def build_jira_router(ingest: Ingest, config: GatewayConfig) -> APIRouter:
    router = APIRouter()
    del config  # the live config is read from the ingest's state at request time

    @router.post(JIRA_PATH, operation_id="jiraWebhook")
    async def jira_webhook(request: Request) -> Any:
        live = ingest.state.config.jira
        secret = (
            os.environ.get(live.webhook.secret_env)
            if live is not None and live.webhook.enabled
            else None
        )
        if not secret:
            return JSONResponse(status_code=404, content={"status": "not found"})
        body = await request.body()
        ident = request.headers.get("X-Atlassian-Webhook-Identifier") or "-"
        if (
            verify_signature(secret, body, request.headers.get("X-Hub-Signature"))
            is not True
        ):
            ingest._dropped("jira", "webhook", ident, "bad-signature")
            return JSONResponse(
                status_code=401, content={"status": "invalid signature"}
            )
        kind = _kind(body)
        try:
            outcome = ingest.accept(
                "jira", "webhook", kind, ident, request.headers, body
            )
        except Exception:  # noqa: BLE001
            logger.exception("gateway: storing Jira delivery %s failed", ident)
            return JSONResponse(status_code=500, content={"status": "store failed"})
        if outcome.status == "invalid":
            return JSONResponse(status_code=400, content={"status": "invalid payload"})
        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted" if outcome.accepted else "dropped",
                "reason": outcome.reason or None,
            },
        )

    return router


def _kind(body: bytes) -> str:
    """``webhookEvent`` of the delivery, read leniently (the ingest parses for real)."""
    import json

    try:
        doc = json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "unknown"
    from ...webhook.jira import read_doorbell

    return read_doorbell(doc if isinstance(doc, dict) else {}).event or "unknown"
