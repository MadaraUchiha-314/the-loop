"""Claude Code adapter: ``claude -p … --resume <session-id> --output-format json``.

The session id comes from the JSON output of a previous run (or Claude Code's
``$CLAUDE_SESSION_ID`` at registration time); resume lookup is scoped to the
project directory, hence the session's recorded ``cwd``.
"""

from __future__ import annotations

from typing import List

from .base import HarnessAdapter
from ..sessions import Session


class ClaudeCodeAdapter(HarnessAdapter):
    name = "claude"
    default_binary = "claude"

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

    def interactive_argv(self, prompt: str, session_id: str) -> List[str]:
        # Flags first, positional prompt last — parsers that stop option
        # processing at the first positional must still see extra_args.
        return ["--session-id", session_id] + self.extra_args + [prompt]

    def interactive_resume_argv(self, prompt: str, session_id: str) -> List[str]:
        # `--resume <id>` without `-p` keeps Claude Code in its TUI and
        # continues the recorded conversation; the positional prompt is
        # submitted into it (issue-89). Same flags-first ordering as above.
        # Resume lookup is scoped to the project directory, hence the tmux
        # session being spawned in the registry's recorded cwd.
        return ["--resume", session_id] + self.extra_args + [prompt]
