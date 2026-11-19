"""The one string catalog — the-loop's human-facing messages (issue-540).

``the_loop/strings/en.json`` is a flat JSON object of stable dotted keys to message
text (``"slack.title.decision-pending": "Decision needed"``), with named
``{placeholder}`` fields. A translation is a sibling ``<locale>.json`` holding the
keys it translates; every key it lacks falls back to ``en``.

* :func:`t` — one message, formatted.
* :func:`section` — every message under a prefix, as ``{suffix: text}``. The
  migrated per-module dictionaries keep their public ``Dict[str, str]`` shape by
  being built from it.

The locale is ``THE_LOOP_LOCALE`` when set, else ``en``, and :func:`set_locale`
selects one explicitly. Keys come from code, never from input. A value passed to
:func:`t` is inserted literally: ``str.format`` is single-pass.

Log lines and exception messages are not catalogued. They are for operators,
stay in English, and are grepped.

Spec: docs/specs/issue-540/design.md.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Mapping, Optional

__all__ = ["DEFAULT_LOCALE", "catalog", "section", "set_locale", "t"]

logger = logging.getLogger("the-loop.strings")

DEFAULT_LOCALE = "en"

#: Where the catalogs live. A module attribute so a test can point it elsewhere.
_DIR = Path(__file__).resolve().parent

_LOCALE = re.compile(r"^[a-z]{2,3}([_-][A-Za-z0-9]{2,8})*$")

_cache: Dict[str, Mapping[str, str]] = {}
_selected: Optional[str] = None


def _reset() -> None:
    """Forget the loaded catalogs and the selected locale (tests)."""
    global _selected
    _cache.clear()
    _selected = None


def _check(locale: str) -> str:
    if not isinstance(locale, str) or not _LOCALE.match(locale):
        raise ValueError(f"not a locale name: {locale!r}")
    return locale


def _parse(path: Path) -> Mapping[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        raise ValueError(f"{path.name} is not a JSON object of strings")
    return data


def catalog(locale: str = DEFAULT_LOCALE) -> Mapping[str, str]:
    """The key → text mapping of one locale's own file, cached.

    ``en`` failing to load raises: it ships with the package, so its absence is a
    broken install. Any other locale that is missing or malformed logs one warning
    and reads as empty, which makes every lookup fall back to ``en``.
    """
    _check(locale)
    if locale in _cache:
        return _cache[locale]
    path = _DIR / f"{locale}.json"
    if locale == DEFAULT_LOCALE:
        try:
            data = _parse(path)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name} is not valid JSON: {exc}") from None
    else:
        try:
            data = _parse(path)
        except FileNotFoundError:
            data = {}
        except (OSError, ValueError) as exc:
            logger.warning("ignoring locale catalog %s: %s", path.name, exc)
            data = {}
    _cache[locale] = data
    return data


def _active() -> str:
    if _selected is not None:
        return _selected
    wanted = (os.environ.get("THE_LOOP_LOCALE") or "").strip()
    if not wanted:
        return DEFAULT_LOCALE
    try:
        return _check(wanted)
    except ValueError:
        logger.warning("THE_LOOP_LOCALE %r is not a locale name; using en", wanted)
        return DEFAULT_LOCALE


def set_locale(locale: str) -> None:
    """Select the locale :func:`t` and :func:`section` read first."""
    global _selected
    _selected = _check(locale)


def _text(key: str) -> str:
    active = _active()
    if active != DEFAULT_LOCALE:
        found = catalog(active).get(key)
        if found is not None:
            return found
    try:
        return catalog(DEFAULT_LOCALE)[key]
    except KeyError:
        raise KeyError(f"the-loop string catalog has no key {key!r}") from None


def t(key: str, /, **variables: object) -> str:
    """The message for ``key`` in the active locale (``en`` fallback), formatted."""
    text = _text(key)
    return text.format(**variables)


def section(prefix: str) -> Dict[str, str]:
    """``{suffix: text}`` for every key under ``prefix.`` — unformatted.

    Keys come from ``en``, the complete catalog. Each text is the active locale's
    when it translates that key.
    """
    head = prefix + "."
    return {
        key[len(head) :]: _text(key)
        for key in catalog(DEFAULT_LOCALE)
        if key.startswith(head)
    }
