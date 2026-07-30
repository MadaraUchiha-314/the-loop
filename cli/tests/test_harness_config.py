"""The harness-config read surface (issue-121).

Issue #121 asked why the CLI reads a repository's ``harness-config.yaml`` at all. The
answer — those keys are the repository's own policy and the CLI executes it on the
repository's behalf — is decision-044, and the rule it states runs in one direction:

    a repository's harness config may configure work done **on that repository**;
    it may never configure the daemon itself.

A rule nothing checks is a rule that drifts, and this one already had: three modules read
the file, each with its own copy of the pre-rename fallback, and four documents claimed
the daemon never read it at all (it has, on the ``graphlink`` path, since issue-113).

Four assertions, in ``test_docs_parity.py``'s idiom — pure filesystem reads, no network,
no subprocess, no fixtures:

======  =========================================================  =========================
H1      every ``READS`` key resolves in the harness-config schema  a key declared under a name the schema lacks
H2      only ``harness_config.py`` opens a harness config file     a fourth reader added quietly
H3      every ``READS`` key is documented as CLI-read              reading a key nobody documented
H4      every key documented as CLI-read is in ``READS``           documenting a read that no longer happens
======  =========================================================  =========================

H2 is deliberately a **source** assertion. There is no runtime signal for "somebody
opened this file", and the failure mode being pinned is a contributor adding a fourth
reader — which is visible in the diff and only in the diff. It matches a filename
constant used as a *path component* (next to ``.the-loop``), so the several docstrings
that mention ``harness-config.yaml`` in prose do not trip it.

Run with: pytest (from the ``cli/`` directory).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Set

import pytest

from the_loop import harness_config
from the_loop.harness_config import HarnessConfigError

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "cli" / "the_loop"
HARNESS_SCHEMA = REPO_ROOT / ".the-loop" / "harness-config.schema.json"
HARNESS_CONFIG_DOC = REPO_ROOT / "docs" / "config" / "harness-config.md"

#: The heading the CLI-read table lives under, and the shape of one of its rows:
#: ``| `workflow.specDir` | `check`, `graph` | … |``.
_DOC_SECTION = "## What the CLI reads from it"
_DOC_ROW = re.compile(r"^\|\s*`([A-Za-z0-9_.\[\]-]+)`\s*\|")

needs_docs = pytest.mark.skipif(
    not HARNESS_CONFIG_DOC.is_file(),
    reason="documentation site not present (source distribution)",
)


# ----------------------------------------------------------------- the read surface


def test_reads_is_not_empty_and_is_self_describing() -> None:
    """``READS`` is the answer to "which keys?", so every field has to carry weight."""
    assert harness_config.READS, "the CLI reads at least one key; declare it"
    for read in harness_config.READS:
        assert read.key, "a read with no key documents nothing"
        assert read.command, f"{read.key}: name the command(s) that read it"
        assert read.why, f"{read.key}: say why it is the repository's to declare"


def test_h1_every_declared_key_resolves_in_the_harness_schema() -> None:
    """A declared key the schema does not define is a typo or a removed setting."""
    schema = json.loads(HARNESS_SCHEMA.read_text(encoding="utf-8"))
    unresolved = sorted(
        read.key for read in harness_config.READS if not _resolves(schema, read.key)
    )
    assert not unresolved, (
        "harness_config.READS declares keys that .the-loop/harness-config.schema.json "
        f"does not define: {', '.join(unresolved)}"
    )


def test_h2_only_the_shared_reader_opens_a_harness_config() -> None:
    """A fourth reader is how the read surface stops being enumerable."""
    offenders: List[str] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        if path.name == "harness_config.py":
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if _opens_a_harness_config(line):
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{number}: {line.strip()}"
                )
    assert not offenders, (
        "the harness config is read in exactly one module (the_loop.harness_config) so "
        "its read surface stays enumerable — see decision-044. Offending lines:\n"
        + "\n".join(offenders)
    )


@needs_docs
def test_h3_every_declared_key_is_documented() -> None:
    """Reading a repository's key without telling its owner is the original defect."""
    documented = _documented_keys()
    missing = sorted(
        read.key for read in harness_config.READS if read.key not in documented
    )
    assert not missing, (
        f"keys read by the CLI but absent from '{_DOC_SECTION}' in "
        f"docs/config/harness-config.md: {', '.join(missing)}"
    )


@needs_docs
def test_h4_every_documented_key_is_still_read() -> None:
    """The other direction: documentation for a read that no longer happens."""
    declared = {read.key for read in harness_config.READS}
    stale = sorted(_documented_keys() - declared)
    assert not stale, (
        f"'{_DOC_SECTION}' in docs/config/harness-config.md documents keys the CLI no "
        f"longer reads: {', '.join(stale)}"
    )


# ------------------------------------------------------------------------ resolution


