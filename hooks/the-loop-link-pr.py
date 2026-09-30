#!/usr/bin/env python3
"""Record the pull requests this session opened (issue-370, issue-447).

`the-loop sessions link-pr` is how a work item's tracking learns that a pull
request delivers it (issue-274, issue-368). Until issue-370 the only thing that
ran it was a **prose rule**, and a rule a language model has to remember is not
a guarantee — so a hook does it.

**It asks GitHub; it reads no tool's output** (issue-447). This hook used to
look for `gh pr create` in the agent's shell and parse the pull request's URL out
of what `gh` printed — a heuristic tied to one tool, which is exactly the `gh`
dependency issue-447 removes from the harness. Now it is trigger-agnostic: after
a `git push`, anything that creates a pull request (`gh pr create`, `hub
pull-request`, a GitHub MCP server's `create_pull_request`), it runs `the-loop
sessions link-pr --discover`, which lists the open pull requests whose head is
the checkout's branch and links each one. Linking is idempotent, so a push that
opened nothing costs one request and writes nothing. `the-loop pr create` links
the PR it opens itself, so it is not a trigger; this hook is the safety net for
pull requests opened by hand or by MCP.

**Every path exits 0.** `PostToolUse` exit 2 feeds stderr back to the model and
interrupts the work; this is bookkeeping, best-effort by contract like
`sessions register` beside it, and it must never be the reason a session stops.
Unknown work item, no `the-loop` on PATH, an unreadable payload, a failing
discovery: all silent no-ops.

**Stdlib only, and it imports nothing from ``the_loop``** — the same contract as
`the-loop-gate.py`, for the same reason: the plugin has to survive the CLI not
being installed, so it talks to the CLI over its JSON interface. And it holds no
GitHub credential and runs no `gh`: the CLI does the asking, through the service
when one runs.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

#: How long either subprocess may take. Short: this runs between the agent's tool
#: calls, and a slow GitHub must not be felt as a hung session.
CLI_TIMEOUT_SECONDS = 20

#: A tool whose name ends in `create_pull_request` is a GitHub MCP server's,
#: whatever prefix the deployment gave it.
_MCP_CREATE_RE = re.compile(r"create_pull_request$")
#: The `Bash` commands that can make a pull request exist: a push (the PR may be
#: opened by a person, or be about to be), and any `pr create` / `pull-request`.
_GIT_PUSH_RE = re.compile(r"\bgit\b[^\n|;&]*\bpush\b")
_PR_CREATE_RE = re.compile(r"\bpr\b[^\n|;&]*\bcreate\b|\bpull-request\b")
#: the-loop's own verb links the PR it opens (R4.4): not a trigger.
_OWN_VERB_RE = re.compile(r"\bthe-loop\b[^\n|;&]*\bpr\b[^\n|;&]*\bcreate\b")
#: `--dry-run` as a flag, not as the text of a `--title`.
_DRY_RUN_RE = re.compile(r"(?:^|\s)--dry-run(?:[\s=]|$)")

#: `github:[host/]owner/repo#n`, the-loop's spelling of a work item.
_REF_RE = re.compile(
    r"^(?P<provider>[a-z]+):(?:(?P<host>[A-Za-z0-9.-]+)/)?"
    r"(?P<owner>[A-Za-z0-9._-]+)/(?P<repo>[A-Za-z0-9._-]+)#(?P<number>\d+)$"
)


def read_payload() -> Dict[str, Any]:
    """The hook payload on stdin. ``{}`` for anything unreadable."""
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def should_discover(payload: Dict[str, Any]) -> bool:
    """Whether this tool call may have made a pull request exist.

    Decided from the tool and its command alone — never from its output — and
    cheap to get wrong in the permissive direction: a discovery after a push that
    opened nothing links nothing.
    """
    tool = str(payload.get("tool_name") or "")
    if tool == "Bash":
        command = str((payload.get("tool_input") or {}).get("command") or "")
        if _OWN_VERB_RE.search(command) or _DRY_RUN_RE.search(command):
            return False
        if not (_GIT_PUSH_RE.search(command) or _PR_CREATE_RE.search(command)):
            return False
    elif not _MCP_CREATE_RE.search(tool):
        return False
    return not _interrupted(payload)


def _interrupted(payload: Dict[str, Any]) -> bool:
    response = payload.get("tool_response")
    return bool(isinstance(response, dict) and response.get("interrupted"))


def _run(
    argv: List[str], cwd: Optional[str] = None
) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=CLI_TIMEOUT_SECONDS,
            cwd=cwd,
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


def _checkout(payload: Dict[str, Any]) -> Optional[str]:
    """The session's working directory — where the branch and origin are read."""
    cwd = str(payload.get("cwd") or "")
    return cwd if cwd and os.path.isdir(cwd) else None


def main() -> int:
    payload = read_payload()
    if not should_discover(payload):
        return 0
    if not shutil.which("the-loop"):
        return 0
    work_item = work_item_for(payload)
    if not work_item:
        return 0
    proc = _run(
        ["the-loop", "sessions", "link-pr", "--work-item", work_item, "--discover"],
        cwd=_checkout(payload),
    )
    if proc is not None and proc.returncode == 0:
        # PostToolUse stdout is transcript-only, which is the whole intent: the
        # agent is told a link was recorded so it does not repeat it, and is
        # never interrupted when nothing was.
        for line in (proc.stdout or "").splitlines():
            if line.startswith("recorded "):
                print(f"the-loop: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
