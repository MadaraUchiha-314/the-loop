"""Claude Code adapter: host the ``claude`` TUI in tmux; run it one-shot for critics.

The session id is pre-assigned by the dispatcher (``--session-id``) or comes
from Claude Code's ``$CLAUDE_SESSION_ID`` at registration time; resume lookup
is scoped to the project directory, hence the session's recorded ``cwd``.

It is also the adapter that has something to prepare before a spawn: Claude
Code's workspace-trust dialog and bypass-permissions disclaimer are not
permission rules, so no CLI flag silences them and an unattended session stalls
on them (issue-90) — and the-loop's own plugin, which carries the skill, the
commands and the hooks the spawn prompt assumes, has to be enabled or the
session runs a loop it does not have (issue-143). See :mod:`the_loop.trust` and
:mod:`the_loop.harness_plugins`.
"""

from __future__ import annotations

from typing import List, Optional

from .base import HarnessAdapter
from ..harness_plugins import ClaudePluginStore
from ..trust import ClaudeTrustStore, TrustResult, args_request_bypass


class ClaudeCodeAdapter(HarnessAdapter):
    name = "claude"
    default_binary = "claude"
    model_flag = "--model"

    def prepare_environment(self, cwd: str, root: Optional[str] = None) -> TrustResult:
        """Pre-trust ``cwd``, accept the bypass disclaimer, enable the plugin.

        ``root`` widens the trust entry to the workspace root — the dispatcher
        only passes one under ``scope: workspace-root``, and the store ignores a
        root that does not contain ``cwd``.

        The plugin step (issue-143) is **independent** of trust: an operator who
        trusts their checkouts by hand still wants the session to load the loop,
        and one who declines the plugin still wants the trust write. ``merge``
        keeps every note and the first error, so neither step can hide or block
        the other.
        """
        result = TrustResult()
        if self.trust.enabled:
            store = ClaudeTrustStore()
            result = store.trust(cwd, root if self.trust.roots_allowed else None)
            if self._wants_bypass():
                # Independent files: a failed trust write must not skip this one.
                result = result.merge(store.accept_bypass_permissions())
        if self.plugins.enabled:
            result = result.merge(
                ClaudePluginStore().enable(self.plugins.marketplace_repo)
            )
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

    def _oneshot_argv(self, prompt: str) -> List[str]:
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