def test_config_path_prefers_the_current_name(tmp_path: Path) -> None:
    directory = tmp_path / ".the-loop"
    directory.mkdir()
    (directory / "config.yaml").write_text("workflow: {}\n")
    (directory / "harness-config.yaml").write_text("workflow: {}\n")
    assert harness_config.config_path(tmp_path) == directory / "harness-config.yaml"


def test_config_path_falls_back_to_the_pre_rename_name(tmp_path: Path) -> None:
    # issue-82/decision-035: a repository that has not run /the-loop:upgrade-the-loop
    # still has config.yaml, and must keep working.
    directory = tmp_path / ".the-loop"
    directory.mkdir()
    (directory / "config.yaml").write_text("workflow: {}\n")
    assert harness_config.config_path(tmp_path) == directory / "config.yaml"


def test_config_path_is_none_when_the_repo_has_neither(tmp_path: Path) -> None:
    assert harness_config.config_path(tmp_path) is None


# ------------------------------------------------------------------------ best-effort


@pytest.mark.parametrize(
    "text",
    [
        "workflow: {specDir: specs}\n",
        "",
        "  \n",
    ],
)
def test_load_returns_a_mapping_for_anything_parseable(
    tmp_path: Path, text: str
) -> None:
    _write(tmp_path, text)
    assert isinstance(harness_config.load(tmp_path), dict)


def test_load_reads_the_document(tmp_path: Path) -> None:
    _write(tmp_path, "workflow:\n  specDir: specs\n")
    assert harness_config.load(tmp_path)["workflow"]["specDir"] == "specs"


def test_load_is_empty_when_absent(tmp_path: Path) -> None:
    assert harness_config.load(tmp_path) == {}


def test_load_is_empty_for_an_unparseable_file(tmp_path: Path) -> None:
    # `the-loop check` must still report the phase it can compute in a repository whose
    # config someone is halfway through editing.
    _write(tmp_path, "workflow: [unclosed\n")
    assert harness_config.load(tmp_path) == {}


def test_load_is_empty_for_a_non_mapping(tmp_path: Path) -> None:
    _write(tmp_path, "- a list, not a config\n")
    assert harness_config.load(tmp_path) == {}


# ----------------------------------------------------------------------------- strict


def test_load_strict_is_empty_when_absent(tmp_path: Path) -> None:
    # Absent is not an error: a repository with no critics configured has none, and
    # `the-loop critic list` says so rather than failing.
    assert harness_config.load_strict(tmp_path) == {}


def test_load_strict_raises_for_an_unparseable_file(tmp_path: Path) -> None:
    # A critic round that silently reviews nothing is a false green.
    _write(tmp_path, "reviews: [unclosed\n")
    with pytest.raises(HarnessConfigError):
        harness_config.load_strict(tmp_path)


def test_load_strict_raises_for_a_non_mapping(tmp_path: Path) -> None:
    _write(tmp_path, "- a list, not a config\n")
    with pytest.raises(HarnessConfigError):
        harness_config.load_strict(tmp_path)


# ---------------------------------------------------------------------------- helpers


def _write(root: Path, text: str, name: str = "harness-config.yaml") -> Path:
    directory = root / ".the-loop"
    directory.mkdir(exist_ok=True)
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def _resolves(schema: dict, key: str) -> bool:
    """Whether a dotted ``READS`` key names a property of the harness schema.

    Only the two shapes ``READS`` uses are walked — a nested object (``workflow.specDir``)
    and a property that is itself the leaf (``notifications``, ``reviews.critics``). An
    array's item shape is not descended into, because no declared key names one; a future
    key that does will fail here loudly rather than pass vacuously.
    """
    node: Dict[str, object] = schema
    for part in key.split("."):
        properties = node.get("properties")
        if not isinstance(properties, dict) or part not in properties:
            return False
        child = properties[part]
        node = child if isinstance(child, dict) else {}
    return True


def _opens_a_harness_config(line: str) -> bool:
    """Whether ``line`` uses a harness-config filename as a path component.

    ``"harness-config.yaml"`` beside ``.the-loop`` is a read; the same name inside prose
    is a reference. The distinction is the neighbouring directory, which every real read
    site needs and no docstring sentence has.
    """
    if ".the-loop" not in line:
        return False
    return any(
        f'"{name}"' in line or f"'{name}'" in line for name in harness_config.FILENAMES
    )


def _documented_keys() -> Set[str]:
    """The keys listed in the CLI-read table of ``docs/config/harness-config.md``."""
    lines = HARNESS_CONFIG_DOC.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index(_DOC_SECTION)
    except ValueError:  # pragma: no cover - H3 reports the missing section
        return set()
    keys: Set[str] = set()
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        match = _DOC_ROW.match(line)
        if match:
            keys.add(match.group(1))
    return keys
