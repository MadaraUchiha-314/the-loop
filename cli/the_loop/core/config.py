"""Core capability: the operator's CLI config, read and changed (issue-222).

The CLI config is the daemon's whole control surface — who may command the loop, where
sessions are checked out, which harness is spawned, what the receiver listens on — and
until now it was editable in exactly one way: open the file and hand-edit YAML. This
module is what the Control Plane's Settings tab drives, and (should a CLI verb ever want
it) what that would call too: one implementation, transports on top (decision-058).

Three properties are what make a write path into somebody's daemon config defensible, and
each is enforced here rather than at the edge:

**The file survives.** Changes are spliced into the original text by
:mod:`the_loop.yamlpatch`, so an operator's comments — about half of the shipped config —
are still there afterwards. A round-trip through a YAML dumper would delete them.

**Nothing invalid is written.** The *merged* document (file + patch) is checked against
the packaged schema, then against the migration gate, then against the one CORS pairing
:mod:`the_loop.api.config` refuses to boot on. Any failure leaves the file byte-identical.

**The path is not the caller's to choose.** It is resolved by the same rules every other
the-loop process uses (``--config``, ``$THE_LOOP_CLI_CONFIG``, ``./.the-loop/``, ``~``).
The API exposes no field that names a file, so this route cannot write anywhere else.

Hot reload comes free for the daemons — :class:`the_loop.reload.Reloader` content-hashes
this path and the poller and receiver check it as they run — and is arranged for the
service itself in :mod:`the_loop.api.app`. What cannot reload is reported instead: see
:data:`RESTART_REQUIRED`.
"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

import yaml

from .. import configschema, eventlog, yamlpatch

# `api.config` is a *config accessor* that happens to live under `api/` — it resolves the
# `service` block and imports nothing from FastAPI — so reaching for it here keeps the
# facade importable without a web framework while leaving the CORS rule stated once.
from ..api.config import cors_config
from ..cli_config import default_cli_config_path
from ..migrations import CURRENT_CONFIG_VERSION, ConfigTooOld, assert_current

__all__ = ["RESTART_REQUIRED", "get_config", "get_schema", "update_config"]

#: The editor directive a config this module *creates* opens with. ``yaml-language-server``
#: honours it on the first line and nowhere else (issue-220, decision-080), and it points
#: at the published schema rather than a local copy, so the operator's editor validates a
#: file this service wrote exactly as it validates one ``/the-loop:init`` wrote.
MODELINE = (
    "# yaml-language-server: $schema=https://raw.githubusercontent.com/"
    "MadaraUchiha-314/the-loop/main/.the-loop/cli-config.schema.json\n"
)

#: Key paths that only take effect on a restart. The bind is uvicorn's, taken once in
#: ``api/serve.py``; the CORS middleware is Starlette's, built once in ``create_app`` —
#: as is the MCP mount (``service.mcp``, issue-228). Everything else in the config is
#: read per use, from the value the service refreshes.
RESTART_REQUIRED = (
    "service.host",
    "service.port",
    "service.exposed",
    "service.cors",
    "service.mcp",
    "service.hostIngresses",
)

#: A config this module creates is readable by its owner only: it names authorized GitHub
#: logins and local paths, and a fresh file has no reason to be world-readable. An
#: existing file keeps whatever mode the operator gave it.
_NEW_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR


def _resolve(path: Optional[Union[str, Path]]) -> Path:
    return Path(path) if path is not None else Path(default_cli_config_path())


def get_config(path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """``{path, exists, version, config}`` for the resolved CLI config.

    A missing file is a **normal** state — a workstation nobody has configured yet — and
    reads as ``exists: false`` with an empty config and the path it would be written to.
    An *unparseable* file is not: it raises :class:`ValueError`, because reporting an
    empty config for a file that is halfway through an edit tells the operator that
    everything is at its default, which is the one thing it is not.

    The document is served as authored. ``load_cli_config`` would additionally fan
    ``integrations.github.cli.binary`` out into private ``_ghBinary`` keys — a runtime
    convenience that is not in the schema, and would come back on the next save as an
    unknown key — so the two steps that matter are taken directly instead.
    """
    resolved = _resolve(path)
    if not resolved.is_file():
        return {"path": str(resolved), "exists": False, "version": "", "config": {}}
    config = _parse(resolved)
    return {
        "path": str(resolved),
        "exists": True,
        "version": str(config.get("version") or ""),
        "config": config,
    }


def get_schema() -> Dict[str, Any]:
    """The CLI config's JSON Schema, every ``$ref`` already resolved.

    Resolved server-side on purpose: the client rendering a form from it should need one
    call, not one call plus however many documents the schema happens to reference.
    """
    return configschema.load_schema("cli-config")


def update_config(
    patch: Mapping[str, Any], path: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """Apply a **sparse** patch to the CLI config and report what it did.

    ``patch`` is a nested mapping naming only what changes: mappings merge, other values
    replace, and a leaf of ``None`` removes the key so the built-in default applies again.
    Sending a value the file already carries is not a change and writes nothing — which is
    why "an empty patch" needs no special case.

    Returns ``{path, exists, changed, restartRequired, written, config}``. Raises
    :class:`ValueError` for anything the operator can fix (a malformed patch, a schema
    violation, a config too old, the un-bootable CORS pair) — the file is untouched in
    every one of those cases — and :class:`the_loop.yamlpatch.SpliceError` if the edited
    text cannot be proven to hold the intended document.
    """
    if not isinstance(patch, Mapping):
        raise ValueError("patch must be an object mapping config keys to values")

    resolved = _resolve(path)
    exists = resolved.is_file()
    text = resolved.read_text(encoding="utf-8") if exists else ""
    current = _parse(resolved) if exists else {}

    if patch and not exists and "version" not in patch:
        # A file created here declares its version, so the migration gate has something
        # to believe and `/the-loop:upgrade-the-loop` has something to compare.
        patch = {"version": CURRENT_CONFIG_VERSION, **dict(patch)}

    changed = yamlpatch.changed_paths(current, patch)
    if not changed:
        return {
            "path": str(resolved),
            "exists": exists,
            "changed": [],
            "restartRequired": [],
            "written": False,
            "config": current,
        }

    merged = yamlpatch.deep_merge(current, patch)
    _reject_invalid(merged)

    updated = yamlpatch.apply(text, patch, header="" if exists else MODELINE)
    _write_atomically(resolved, updated, exists)

    eventlog.emit("config.updated", path=str(resolved), keys=changed)
    return {
        "path": str(resolved),
        "exists": True,
        "changed": changed,
        "restartRequired": _restart_required(changed),
        "written": True,
        "config": merged,
    }


def _parse(resolved: Path) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{resolved} is not valid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{resolved} does not hold a mapping at the top level")
    return data


def _reject_invalid(merged: Mapping[str, Any]) -> None:
    """The three gates a write must clear, in the order that gives the best message.

    The schema first, because it names the exact key; the migration gate next, because its
    message names the command that fixes it; the CORS pair last, because it is the only
    one whose failure is about a *combination* rather than a value. All three run against
    the merged document, never the patch — a patch is not a config.
    """
    errors = configschema.validate(merged)
    if errors:
        raise ValueError(
            "this change would make the CLI config invalid:\n"
            + "\n".join(f"  · {error}" for error in errors)
        )
    try:
        assert_current(merged)
    except ConfigTooOld as exc:
        raise ValueError(str(exc)) from exc
    # Raises for `allowOrigins: ["*"]` with credentials — the pairing `api/serve.py`
    # refuses to boot on. One function, so the write-time rule and the boot-time rule
    # cannot drift apart; saving a config the service could not restart on is not a
    # kindness.
    cors_config(dict(merged))


def _restart_required(changed: List[str]) -> List[str]:
    return [
        key
        for key in changed
        if any(
            key == prefix or key.startswith(f"{prefix}.") for prefix in RESTART_REQUIRED
        )
    ]


def _write_atomically(resolved: Path, text: str, exists: bool) -> None:
    """Replace the file's contents in one step.

    A reader — the poller's :class:`~the_loop.reload.Reloader`, another the-loop process,
    the operator's editor — sees either the whole old file or the whole new one, never a
    half-written config. A **symlinked** config is written *through*: `os.replace` on the
    link would leave a regular file where the operator put a pointer, which is a change
    they did not ask for. The temp file is created in the **same directory** so
    ``os.replace`` is a rename within one filesystem, and is removed if anything fails.
    """
    target = resolved.resolve() if resolved.is_symlink() else resolved
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = target.stat().st_mode & 0o777 if exists else _NEW_FILE_MODE
    handle, temp_path = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, target)
    except BaseException:
        Path(temp_path).unlink(missing_ok=True)
        raise
