"""Cursor adapter: ``cursor-agent -p … --resume <chat-id> --output-format json``.

Cursor has no official Python SDK (its SDK is TypeScript), so the official
CLI is the programmatic surface (issue #15's TODO). Non-interactive
``cursor-agent ls`` is unreliable for id discovery, so the chat id is
required at registration time. ``--force`` (auto-approval) is only added when
the user configures it via ``routing.harnessArgs.cursor``.
"""

from __future__ import annotations

from typing import List

from .base import HarnessAdapter
from ..sessions import Session


class CursorAgentAdapter(HarnessAdapter):
    name = "cursor"
    default_binary = "cursor-agent"

    def _resume_argv(self, session: Session, prompt: str) -> List[str]:
        return [
            "-p",
            prompt,
            "--resume",
            session.harness_session_id,
            "--output-format",
            "json",
        ] + self.extra_args

    def _spawn_argv(self, prompt: str) -> List[str]:
        return ["-p", prompt, "--output-format", "json"] + self.extra_args
