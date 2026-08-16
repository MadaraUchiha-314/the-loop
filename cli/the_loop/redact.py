"""Scrub PII and environment data out of free text before it leaves the machine.

Built for self-diagnosis (issue-242), whose reports are composed from event-log
material and agent output and posted to a **public** repository. The primary
control there is a field *allow-list* (only named fields ever reach a report —
the ``webhook/excerpt.py`` argument); this module is the defense-in-depth
beneath it, cleaning the free text that legitimately survives: ``error``
strings and the diagnosis agent's prose.

Two rules shape the implementation:

* **Masks are visible.** Every replacement is a named placeholder
  (``<redacted:path>``, ``<redacted:token>``, …) so a reader can see *that*
  something was removed and *what kind* of thing it was — silent removal would
  make a redacted report indistinguishable from a complete one.
* **Only value-scan sensitive-NAMED environment variables.** Masking every
  environment value would eat the text (``LANG=C`` would censor the letter C);
  a variable is value-scanned only when its *name* says it holds a credential
  and its value is long enough to be one.

``defang_control_keywords`` is the second half of the issue-242 contract: a
composed issue body must never carry a control keyword
(:func:`the_loop.control.parse_command` matches them anywhere in a body), but
the agent's prose may legitimately *mention* one. Defanging visibly breaks the
token instead of deleting the sentence.
"""

from __future__ import annotations

import getpass
import os
import re
import socket
from typing import Iterable, Mapping, Optional

__all__ = ["defang_control_keywords", "scrub"]

#: Environment-variable NAMES that mark a value as a credential.
_SENSITIVE_ENV_RE = re.compile(
    r"TOKEN|SECRET|KEY|PASSWORD|PASSWD|CREDENTIAL|AUTH", re.IGNORECASE
)

#: A credential shorter than this is not maskable without eating ordinary text.
_ENV_VALUE_MIN_CHARS = 6

# An absolute POSIX path (or ~ path), only where a path can start: the start of
# the text or after whitespace/quote/=/(/:/, — so the slashes inside a URL
# (`https://host/path`) never match, each being preceded by `:`+`/` or a word
# character.
_POSIX_PATH_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s\"'`=(:,]))(?:~[\w@./+~-]*|/[\w@.+~-]+(?:/[\w@.+~-]+)*)"
)
_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']+")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# Token-shaped: >= 20 chars of credential alphabet containing at least one
# digit — long hyphenated English words carry no digits and survive.
_TOKEN_RE = re.compile(r"(?<![\w/])(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{20,}(?![\w-])")

# The same token boundaries `control.parse_command` uses.
_KEYWORD_BOUNDARY_BEFORE = r"(?<![\w:-])"
_KEYWORD_BOUNDARY_AFTER = r"(?![\w:-])"


def scrub(
    text: str,
    *,
    env: Optional[Mapping[str, str]] = None,
    home: Optional[str] = None,
    user: Optional[str] = None,
    host: Optional[str] = None,
) -> str:
    """``text`` with PII and environment data masked. Pure given its keywords.

    The keyword parameters exist for tests; the defaults read this machine's
    identity at call time.
    """
    env = os.environ if env is None else env
    home = os.path.expanduser("~") if home is None else home
    user = _local_user() if user is None else user
    host = socket.gethostname() if host is None else host

    values = [
        value
        for name, value in env.items()
        if _SENSITIVE_ENV_RE.search(name) and len(value) >= _ENV_VALUE_MIN_CHARS
    ]
    for value in sorted(values, key=len, reverse=True):
        text = text.replace(value, "<redacted:env>")

    if home and len(home) >= 4:
        text = text.replace(home, "<redacted:home>")
    text = _WINDOWS_PATH_RE.sub("<redacted:path>", text)
    text = _POSIX_PATH_RE.sub("<redacted:path>", text)
    if user and len(user) >= 3:
        text = re.sub(
            r"(?<![\w-])" + re.escape(user) + r"(?![\w-])", "<redacted:user>", text
        )
    if host and len(host) >= 4 and host != "localhost":
        text = text.replace(host, "<redacted:host>")
    text = _EMAIL_RE.sub("<redacted:email>", text)
    text = _TOKEN_RE.sub("<redacted:token>", text)
    return text


def _local_user() -> str:
    try:
        return getpass.getuser()
    except OSError:  # no passwd entry (containers) — nothing to mask
        return ""


def defang_control_keywords(text: str, keywords: Iterable[str]) -> str:
    """``text`` with any whole-token control keyword visibly broken.

    After this, :func:`the_loop.control.parse_command` finds no command in the
    text, while a reader still sees which keyword was meant. Case-insensitive,
    longest keyword first (so a keyword embedding another is defanged whole).
    """
    for keyword in sorted({k for k in keywords if k}, key=len, reverse=True):
        if " " in keyword:
            replacement = keyword.replace(" ", " ‹defanged› ")
        else:
            replacement = keyword[:1] + "‹defanged›" + keyword[1:]
        pattern = (
            _KEYWORD_BOUNDARY_BEFORE + re.escape(keyword) + _KEYWORD_BOUNDARY_AFTER
        )
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text
