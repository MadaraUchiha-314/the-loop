"""Resolve and load a repository's HARNESS config — the mirror image of ``cli_config``.

Two files configure the-loop, and the rule for which is which is **directional**, not
per-process (issue-121, decision-044):

    a repository's harness config may configure work done **on that repository**;
    it may never configure the daemon itself.

``cli_config.py`` holds the other half: the operator's machine — ingress, routing, who
may trigger, session hosting, the event log — resolved from four places, tied to no
repository, and with no fallback to any checkout (decision-032). Nothing here is
reachable from there, and that is the point.

The keys the CLI reads *from* a repository are declared in :data:`READS`. All of them are
the same values the plugin and the skill read; the CLI reads them because it executes
that repository's policy on the repository's behalf — a phase label the repo names, a spec
directory the repo chose, the critics the repo declared. Moving them to the CLI config
would put per-repo policy in one machine-scoped file, fork the source of truth with the
skill, and leave ``check``/``scenarios`` unconfigurable in the bare CI checkout where they
actually run.

Reading is **repo-scoped and best-effort**: :func:`load` degrades a missing, unparseable
or non-mapping file to ``{}`` so ``the-loop check`` still reports the phase it can compute
in a repository whose config someone is halfway through editing. :func:`load_strict`
exists for the one caller that must not degrade — ``the-loop critic``, where a round that
silently reviews nothing is a false green.

The daemon reaches this module too, on the ``graphlink`` path (issue-113), for the
work item's **own** checkout and only after ``_checkout_belongs_to`` has proved via the
``origin`` remote that the directory really is that repository's. That is the ⟶ direction
and it is allowed; the ⟵ direction — a checkout supplying ``authorizedUsers`` or a poll
source's ``repos`` — is not, and has no code path here.

Decision: 044  ·  Spec: docs/specs/issue-121/
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import yaml

logger = logging.getLogger("the-loop.harness-config")

__all__ = [
    "DEFAULT_CONFIG_FILE",
    "DEFAULT_SPEC_DIR",
    "FILENAMES",
    "HarnessConfigError",
    "HarnessConfigRead",
    "READS",
    "config_path",
    "default_config_path",
    "defaults",
    "initialized",
    "load",
    "load_strict",
    "origin_repo",
    "scaffold",
    "spec_dir",
]

#: Where a repository keeps its per-work-item specs when it says nothing. Expressed here
#: rather than at each call site because ``graph/bootstrap.py`` and ``graphlink.py`` must
#: agree on it: they resolve the same directory for the same work item, one to gate on and
#: one to write into, and two copies of a literal is how they came to disagree (issue-123).
DEFAULT_SPEC_DIR = "docs/specs"

#: The config filename, then the pre-rename one. Expressed **once**: before issue-121
#: three modules each carried their own copy of this fallback, which is how "which name
#: wins?" became three separate answers. Renamed in issue-82 (decision-035); the old name
#: stays readable for repositories that have not run ``/the-loop:upgrade-the-loop``.
FILENAMES: Tuple[str, ...] = ("harness-config.yaml", "config.yaml")

#: The built-in default harness config, shipped as package data beside this module
#: (issue-193). It belongs to the **CLI**, for the same reason the process graphs do
#: (``graph.model.shipped_graph_path``): the reader is an installed ``the-loopy-one``,
#: which has no plugin checkout to find ``skills/the-loop/templates/`` in. It is a
#: byte-for-byte copy of that template — one configuration with two writers, the-loop's
#: ingress and ``/the-loop:init`` — and the copy is pinned by a test, so a drift is a
#: build failure rather than two products' worth of "the defaults".
DEFAULT_CONFIG_FILE = "harness-config.default.yaml"

#: The provenance header :func:`scaffold` puts above the default it writes. A config file
#: nobody remembers creating is a config file nobody trusts, so the written one says who
#: wrote it, why, and how to replace it with a considered one.
_SCAFFOLD_HEADER = """\
# Written by the-loop: this repository carried no .the-loop/harness-config.yaml, so
# the-loop adopted it with its BUILT-IN DEFAULTS (issue-193) rather than working it
# under nothing. This is the same baseline `/the-loop:init --defaults` writes — run
# `/the-loop:init` for the guided version, and edit this file freely; the-loop never
# rewrites a config that already exists.

