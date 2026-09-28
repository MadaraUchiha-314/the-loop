"""The top-level ``hooks`` block of the CLI config (issue-344, R3).

Parsed here, imported nowhere here: ``the-loop hooks`` reports a declaration without
running a line of it (R5.1), and the daemons load it once at start. Every rule is a
refusal that names the entry — a declaration that cannot be honoured is never read as
"no hooks" (decision-137 D6).

Why the operator's CLI config: what runs inside the-loop's process with the-loop's
credentials is decided on the operator's machine (decision-123), as ``critics[]``,
``routing.graph.hooks`` and ``graphs[]`` already are. A ``path`` resolves against the
directory of **this config file**, never a checkout (decision-136 D1) — so a session
cannot plant a module where its own daemon will import it.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple, Union
from urllib.parse import urlsplit

from .contract import POINTS

__all__ = [
    "CONFIG_KEY",
    "Declaration",
    "Entry",
    "HooksConfigError",
    "config_base_dir",
    "read_declaration",
]

#: Where the operator declares the hooks, for messages that have to name it.
CONFIG_KEY = "hooks"

DEFAULT_TIMEOUT_SECONDS = 10.0

_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
_DOTTED = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_COMMON_KEYS = {"name", "module", "path", "url", "on", "required", "enabled"}
_LOCAL_KEYS = {"executor", "with"}
_REMOTE_KEYS = {"tokenEnv", "headers", "timeoutSeconds"}
_ALL_KEYS = _COMMON_KEYS | _LOCAL_KEYS | _REMOTE_KEYS

_LOOPBACK_NAMES = {"localhost", "localhost.localdomain"}


class HooksConfigError(ValueError):
    """The ``hooks`` declaration cannot be honoured; the message names the entry."""


@dataclass(frozen=True)
class Entry:
    """One ``hooks[]`` entry, validated but not executed."""

    name: str
    #: ``module`` | ``path`` | ``url``.
    kind: str
    module: str = ""
    path: str = ""
    url: str = ""
    executor: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)
    token_env: str = ""
    headers: Mapping[str, str] = field(default_factory=dict)
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    #: The points this entry handles; empty means the executor's own default (a local
    #: class: the methods it overrides; a remote: every point).
    on: Tuple[str, ...] = ()
    required: bool = False
    enabled: bool = True

    @property
    def target(self) -> str:
        return f"{self.kind} {self.module or self.path or self.url}"

    def resolved_path(self, base_dir: Union[str, Path]) -> Path:
        """The module file a ``path`` entry names: ``~`` expanded, a relative path
        taken against ``base_dir`` — the config file's directory — then resolved."""
        candidate = Path(os.path.expanduser(self.path))
        if not candidate.is_absolute():
            candidate = Path(base_dir) / candidate
        return candidate.resolve()

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "target": self.module or self.path or self.url,
            "on": list(self.on),
            "required": self.required,
            "enabled": self.enabled,
        }
        if self.kind == "url":
            out.update(
                {
                    "tokenEnv": self.token_env or None,
                    "headers": dict(self.headers),
                    "timeoutSeconds": self.timeout,
                }
            )
        else:
            out.update({"executor": self.executor or None, "with": dict(self.params)})
        return out


@dataclass(frozen=True)
class Declaration:
    entries: Tuple[Entry, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.entries

    def digest(self) -> str:
        blob = json.dumps(
            [e.as_dict() for e in self.entries], sort_keys=True, default=str
        ).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]


def config_base_dir(config_path: Union[str, Path]) -> Path:
    """The directory a relative ``path`` resolves against — the config file's own.

    Made absolute without resolving symlinks: "this file's directory" means the path
    the operator wrote, not where a link happens to point (issue-343 review, F10).
    """
    return Path(os.path.abspath(config_path)).parent


def read_declaration(cli_config: Mapping[str, Any]) -> Declaration:
    """Parse the top-level ``hooks`` out of an already-loaded CLI config.

    An **absent** or empty block is not malformed: it declares nothing, which is what
    every operator who has never heard of this feature gets. A malformed one raises.
    """
    if not isinstance(cli_config, Mapping):
        return Declaration()
    raw = cli_config.get(CONFIG_KEY)
    if raw is None or raw == []:
        return Declaration()
    if isinstance(raw, (str, Mapping)) or not isinstance(raw, Sequence):
        raise HooksConfigError(
            f"CLI config: `{CONFIG_KEY}` must be a list of entries, one per hook"
        )
    entries = []
    seen: Dict[str, int] = {}
    for index, item in enumerate(raw):
        entry = _read_entry(item, index)
        if entry.name in seen:
            raise HooksConfigError(
                f"CLI config: `{CONFIG_KEY}` names {entry.name!r} twice (entries "
                f"{seen[entry.name]} and {index}); every hook has one name"
            )
        seen[entry.name] = index
        entries.append(entry)
    return Declaration(entries=tuple(entries))


