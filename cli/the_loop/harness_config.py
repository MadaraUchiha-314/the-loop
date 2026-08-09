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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import yaml

logger = logging.getLogger("the-loop.harness-config")

__all__ = [
    "DEFAULT_OUTER_LOOP_SURFACE",
    "DEFAULT_SPEC_DIR",
    "FILENAMES",
    "HarnessConfigError",
    "HarnessConfigRead",
    "OUTER_LOOP_SURFACES",
    "READS",
    "config_path",
    "load",
    "load_strict",
    "origin_repo",
    "outer_loop_surface",
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

#: Where a project iterates the OUTER loop's artifacts (issue-183). ``issue`` is
#: the ticket, Jira-style; ``pull-request`` is a pull request in the origin
#: repository, which is what every repository did before the key existed — hence
#: the default. The INNER loop has no surface: a pull request's loop runs on that
#: pull request, and no configuration moves it.
OUTER_LOOP_SURFACES: Tuple[str, ...] = ("issue", "pull-request")
DEFAULT_OUTER_LOOP_SURFACE = "pull-request"


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
        "workflow.outerLoop.surface",
        "graph, and the daemon via graphlink",
        "where a project iterates its outer-loop artifacts — the ticket or a pull "
        "request in the origin repository — is a property of that project's process, "
        "and the CLI renders it into what a session is told to do",
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


def outer_loop_surface(harness: Mapping[str, Any]) -> str:
    """``workflow.outerLoop.surface`` — ``issue`` or ``pull-request`` (issue-183).

    Anything else resolves to :data:`DEFAULT_OUTER_LOOP_SURFACE`: absent (the
    only case that is not a mistake), a non-mapping ``outerLoop``, a non-string
    value, or a string outside the two the schema accepts. Resolving rather than
    raising is the same rule :func:`load` follows — ``the-loop check`` must still
    report a phase in a repository whose config someone is halfway through
    editing — and the fallback is the *more* review-bearing of the two options.
    """
    workflow = harness.get("workflow") or {}
    if not isinstance(workflow, dict):
        return DEFAULT_OUTER_LOOP_SURFACE
    outer = workflow.get("outerLoop") or {}
    if not isinstance(outer, dict):
        return DEFAULT_OUTER_LOOP_SURFACE
    surface = outer.get("surface")
    if isinstance(surface, str) and surface in OUTER_LOOP_SURFACES:
        return surface
    return DEFAULT_OUTER_LOOP_SURFACE


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
