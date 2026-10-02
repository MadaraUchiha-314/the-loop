"""Codex's instruction files and positively identified rollout transcripts."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import threading
from itertools import islice
from pathlib import Path
from typing import Dict, Optional, Tuple

from .gitexclude import exclude_from_git
from .trust import TrustResult, _lock_for, update_json

_UUID = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
BEGIN = "<!-- the-loop:codex:start -->"
END = "<!-- the-loop:codex:end -->"
GATE_SCRIPT = "the-loop-gate.py"


def codex_home(user_home: Optional[Path] = None) -> Path:
    """``$CODEX_HOME`` (stripped, ``~`` expanded), else ``<home>/.codex``.

    The one lookup every Codex path uses, so hooks, trust and rollouts never
    disagree about where Codex keeps its state.
    """
    override = (os.environ.get("CODEX_HOME") or "").strip()
    if override:
        return Path(override).expanduser()
    return (user_home or Path.home()) / ".codex"


def conversation_marker(session_id: str) -> str:
    return f"[the-loop conversation: {session_id}]"


#: Rollout ``session_meta`` (native id, real cwd) by resolved path, valid while
#: the file's (inode, mtime, size) is unchanged. A finished rollout is parsed
#: once per process instead of on every event (the dispatcher resolves on its
#: hot path); a replaced or growing file is simply re-read.
_META: Dict[Path, Tuple[Tuple[int, int, int], Tuple[str, str]]] = {}
#: Positively identified rollouts by (real cwd, requested id).
_FOUND: Dict[Tuple[str, str], Path] = {}
_CACHE_LOCK = threading.Lock()


def rollout_path(cwd: str, session_id: str) -> Optional[Path]:
    """Match native id or the launch marker, never the most recent chat.

    Both metadata and cwd must match. Symlinks escaping the session store,
    malformed records and ambiguous launch markers are refused. A match is
    remembered, and rollouts whose metadata rules them out are not re-read.
    """
    if not _UUID.fullmatch(session_id):
        return None
    root = (codex_home() / "sessions").resolve()
    if not root.is_dir():
        return None
    real_cwd = os.path.realpath(cwd)
    key = (real_cwd, session_id)
    with _CACHE_LOCK:
        known = _FOUND.get(key)
    if known is not None and known.is_relative_to(root) and known.is_file():
        return known
    found = _find_rollout(root, real_cwd, session_id)
    if found is not None:
        with _CACHE_LOCK:
            _FOUND[key] = found
    return found


def _rollout_meta(path: Path) -> Optional[Tuple[str, str]]:
    """(native id, real cwd) from a rollout's ``session_meta``, cached."""
    try:
        stat = path.stat()
    except OSError:
        return None
    version = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
    with _CACHE_LOCK:
        cached = _META.get(path)
    if cached is not None and cached[0] == version:
        return cached[1]
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            first = json.loads(handle.readline())
    except (OSError, ValueError):
        return None  # possibly still being written: retry next time
    meta = (
        first.get("payload", {})
        if isinstance(first, dict) and first.get("type") == "session_meta"
        else {}
    )
    if not isinstance(meta, dict):
        meta = {}
    native_id = meta.get("id", "")
    recorded_cwd = meta.get("cwd")
    if (
        not isinstance(native_id, str)
        or not _UUID.fullmatch(native_id)
        or not isinstance(recorded_cwd, str)
        or not os.path.isabs(recorded_cwd)
    ):
        result = ("", "")
    else:
        result = (native_id, os.path.realpath(recorded_cwd))
    with _CACHE_LOCK:
        _META[path] = (version, result)
    return result


def _find_rollout(root: Path, real_cwd: str, session_id: str) -> Optional[Path]:
    matches = []
    candidates = list(root.glob(f"**/rollout-*-{session_id}.jsonl"))
    for candidate in candidates or root.glob("**/rollout-*.jsonl"):
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            continue
        meta = _rollout_meta(resolved)
        if meta is None:
            continue
        native_id, recorded_cwd = meta
        if not native_id or recorded_cwd != real_cwd:
            continue
        if native_id == session_id:
            return resolved
        marker = conversation_marker(session_id)
        try:
            with resolved.open(encoding="utf-8", errors="replace") as handle:
                handle.readline()
                for raw in islice(handle, 64):
                    # Bound the discovery read to the start of the rollout.
                    if len(raw) > 1024 * 1024:
                        continue
                    entry = json.loads(raw)
                    payload = entry.get("payload", {})
                    if (
                        entry.get("type") == "response_item"
                        and payload.get("role") == "user"
                    ):
                        contents = payload.get("content", [])
                        if isinstance(contents, list) and any(
                            isinstance(block, dict)
                            and marker in str(block.get("text", ""))
                            for block in contents
                        ):
                            matches.append(resolved)
                            break
        except (OSError, ValueError, AttributeError, TypeError):
            continue
    return matches[0] if len(matches) == 1 else None


