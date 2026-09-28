#!/usr/bin/env python3
"""the-loop's gate wrapper — the harness stop hook's payload (issue-109, task 34).

The harness hook is a **clock**, not a state machine. It says *when* to look; the
graph says *what we are looking at*. So this wrapper never needs to know which
phase a work item is in — it asks ``the-loop check``, which resolves the current
node from work-item state.

Harness protocols, which is why this file lives with the plugin (the harness
integration) rather than with the CLI:

* **Claude Code** — exit 2 blocks the stop and stderr goes back to the model.
* **Cursor** — ``{"followup_message": ...}`` on stdout, which Cursor auto-submits.

``THE_LOOP_WORK_ITEM`` names the work item. Without it the hook is a no-op, so an
unrelated session is never blocked by a gate that does not apply to it.

**Stdlib only, and it imports nothing from ``the_loop``.** It has to survive the
CLI not being installed — in that case it no-ops rather than erroring on every
turn — so it talks to the CLI over its JSON interface, not its Python API.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_MAX_ATTEMPTS = 3
CHECK_TIMEOUT_SECONDS = 30


def attempts_path(work_item: str, repo: str) -> Path:
    """A per-(repo, work item) counter file.

    Keyed by the repository too: the bash version keyed on the work-item id
    alone, so two checkouts working on ``issue-1`` shared one counter and each
    one's attempts silently consumed the other's budget.
    """
    digest = hashlib.sha256(f"{repo}\0{work_item}".encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"the-loop-gate-{digest}"


def read_attempts(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return 0


def run_check(work_item: str) -> dict | None:
    """Ask the CLI where the work item stands. ``None`` means "cannot tell".

    ``--recompute`` stays. Work-item state is a **cache, not an authority**, and
    this is a gate: the state file is one the agent being gated can write. The
    one thing the gate takes from it is *where* the item is — the report's
    ``pointer`` — and :func:`blocking_node` walks the graph from its start up to
    that position, so a pointer moved forward past a broken node still finds it
    (issue-429). Every verdict is evaluated from the artifacts.
    """
    if not shutil.which("the-loop"):
        return None
    try:
        proc = subprocess.run(
            ["the-loop", "check", work_item, "--format", "json", "--recompute"],
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def blocking_node(report: dict) -> dict | None:
    """The node the agent should not stop on, if there is one.

    The first node that is not satisfied, **at or before the node the work item
    is at** — and only when that node is a ``block``. Each narrowing is a way an
    earlier version got it wrong:

    * Only nodes the work item has *reached* count. A node further along is not
      done yet, and treating that as a blocker would fire the gate on every turn
      of every work item forever.
    * "Reached" is bounded by the report's ``pointer`` — the node work-item state
      places the item at — not by ``currentNode``. Under ``--recompute``,
      ``currentNode`` is the first node the *artifacts* leave unmet, which runs
      ahead of the item whenever the nodes before it pass but the item has not
      been advanced into it: a work item parked at ``phase-selection`` with its
      selection recorded was ordered to write ``design.md`` (issue-429). Only the
      position comes from state; every verdict is still the recomputed one.
    * A report that cannot say where the item is — no ``currentNode``, a
      ``pointer`` that is empty (no state file was found) or names no node in
      the report — is **inconclusive**, and the turn ends. A gate that cannot
      tell where the item is must not invent a requirement.
    * Only ``block`` counts, not ``wait``. ``wait`` means the node is parked on a
      human — a review that has not come back. Blocking the agent from ending its
      turn then would spin it against a person who is not there, which is the one
      thing an attempt cap exists to contain rather than to cause.
    """
    nodes = report.get("nodes") or []
    ids = [node.get("node") for node in nodes]
    current = report.get("currentNode")
    if not current or current not in ids:
        return None
    # A CLI older than issue-429 sends no pointer; its `currentNode` is the only
    # position there is.
    reached = report.get("pointer") if "pointer" in report else current
    if not reached or reached not in ids:
        return None
    for node in nodes:
        if node.get("status") not in ("pass", "skip"):
            return node if node.get("status") == "block" else None
        if node.get("node") == reached:
            return None
    return None


def feedback_text(node: dict, attempts: int, maximum: int) -> str:
    lines = ["the-loop: this step is not complete."]
    lines += [f"  · {m}" for m in (node.get("messages") or [])]
    lines.append("")
    lines.append(f"Fix the above, then finish. (attempt {attempts}/{maximum})")
    return "\n".join(lines)


def emit(harness: str, text: str) -> int:
    """Speak the harness's protocol. Return this process's exit code."""
    if harness == "cursor":
        # Cursor cannot block a stop, but it auto-submits followup_message as
        # the next user turn — and caps that natively (loop_limit, hard max 5).
        print(json.dumps({"followup_message": text}))
        return 0
    # Claude Code: exit 2 prevents the stop; stderr is what the model reads.
    print(text, file=sys.stderr)
    return 2


def main(argv: list[str]) -> int:
    harness = argv[1] if len(argv) > 1 else "claude"
    work_item = os.environ.get("THE_LOOP_WORK_ITEM", "").strip()
    if not work_item:
        return 0

    try:
        maximum = int(os.environ.get("THE_LOOP_GATE_MAX_ATTEMPTS", ""))
    except ValueError:
        maximum = DEFAULT_MAX_ATTEMPTS
    maximum = max(1, maximum)

    report = run_check(work_item)
    if report is None:
        return 0

    counter = attempts_path(work_item, os.getcwd())
    node = blocking_node(report)
    if node is None:
        counter.unlink(missing_ok=True)
        return 0

    attempts = read_attempts(counter) + 1
    try:
        counter.write_text(str(attempts), encoding="utf-8")
    except OSError:
        pass

    # Claude Code caps nothing, so the-loop caps it here. Cursor caps
    # auto-followups natively — the asymmetry runs the opposite way to the
    # obvious guess, which is why the bound lives on this path at all.
    if attempts > maximum:
        counter.unlink(missing_ok=True)
        # Bail out rather than loop forever. The CI gate is the backstop, and a
        # hook that can wedge a session is worse than one that gives up loudly.
        print(
            f"the-loop: {work_item} is still incomplete after {maximum} attempts; "
            "letting the turn end. `the-loop check` will still report it, and CI "
            "gates the merge.",
            file=sys.stderr,
        )
        return 0

    return emit(harness, feedback_text(node, attempts, maximum))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
