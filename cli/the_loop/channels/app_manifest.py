"""The Slack app manifest, named for its operator (issue-464).

The packaged ``slack-app-manifest.yaml`` stays the single source: every output —
the renamed manifest, Slack's one-click create link, the kept
``slack-app-manifest.json`` beside the CLI config — is built from it plus one
input, the app's name. Regenerating the kept file reads only that name back, so
an upgrade restores the shipped scopes and events whatever the old file said.

No network, no token: the link is opened by the operator's browser, and Slack's
own dialog confirms the workspace and the scopes.

Spec: docs/specs/issue-464/design.md.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import yaml

from .. import cli_config
from .commands import manifest_text

__all__ = [
    "CREATE_URL",
    "KEPT_FILENAME",
    "MAX_NAME",
    "build",
    "check_name",
    "default_path",
    "delta",
    "handle",
    "link",
    "render_json",
    "write",
]

#: Slack's create-app dialog, prefilled from a manifest (R2.1).
CREATE_URL = "https://api.slack.com/apps?new_app=1&manifest_json="
#: The kept manifest's name, in the directory holding the CLI config (R3.1).
KEPT_FILENAME = "slack-app-manifest.json"
#: Slack refuses an app name (``display_information.name``) longer than this.
MAX_NAME = 35

_NOT_HANDLE = re.compile(r"[^a-z0-9._-]+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def handle(name: str) -> str:
    """The bot's display name for ``name`` (R1.3): lowercase, ``[a-z0-9._-]`` only."""
    return _NOT_HANDLE.sub("-", name.strip().lower()).strip("-")


def check_name(name: str) -> str:
    """``name`` trimmed, or ``ValueError`` naming why Slack would refuse it (R1.4)."""
    if _CONTROL.search(name):
        raise ValueError("the app name must not contain a control character")
    trimmed = name.strip()
    if not trimmed:
        raise ValueError("the app name is empty")
    if len(trimmed) > MAX_NAME:
        raise ValueError(
            f"the app name is {len(trimmed)} characters; Slack allows {MAX_NAME}"
        )
    if not handle(trimmed):
        raise ValueError(
            "the app name needs at least one letter or digit (a-z, 0-9) for the "
            "bot's handle"
        )
    return trimmed


def build(name: Optional[str] = None) -> Dict[str, Any]:
    """The packaged manifest, renamed when ``name`` is given (R1.2)."""
    manifest = yaml.safe_load(manifest_text())
    if name is not None:
        name = check_name(name)
        manifest["display_information"]["name"] = name
        manifest["features"]["bot_user"]["display_name"] = handle(name)
    return manifest


def link(manifest: Dict[str, Any]) -> str:
    """Slack's one-click create-app URL carrying ``manifest`` (R2.1)."""
    compact = json.dumps(manifest, separators=(",", ":"), ensure_ascii=False)
    return CREATE_URL + quote(compact, safe="")


def render_json(manifest: Dict[str, Any]) -> str:
    """The kept file's text: readable, and pasteable into Slack's manifest editor."""
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def default_path() -> Path:
    """``slack-app-manifest.json`` beside the resolved CLI config (R3.1)."""
    return cli_config.default_cli_config_path().parent / KEPT_FILENAME


def _bot(manifest: Dict[str, Any], *keys: str) -> List[str]:
    node: Any = manifest
    for key in keys:
        node = node.get(key) if isinstance(node, dict) else None
    return [str(item) for item in node] if isinstance(node, list) else []


def delta(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Dict[str, List[str]]]:
    """The bot scopes and bot events ``new`` adds to and removes from ``old`` (R3.5)."""
    out: Dict[str, Dict[str, List[str]]] = {}
    for label, keys in (
        ("scopes", ("oauth_config", "scopes", "bot")),
        ("events", ("settings", "event_subscriptions", "bot_events")),
    ):
        before, after = _bot(old, *keys), _bot(new, *keys)
        out[label] = {
            "added": [item for item in after if item not in before],
            "removed": [item for item in before if item not in after],
        }
    return out


def _kept_name(text: str) -> Optional[str]:
    try:
        kept = json.loads(text)
    except ValueError:
        return None
    info = kept.get("display_information") if isinstance(kept, dict) else None
    name = info.get("name") if isinstance(info, dict) else None
    return name if isinstance(name, str) and name.strip() else None


def write(path: Path, name: Optional[str] = None) -> Dict[str, Any]:
    """Write the manifest to ``path`` as JSON, reusing the kept name (R3.2–R3.5).

    Returns ``{path, name, status, scopes, events, link}`` with ``status`` one of
    ``created``, ``updated`` or ``unchanged``. ``ValueError`` for a name Slack
    would refuse, or for a file that holds no manifest when no name is given —
    and then the file is left as it was.
    """
    old_text = path.read_text(encoding="utf-8") if path.exists() else None
    if name is None and old_text is not None:
        name = _kept_name(old_text)
        if name is None:
            raise ValueError(
                f"{path} holds no Slack app manifest this command can read; pass "
                "--name to regenerate it under that name"
            )
    manifest = build(name)
    text = render_json(manifest)
    result: Dict[str, Any] = {
        "path": str(path),
        "name": manifest["display_information"]["name"],
        "link": link(manifest),
    }
    if old_text is None:
        status = "created"
    elif old_text == text:
        status = "unchanged"
    else:
        status = "updated"
    try:
        old = json.loads(old_text) if old_text is not None else {}
    except ValueError:
        old = {}
    result.update(delta(old if isinstance(old, dict) else {}, manifest))
    result["status"] = status
    if status != "unchanged":
        _replace(path, text)
    return result


def _replace(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically: a crash never leaves half a manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle_:
            handle_.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