def native_session_id(path: Path) -> str:
    try:
        with path.open(encoding="utf-8") as handle:
            return str(json.loads(handle.readline())["payload"]["id"])
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def resources_root() -> Path:
    bundled = Path(__file__).resolve().parent / "resources"
    if (bundled / "skills/the-loop/SKILL.md").is_file():
        return bundled
    source = Path(__file__).resolve().parents[2]
    if (source / "skills/the-loop/SKILL.md").is_file():
        return source
    raise FileNotFoundError(
        "the-loop's bundled Codex instructions are missing; reinstall the CLI"
    )


def transcript_entry(entry: dict) -> dict:
    """Add the shared trace message shape without losing the original event."""
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        return entry
    mapped = dict(entry)
    kind = payload.get("type")
    if entry.get("type") == "response_item":
        if kind == "message":
            role = payload.get("role", "assistant")
            content = [
                {"type": "text", "text": block.get("text", "")}
                for block in payload.get("content", [])
                if isinstance(block, dict)
                and block.get("type") in ("input_text", "output_text")
            ]
            mapped.update(type=role, message={"role": role, "content": content})
        elif kind in ("function_call", "custom_tool_call"):
            arguments = payload.get("arguments", payload.get("input", ""))
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    pass
            mapped.update(
                type="assistant",
                message={
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": payload.get("call_id", ""),
                            "name": payload.get("name", "tool"),
                            "input": arguments,
                        }
                    ],
                },
            )
        elif kind in ("function_call_output", "custom_tool_call_output"):
            mapped.update(
                type="user",
                message={
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": payload.get("call_id", ""),
                            "content": payload.get("output", ""),
                        }
                    ],
                },
            )
        elif kind == "reasoning":
            texts = [
                str(block.get("text", ""))
                for block in payload.get("summary", [])
                if isinstance(block, dict)
            ]
            mapped.update(
                type="assistant",
                message={
                    "role": "assistant",
                    "content": [{"type": "thinking", "thinking": "\n".join(texts)}],
                },
            )
    elif entry.get("type") == "compacted":
        mapped.update(
            type="summary", summary=payload.get("message", "Context compacted")
        )
    return mapped


