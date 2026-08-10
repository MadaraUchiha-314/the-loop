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


# ------------------------------------------------------------------- the built-in default
# issue-193. the-loop is routinely pointed at a repository that never ran
# `/the-loop:init`: the daemon clones it, spawns a session in it, and the session finds no
# `.the-loop/` at all. The answer is one built-in default — shipped INSIDE the package,
# because the reader is an installed CLI with no plugin checkout to look in — and one
# writer that puts it there.


def test_defaults_reads_the_packaged_configuration() -> None:
    """R1.1 — the default resolves from the installed package, not from a checkout."""
    defaults = harness_config.defaults()
    assert defaults, "the packaged default must ship with the CLI"
    assert defaults["workflow"]["specDir"] == harness_config.DEFAULT_SPEC_DIR
    assert defaults["ticketing"]["github"]["owner"] == ""


def test_defaults_degrades_when_the_package_data_is_unreadable(monkeypatch) -> None:
    """R1.4 — a packaging fault must not cost a webhook delivery."""
    monkeypatch.setattr(
        harness_config, "default_config_path", lambda: Path("/nonexistent/none.yaml")
    )
    assert harness_config.defaults() == {}


def test_the_packaged_default_is_the_shipped_template() -> None:
    """R1.2 — one default with two writers, not two defaults with one name.

    Byte parity rather than data parity: `cp` is then the only correct way to move the
    default forward, and nobody has to reason about which of the two files' comments
    drifted.
    """
    template = REPO_ROOT / "skills" / "the-loop" / "templates" / "harness-config.yaml"
    if not template.is_file():
        pytest.skip("plugin templates not present (source distribution)")
    assert harness_config.default_config_path().read_bytes() == template.read_bytes(), (
        "cli/the_loop/harness-config.default.yaml and "
        "skills/the-loop/templates/harness-config.yaml have drifted. They are the same "
        "configuration written by two different things (`the-loop`'s ingress and "
        "`/the-loop:init`); copy one over the other."
    )


def test_the_packaged_default_agrees_with_the_per_key_fallbacks(tmp_path: Path) -> None:
    """R1.1 — the constants the CLI falls back to when it cannot write a file.

    `DEFAULT_SPEC_DIR` and `build_runtime`'s `phaseLabelPrefix` fallback exist because
    reading configuration is best-effort; they are only honest while they say what the
    packaged default says.
    """
    from the_loop.graph.bootstrap import build_runtime

    defaults = harness_config.defaults()
    assert harness_config.spec_dir(defaults) == harness_config.DEFAULT_SPEC_DIR
    fallback = build_runtime(tmp_path).config["phaseLabelPrefix"]
    assert fallback == defaults["workflow"]["phaseLabelPrefix"]


# --------------------------------------------------------------------------- scaffolding


def test_scaffold_writes_the_default_into_an_unadopted_repository(
    tmp_path: Path,
) -> None:
    """R2.1 — after adoption the repository configures itself like any other."""
    assert harness_config.scaffold(tmp_path) == "written"
    written = tmp_path / ".the-loop" / "harness-config.yaml"
    assert written.is_file()
    assert harness_config.initialized(tmp_path)
    assert harness_config.load(tmp_path) == harness_config.defaults()


def test_scaffold_says_who_wrote_the_file(tmp_path: Path) -> None:
    """The next human to open it should not have to guess where it came from."""
    harness_config.scaffold(tmp_path)
    head = (tmp_path / ".the-loop" / "harness-config.yaml").read_text(encoding="utf-8")
    assert head.startswith("#")
    assert "the-loop" in head.split("\n\n")[0]
    assert "issue-193" in head.split("\n\n")[0]


def test_scaffold_names_the_repository_it_was_written_for(tmp_path: Path) -> None:
    """R2.2 — `originRepo` resolves instead of failing closed (issue-183)."""
    assert harness_config.scaffold(tmp_path, "octo", "repo") == "written"
    loaded = harness_config.load(tmp_path)
    assert harness_config.origin_repo(loaded) == "octo/repo"
    # The template's inline comments survive: this is a config a human will edit.
    text = (tmp_path / ".the-loop" / "harness-config.yaml").read_text(encoding="utf-8")
    assert "# github | jira" in text


def test_scaffold_never_overwrites_an_existing_config(tmp_path: Path) -> None:
    """Abuse case 3 — an inbound event must not replace an operator's policy."""
    mine = _write(tmp_path, "workflow:\n  specDir: my/specs\n")
    assert harness_config.scaffold(tmp_path, "octo", "repo") == "present"
    assert mine.read_text(encoding="utf-8") == "workflow:\n  specDir: my/specs\n"


def test_scaffold_leaves_a_pre_rename_config_alone(tmp_path: Path) -> None:
    """T10 — a repository that has not run /the-loop:upgrade-the-loop is adopted."""
    _write(tmp_path, "workflow: {}\n", name="config.yaml")
    assert harness_config.scaffold(tmp_path) == "present"
    assert not (tmp_path / ".the-loop" / "harness-config.yaml").exists()


def test_scaffold_is_idempotent(tmp_path: Path) -> None:
    """R2.4 — every adoption path runs on every event; the second is a no-op."""
    assert harness_config.scaffold(tmp_path) == "written"
    assert harness_config.scaffold(tmp_path) == "present"


@pytest.mark.parametrize(
    "owner,repo",
    [
        ('x"\n\nautonomy:\n  defaultTier: 1', "repo"),
        ("octo", "repo\nsecurity:\n  review:\n    required: false"),
        ("../../etc", "repo"),
        ("", "repo"),
        ("octo", ""),
        ("-leading-dash", "repo"),
    ],
)
def test_scaffold_refuses_a_forged_owner_or_repo(
    tmp_path: Path, owner: str, repo: str
) -> None:
    """Abuse case 1 — payload text reaching a YAML document is an injection surface.

    Dropped rather than escaped: there is then no encoder to get wrong, and the written
    file is the packaged default verbatim, whose `ticketing.github` is empty.
    """
    assert harness_config.scaffold(tmp_path, owner, repo) == "written"
    loaded = harness_config.load(tmp_path)
    assert harness_config.origin_repo(loaded) == ""
    assert (
        loaded["autonomy"]["defaultTier"]
        == harness_config.defaults()["autonomy"]["defaultTier"]
    )
    assert loaded["security"]["review"]["required"] is True


def test_scaffold_degrades_when_it_cannot_write(tmp_path: Path, monkeypatch) -> None:
    """R2.5 — no delivery, spawn or transition is lost because a config was not written."""

    def boom(*_args, **_kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(Path, "mkdir", boom)
    assert harness_config.scaffold(tmp_path) == ""
    assert not (tmp_path / ".the-loop").exists()


def test_scaffold_degrades_when_the_packaged_default_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    """R1.4 again, at the writer: nothing is written from a default nobody could read."""
    monkeypatch.setattr(
        harness_config, "default_config_path", lambda: Path("/nonexistent/none.yaml")
    )
    assert harness_config.scaffold(tmp_path) == ""
    assert not (tmp_path / ".the-loop").exists()


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
