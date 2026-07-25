"""Claude Code adapter: ``claude -p … --resume <session-id> --output-format json``.

The session id comes from the JSON output of a previous run (or Claude Code's
``$CLAUDE_SESSION_ID`` at registration time); resume lookup is scoped to the
project directory, hence the session's recorded ``cwd``.

It is also the adapter that has something to prepare before a spawn: Claude
Code's workspace-trust dialog and bypass-permissions disclaimer are not
permission rules, so no CLI flag silences them and an unattended session stalls
on them (issue-90). See :mod:`the_loop.trust`.
"""

from __future__ import annotations

from typing import List

from .base import HarnessAdapter
from ..sessions import Session
from ..trust import ClaudeTrustStore, TrustResult, args_request_bypass


class ClaudeCodeAdapter(HarnessAdapter):
    name = "claude"
    default_binary = "claude"

    def prepare_environment(self, cwd: str) -> TrustResult:
        """Pre-trust ``cwd`` (and accept the bypass disclaimer when configured)."""
        if not self.trust.enabled:
            return TrustResult()
        store = ClaudeTrustStore()
        result = store.trust(cwd)
        if self._wants_bypass():
            # Independent files: a failed trust write must not skip this one.
            result = result.merge(store.accept_bypass_permissions())
        return result

    def _wants_bypass(self) -> bool:
        """Whether to record the bypass-permissions disclaimer acceptance.

        ``auto`` (the default) follows the operator's own ``harnessArgs``: the
        acceptance is recorded only for a session that was already configured
        to run in bypass mode, so the-loop never widens permissions nobody
        asked for.
        """
        mode = self.trust.accept_bypass_permissions
        if mode == "always":
            return True
        if mode == "never":
            return False
        return args_request_bypass(self.extra_args)

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
