"""Adapter contract + shared subprocess plumbing (issue-15, R4).

Every adapter shells out to its harness's official CLI in non-interactive
print mode with JSON output, run in the session's recorded working directory
(resume lookup is scoped to the project directory). Extra args come from
``routing.harnessArgs`` — the dispatcher never widens permissions itself.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence

from ..sessions import Session, WorkItemRef

logger = logging.getLogger("the-loop.harness")

# JSON keys the harness CLIs use for their session/chat id, in match order.
_SESSION_ID_KEYS = ("session_id", "sessionId", "chat_id", "chatId", "id")


@dataclass
class DispatchResult:
    """Outcome of one resume/spawn subprocess."""

    ok: bool
    session_id: str = ""
    output: str = ""
    error: str = ""


class HarnessAdapter:
    """Contract: ``resume`` an existing session / ``spawn`` a new one.

    Subclasses set ``name``/``default_binary`` and implement the two
    ``_*_argv`` methods. SDK-based implementations remain possible behind
    this same contract (R4.5) but are out of scope (decision-016).
    """

    name: str = ""
    default_binary: str = ""

    def __init__(
        self,
        binary: Optional[str] = None,
        extra_args: Optional[Sequence[str]] = None,
    ):
        self.binary = binary or self.default_binary
        self.extra_args = list(extra_args or [])

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def _resume_argv(self, session: Session, prompt: str) -> List[str]:
        raise NotImplementedError

    def _spawn_argv(self, prompt: str) -> List[str]:
        raise NotImplementedError

    def resume(
        self, session: Session, prompt: str, timeout: Optional[float] = None
    ) -> DispatchResult:
        """Wake ``session`` with ``prompt``, run in the session's cwd (R4.2)."""
        return self._run(self._resume_argv(session, prompt), session.cwd, timeout)

    def spawn(
        self,
        work_item: WorkItemRef,
        prompt: str,
        cwd: str,
        timeout: Optional[float] = None,
    ) -> DispatchResult:
        """Start a fresh session; the new id is in ``result.session_id`` (R4.4)."""
        result = self._run(self._spawn_argv(prompt), cwd, timeout)
        if result.ok and not result.session_id:
            result = DispatchResult(
                ok=False,
                output=result.output,
                error=(
                    f"{self.binary} did not report a session id in its JSON "
                    "output; cannot register the spawned session"
                ),
            )
        return result

    def _run(
        self, argv: List[str], cwd: str, timeout: Optional[float]
    ) -> DispatchResult:
        if not self.is_available():
            return DispatchResult(
                ok=False,
                error=(
                    f"harness CLI {self.binary!r} not found on PATH; install it "
                    f"or point the {self.name} adapter at the right binary"
                ),
            )
        cmd = [self.binary] + argv
        logger.debug("running %s (cwd=%s)", " ".join(cmd[:5]) + " …", cwd)
        try:
            proc = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return DispatchResult(
                ok=False, error=f"{self.binary} timed out after {timeout}s"
            )
        except OSError as exc:
            return DispatchResult(ok=False, error=f"could not run {self.binary}: {exc}")
        if proc.returncode != 0:
            return DispatchResult(
                ok=False,
                output=proc.stdout,
                error=(
                    f"{self.binary} exited {proc.returncode}: "
                    f"{proc.stderr.strip() or proc.stdout.strip()}"
                ),
            )
        return DispatchResult(
            ok=True,
            session_id=_session_id_from_output(proc.stdout),
            output=proc.stdout,
        )


def _session_id_from_output(stdout: str) -> str:
    """Best-effort session/chat id from the CLI's JSON output."""
    try:
        data = json.loads(stdout.strip() or "{}")
    except json.JSONDecodeError:
        return ""
    if isinstance(data, dict):
        for key in _SESSION_ID_KEYS:
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    return ""
