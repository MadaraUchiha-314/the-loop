"""Cursor adapter: one-shot ``cursor-agent -p … --output-format json`` (critics).

Cursor has no official Python SDK (its SDK is TypeScript), so the official
CLI is the programmatic surface (issue #15's TODO). ``cursor-agent`` has no
pre-assignable session id in interactive mode, so it cannot be hosted in tmux
(the base class's ``interactive_*`` methods raise ``UnsupportedRunnerError``);
it remains available as a critic harness via ``oneshot_argv``. ``--force``
(auto-approval) is only added when the user configures it via
``routing.harnessArgs.cursor``.
"""

from __future__ import annotations

from typing import List

from .base import HarnessAdapter


class CursorAgentAdapter(HarnessAdapter):
    name = "cursor"
    default_binary = "cursor-agent"
    model_flag = "-m"

    def _oneshot_argv(self, prompt: str) -> List[str]:
        return ["-p", prompt, "--output-format", "json"] + self.extra_args
