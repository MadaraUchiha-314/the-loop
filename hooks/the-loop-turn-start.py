#!/usr/bin/env python3
"""Record that this session's turn started (issue-551, R4.5, R4.6).

The idle watcher tells a working session from an idle one by its turn records:
a turn's end is written by the Stop gate, and a turn's start is written here, by
`the-loop sessions turn-start`. A start is also the only thing that ends a
stall. Without this hook a session has no turn records and the watcher leaves
it alone.

The harness runs it when a prompt is submitted — Claude Code and Codex on
``UserPromptSubmit``, Cursor on ``beforeSubmitPrompt``.

**Every path exits 0, and Claude Code and Codex get no output at all.** Both
add this event's stdout to the prompt as context, and exit 2 would block the
prompt. Cursor is answered ``{"continue": true}``, its word for "submit it".
This is bookkeeping: an unknown work item, no `the-loop` on PATH, a failing or
slow CLI are all silent no-ops, and the prompt goes through.

``THE_LOOP_WORK_ITEM`` names the work item, as it does for the gate. Without it
the hook does nothing, so an unrelated session records nothing.

**Stdlib only, and it imports nothing from ``the_loop``** — the same contract as
`the-loop-gate.py`, for the same reason: the plugin has to survive the CLI not
being installed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

#: How long the CLI may take. This runs before every prompt of the session, so a
#: slow service must not be felt as a hung prompt.
CLI_TIMEOUT_SECONDS = 10


def record() -> None:
    """Run the verb for this session's work item, if there is one and a CLI."""
    work_item = os.environ.get("THE_LOOP_WORK_ITEM", "").strip()
    # A value shaped like a flag would be read as one, not as the work item.
    if not work_item or work_item.startswith("-"):
        return
    if not shutil.which("the-loop"):
        return
    subprocess.run(
        ["the-loop", "sessions", "turn-start", "--work-item", work_item],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=CLI_TIMEOUT_SECONDS,
    )


def main(argv: list[str]) -> int:
    harness = argv[1] if len(argv) > 1 else "claude"
    try:
        record()
    except Exception:  # noqa: BLE001 — bookkeeping never stops a prompt
        pass
    if harness == "cursor":
        print(json.dumps({"continue": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