def prepare_instructions(
    cwd: str,
    *,
    global_scope: bool = False,
    hook_home: Optional[Path] = None,
    keep_out_of_git: bool = False,
) -> TrustResult:
    """Preserve project instructions and hooks; add only our managed entries.

    ``keep_out_of_git`` is for per-work-item checkouts: the managed block holds
    this machine's absolute paths, so an untracked instructions file is added
    to the checkout's ``info/exclude`` instead of being left for a session to
    commit into the project's history.
    """
    try:
        resources = resources_root()
        directory = Path(cwd).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        override = directory / "AGENTS.override.md"
        agents = override if override.exists() else directory / "AGENTS.md"
        hooks_file = (
            (hook_home / "hooks.json")
            if hook_home
            else directory / ("hooks.json" if global_scope else ".codex/hooks.json")
        )
        if not agents.resolve().is_relative_to(directory) or (
            hook_home is None and not hooks_file.resolve().is_relative_to(directory)
        ):
            return TrustResult(
                ok=False, error="Codex instruction files resolve outside the checkout"
            )
        original = agents.read_text(encoding="utf-8") if agents.exists() else ""
        if (
            original.count(BEGIN) != original.count(END)
            or original.count(BEGIN) > 1
            or (BEGIN in original and original.index(END) < original.index(BEGIN))
        ):
            return TrustResult(
                ok=False,
                error="AGENTS.md has an incomplete the-loop managed block; leaving it untouched",
            )
        block = (
            f"{BEGIN}\n"
            "This session runs the-loop. Read and follow the operating skill at\n"
            f"{resources / 'skills/the-loop/SKILL.md'} and its relevant references.\n"
            "Read .the-loop/harness-config.yaml and custom instructions when present.\n"
            "Use the-loop ticket show, graph status, graph complete, check, comment,\n"
            "ask, and pr create for the work item in THE_LOOP_WORK_ITEM.\n"
            "A graph command such as /the-loop:work-on names a procedure; read the\n"
            f"corresponding Markdown under {resources / 'commands'} and perform it.\n"
            "Use the-loop ask for human decisions; advance the graph after completing\n"
            "the current node. Honor frozen selections and human gates.\n"
            f"{END}"
        )
        if BEGIN in original:
            start, finish = original.index(BEGIN), original.index(END) + len(END)
            desired = original[:start] + block + original[finish:]
        else:
            desired = original + ("\n\n" if original else "") + block + "\n"
        notes = []
        if desired != original:
            _write_agents(agents, original, desired)
            notes.append(f"prepared the-loop instructions in {agents}")
        if keep_out_of_git:
            notes += _keep_out_of_git(agents)
        command = shlex.join(
            [sys.executable, str(resources / "hooks" / GATE_SCRIPT), "codex"]
        )

        def mutate(data: dict) -> bool:
            hooks = data.setdefault("hooks", {})
            if not isinstance(hooks, dict):
                raise ValueError("hooks must be an object")
            groups = hooks.setdefault("Stop", [])
            if not isinstance(groups, list):
                raise ValueError("Stop hooks must be a list")
            for group in groups:
                if not isinstance(group, dict) or not isinstance(
                    group.get("hooks"), list
                ):
                    raise ValueError("each Stop matcher must contain a hooks list")
            # Identify our gate by script and argument, not by the exact command:
            # another interpreter or install path must replace the old entry, not
            # add a second gate that shares (and halves) the attempts budget.
            gates = [
                (group, h)
                for group in groups
                for h in group["hooks"]
                if _is_codex_gate(h)
            ]
            if len(gates) == 1 and gates[0][1].get("command") == command:
                return False
            if gates:
                gates[0][1]["command"] = command
                emptied = []
                for group, stale in gates[1:]:
                    group["hooks"][:] = [h for h in group["hooks"] if h is not stale]
                    if not group["hooks"]:
                        emptied.append(group)
                groups[:] = [g for g in groups if not any(g is e for e in emptied)]
                return True
            groups.append(
                {"hooks": [{"type": "command", "command": command, "timeout": 60}]}
            )
            return True

        result = update_json(hooks_file, mutate)
        if result.applied:
            notes.append(
                "Codex Stop hook installed; review and trust this definition once using /hooks"
            )
        return TrustResult(applied=notes).merge(result)
    except (OSError, ValueError) as exc:
        return TrustResult(
            ok=False, error=f"could not prepare Codex instructions: {exc}"
        )


def _is_codex_gate(hook: object) -> bool:
    """True for a hook running the-loop's gate for Codex, whatever its path."""
    if not isinstance(hook, dict) or not isinstance(hook.get("command"), str):
        return False
    try:
        tokens = shlex.split(hook["command"])
    except ValueError:
        return False
    return (
        len(tokens) >= 2
        and tokens[-1] == "codex"
        and Path(tokens[-2]).name == GATE_SCRIPT
    )


def _keep_out_of_git(agents: Path) -> list:
    """Exclude an untracked instructions file; report a tracked one.

    A tracked file cannot be excluded: the managed block then shows as a local
    change, and the note says so rather than staying silent.
    """
    directory = agents.parent
    try:
        tracked = subprocess.run(
            [
                "git",
                "-C",
                str(directory),
                "ls-files",
                "--error-unmatch",
                "--",
                agents.name,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        prefix = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-prefix"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if prefix.returncode != 0:
        return []  # not a git checkout — nothing to keep out of history
    if tracked.returncode == 0:
        return [
            f"{agents.name} is tracked in this checkout; the-loop's managed block "
            "is a local change there — keep it out of commits"
        ]
    entry = "/" + prefix.stdout.strip() + agents.name
    if exclude_from_git(directory, entry) == "added":
        return [f"excluded {entry} from git in {directory}"]
    return []


def _write_agents(path: Path, original: str, desired: str) -> None:
    """Write through a symlink, atomically, without racing another writer."""
    target = path.resolve()
    with _lock_for(target):
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != original:
            raise ValueError(
                "instructions changed during preparation; retry without overwriting them"
            )
        mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
        fd, name = tempfile.mkstemp(dir=target.parent, prefix=".the-loop-agents-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(desired)
            os.chmod(name, mode)
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
