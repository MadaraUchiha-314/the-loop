"""Bearer-token authentication for the control-plane API (issue-161).

The token is minted per service boot — 32 bytes of ``os.urandom``, hex — and
written 0600 under the state root's ``local/`` half, where machine-bound
handles live (issue-128). No API response ever contains it; the CLI and the UI
read/receive it out of band. Missing or mismatched credentials are rejected
before any core call (abuse case 1), and the rejection is logged.
"""

from __future__ import annotations

import hmac
import os
from pathlib import Path


def mint_token(path: Path) -> str:
    token = os.urandom(32).hex()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, token.encode("ascii"))
    finally:
        os.close(fd)
    return token


def read_token(path: Path) -> str:
    """The current token, or ``""`` when no service has minted one."""
    try:
        return path.read_text(encoding="ascii").strip()
    except OSError:
        return ""


def token_matches(expected: str, presented: str) -> bool:
    """Constant-time comparison; an empty expected token never matches."""
    if not expected or not presented:
        return False
    return hmac.compare_digest(expected, presented)
