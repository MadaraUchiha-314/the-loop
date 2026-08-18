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
degrades to a logged no-op. Sessions with no tmux session yet are skipped
(there is nothing to attach to) and so are non-GitHub work items.

The comment body is built **only** from the session's own registry fields — the
work-item ref, the tmux target and the harness name. No event-payload data
reaches it (so nobody can inject text into what the-loop posts) and no
filesystem path, harness session id or hostname does either.

Like every comment the-loop posts, the body carries the loop-prevention marker
(``authz.mark_self_authored``). Without it the announcement — posted with the
operator's own credentials, hence authorized — came back on the next poll cycle
and was pasted into the very session it announced (issue-104).

Spec: docs/specs/issue-86/design.md, docs/specs/issue-104/design.md.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

from . import eventlog
from .authz import mark_self_authored
from .comments import post_issue_comment
from .linkage import looks_not_found
from .sessions import Session, WorkItemRef

logger = logging.getLogger("the-loop.announce")

__all__ = ["AnnounceConfig", "SessionAnnouncer", "announcement_body"]


@dataclass
class AnnounceConfig:
    """Mirror of ``routing.announce`` (see config schema)."""

    enabled: bool = True
    gh_binary: str = "gh"

    @classmethod
    def from_mapping(cls, data: dict) -> "AnnounceConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", True)),
            gh_binary=str(data.get("_ghBinary", "gh")),
        )


def announcement_body(session: Session) -> str:
    """The markdown comment announcing ``session`` and how to attach to it.

    Pure and payload-free (see the module docstring): every value comes from
    the session's own registry record — which is also why marking it as
    the-loop's own is safe here (:func:`mark_self_authored` must never be
    applied to foreign text).
    """
    target = session.tmux_target
    ref = session.work_item.ref
    note = (
        "The session is kept after the work completes, so this transcript "
        "stays readable. A respawn reuses this same tmux session name, so "
        "these commands keep working."
    )
    return mark_self_authored(
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
        on_work_item_missing: Optional[Callable[[WorkItemRef], None]] = None,
    ):
        self.config = config or AnnounceConfig()
        self._runner = runner
        self.timeout = timeout
        self._warned_missing_gh = False
        # Where a 404 on the work item itself is reported (issue-269). The
        # dispatcher wires it to the existence check's cache; unset, the failure
        # is still recorded on the event log.
        self._on_work_item_missing = on_work_item_missing

    def announce(self, session: Session) -> bool:
        """Comment on ``session``'s work item with its tmux attach details.

        Called on **first spawn only** (owner decision, PR #87): a respawn
        reuses the same ``loop-<slug>`` name, so the attach command already on
        the ticket stays correct and a second comment would be noise.
        """
        config = self.config
        if not config.enabled:
            return False
        if not session.tmux_target:
            # No tmux session yet (nothing spawned) — nothing to announce.
            return False
        item = session.work_item
        ok, error = post_issue_comment(
            item,
            announcement_body(session),
            gh_binary=config.gh_binary,
            runner=self._runner,
            timeout=self.timeout,
        )
        if not ok:
            if error.endswith("not found on PATH"):
                # One warning per process, then silence: a machine without `gh`
                # would otherwise log this on every spawn.
                if not self._warned_missing_gh:
                    self._warned_missing_gh = True
                    logger.warning(
                        "%s — session announcements are a no-op (install gh or "
                        "set routing.announce.enabled: false)",
                        error,
                    )
                return False
            if "is not a GitHub one" in error or "unusable repo coordinates" in error:
                logger.debug("%s; skipping the session announcement", error)
                return False
            return self._failed(session, error)
        logger.info("announced tmux session %s on %s", session.tmux_target, item.ref)
        eventlog.emit(
            "session.announced",
            work_item=item.ref,
            tmux_target=session.tmux_target,
        )
        return True

    def _failed(self, session: Session, error: str) -> bool:
        if looks_not_found(error):
            return self._work_item_missing(session, error)
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

    def _work_item_missing(self, session: Session, error: str) -> bool:
        """A 404 on the work item is evidence, not a failed comment (issue-269).

        the-loop has just spawned a session for a work item the provider says
        does not exist — the situation a branch-invented ref produced before the
        existence check, and one a mistyped cross-repository closing keyword can
        still produce. Said out loud at error level, and handed to the sink so
        the next event naming this ref does not repeat the spawn.

        Deliberately **not** a kill: a repository the operator's credential
        cannot see answers 404 for items that do exist, and ending a live agent's
        session (with its checkout and its uncommitted work) on an ambiguous
        signal is a worse outcome than the one being reported.
        """
        item = session.work_item
        logger.error(
            "%s does not exist (%s), but a session for it is already running in "
            "%s — the work item was probably invented by a branch name. Inspect "
            "it, then `the-loop sessions stop --work-item %s`",
            item.ref,
            error,
            session.tmux_target or "no tmux session",
            item.ref,
        )
        eventlog.emit(
            "session.work_item_missing",
            level="error",
            work_item=item.ref,
            tmux_target=session.tmux_target or None,
            error=error,
        )
        if self._on_work_item_missing is not None:
            try:
                self._on_work_item_missing(item)
            except Exception as exc:  # noqa: BLE001 — bookkeeping, never a raise
                logger.debug("could not record %s as missing: %s", item.ref, exc)
        return False
