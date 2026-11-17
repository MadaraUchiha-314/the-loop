"""Mask every session credential value out of text before it leaves the daemon.

issue-533 lets an operator hand an agent session a token (``env.sessionCredentials``).
An agent holding a token can paste it — an ``env`` dump, ``set -x`` output, a debug
log — into a comment, a question, a PR body or a Slack post. Every one of those goes
through the service (issue-482, R3), so the service is where the value is masked.

Two sources of values, merged:

* **Configured, now.** :func:`current_values` resolves every entry's source value from
  the env file (re-read when the file changes) or this process's environment. A
  rotated value is masked from the moment it is configured (R5.2).
* **Remembered.** Every value this process has resolved or handed to a pane is kept
  for the process's life, so a value rotated *out* — which a stale session may still
  hold — stays masked. :func:`scrub_tree` (the event log's) uses only these, so a log
  line never costs a disk read.

Masks are visible (``<redacted:session-credential>``), the rule ``redact`` follows.
A value shorter than :data:`MIN_VALUE_CHARS` is never masked: it would eat ordinary
text. No function here ever logs a value.

Spec: docs/specs/issue-533/design.md § sessioncreds.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, FrozenSet, Iterable, Mapping, Optional, Tuple

from . import envfile

logger = logging.getLogger("the-loop.sessioncreds")

__all__ = ["MASK", "MIN_VALUE_CHARS", "current_values", "remember", "scrub", "scrub_tree"]

MASK = "<redacted:session-credential>"

#: Shorter than this, a value is not masked (and the operator is warned once).
MIN_VALUE_CHARS = 8

_lock = threading.Lock()
_remembered: set = set()
_warned_short: set = set()
#: ``(path, mtime_ns, size) -> parsed values`` — one parse per change of the file.
_file_cache: dict = {}


def _sources(config: Mapping) -> Tuple[str, ...]:
    block = config.get("env") if isinstance(config, Mapping) else None
    listed = block.get("sessionCredentials") if isinstance(block, Mapping) else None
    if not isinstance(listed, (list, tuple)):
        return ()
    found = []
    for entry in listed:
        if not isinstance(entry, Mapping):
            continue
        source = entry.get("from", entry.get("name"))
        if isinstance(source, str) and envfile.NAME_RE.fullmatch(source):
            found.append(source)
    return tuple(found)


def _file_values(config: Mapping, config_path: Path) -> Mapping[str, str]:
    from .cli_config import resolve_env_file

    try:
        path = resolve_env_file(config, config_path)
    except Exception:  # noqa: BLE001 — a broken block names no file
        return {}
    if path is None:
        return {}
    try:
        st = path.stat()
    except OSError:
        return {}
    key = (str(path), st.st_mtime_ns, st.st_size)
    with _lock:
        cached = _file_cache.get(key)
    if cached is not None:
        return cached
    try:
        values = dict(envfile.parse(path.read_text(encoding="utf-8")).values)
    except (OSError, ValueError):
        return {}
    with _lock:
        _file_cache.clear()
        _file_cache[key] = values
    return values


def current_values(
    config: Optional[Mapping], config_path: Optional[Path] = None
) -> FrozenSet[str]:
    """Every configured source's value now, remembered as a side effect.

    Repository scope is ignored: any session may hold any of them, and a value that
    reached a session out of scope is still masked.
    """
    sources = _sources(config or {})
    if not sources:
        return frozenset()
    file_values: Mapping[str, str] = {}
    if config_path is not None:
        file_values = _file_values(config or {}, Path(config_path))
    values = set()
    for source in sources:
        value = file_values.get(source, os.environ.get(source))
        if value:
            values.add(value)
    remember(values)
    return frozenset(values)


def remember(values: Iterable[str]) -> None:
    """Keep ``values`` masked for the life of this process."""
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        if len(value) < MIN_VALUE_CHARS:
            with _lock:
                fresh = value not in _warned_short
                _warned_short.add(value)
            if fresh:
                logger.warning(
                    "a session credential is shorter than %d characters and will not "
                    "be masked in outbound text",
                    MIN_VALUE_CHARS,
                )
            continue
        with _lock:
            _remembered.add(value)


def _known(extra: Iterable[str] = ()) -> Tuple[str, ...]:
    with _lock:
        values = set(_remembered)
    values.update(v for v in extra if len(v) >= MIN_VALUE_CHARS)
    return tuple(sorted(values, key=len, reverse=True))


def _mask(text: str, values: Tuple[str, ...]) -> str:
    for value in values:
        if value in text:
            text = text.replace(value, MASK)
    return text


def scrub(
    text: Optional[str],
    config: Optional[Mapping] = None,
    config_path: Optional[Path] = None,
) -> Optional[str]:
    """``text`` with every configured and remembered credential value masked (R5.1).

    With nothing configured and nothing remembered it is ``text`` unchanged, read
    without touching disk (R5.3). ``None`` and non-strings pass through.
    """
    if not isinstance(text, str) or not text:
        return text
    values = _known(current_values(config, config_path) if config else ())
    if not values:
        return text
    return _mask(text, values)


def scrub_tree(node: Any) -> Any:
    """Every string in ``node`` (dicts, lists, tuples) masked with remembered values.

    The event log's scrub: no disk read, and the identity when nothing is known.
    """
    values = _known()
    if not values:
        return node
    return _walk(node, values)


def _walk(node: Any, values: Tuple[str, ...]) -> Any:
    if isinstance(node, str):
        return _mask(node, values)
    if isinstance(node, Mapping):
        return {key: _walk(value, values) for key, value in node.items()}
    if isinstance(node, (list, tuple)):
        return type(node)(_walk(item, values) for item in node)
    return node


def _forget_all() -> None:
    """Tests only: drop every remembered value and the file cache."""
    with _lock:
        _remembered.clear()
        _warned_short.clear()
        _file_cache.clear()
