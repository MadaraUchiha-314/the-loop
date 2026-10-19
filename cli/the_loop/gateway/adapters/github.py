"""``POST /gh-webhook`` on the gateway (issue-496, R1.3, R2.4, R6.4; abuse case 1).

GitHub's own contract, verbatim: the ``X-Hub-Signature-256`` HMAC the instance's stdlib
receiver verifies today (``webhook/server.verify_signature``, constant-time), the
``X-GitHub-Event`` and ``X-GitHub-Delivery`` headers, ``202`` once stored. A webhook
configured for an instance is re-pointed at the gateway without change. The route is
served only while its secret variable is set: no secret, no route (fail-closed).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from ...webhook.server import verify_signature
from ..config import GatewayConfig
from .ingest import Ingest

__all__ = ["build_github_router", "github_secret"]

logger = logging.getLogger("the-loop.gateway.github")


def github_secret(config: GatewayConfig) -> Optional[str]:
    """The webhook secret's value, or ``None`` when the route must not be served."""
    if config.github is None or not config.github.webhook.enabled:
        return None
    return os.environ.get(config.github.webhook.secret_env) or None


def build_github_router(ingest: Ingest, config: GatewayConfig) -> APIRouter:
    router = APIRouter()
    path = config.github.webhook.path if config.github else "/gh-webhook"
    secret_env = config.github.webhook.secret_env if config.github else ""

    @router.post(path, operation_id="githubWebhook", include_in_schema=True)
    async def gh_webhook(request: Request) -> Any:
        secret = os.environ.get(secret_env) if secret_env else None
        if not secret:
            # the route exists in the schema but is not served without its secret
            return JSONResponse(status_code=404, content={"status": "not found"})
        body = await request.body()
        delivery = request.headers.get("X-GitHub-Delivery", "-")
        event = request.headers.get("X-GitHub-Event", "unknown")
        if (
            verify_signature(secret, body, request.headers.get("X-Hub-Signature-256"))
            is not True
        ):
            ingest._dropped("github", event, delivery, "bad-signature")
            return JSONResponse(
                status_code=401, content={"status": "invalid signature"}
            )
        try:
            outcome = ingest.accept(
                "github", "webhook", event, delivery, request.headers, body
            )
        except Exception:  # noqa: BLE001 — the store failed: GitHub retries on a 5xx
            logger.exception("gateway: storing GitHub delivery %s failed", delivery)
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

    @router.get("/health", operation_id="ingressHealth", include_in_schema=False)
    def health() -> Response:
        return JSONResponse(content={"status": "ok"})

    return router
