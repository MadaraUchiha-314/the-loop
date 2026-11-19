"""The GitHub reads behind ``the-loop graph pr-spec`` (issue-543, AC1/AC2, R5.2).

Two questions, both answered from the API and never from a session's text:

* **Does recording this PR spec disclose the work item to a wider audience?**
  Both repositories' ``visibility`` is read and ordered
  ``private`` < ``internal`` < ``public``. Anything else, including a failed
  read, is ``unknown`` and counts as narrowing (AC2): silence is never "same".
* **Did an authorized human say so?** A comment URL is accepted only when it
  is a comment on the expected thread, its author is in the operator's
  ``routing.authorizedUsers``, and it is not the-loop's own (the agent's words
  never authorize). A disclosure grant must also name the target repository:
  ``allow-disclosure <owner>/<repo>``.

The client is passed in (``GitHubApi`` or a test stub). Only reads are made.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Sequence, Tuple

from ..authz import is_self_authored

__all__ = [
    "VISIBILITY_RANK",
    "authorize_comment",
    "check_disclosure",
    "narrows",
    "repository_visibility",
]

VISIBILITY_RANK = {"private": 0, "internal": 1, "public": 2}

_COMMENT_URL_RE = re.compile(
    r"https://(?P<host>[^/\s]+)/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/"
    r"(?P<kind>issues|pull)/(?P<number>\d+)(?:/files)?"
    r"#(?P<anchor>issuecomment-\d+|discussion_r\d+|pullrequestreview-\d+)"
)


def _split(repo: str) -> Tuple[str, str]:
    owner, _, name = repo.strip().partition("/")
    return owner, name


def repository_visibility(client: Any, repo: str) -> str:
    """``private`` | ``internal`` | ``public`` | ``unknown`` — never raises."""
    owner, name = _split(repo)
    try:
        data = client.repository(owner, name)
    except Exception:  # noqa: BLE001 — any failure is "unknown", which fails closed
        return "unknown"
    value = str((data or {}).get("visibility") or "").strip().lower()
    return value if value in VISIBILITY_RANK else "unknown"


def narrows(origin: str, target: str) -> bool:
    """Is writing from ``origin`` into ``target`` a disclosure to a wider audience?"""
    if origin not in VISIBILITY_RANK or target not in VISIBILITY_RANK:
        return True
    return VISIBILITY_RANK[target] > VISIBILITY_RANK[origin]


def _parse_ref(ref: str) -> Tuple[str, int]:
    from ..sessions import WorkItemRef

    try:
        parsed = WorkItemRef.parse(ref)
    except ValueError:
        return "", 0
    return (f"{parsed.owner}/{parsed.repo}" if parsed.repo else ""), parsed.number


def authorize_comment(
    client: Any,
    url: str,
    *,
    expected: str,
    authorized: Sequence[str],
    must_contain: str = "",
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """``({by, comment, at}, None)`` when ``url`` authorizes, else ``(None, reason)``.

    ``expected`` is the thread the comment must be on: the work item for a
    disclosure grant, this PR for ``--still-valid``. The comment is fetched
    through ``client``; nothing the caller says about it is believed.
    """
    match = _COMMENT_URL_RE.fullmatch((url or "").strip())
    if not match:
        return None, f"{url!r} is not a GitHub comment URL"
    want_repo, want_number = _parse_ref(expected)
    repo = f"{match['owner']}/{match['repo']}"
    if (
        not want_repo
        or repo.lower() != want_repo.lower()
        or int(match["number"]) != want_number
    ):
        return None, f"{url} is not a comment on {expected}"
    try:
        comments = client.list_comments(
            match["owner"], match["repo"], want_number, match["kind"] == "pull"
        )
    except Exception as exc:  # noqa: BLE001 — a failed read authorizes nothing
        return (
            None,
            f"could not read the comments of {expected} ({exc.__class__.__name__})",
        )
    anchor = "#" + match["anchor"]
    found = next(
        (c for c in comments if str(getattr(c, "url", "")).endswith(anchor)), None
    )
    if found is None:
        return None, f"{url} was not found on {expected}"
    if is_self_authored(found.body):
        return None, f"{url} is the-loop's own comment; only a person can authorize"
    author = str(found.author or "")
    if not author or author.lower() not in {a.lower() for a in authorized}:
        return (
            None,
            f"{url} is by @{author or '?'}, who is not authorized (routing.authorizedUsers)",
        )
    if must_contain and not re.search(
        rf"(?i)(?<![\w-]){re.escape(must_contain)}(?![\w./-])", found.body or ""
    ):
        return None, f"{url} does not say `{must_contain}`"
    return {"by": f"@{author}", "comment": url.strip(), "at": found.created_at}, None


def check_disclosure(
    client: Any,
    *,
    origin: str,
    target: str,
    work_item: str,
    approval_url: str,
    authorized: Sequence[str],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """``(disclosure record, None)`` when allowed, else ``(None, reason)`` (AC1, AC2)."""
    origin_vis = repository_visibility(client, origin)
    target_vis = repository_visibility(client, target)
    base = {"origin": origin_vis, "target": target_vis}
    if not narrows(origin_vis, target_vis):
        return {**base, "verdict": "same-or-narrower"}, None
    reason = (
        "visibility-unknown"
        if "unknown" in (origin_vis, target_vis)
        else f"{origin} is {origin_vis} and {target} is {target_vis}"
    )
    if not approval_url:
        return None, (
            f"disclosure refused ({reason}): an authorized person must comment "
            f"`allow-disclosure {target}` on {work_item}; pass its URL as "
            "--disclosure-approval"
        )
    grant, problem = authorize_comment(
        client,
        approval_url,
        expected=work_item,
        authorized=authorized,
        must_contain=f"allow-disclosure {target}",
    )
    if problem:
        return None, f"disclosure refused ({reason}): {problem}"
    assert grant is not None
    return {**base, "verdict": "approved", **grant}, None
