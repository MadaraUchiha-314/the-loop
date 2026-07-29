"""Slack providers — the official SDK, and a dependency-free fallback.

Slack **does** publish an official Python SDK, and `slack_sdk.webhook
.WebhookClient` is how an incoming webhook is *properly* called: retry with
exponential backoff, proxy support, SSL context. It declares **zero required
runtime dependencies**, so adopting it costs nothing.

"webhook or SDK" was a false dichotomy — the SDK *is* the client for the
webhook. The raw transport remains for operators who want no dependency at all.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, FrozenSet

from .base import IntegrationError, OperationUnsupported

logger = logging.getLogger("the-loop.graph.integrations")

__all__ = ["OPERATIONS", "SlackSdk", "SlackWebhook"]

OPERATIONS: FrozenSet[str] = frozenset({"post-message"})


class _SlackBase:
    name = "slack"
    operations = OPERATIONS

    def __init__(self, url_env: str):
        self.url_env = url_env

    def _url(self) -> str:
        url = os.environ.get(self.url_env)
        if not url:
            raise IntegrationError(f"slack has no webhook url — set {self.url_env}")
        return url


class SlackSdk(_SlackBase):
    """The official `slack-sdk` webhook client."""

    transport = "sdk"

    def __init__(self, url_env: str):
        super().__init__(url_env)
        from slack_sdk.webhook import (  # type: ignore[import-not-found]
            WebhookClient,  # noqa: F401 — probed here so `auto` can fall back
        )

        self._client_cls = WebhookClient

    def call(self, op: str, **params: Any) -> Dict[str, Any]:
        if op not in self.operations:
            raise OperationUnsupported(f"slack/sdk does not implement {op!r}")
        client = self._client_cls(url=self._url())
        response = client.send(text=str(params["text"]))
        if response.status_code != 200:
            raise IntegrationError(
                f"slack webhook returned {response.status_code}: {response.body}"
            )
        return {"result": "ok"}


class SlackWebhook(_SlackBase):
    """Raw POST — no dependency at all."""

    transport = "webhook"

    def call(self, op: str, **params: Any) -> Dict[str, Any]:
        if op not in self.operations:
            raise OperationUnsupported(f"slack/webhook does not implement {op!r}")
        payload = json.dumps({"text": str(params["text"])}).encode()
        req = urllib.request.Request(
            self._url(),
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    raise IntegrationError(f"slack webhook returned {resp.status}")
        except urllib.error.URLError as exc:
            raise IntegrationError(f"slack webhook failed: {exc.reason}") from None
        return {"result": "ok"}
