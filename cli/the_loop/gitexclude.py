"""Checkout-local git ignores: ``info/exclude`` entries that are never committed."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("the-loop")


def exclude_from_git(repo: Path, entry: str) -> str:
    """Append ``entry`` to ``repo``'s ``info/exclude`` unless already present.

    Resolved via ``rev-parse --git-path`` so a linked worktree lands on the
    shared file. Best-effort: a non-git directory or an unwritable exclude file
    returns ``""`` rather than raising. Returns ``"added"``, ``"present"`` or
    ``""`` (could not / nothing to do).
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--git-path", "info/exclude"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("could not resolve %s's exclude file: %s", repo, exc)
        return ""
    if proc.returncode != 0:
        return ""  # not a git checkout — nothing to keep out of history
    path = Path(proc.stdout.strip())
    if not path.is_absolute():
        path = repo / path
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        if entry in existing.splitlines():
            return "present"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            if existing and not existing.endswith("\n"):
                fh.write("\n")
            fh.write(entry + "\n")
    except OSError as exc:
        logger.warning("could not exclude %s from git: %s", entry, exc)
        return ""
    return "added"
