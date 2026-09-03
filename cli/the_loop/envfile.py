"""Load a dotenv-format file into an environment mapping (issue-318, decision-108).

Every credential the-loop uses is **named** in the CLI config and **read** from the
process environment — ``webhooks.ghWebhook.secretEnv``, ``channels.slack.botTokenEnv``,
``integrations.github.api.tokenEnv`` — and the config never carries a value. This module
lets the config name the *file* that holds those values (``env.file``), so an operator
need not ``export`` them by hand before every ``the-loop start``. The values still enter
the process only through the environment, and only for names not already set there.

The grammar is deliberately small and stated here rather than borrowed from a library,
because the CLI has one runtime dependency (PyYAML, decision-038) and the behaviour is
the-loop's to document and test:

* one ``NAME=value`` per line; blank lines and lines starting with ``#`` are ignored;
* an optional leading ``export``;
* ``"…"``: the text up to the closing unescaped quote, with ``\\n \\t \\r \\\\ \\"``
  unescaped; ``'…'``: literal to the closing quote; otherwise the value is trimmed and
  cut at the first ``␣#`` (a trailing comment);
* no interpolation (``${OTHER}`` is four characters), no multi-line values;
* a line that is not of that shape is **skipped and reported by number** — never by
  text, because the text may be a secret.

Nothing here evaluates, expands or executes any part of the file, and nothing here logs
a value.
"""

from __future__ import annotations

import logging
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, MutableMapping, Optional, Tuple

logger = logging.getLogger("the-loop.env")

__all__ = ["LoadResult", "ParseResult", "load", "parse"]

#: A POSIX environment-variable name.
NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_DOUBLE_QUOTE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}


@dataclass(frozen=True)
class ParseResult:
    """The values a file declares, in file order (a later duplicate wins), and the
    1-based numbers of the lines that were skipped."""

    values: Dict[str, str]
    invalid_lines: Tuple[int, ...]


@dataclass(frozen=True)
class LoadResult:
    """What one :func:`load` did: the names it set, the names it left alone because the
    environment already had them, and the lines it skipped."""

    path: Path
    loaded: Tuple[str, ...]
    skipped: Tuple[str, ...]
    invalid_lines: Tuple[int, ...]


def _unquote_double(rest: str) -> Optional[str]:
    """The text of a ``"…"`` value; ``None`` when the quote is never closed."""
    out: List[str] = []
    i = 0
    while i < len(rest):
        ch = rest[i]
        if ch == "\\" and i + 1 < len(rest):
            out.append(_DOUBLE_QUOTE_ESCAPES.get(rest[i + 1], "\\" + rest[i + 1]))
            i += 2
            continue
        if ch == '"':
            return "".join(out)
        out.append(ch)
        i += 1
    return None


def _parse_value(raw: str) -> Optional[str]:
    """One value as written after ``=``; ``None`` when it is malformed."""
    raw = raw.strip()
    if raw.startswith('"'):
        return _unquote_double(raw[1:])
    if raw.startswith("'"):
        end = raw.find("'", 1)
        return None if end == -1 else raw[1:end]
    cut = raw.find(" #")
    if cut != -1:
        raw = raw[:cut]
    return raw.strip()


def parse(text: str) -> ParseResult:
    """Parse dotenv-format ``text``. Pure: reads a string, touches no environment."""
    values: Dict[str, str] = {}
    invalid: List[int] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export ") or stripped.startswith("export\t"):
            stripped = stripped[len("export") :].lstrip()
        name, sep, raw = stripped.partition("=")
        name = name.strip()
        if not sep or NAME_RE.fullmatch(name) is None:
            invalid.append(number)
            continue
        value = _parse_value(raw)
        if value is None:
            invalid.append(number)
            continue
        values[name] = value
    return ParseResult(values=values, invalid_lines=tuple(invalid))


def _warn_if_readable_by_others(path: Path, mode: int) -> None:
    if os.name == "posix" and mode & 0o077:
        logger.warning(
            "%s is readable by others (mode %s); it holds secrets — consider chmod 600",
            path,
            oct(stat.S_IMODE(mode)),
        )


def load(path: Path, environ: MutableMapping[str, str]) -> Optional[LoadResult]:
    """Load ``path`` into ``environ``, setting only the names not already present.

    Never raises and never logs a value: a missing or unreadable file is a warning
    naming the path (and the error class) and ``None``; a malformed line is a warning
    naming the file and the line number, with the valid lines still loaded.
    """
    try:
        info = path.stat()
    except OSError as exc:
        logger.warning(
            "env file %s does not exist or cannot be read (%s); nothing loaded",
            path,
            type(exc).__name__,
        )
        return None
    if not stat.S_ISREG(info.st_mode):
        logger.warning("env file %s is not a regular file; nothing loaded", path)
        return None
    _warn_if_readable_by_others(path, info.st_mode)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        logger.warning(
            "env file %s cannot be read (%s); nothing loaded", path, type(exc).__name__
        )
        return None
    parsed = parse(text)
    if parsed.invalid_lines:
        logger.warning(
            "env file %s: skipped malformed line %s",
            path,
            ", ".join(f"line {n}" for n in parsed.invalid_lines),
        )
    loaded: List[str] = []
    skipped: List[str] = []
    for name, value in parsed.values.items():
        if name in environ:
            skipped.append(name)
            continue
        environ[name] = value
        loaded.append(name)
    logger.info(
        "loaded %d variable(s) from env file %s (%d already set, left alone)",
        len(loaded),
        path,
        len(skipped),
    )
    if loaded:
        logger.debug("env file %s set: %s", path, ", ".join(loaded))
    if skipped:
        logger.debug("env file %s left alone: %s", path, ", ".join(skipped))
    return LoadResult(
        path=path,
        loaded=tuple(loaded),
        skipped=tuple(skipped),
        invalid_lines=parsed.invalid_lines,
    )
