#!/usr/bin/env python3
"""the-loop's gate wrapper — the harness stop hook's payload (issue-109, task 34).

The harness hook is a **clock**, not a state machine. It says *when* to look; the
graph says *what we are looking at*. So this wrapper never needs to know which
phase a work item is in — it asks the-loop.

It asks the service first (issue-551): ``the-loop sessions stop-check`` is given
the harness's own hook payload and answers ``allow`` or ``refuse``, because only
the service knows of an open ask, a declared wait and who owns each node. The
attempt cap stays here, so it holds when the service is down, and a give-up is
reported back with ``--gave-up``. The plugin and the CLI ship separately: when
the verb is missing or nothing usable comes back, the wrapper judges
``the-loop check`` itself, as it did before there was a service.

Harness protocols, which is why this file lives with the plugin (the harness
integration) rather than with the CLI:

* **Claude Code** — exit 2 blocks the stop and stderr goes back to the model.
* **Codex** — ``{"decision": "block", "reason": ...}`` on stdout; ``{}`` lets
  the stop through.
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
import select
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_MAX_ATTEMPTS = 3
CHECK_TIMEOUT_SECONDS = 30
#: The service's answer and the give-up report (issue-551). Both are bounded so
#: the worst case — the service times out and `check` runs after it — still ends
#: inside the 60 seconds a harness gives this hook.
STOP_CHECK_TIMEOUT_SECONDS = 20
GAVE_UP_TIMEOUT_SECONDS = 10
#: The second try at the service, after the fallback allowed a stop.
RETRY_TIMEOUT_SECONDS = 5
#: All the time this hook may spend in the CLI, whatever path it takes. Every
#: call's timeout is cut to what is left of it, and a call with under a second
#: left is not made.
HOOK_BUDGET_SECONDS = 55


def time_left(deadline: float | None, cap: float) -> float:
    """``cap``, or what is left until ``deadline`` when that is less."""
    if deadline is None:
        return cap
    return max(0.0, min(cap, deadline - time.monotonic()))


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


#: How long the payload is waited for: this long for its first byte, and this
#: long again for the rest once some of it has come.
PAYLOAD_WAIT_SECONDS = 1.0


def read_payload(harness: str = "claude") -> str:
    """The harness's hook payload from stdin; ``""`` when there is none to use.

    It is forwarded to the service unread: the service takes the list of
    background tasks from it. Only Claude Code's payload carries one, so no
    other harness's stdin is touched. A terminal is never read, and the read
    never waits for the stream to end: a harness that keeps its end open would
    hold the stop until the hook timed out.
    """
    if harness != "claude":
        return ""
    stream = sys.stdin
    try:
        if stream is None or stream.isatty():
            return ""
        return _read_what_is_there(stream)
    except (OSError, ValueError):
        return ""


def _read_what_is_there(stream) -> str:
    """What ``stream`` holds now, or within the wait, without needing its end."""
    try:
        descriptor = stream.fileno()
    except (AttributeError, OSError, ValueError):
        return stream.read()  # an in-memory stream: it cannot block
    chunks: list[bytes] = []
    deadline = time.monotonic() + PAYLOAD_WAIT_SECONDS
    while True:
        try:
            ready = select.select(
                [descriptor], [], [], max(0.0, deadline - time.monotonic())
            )[0]
        except (OSError, ValueError, TypeError):
            # Not selectable (Windows). Reading it is all that is left.
            return stream.read() if not chunks else _text(chunks)
        if not ready:
            break
        chunk = os.read(descriptor, 65536)
        if not chunk:
            break
        if not chunks:
            deadline = time.monotonic() + PAYLOAD_WAIT_SECONDS
        chunks.append(chunk)
    return _text(chunks)


def _text(chunks: list[bytes]) -> str:
    return b"".join(chunks).decode("utf-8", errors="replace")


def ask_service(
    work_item: str, payload: str, timeout: float = STOP_CHECK_TIMEOUT_SECONDS
) -> dict | None:
    """The service's verdict on this stop, or ``None`` when there is none to use.

    ``None`` sends the caller to :func:`run_check` (issue-551, version skew). It
    covers every way of not getting an answer: no CLI, a CLI without the verb
    (argparse exits non-zero), a service that is down or does not know the work
    item (non-zero, nothing on stdout), a timeout, and output that is not a JSON
    object with a known ``verdict``.
    """
    # A value shaped like a flag would be read as one, not as the work item.
    if work_item.startswith("-") or not shutil.which("the-loop"):
        return None
    if timeout < 1:
        return None
    try:
        proc = subprocess.run(
            ["the-loop", "sessions", "stop-check", "--work-item", work_item],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            return None
        answer = json.loads(proc.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if not isinstance(answer, dict) or answer.get("verdict") not in ("allow", "refuse"):
        return None
    return answer


def report_give_up(work_item: str, timeout: float = GAVE_UP_TIMEOUT_SECONDS) -> None:
    """Tell the service the cap let this stop through (issue-551, R3.6).

    It records the turn's end as ``gate-gave-up``, which the idle watcher then
    covers. Best effort: the stop is already allowed, so a failure changes nothing.
    """
    if timeout < 1:
        return
    try:
        subprocess.run(
            [
                "the-loop",
                "sessions",
                "stop-check",
                "--work-item",
                work_item,
                "--gave-up",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def run_check(work_item: str, timeout: float = CHECK_TIMEOUT_SECONDS) -> dict | None:
    """Ask the CLI where the work item stands. ``None`` means "cannot tell".

    The fallback for a CLI or a service that cannot answer ``stop-check``
    (issue-551). It knows nothing of asks or waits and records nothing.

    ``--recompute`` stays. Work-item state is a **cache, not an authority**, and
    this is a gate: the state file is one the agent being gated can write. The
    one thing the gate takes from it is *where* the item is — the report's
    ``pointer`` — and :func:`blocking_node` walks the graph from its start up to
    that position, so a pointer moved forward past a broken node still finds it
    (issue-429). Every verdict is evaluated from the artifacts.
    """
    if not shutil.which("the-loop") or timeout < 1:
        return None
    try:
        proc = subprocess.run(
            ["the-loop", "check", work_item, "--format", "json", "--recompute"],
            capture_output=True,
            text=True,
            timeout=timeout,
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

    Used when the service gave no verdict (issue-551). A ``block`` **before**
    the node the work item is at, else that node itself when it is a ``block``.
    Each narrowing is a way an earlier version got it wrong:

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
    * Only ``block`` counts, not ``wait``. ``wait`` on the item's own node means
      it is parked on a human — a review that has not come back. Blocking the
      agent from ending its turn then would spin it against a person who is not
      there, which is the one thing an attempt cap exists to contain rather than
      to cause.
    * A ``wait`` **before** the item's node counts as passed (issue-551, R3.3).
      It can only be an approved human gate, which recomputes as ``wait`` for
      good, or a graph wait the pointer is already past. The walk used to end at
      the first such node and allow the stop, so one approved gate switched this
      gate off for every node after it. A ``block`` before the item's node still
      blocks and is the node named (issue-429, R3.4); any other status there
      leaves the report inconclusive.
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
        status = node.get("status")
        if status == "block":
            return node
        if node.get("node") == reached or status not in ("pass", "skip", "wait"):
            return None
    return None


#: The feedback's words (issue-540), beside this script: the ``hooks/`` directory
#: ships whole in the plugin and in the wheel. Three lines, by position — the
#: heading, one unmet-check line (repeated per message, ``{message}``) and the
#: closing line (``{attempts}``, ``{maximum}``). ``str.format``, single-pass.
FEEDBACK_PROMPT = Path(__file__).resolve().parent / "prompts" / "gate-feedback.md"


def _prompt(name: str) -> str:
    """A prompt file beside this script, or ``""`` when it cannot be read."""
    try:
        return (FEEDBACK_PROMPT.parent / name).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def feedback_text(node: dict, attempts: int, maximum: int) -> str:
    """The text that stops the turn.

    A missing, unreadable or malformed prompt file never crashes a stop (the
    hook is the harness's clock), and never stops it from blocking either: the
    unmet checks' own messages are then the whole text, so the gate still holds.
    """
    messages = [str(m) for m in (node.get("messages") or [])]
    try:
        heading, item, closing = _prompt("gate-feedback.md").splitlines()[:3]
        lines = [heading.format()]
        lines += [item.format(message=m) for m in messages]
        lines.append("")
        lines.append(closing.format(attempts=attempts, maximum=maximum))
    except (ValueError, KeyError, IndexError):
        return "\n".join(messages) or "the-loop check: unmet"
    return "\n".join(lines)


def refusal_text(answer: dict, attempts: int, maximum: int) -> str:
    """The service's refusal, with this hook's attempt count under it.

    The words are the service's (``text``); the count is the one thing only the
    hook knows. An answer without ``text`` is worded from its ``messages``.
    """
    text = answer.get("text")
    if not isinstance(text, str) or not text.strip():
        return feedback_text(answer, attempts, maximum)
    try:
        line = _prompt("gate-attempt.md").strip()
        count = line.format(attempts=attempts, maximum=maximum)
    except (ValueError, KeyError, IndexError):
        count = ""
    return f"{text}\n{count}" if count else text


def give_up_text(work_item: str, maximum: int) -> str:
    """The stderr line when the attempts are spent, or ``""`` without its file."""
    try:
        return (
            _prompt("gate-give-up.md")
            .rstrip("\n")
            .format(work_item=work_item, maximum=maximum)
        )
    except (ValueError, KeyError, IndexError):
        return ""


def emit(harness: str, text: str) -> int:
    """Speak the harness's protocol. Return this process's exit code."""
    if harness == "codex":
        print(json.dumps({"decision": "block", "reason": text}))
        return 0
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
    deadline = time.monotonic() + HOOK_BUDGET_SECONDS
    work_item = os.environ.get("THE_LOOP_WORK_ITEM", "").strip()
    if not work_item:
        if harness == "codex":
            print("{}")
        return 0

    try:
        maximum = int(os.environ.get("THE_LOOP_GATE_MAX_ATTEMPTS", ""))
    except ValueError:
        maximum = DEFAULT_MAX_ATTEMPTS
    maximum = max(1, maximum)

    payload = read_payload(harness)
    answer = ask_service(
        work_item, payload, time_left(deadline, STOP_CHECK_TIMEOUT_SECONDS)
    )
    node = None
    if answer is None:
        # Version skew, or no service: judge `the-loop check` here.
        report = run_check(work_item, time_left(deadline, CHECK_TIMEOUT_SECONDS))
        node = blocking_node(report) if report is not None else None
        if node is None:
            # The fallback records nothing, and a turn's end that is never
            # recorded leaves the session looking as if it still worked. The
            # service may have been away for a moment only, so it is asked
            # once more. Its verdict then stands, and an allow records the end.
            answer = ask_service(
                work_item, payload, time_left(deadline, RETRY_TIMEOUT_SECONDS)
            )
            if answer is None and report is None:
                if harness == "codex":
                    print("{}")
                return 0
    if answer is not None:
        node = answer if answer["verdict"] == "refuse" else None

    counter = attempts_path(work_item, os.getcwd())
    if node is None:
        if harness == "codex":
            print("{}")
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
        if harness == "codex":
            print("{}")
        counter.unlink(missing_ok=True)
        # Bail out rather than loop forever. The CI gate is the backstop, and a
        # hook that can wedge a session is worse than one that gives up loudly.
        message = give_up_text(work_item, maximum)
        if message:
            print(message, file=sys.stderr)
        if answer is not None:
            report_give_up(work_item, time_left(deadline, GAVE_UP_TIMEOUT_SECONDS))
        return 0

    if answer is not None:
        return emit(harness, refusal_text(answer, attempts, maximum))
    return emit(harness, feedback_text(node, attempts, maximum))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
