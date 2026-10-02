"""Codex adapter: host the ``codex`` TUI in tmux; run ``codex exec`` for critics.

Codex CLI (issue-449) follows decision-016 like the others: the official CLI is
the programmatic surface. Hosting works, with one honest asymmetry: ``codex``
has no pre-assignable session id in interactive mode (the flag is an open
upstream request, openai/codex#13242), so the id the dispatcher passes into
``interactive_argv`` cannot be handed to the TUI. The session is launched
id-less and the registry's ``harness_session_id`` stays the-loop's own name for
the conversation, not codex's. Respawn therefore resumes by recency —
``codex resume --last`` — scoped by the session's recorded cwd, which is unique
per work item under the workspace's worktree strategy.

Unattended, nothing is taken away (`_UNATTENDED_ARGS` is empty): codex's
approval prompts are governed by sandbox/approval *policy* flags
(``--dangerously-bypass-approvals-and-sandbox``, ``--sandbox``), and policy is
the operator's to declare via ``harnesses[].args`` — the-loop never widens
permissions itself.
"""

from __future__ import annotations

from typing import List

from .base import HarnessAdapter


class CodexAdapter(HarnessAdapter):
    name = "codex"
    default_binary = "codex"
    #: Long and short (``-m``) both exist on ``codex`` and ``codex exec``; the
    #: long form is used for the same reason as cursor's (issue-360): it is the
    #: one spelling both surfaces document.
    model_flag = "--model"
    #: Codex spells effort as the ``model_reasoning_effort`` config key, set per
    #: run with ``-c`` (its ``--help``'s own example mechanism). Levels the-loop
    #: knows that codex cannot express are simply absent — `models check`
    #: validates each mapping against the installed CLI rather than trusting
    #: this table (decision-124).
    _EFFORT_ARGS = {
        "low": ("-c", "model_reasoning_effort=low"),
        "medium": ("-c", "model_reasoning_effort=medium"),
        "high": ("-c", "model_reasoning_effort=high"),
        "xhigh": ("-c", "model_reasoning_effort=xhigh"),
        "ultra": ("-c", "model_reasoning_effort=ultra"),
    }

    def _oneshot_argv(self, prompt: str) -> List[str]:
        # Plain text out, no `--json`: codex's JSON mode is JSONL events, which
        # neither `parse_json_object` nor a critic's `output_format: json`
        # extraction reads; the critic path's text fallback wants the prose.
        # `--skip-git-repo-check` keeps probes runnable outside a repository.
        return ["exec", "--skip-git-repo-check"] + self.extra_args + [prompt]

    def interactive_argv(self, prompt: str, session_id: str) -> List[str]:
        # `session_id` is accepted and dropped: codex mints its own id at
        # launch (see module docstring). Flags first, positional prompt last.
        return self._launch_args() + [prompt]

    def interactive_resume_argv(self, prompt: str, session_id: str) -> List[str]:
        # ponytail: resume-by-recency; swap to `resume <id>` when codex grows a
        # pre-assignable id (openai/codex#13242) or an id-discovery hook lands.
        return ["resume", "--last"] + self._launch_args() + [prompt]
