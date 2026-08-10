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
    """Where the webhook URL comes from — the one thing both transports share.

    Two sources, `integrations.slack.url` first (issue-203). The env-only rule
    that preceded it made the single value that turns notifications on the one
    value the-loop's own configuration could not hold: it had to be exported into
    every process that might deliver one — the poll daemon, the harness sessions
    it spawns, a fresh machine's provisioning — and a restart from a shell
    missing the export stopped delivery with nothing louder than a log line.

    An incoming-webhook URL is a bearer credential for exactly one channel, so
    whether it is a secret is the operator's call to make, not the harness's. It
    is still a credential: inlining it commits it, which is why `urlEnv` remains
    the default and the documentation states the trade-off rather than the
    choice. Precedence never depends on the environment — otherwise reading the
    config would not tell you where a notification goes.
    """

    name = "slack"
    operations = OPERATIONS

    def __init__(self, url_env: str, url: str = ""):
        self.url_env = url_env
        self.url = url

    def _url(self) -> str:
        # Read at call time, not construction time: a provider outlives many
        # graph transitions and must see the environment as it is when it posts.
        url = self.url or os.environ.get(self.url_env) or ""
        if not url:
            raise IntegrationError(
                "slack has no webhook url — set integrations.slack.url in the "
                f"CLI config, or export {self.url_env}"
            )
        return url


class SlackSdk(_SlackBase):
    """The official `slack-sdk` webhook client."""

    transport = "sdk"

    def __init__(self, url_env: str, url: str = ""):
        super().__init__(url_env, url)
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
