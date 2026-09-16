#!/usr/bin/env python3
"""Record the pull request this session just opened (issue-370).

`the-loop sessions link-pr` is how a work item's tracking learns that a pull
request delivers it (issue-274, issue-368). Until now the only thing that ran it
was a **prose rule** — `reference/automation.md`, `/work-on` and
`/execute-tasks` all tell the agent to run it right after `gh pr create` — and a
rule a language model has to remember is not a guarantee. What covered the gap
was inference: the poller and the dispatcher reconstructed the linkage from
GitHub's closing references, an `issue-<n>` branch name or a closing keyword.
Issue-370 removed that, because it tracked pull requests nobody stated. So the
recording has to actually happen, which means a hook does it.

**PostToolUse, and it reads the result rather than the intent.** The pull
request's number comes from what the tool *returned* — the URL `gh pr create`
prints, or the GitHub MCP tool's response — never from the command string. A
command that failed, was interrupted, or was `gh pr create --dry-run` returns no
URL and links nothing; a regex over the argv could not tell those apart.

**Every path exits 0.** `PostToolUse` exit 2 feeds stderr back to the model and
interrupts the work; this is bookkeeping, best-effort by contract like
`sessions register` beside it, and it must never be the reason a session stops.
Unknown work item, no `the-loop` on PATH, an unreadable payload, a `gh` failure:
all silent no-ops.

**Stdlib only, and it imports nothing from ``the_loop``** — the same contract as
`the-loop-gate.py`, for the same reason: the plugin has to survive the CLI not
being installed, so it talks to the CLI over its JSON interface.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

#: How long either subprocess may take. Short: this runs between the agent's tool
#: calls, and a hung `gh` must not be felt as a hung session.
CLI_TIMEOUT_SECONDS = 20

#: The tools that can create a pull request. `Bash` is narrowed further by the
#: command it ran; a tool whose name ends in `create_pull_request` is a GitHub
#: MCP server's, whatever prefix the deployment gave it.
_MCP_CREATE_RE = re.compile(r"create_pull_request$")
_GH_PR_CREATE_RE = re.compile(r"\bgh\b[^\n|;&]*\bpr\b[^\n|;&]*\bcreate\b")

#: A pull request URL in a tool's output: `https://<host>/<owner>/<repo>/pull/<n>`.
#: Deliberately the only way a number is ever extracted — see the module
#: docstring. The name shapes are GitHub's own, which is also what keeps the
#: captured text safe to put in an argv.
_PR_URL_RE = re.compile(
    r"https?://([A-Za-z0-9.-]+)/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)/pull/(\d+)\b"
)

#: `github:[host/]owner/repo#n`, the-loop's spelling of a work item.
_REF_RE = re.compile(
    r"^(?P<provider>[a-z]+):(?:(?P<host>[A-Za-z0-9.-]+)/)?"
    r"(?P<owner>[A-Za-z0-9._-]+)/(?P<repo>[A-Za-z0-9._-]+)#(?P<number>\d+)$"
)

_PUBLIC_HOSTS = ("github.com", "www.github.com", "api.github.com")


def read_payload() -> Dict[str, Any]:
    """The hook payload on stdin. ``{}`` for anything unreadable."""
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _response_text(payload: Dict[str, Any]) -> str:
    """Everything the tool returned, as one searchable string.

    ``tool_response`` is a dict for `Bash` (``stdout``/``stderr``) and shaped by
    the server for an MCP tool, so it is serialized whole rather than reached
    into: the URL is looked for, not parsed out of a schema this hook would then
    have to track.
    """
    response = payload.get("tool_response")
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    try:
        return json.dumps(response)
    except (TypeError, ValueError):
        return str(response)


def created_pull_request(
    payload: Dict[str, Any],
) -> Optional[Tuple[str, str, str, int]]:
    """``(host, owner, repo, number)`` for a pull request this tool created.

    ``None`` unless the tool is one that creates pull requests **and** its
    response carries a pull request URL. Both halves matter: the first keeps the
    hook off every other `Bash` call, the second is what makes a failed or
    dry-run creation link nothing.
    """
    tool = str(payload.get("tool_name") or "")
    if tool == "Bash":
        command = str((payload.get("tool_input") or {}).get("command") or "")
        if not _GH_PR_CREATE_RE.search(command) or "--dry-run" in command:
            return None
    elif not _MCP_CREATE_RE.search(tool):
        return None
    if _interrupted(payload):
        return None
    match = _PR_URL_RE.search(_response_text(payload))
    if match is None:
        return None
    host, owner, repo, number = match.groups()
    return host, owner, repo, int(number)


def _interrupted(payload: Dict[str, Any]) -> bool:
    response = payload.get("tool_response")
    return bool(isinstance(response, dict) and response.get("interrupted"))


def _run(argv: List[str]) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=CLI_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _registered_sessions() -> List[Dict[str, Any]]:
    proc = _run(["the-loop", "sessions", "list", "--format", "json"])
    if proc is None or proc.returncode != 0 or not (proc.stdout or "").strip():
        return []
    try:
        rows = json.loads(proc.stdout)
    except ValueError:
        return []
    return (
        [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    )


def work_item_for(payload: Dict[str, Any]) -> str:
    """Which work item this session is for — or ``""``, which means give up.

    Three answers, most authoritative first: the variable the daemon exports into
    a spawned session (issue-370, R5.1), then the registry matched on the harness
    session id, then the registry matched on the working directory. There is no
    fourth: guessing from a branch name is the inference this work item deleted,
    and reintroducing it here would make the deletion pointless.
    """
    stated = os.environ.get("THE_LOOP_WORK_ITEM", "").strip()
    if _REF_RE.match(stated):
        return stated
    session_id = str(payload.get("session_id") or "")
    cwd = os.path.realpath(str(payload.get("cwd") or os.getcwd()))
    rows = _registered_sessions() if (session_id or cwd) else []
    by_cwd = ""
    for row in rows:
        ref = str((row.get("workItem") or {}).get("ref") or "")
        if not _REF_RE.match(ref) or row.get("status") == "closed":
            continue
        if session_id and str(row.get("harnessSessionId") or "") == session_id:
            return ref
        row_cwd = str(row.get("cwd") or "")
        if not by_cwd and row_cwd and os.path.realpath(row_cwd) == cwd:
            by_cwd = ref
    return by_cwd


def pull_request_argument(work_item: str, pr: Tuple[str, str, str, int]) -> str:
    """How to name the pull request to ``sessions link-pr``.

    Its bare number when it lives in the work item's own repository — the common
    case, and the spelling the command documents — and a full ref otherwise, which
    is the only way to name a pull request in a contributing repository. The host
    is carried over only when it is not github.com, the way `WorkItemRef` spells
    it.
    """
    host, owner, repo, number = pr
    item = _REF_RE.match(work_item)
    if item is not None and (owner, repo) == (item.group("owner"), item.group("repo")):
        return str(number)
    prefix = "" if host.lower() in _PUBLIC_HOSTS else f"{host}/"
    return f"github:{prefix}{owner}/{repo}#{number}"


def main() -> int:
    payload = read_payload()
    pr = created_pull_request(payload)
    if pr is None:
        return 0
    if not shutil.which("the-loop"):
        return 0
    work_item = work_item_for(payload)
    if not work_item:
        return 0
    argument = pull_request_argument(work_item, pr)
    proc = _run(
        [
            "the-loop",
            "sessions",
            "link-pr",
            "--work-item",
            work_item,
            "--pull-request",
            argument,
        ]
    )
    if proc is not None and proc.returncode == 0:
        # PostToolUse stdout is transcript-only, which is the whole intent: the
        # agent is told the bookkeeping is done so it does not repeat it, and is
        # never interrupted when it is not.
        print(f"the-loop: recorded {argument} against {work_item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
