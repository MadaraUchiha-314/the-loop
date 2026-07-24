"""Announce a spawned interactive session on its work item (issue-86).

When the dispatcher hosts a work item in a tmux session, the only place that
said so was the daemon's log — the human reading the GitHub issue never learned
the session existed, let alone how to attach to it. This module posts that
information where the human already is: a comment on the issue/PR carrying the
tmux session name and the ``tmux attach -t loop-<slug>`` command. Posted on the
work item's **first spawn** only — a respawn reuses the same session name, so
re-announcing would just be noise on the ticket (owner decision, PR #87).

Built in the mould of :mod:`the_loop.reactions`: it shells the operator's own
``gh`` CLI (no token of the-loop's own), and everything is best-effort — an
announcement must never fail, delay or drop the dispatch, so every failure
degrades to a logged no-op. Process-runner sessions are skipped (there is no
terminal to attach) and so are non-GitHub work items.

The comment body is built **only** from the session's own registry fields — the
work-item ref, the tmux target and the harness name. No event-payload data
reaches it (so nobody can inject text into what the-loop posts) and no
filesystem path, harness session id or hostname does either.

Spec: docs/specs/issue-86/design.md.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

from . import eventlog
from .sessions import Session

logger = logging.getLogger("the-loop.announce")

__all__ = ["AnnounceConfig", "SessionAnnouncer", "announcement_body"]

# Defensive validation of the API coordinates, mirroring reactions.py. These
# come from the registry (already parsed by WorkItemRef) rather than a payload,
# but they still end up in a `gh` argv.
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass
class AnnounceConfig:
    """Mirror of ``webhooks.ghWebhook.routing.announce`` (see config schema)."""

    enabled: bool = True
    gh_binary: str = "gh"

    @classmethod
    def from_mapping(cls, data: dict) -> "AnnounceConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", True)),
            gh_binary=str(data.get("ghBinary", "gh")),
        )


def announcement_body(session: Session) -> str:
    """The markdown comment announcing ``session`` and how to attach to it.

    Pure and payload-free (see the module docstring): every value comes from
    the session's own registry record.
    """
    target = session.tmux_target
    ref = session.work_item.ref
    note = (
        "The session is kept after the work completes, so this transcript "
        "stays readable. A respawn reuses this same tmux session name, so "
        "these commands keep working."
    )
    return (
        f"🖥️ **the-loop** started an interactive session for `{ref}`.\n"
        "\n"
        "| | |\n"
        "|---|---|\n"
        f"| tmux session | `{target}` |\n"
        f"| harness | `{session.harness}` |\n"
        "\n"
        "Attach from the machine running the-loop:\n"
        "\n"
        "```sh\n"
        f"tmux attach -t {target}\n"
        "# or, without a keyboard:\n"
        f"the-loop sessions attach --work-item {ref} --read-only\n"
        "```\n"
        "\n"
        f"{note}\n"
    )


class SessionAnnouncer:
    """Posts session announcements through the operator's ``gh`` CLI.

    Never raises: every failure path is a logged no-op returning ``False`` —
    the dispatch outcome must not depend on a comment. ``runner`` is injectable
    so tests drive it without a real ``gh`` (mirrors ``GitHubReactor``).
    """

    def __init__(
        self,
        config: Optional[AnnounceConfig] = None,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        timeout: Optional[float] = 30.0,
    ):
        self.config = config or AnnounceConfig()
        self._runner = runner
        self.timeout = timeout
        self._warned_missing_gh = False

    def announce(self, session: Session) -> bool:
        """Comment on ``session``'s work item with its tmux attach details.

        Called on **first spawn only** (owner decision, PR #87): a respawn
        reuses the same ``loop-<slug>`` name, so the attach command already on
        the ticket stays correct and a second comment would be noise.
        """
        config = self.config
        if not config.enabled:
            return False
        if session.runner != "tmux" or not session.tmux_target:
            # A headless process session has no terminal to attach to.
            return False
        item = session.work_item
        if item.provider != "github":
            logger.debug(
                "work item %s is not a GitHub one; skipping the session announcement",
                item.ref,
            )
            return False
        if not _NAME_RE.match(item.owner) or not _NAME_RE.match(item.repo):
            logger.debug("unusable repo coordinates in %s; skipping", item.ref)
            return False
        if shutil.which(config.gh_binary) is None:
            if not self._warned_missing_gh:
                self._warned_missing_gh = True
                logger.warning(
                    "gh CLI %r not found on PATH — session announcements are a "
                    "no-op (install gh or set routing.announce.enabled: false)",
                    config.gh_binary,
                )
            return False

        cmd = [config.gh_binary] + self._argv(session)
        try:
            proc = self._runner(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return self._failed(session, str(exc))
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            return self._failed(session, f"gh exited {proc.returncode}: {detail}")
        logger.info("announced tmux session %s on %s", session.tmux_target, item.ref)
        eventlog.emit(
            "session.announced",
            work_item=item.ref,
            tmux_target=session.tmux_target,
        )
        return True

    @staticmethod
    def _argv(session: Session) -> list:
        item = session.work_item
        # The issues endpoint serves PR conversations too (as in reactions.py).
        return [
            "api",
            "--method",
            "POST",
            f"repos/{item.owner}/{item.repo}/issues/{item.number}/comments",
            "-f",
            f"body={announcement_body(session)}",
        ]

    def _failed(self, session: Session, error: str) -> bool:
        logger.warning(
            "could not announce tmux session %s on %s: %s",
            session.tmux_target,
            session.work_item.ref,
            error,
        )
        eventlog.emit(
            "session.announce_failed",
            level="warning",
            work_item=session.work_item.ref,
            tmux_target=session.tmux_target,
            error=error,
        )
        return False
