"""Which GitHub? — the one resolver for a host no event supplied (issue-311).

A work item that arrives through an event carries its host in its ref
(issue-130): the webhook payload's ``html_url``, or the polled item's own URL,
says where it lives, and everything derived from the ref — its browser URL, its
file name, its existence check — follows. A ref the-loop **mints from
configuration** has no such source: the graph derives its work item from
``ticketing.github`` (owner and repo, no host), and until this module every such
ref meant github.com. The Slack link for a pending decision is derived from
exactly that ref, which is the symptom the ticket reports.

So: one function, one documented precedence, one grammar.

1. ``integrations.github.host`` in the CLI config — the operator's declaration;
2. the host of ``integrations.github.api.baseUrl`` when it is not the public API
   (GitHub Enterprise publishes its API at ``https://<host>/api/v3``);
3. ``$GH_HOST`` — ``gh``'s own override;
4. the ``origin`` remote of the repository at hand — ``gh``'s own next answer,
   consulted only when a caller names a root (the graph's own session; never a
   daemon, which runs outside any checkout);
5. ``github.com``.

Every candidate passes :func:`the_loop.sessions.is_github_host` before it is
returned — the same expression a host inside a ref must satisfy — so nothing
that is not a host (a scheme, a path, credentials, whitespace, an argv fragment)
reaches a URL or a ``--hostname`` argument. A candidate that fails is skipped
with a warning and the walk continues: the fail-closed direction is "the next
tier", never "an unvalidated string".

The resolver reads configuration, the environment and (optionally) a subprocess.
It is deliberately **not** a method on :class:`~the_loop.sessions.WorkItemRef`,
which stays a pure value: the ref carries a host, this decides which one to
carry when nothing else did.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from .sessions import DEFAULT_GITHUB_HOST, host_from_url, is_github_host

logger = logging.getLogger("the-loop.ghhost")

__all__ = ["api_base_for", "github_host", "host_from_remote", "host_of_api_base"]

#: The public API's base, as the shipped config spells it. Any other base is
#: taken to name an enterprise host.
PUBLIC_API_BASE = "https://api.github.com"

#: The scp-like remote form git accepts without a scheme: ``[user@]host:path``.
#: A drive letter or a local path never matches: the host half must be a host.
_SCP_REMOTE_RE = re.compile(r"^(?:[^@/\s]+@)?(?P<host>[^:/\s]+):(?!//)(?P<path>.+)$")


def host_from_remote(url: str) -> str:
    """The host of a git remote URL, or ``""`` when it has none.

    Handles the shapes a real checkout carries — ``https://host/o/r.git``,
    ``ssh://git@host[:port]/o/r``, ``git@host:o/r.git`` — and answers ``""`` for
    a local path or anything else, because "no host" is what a remote without one
    means, not github.com.
    """
    value = (url or "").strip()
    if not value:
        return ""
    host = host_from_url(value, default="")
    if host:
        return host
    match = _SCP_REMOTE_RE.match(value)
    return match.group("host") if match else ""


def host_of_api_base(base_url: str) -> str:
    """The enterprise host an API base names, or ``""`` for the public API.

    ``https://ghe.corp/api/v3`` → ``ghe.corp``; ``https://api.github.com`` (with
    or without a trailing slash) and anything unparsable → ``""``.
    """
    value = (base_url or "").strip().rstrip("/")
    if not value or value == PUBLIC_API_BASE:
        return ""
    host = host_from_url(value, default="")
    if host == "api.github.com":
        return ""
    return host


def api_base_for(host: str) -> str:
    """The REST base for ``host``: the public API, or ``https://<host>/api/v3``."""
    if not host or host == DEFAULT_GITHUB_HOST:
        return PUBLIC_API_BASE
    return f"https://{host}/api/v3"


def _origin_remote(root: Path) -> str:
    """``remote.origin.url`` of the checkout at ``root``, or ``""``.

    Through git itself rather than ``.git/config`` (a worktree's config is not
    the file beside its ``.git``), from an argv list with no shell, and empty on
    every failure — the same read :mod:`the_loop.graphlink` makes to prove a
    checkout is the work item's.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("could not read the origin remote of %s: %s", root, exc)
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _github_section(cli_config: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    integrations = (
        cli_config.get("integrations") if isinstance(cli_config, Mapping) else None
    )
    github = integrations.get("github") if isinstance(integrations, Mapping) else None
    return github if isinstance(github, Mapping) else {}


def github_host(
    cli_config: Optional[Mapping[str, Any]],
    *,
    env: Optional[Mapping[str, str]] = None,
    repo_root: Optional[Path] = None,
    remote_url: Optional[str] = None,
    remote_reader: Optional[Callable[[Path], str]] = None,
) -> str:
    """The GitHub host a ref minted from configuration should carry.

    ``env`` defaults to the process environment; ``repo_root`` enables tier 4 and
    ``remote_url`` supplies that tier directly (tests, or a caller that already
    read the remote). The answer is always a validated host, ``github.com``
    included — callers hand it to :class:`~the_loop.sessions.WorkItemRef`, which
    leaves the default unwritten.
    """
    environ: Mapping[str, str] = os.environ if env is None else env
    github = _github_section(cli_config)
    api_raw = github.get("api")
    api: Mapping[str, Any] = api_raw if isinstance(api_raw, Mapping) else {}

    candidates = [
        ("integrations.github.host", str(github.get("host") or "").strip()),
        (
            "integrations.github.api.baseUrl",
            host_of_api_base(str(api.get("baseUrl") or "")),
        ),
        ("GH_HOST", str(environ.get("GH_HOST") or "").strip()),
    ]
    if remote_url is not None:
        candidates.append(("origin remote", host_from_remote(remote_url)))
    elif repo_root is not None:
        reader = remote_reader or _origin_remote
        candidates.append(("origin remote", host_from_remote(reader(repo_root))))

    for tier, value in candidates:
        if not value:
            continue
        if not is_github_host(value):
            logger.warning(
                "%s names %r, which is not the shape of a host (a dotted name or "
                "one with a port, no scheme or path) — skipped",
                tier,
                value,
            )
            continue
        logger.debug("github host is %s (from %s)", value, tier)
        return value
    logger.debug("github host is %s (default)", DEFAULT_GITHUB_HOST)
    return DEFAULT_GITHUB_HOST