"""

#: The editor directive the packaged default opens with (issue-220). ``yaml-language-server``
#: honours it on the **first line only**, which is why :func:`_with_header` exists.
_MODELINE_PREFIX = "# yaml-language-server:"


def _with_header(body: str) -> str:
    """``_SCAFFOLD_HEADER`` above ``body`` — but never above its schema modeline.

    the-loop stopped copying its JSON schemas into projects (issue-220), so a scaffolded
    config's only editor validation is the ``# yaml-language-server: $schema=…`` line the
    packaged default opens with, and that directive works on line 1 or not at all.
    Prepending the provenance header verbatim would push it to line 7 and quietly cost
    the operator the validation this file promises them.

    A body that carries no modeline gets today's plain concatenation, so nothing depends
    on the default keeping that first line — only on the header not jumping over it.
    """
    head, separator, rest = body.partition("\n")
    if not head.startswith(_MODELINE_PREFIX):
        return _SCAFFOLD_HEADER + body
    return head + separator + _SCAFFOLD_HEADER + rest


#: GitHub's own owner/repo charset. Payload-derived text entering a YAML document is an
#: injection surface, and this allow-list is the whole defence: it contains no quote, no
#: newline and no ``": "``, so a value that passes cannot extend, terminate or re-key the
#: document. A value that fails is **dropped, not escaped** — there is then no encoder to
#: get wrong (issue-193, abuse case 1).
_GH_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: A top-level key, i.e. the end of the ``ticketing:`` block the substitution is confined
#: to, and the ``owner``/``repo`` placeholders inside it.
_TOP_LEVEL_KEY = re.compile(r"^[A-Za-z]")
_PLACEHOLDER = re.compile(r'^(?P<indent>\s+)(?P<key>owner|repo): ""(?P<trail>.*)$')


class HarnessConfigError(ValueError):
    """The harness config exists but cannot be understood. Raised only by strict loads."""


@dataclass(frozen=True)
class HarnessConfigRead:
    """One key the CLI reads from a repository's harness config.

    ``why`` is not decoration: it is the argument that this key belongs to the repository
    rather than to the operator, and a new entry that cannot state one is a key that
    probably belongs in ``cli-config.yaml`` instead.
    """

    key: str
    command: str
    why: str


#: The CLI's complete harness-config read surface, pinned by ``test_harness_config.py``
#: against both the schema and the docs. Adding a read means adding a row here.
READS: Tuple[HarnessConfigRead, ...] = (
    HarnessConfigRead(
        "workflow.phaseLabelPrefix",
        "check, graph, and the daemon via graphlink",
        "the label namespace is the repository's own convention; a daemon watching N "
        "repos cannot know it for each of them",
    ),
    HarnessConfigRead(
        "workflow.specDir",
        "check, graph, and the daemon via graphlink",
        "where this project keeps its specs is a fact about this project's layout",
    ),
    HarnessConfigRead(
        "notifications",
        "check, graph, and the daemon via graphlink",
        "who is told about which harness event resolves against the repository's own "
        "collaborators.yaml",
    ),
    HarnessConfigRead(
        "reviews.critics",
        "critic",
        "the review bar is a property of the project, and the skill reads the same "
        "entries — a second source would let the CLI and the agent disagree",
    ),
    HarnessConfigRead(
        "testing.integrationTestGlobs",
        "scenarios",
        "where the integration tests live is part of the repository's layout",
    ),
    HarnessConfigRead(
        "ticketing.github",
        "check, graph, and the daemon via graphlink",
        "the repository the ticket was created in is what makes `pr-loops/pr-<n>/` "
        "attributable to a repository once a work item spans several of them "
        "(issue-183); a daemon watching N repos cannot know it for each of them",
    ),
    HarnessConfigRead(
        "customInstructions",
        "instructions",
        "which conventions govern work on this repository is a fact about this "
        "repository, and the agent reads the same entries — a check resolving a "
        "different list from the one the loop honours would verify nothing",
    ),
)


def spec_dir(harness: Mapping[str, Any]) -> str:
    """``workflow.specDir`` from an already-loaded harness config, else the default.

    Takes the loaded mapping rather than a root so a caller that has read the file for
    something else — ``build_runtime`` reads ``phaseLabelPrefix`` and ``notifications``
    from the same load — does not read it twice.

    An empty or null value reads as "unset". A repository that writes ``specDir: ""`` has
    not chosen the repository root; it has chosen nothing, and the default is the honest
    answer.
    """
    workflow = harness.get("workflow") or {}
    if not isinstance(workflow, dict):
        return DEFAULT_SPEC_DIR
    return str(workflow.get("specDir") or DEFAULT_SPEC_DIR)


def origin_repo(harness: Mapping[str, Any]) -> str:
    """``<owner>/<repo>`` from ``ticketing.github``, or ``""`` (issue-183).

    The **origin repository**: the one the ticket was created in, where the outer
    loop runs and the spec chain lives. Empty when the project is not
    GitHub-ticketed or has not said — callers treat that as "unknown" and fail
    closed rather than guessing.
    """
    ticketing = harness.get("ticketing") or {}
    if not isinstance(ticketing, dict):
        return ""
    github = ticketing.get("github") or {}
    if not isinstance(github, dict):
        return ""
    owner = str(github.get("owner") or "").strip()
    repo = str(github.get("repo") or "").strip()
    return f"{owner}/{repo}" if owner and repo else ""


def config_path(root: Path) -> Optional[Path]:
    """The harness config under ``root``, honouring the pre-rename name (issue-82)."""
    for name in FILENAMES:
        candidate = root / ".the-loop" / name
        if candidate.is_file():
            return candidate
    return None


def initialized(root: Path) -> bool:
    """Whether ``root`` has adopted the-loop — i.e. carries a harness config.

    The contribution loop (issue-185) can be invited into a repository that never
    ran the-loop's setup. Every read still degrades to defaults (:func:`load`), but
    some behaviour is *about* the distinction rather than about any one key: a
    repository that never adopted the-loop must not have the-loop's spec tree
    committed into it, and its review surface is the work item's thread. Those
    callers ask this question, not "what does the config say".
    """
    return config_path(root) is not None


def default_config_path() -> Path:
    """Where the built-in default ships — package data beside this module.

    Resolved from ``__file__`` rather than from a checkout or an environment variable, so
    a wheel, an editable install and a repository checkout all answer identically. May
    not exist in an unusual install; every caller treats that as "no default" rather than
    as an error.
    """
    return Path(__file__).resolve().parent / DEFAULT_CONFIG_FILE


def defaults() -> Dict[str, Any]:
    """The built-in default harness config, or ``{}`` if it cannot be read.

    The named answer to "what does the-loop assume in a repository that never ran
    ``/the-loop:init``?" — previously a scatter of per-call-site literals, of which
    :data:`DEFAULT_SPEC_DIR` and ``build_runtime``'s ``"loop:"`` are the survivors (they
    remain, for the case where nothing can be written, and a test pins them to this file).

    Best-effort like every other read here: a packaging fault degrades to ``{}`` and the
    per-key fallbacks carry the run, because a missing data file must not cost a webhook
    delivery.
    """
    path = default_config_path()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 — any failure degrades to "no default"
        logger.warning("could not read the built-in harness config (%s): %s", path, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("the built-in harness config (%s) is not a mapping", path)
        return {}
    return data


def _named_for(text: str, owner: str, repo: str) -> str:
    """``text`` with ``ticketing.github``'s placeholders filled in, when it is safe to.

    Both values must pass :data:`_GH_NAME` or **neither** is written: a config naming an
    owner but no repository resolves to no origin repository anyway
    (:func:`origin_repo`), so a half-substitution would only make the file look more
    configured than it is.

    A line-anchored substitution rather than a ``yaml.safe_dump`` round trip, because the
    default's value to a human is its inline comments and a round trip destroys every one
    of them. Confined to the ``ticketing:`` block, so an ``owner:`` key elsewhere in the
    document cannot be reached.
    """
    if not (_GH_NAME.match(owner or "") and _GH_NAME.match(repo or "")):
        if owner or repo:
            logger.warning(
                "not naming %r/%r in the harness config: not a plain GitHub owner/repo",
                owner,
                repo,
            )
        return text
    values = {"owner": owner, "repo": repo}
    out, inside = [], False
    for line in text.splitlines(keepends=True):
        if _TOP_LEVEL_KEY.match(line):
            inside = line.startswith("ticketing:")
        elif inside:
            match = _PLACEHOLDER.match(line.rstrip("\n"))
            if match:
                line = (
                    f"{match['indent']}{match['key']}: "
                    f'"{values[match["key"]]}"{match["trail"]}\n'
                )
        out.append(line)
    return "".join(out)


def _inside(root: Path, path: Path) -> bool:
    """Whether ``path`` really lives under ``root``, symlinks resolved.

    :func:`scaffold` is the-loop's first writer into a **cloned** checkout, and a clone
    carries whatever the repository's contributors committed — including a `.the-loop`
    that is a *symlink* to somewhere else on the operator's disk. ``mkdir(exist_ok=True)``
    followed by a write would happily follow it, so the-loop would plant a file at a path
    the repository chose. The write target is a constant, but the directory it names is
    not: only ``resolve()`` can tell the difference.

    The mirror of ``graphlink._is_contained``, which guards the same class of escape for
    the spec directory, and it **fails closed** for the same reason: a path that cannot be
    resolved has not been shown to be contained.
    """
    try:
        resolved = path.resolve()
        base = root.resolve()
    except OSError:
        return False
    return base in resolved.parents


def scaffold(root: Path, owner: str = "", repo: str = "") -> str:
    """Adopt ``root`` with the built-in default. Returns what happened; never raises.

    ``"written"`` — the file was created · ``"present"`` — a harness config of either
    name was already there · ``""`` — nothing could be written.

    the-loop is routinely pointed at a repository that never ran ``/the-loop:init``: the
    daemon clones it, spawns a session in it, and the session finds no ``.the-loop/`` at
    all — so the skill has no workflow, no tooling and no phases to work from (issue-193).
    This is the one function that fixes that by putting the default *on disk*, where the
    agent, the CLI and the next run all read the same file instead of each inventing an
    answer.

    **It never opens an existing config.** An operator's ``autonomy`` tiers,
    ``sensitivePaths`` and ``reviews.critics[]`` (executable config) are policy no inbound
    event may replace, so a repository that has already configured itself — under either
    filename — is left exactly as it is.

    ``owner``/``repo`` name the repository in ``ticketing.github`` so ``originRepo``
    resolves rather than failing closed (issue-183). They are the only payload-derived
    text that reaches the written bytes and are allow-listed by :func:`_named_for`.

    The **caller** decides whether adopting is appropriate at all: a contribution
    (``pdlc-contribution-loop``) must not adopt the repository it was invited into, and
    the daemon must have proved the checkout belongs to the work item first
    (decision-044). Both are conditions about the *work item*, which this function cannot
    see.
    """
    if config_path(root) is not None:
        return "present"
    source = default_config_path()
    try:
        body = source.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("cannot adopt %s: no built-in harness config (%s)", root, exc)
        return ""
    target = root / ".the-loop" / FILENAMES[0]
    if not _inside(root, target.parent):
        logger.warning(
            "not adopting %s: its .the-loop resolves outside the checkout", root
        )
        return ""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_with_header(_named_for(body, owner, repo)), encoding="utf-8")
    except OSError as exc:
        logger.warning("could not write %s: %s", target, exc)
        return ""
    logger.info(
        "%s had no harness config; adopted it with the-loop's built-in defaults (%s)",
        root,
        target,
    )
    return "written"


def load(root: Path) -> Dict[str, Any]:
    """The harness config for ``root``, or ``{}`` — never fatal.

    Absent, unparseable and "not a mapping" are all the same answer, because every
    best-effort caller has its own defaults and none of them can act on the difference.
    """
    path = config_path(root)
    if path is None:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — any parse failure degrades to defaults
        logger.warning("could not parse %s; using built-in defaults", path)
        return {}
    return data if isinstance(data, dict) else {}


def load_strict(root: Path) -> Dict[str, Any]:
    """The harness config for ``root``, raising rather than degrading.

    An **absent** file is still ``{}``: a repository that configured nothing configured
    nothing, and saying so is not an error. A file that exists and cannot be read is —
    it means the operator wrote something the CLI is about to ignore.
    """
    path = config_path(root)
    if path is None:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 — any parse failure is the same to us
        raise HarnessConfigError(f"could not parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HarnessConfigError(f"{path} does not contain a YAML mapping")
    return data
