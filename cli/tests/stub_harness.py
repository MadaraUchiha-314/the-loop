#!/usr/bin/env python3
"""A stub harness for the idle watchdog's end-to-end test (issue-551, T4).

It stands where Claude Code stands in a session the daemon drives: in a tmux
pane, reading what the daemon pastes, and running the plugin's hook scripts at
the two moments a harness runs them. It is an obedient and useless agent: it
never does any work, so every node it is on stays unmet.

* **At start-up** it ends one turn, so the first stop needs no paste.
* **For each pasted prompt** it runs `the-loop-turn-start.py` (a harness's
  prompt-submit hook), then ends the turn.
* **Ending a turn** runs `the-loop-gate.py claude` with a Stop payload on
  stdin. Exit 2 is a refused stop: the text on stderr is what a model would be
  handed, and the stub tries to stop again, as a harness re-prompts the model.
  The hook's own attempt cap is what ends that.

What the daemon pastes (`TmuxRunner.deliver_to`): Ctrl-A Ctrl-U to clear the
line, the prompt as one bracketed paste, then a lone carriage return. tmux
brackets a paste only for a pane that asked for it, so the stub turns bracketed
paste on, and it reads the terminal raw so the bytes arrive as they were sent.

Each finished turn is one JSON line in the transcript file:
``{"turn": n, "prompt": <text or null>, "stops": [{"exit": 2, "stderr": …}, …]}``.

Usage: ``stub_harness.py <hooks-dir> <transcript-file>``. The work item and the
CLI the hooks reach come from the environment, as they do for a real harness.

Stdlib only: it is run by path in a pane, outside the test's interpreter setup.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import termios
import tty
from pathlib import Path
from typing import List, Optional

PASTE_START = b"\x1b[200~"
PASTE_END = b"\x1b[201~"
#: A refused stop is retried until the hook lets it through. The hook's cap is a
#: handful; this only stops a broken hook from spinning the stub for ever.
MAX_STOPS = 20
HOOK_TIMEOUT_SECONDS = 90
STOP_PAYLOAD = json.dumps({"hook_event_name": "Stop", "stop_hook_active": False})


def run_hook(script: Path, payload: Optional[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), "claude"],
        input=payload,
        stdin=None if payload is not None else subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=HOOK_TIMEOUT_SECONDS,
    )


def end_turn(hooks: Path) -> List[dict]:
    """Try to stop until the gate allows it; every attempt, in order."""
    stops: List[dict] = []
    for _ in range(MAX_STOPS):
        proc = run_hook(hooks / "the-loop-gate.py", STOP_PAYLOAD)
        stops.append({"exit": proc.returncode, "stderr": proc.stderr})
        if proc.returncode != 2:
            break
    return stops


def take_turn(hooks: Path, transcript: Path, turn: int, prompt: Optional[str]) -> None:
    if prompt is not None:
        run_hook(hooks / "the-loop-turn-start.py", None)
    stops = end_turn(hooks)
    with transcript.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"turn": turn, "prompt": prompt, "stops": stops}))
        handle.write("\n")
    refused = sum(1 for stop in stops if stop["exit"] == 2)
    # The pane is the test's diagnostics when something goes wrong.
    sys.stdout.write(f"stub: turn {turn} ended after {refused} refused stop(s)\r\n")
    sys.stdout.flush()


def prompts(fd: int):
    """Each submitted prompt: a bracketed paste, then a carriage return."""
    buffer = b""
    pasted: Optional[bytes] = None
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            return
        buffer += chunk
        while True:
            if pasted is None:
                start = buffer.find(PASTE_START)
                if start < 0:
                    # Keep a tail that may be the start of a marker.
                    buffer = buffer[-(len(PASTE_START) - 1) :]
                    break
                end = buffer.find(PASTE_END, start)
                if end < 0:
                    buffer = buffer[start:]
                    break
                pasted = buffer[start + len(PASTE_START) : end]
                buffer = buffer[end + len(PASTE_END) :]
            submit = buffer.find(b"\r")
            if submit < 0:
                break
            buffer = buffer[submit + 1 :]
            # tmux pastes a buffer's line feeds as carriage returns.
            yield pasted.decode("utf-8", "replace").replace("\r", "\n")
            pasted = None


def main(argv: List[str]) -> int:
    hooks, transcript = Path(argv[1]), Path(argv[2])
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setraw(fd)
    sys.stdout.write("\x1b[?2004h")  # bracketed paste on
    sys.stdout.flush()
    try:
        take_turn(hooks, transcript, 0, None)
        for turn, prompt in enumerate(prompts(fd), start=1):
            take_turn(hooks, transcript, turn, prompt)
    finally:
        sys.stdout.write("\x1b[?2004l")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