def _read_entry(item: Any, index: int) -> Entry:
    where = f"`{CONFIG_KEY}[{index}]`"
    if not isinstance(item, Mapping):
        raise HooksConfigError(
            f"CLI config: {where} must be a mapping with a `name` and one of "
            "`module`, `path` or `url` — never a bare value"
        )
    name = item.get("name")
    if not isinstance(name, str) or not _NAME.match(name):
        raise HooksConfigError(
            f"CLI config: {where} needs a `name` matching ^[a-z][a-z0-9-]*$ "
            f"(got {name!r})"
        )
    where = f"`{CONFIG_KEY}` entry {name!r}"
    unknown = sorted(set(item) - _ALL_KEYS)
    if unknown:
        raise HooksConfigError(
            f"CLI config: {where} has unknown key(s) {', '.join(unknown)}; the keys "
            f"are {', '.join(sorted(_ALL_KEYS))}"
        )
    kinds = [k for k in ("module", "path", "url") if item.get(k)]
    if len(kinds) != 1:
        raise HooksConfigError(
            f"CLI config: {where} must name exactly one of `module` (an installed "
            "dotted module), `path` (a .py file beside this config) or `url` (a remote "
            f"JSON-RPC endpoint); it names {kinds or 'none'}"
        )
    kind = kinds[0]
    target = item[kind]
    if not isinstance(target, str) or not target.strip():
        raise HooksConfigError(
            f"CLI config: {where} has a `{kind}` that is not a string"
        )
    target = target.strip()

    foreign = _REMOTE_KEYS if kind != "url" else _LOCAL_KEYS
    present = sorted(k for k in foreign if k in item)
    if present:
        applies = "a remote (`url`)" if kind != "url" else "a local (`module`/`path`)"
        raise HooksConfigError(
            f"CLI config: {where} sets {', '.join(present)}, which apply to {applies} "
            f"entry only"
        )

    on = _read_on(item.get("on"), where)
    required = _read_bool(item.get("required", False), "required", where)
    enabled = _read_bool(item.get("enabled", True), "enabled", where)

    if kind == "module":
        if not _DOTTED.match(target):
            raise HooksConfigError(
                f"CLI config: {where} `module` {target!r} is not an importable dotted "
                "name"
            )
    elif kind == "path":
        if not target.endswith(".py"):
            raise HooksConfigError(
                f"CLI config: {where} `path` {target!r} is not a .py file"
            )
    else:
        if "tokenEnv" in item and not item.get("tokenEnv"):
            raise HooksConfigError(
                f"CLI config: {where} has an empty `tokenEnv`; omit the key, or name "
                "the variable that holds the token"
            )
        token_env = _read_token_env(item.get("tokenEnv", ""), where)
        _check_url(target, token_env, where)

    if kind == "url":
        headers = _read_headers(item.get("headers"), where)
        timeout = _read_timeout(
            item.get("timeoutSeconds", DEFAULT_TIMEOUT_SECONDS), where
        )
        return Entry(
            name=name,
            kind=kind,
            url=target,
            token_env=_read_token_env(item.get("tokenEnv", ""), where),
            headers=headers,
            timeout=timeout,
            on=on,
            required=required,
            enabled=enabled,
        )
    executor = item.get("executor", "")
    if executor is None:
        executor = ""
    if not isinstance(executor, str) or (executor and not _DOTTED.match(executor)):
        raise HooksConfigError(
            f"CLI config: {where} `executor` must be an attribute name in the module"
        )
    params = item.get("with")
    params = {} if params is None else params
    if not isinstance(params, Mapping):
        raise HooksConfigError(
            f"CLI config: {where} has a `with` that is not a mapping"
        )
    return Entry(
        name=name,
        kind=kind,
        module=target if kind == "module" else "",
        path=target if kind == "path" else "",
        executor=executor,
        params=dict(params),
        on=on,
        required=required,
        enabled=enabled,
    )


def _read_on(value: Any, where: str) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, Mapping)) or not isinstance(value, Sequence):
        raise HooksConfigError(f"CLI config: {where} `on` must be a list of points")
    points = tuple(str(v).strip() for v in value)
    if not points:
        raise HooksConfigError(
            f"CLI config: {where} has an empty `on`; omit the key to handle every "
            "point the executor implements, or name the points"
        )
    unknown = [p for p in points if p not in POINTS]
    if unknown:
        raise HooksConfigError(
            f"CLI config: {where} `on` names {', '.join(repr(p) for p in unknown)}, "
            f"which is not a lifecycle point; the points are {', '.join(POINTS)}. "
            "An event-log type is not a hook point (decision-137)"
        )
    return points


def _read_bool(value: Any, key: str, where: str) -> bool:
    if not isinstance(value, bool):
        raise HooksConfigError(f"CLI config: {where} `{key}` must be true or false")
    return value


def _read_token_env(value: Any, where: str) -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or not _ENV.match(value):
        raise HooksConfigError(
            f"CLI config: {where} `tokenEnv` must be the NAME of an environment "
            f"variable (got {value!r}); the value is read at call time and never "
            "written here"
        )
    return value


def _read_headers(value: Any, where: str) -> Dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise HooksConfigError(
            f"CLI config: {where} `headers` must be a mapping of string to string"
        )
    if any(k.lower() == "authorization" for k in value):
        raise HooksConfigError(
            f"CLI config: {where} puts a credential in `headers`; name the variable "
            "that holds it under `tokenEnv` instead — a secret never lives in this file"
        )
    return dict(value)


def _read_timeout(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise HooksConfigError(
            f"CLI config: {where} `timeoutSeconds` must be a positive number"
        )
    return float(value)


def _check_url(url: str, token_env: str, where: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise HooksConfigError(
            f"CLI config: {where} `url` {url!r} must be an http(s) URL with a host"
        )
    if parts.scheme == "http" and token_env and not _is_loopback(parts.hostname):
        raise HooksConfigError(
            f"CLI config: {where} sends a bearer token (`tokenEnv`) to {url!r} over "
            "cleartext http; use https, or a loopback host"
        )


def _is_loopback(host: str) -> bool:
    if host.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
