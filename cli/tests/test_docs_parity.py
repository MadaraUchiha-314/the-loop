"""Documentation ↔ code parity (issue-117).

The defect this guards against is the one that produced issue-117. ``cli/README.md``
was a single 679-line file, and a flat file has nowhere to *put* a new command — so
issue-109 shipped ``check``, ``graph`` and ``migrate-config`` with no entry, added a
whole ``integrations`` block nobody documented, and deleted ``ghBinary`` while five
README references to it stayed. Structure alone does not fix that; structure plus a
test does, because now "someone forgot" is a red build.

Four assertions, both directions on both axes:

======  =========================================================  =========================
P1      every registered command has a page                        a shipped command with no docs
P2      every command page names a registered command              docs for a command that is gone
P3      every documented option exists in the schema               documenting a removed key
P4      every schema leaf is documented                            an undocumented config block
======  =========================================================  =========================

Pure filesystem reads: no network, no subprocess, no fixtures. Skipped when ``docs/``
is absent, so a source distribution that ships ``cli/`` without the site still passes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Set

import pytest

from the_loop.commands import iter_commands

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_DOCS = REPO_ROOT / "docs" / "cli" / "commands"
CLI_CONFIG_DOCS = REPO_ROOT / "docs" / "config" / "cli"
CLI_CONFIG_SCHEMA = REPO_ROOT / ".the-loop" / "cli-config.schema.json"

pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / "docs").is_dir(),
    reason="documentation site not present (source distribution)",
)

#: An option heading: ``### `some.path` `` — the path is relative to the page's
#: ``configBase`` front-matter key (design C3). Trailing prose after the code span is
#: allowed so a heading can carry a marker like `(required)`.
_OPTION_HEADING = re.compile(r"^###\s+`([A-Za-z0-9_.\[\]-]+)`")


def _front_matter(text: str) -> Dict[str, str]:
    """Parse the leading ``---`` block as flat ``key: value`` pairs.

    Deliberately not a YAML load: the only key read here is ``configBase``, a plain
    string, and slicing two delimiters is cheaper to reason about than handing an
    arbitrary document to a parser to retrieve one scalar.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    values: Dict[str, str] = {}
    for line in text[3:end].splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip():
            values[key.strip()] = value.strip().strip("\"'")
    return values


def _documented_options() -> Dict[str, Path]:
    """Every option documented under ``docs/config/cli/``, as absolute dotted paths."""
    found: Dict[str, Path] = {}
    for page in sorted(CLI_CONFIG_DOCS.rglob("*.md")):
        text = page.read_text(encoding="utf-8")
        base = _front_matter(text).get("configBase", "")
        for line in text.splitlines():
            match = _OPTION_HEADING.match(line)
            if match:
                relative = match.group(1)
                found[f"{base}.{relative}" if base else relative] = page
    return found


def _schema_leaves(node: dict, prefix: str = "") -> List[str]:
    """Leaf option paths of the CLI config schema.

    An array whose ``items`` declare their own ``properties`` contributes
    ``path[].child`` leaves (``polling.sources[].provider``). An array whose items are
    a ``$ref`` into another schema (``collaborators``) stays a single leaf — its shape
    is that other schema's to document.
    """
    leaves: List[str] = []
    for key, value in (node.get("properties") or {}).items():
        path = f"{prefix}{key}"
        if not isinstance(value, dict):
            leaves.append(path)
            continue
        items = value.get("items")
        if value.get("properties"):
            leaves.extend(_schema_leaves(value, f"{path}."))
        elif isinstance(items, dict) and items.get("properties"):
            leaves.extend(_schema_leaves(items, f"{path}[]."))
        else:
            leaves.append(path)
    return leaves


def _registered_names() -> Set[str]:
    return {command.name for command in iter_commands()}


def test_p1_every_registered_command_has_a_page() -> None:
    """A command the CLI exposes but nobody documented is invisible to operators."""
    missing = sorted(
        name
        for name in _registered_names()
        if not (COMMAND_DOCS / f"{name}.md").is_file()
    )
    assert not missing, (
        "registered but undocumented — add docs/cli/commands/<name>.md for: "
        + ", ".join(missing)
    )


def test_p2_every_command_page_names_a_registered_command() -> None:
    """A page for a command that no longer exists sends operators at nothing."""
    if not COMMAND_DOCS.is_dir():
        pytest.fail(f"{COMMAND_DOCS} does not exist")
    registered = _registered_names()
    orphans = sorted(
        page.stem
        for page in COMMAND_DOCS.glob("*.md")
        if page.stem != "index" and page.stem not in registered
    )
    assert not orphans, (
        "documented but not registered — remove or rename docs/cli/commands/ pages for: "
        + ", ".join(orphans)
    )


def test_p3_every_documented_option_exists_in_the_schema() -> None:
    """The `ghBinary` failure mode: five documented references, zero in the schema."""
    schema = json.loads(CLI_CONFIG_SCHEMA.read_text(encoding="utf-8"))
    known = set(_schema_leaves(schema))
    documented = _documented_options()
    assert documented, f"no option headings found under {CLI_CONFIG_DOCS}"
    unknown = sorted(
        f"{path} ({page.relative_to(REPO_ROOT)})"
        for path, page in documented.items()
        if path not in known
    )
    assert not unknown, (
        "documented but absent from .the-loop/cli-config.schema.json — the key was "
        "removed or the heading is misspelled:\n  " + "\n  ".join(unknown)
    )


def test_p4_every_schema_leaf_is_documented() -> None:
    """The `integrations` failure mode: a whole config block nobody wrote up."""
    schema = json.loads(CLI_CONFIG_SCHEMA.read_text(encoding="utf-8"))
    documented = set(_documented_options())
    undocumented = sorted(
        leaf for leaf in _schema_leaves(schema) if leaf not in documented
    )
    assert not undocumented, (
        "in the schema but undocumented — add a `### `<path>`` heading under "
        "docs/config/cli/:\n  " + "\n  ".join(undocumented)
    )
