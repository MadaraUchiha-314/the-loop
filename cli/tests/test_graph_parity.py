"""Graph ↔ manifest ↔ template parity (issue-124).

Three files have to agree about what a work item's artifacts are called, and until
this test nothing compared them:

==================================  ==============================================
``cli/the_loop/graph/pdlc.yaml``    which names **gate**, and the sections they carry
``.the-loop/manifest.yaml``         which names the-loop **tracks**, and at which phase
``skills/the-loop/templates/``      which names an agent actually **authors** from
==================================  ==============================================

Issue-124 is what the gap let through. The skill, the reference, the manifest and a
bundled template all blessed ``bugfix.md`` as the phase-1 artifact for a bug; the
shipped graph's ``requirements-definition`` node produced ``requirements.md`` and
nothing else. Every bug work item therefore blocked at phase 1 for the absence of a
file the documentation told it not to write — and the template it *was* told to write
from had no ``## Requirements`` heading either, so fixing only the filename would have
moved the block one line down.

Three assertions, both directions on names plus the per-node sections:

==  =======================================================  ==========================
P1  every tracked artifact is accepted by its phase's node   the graph forgot a name
P2  every gated name is tracked by the manifest              the graph gates an untracked file
P3  every gated name has a template that can satisfy it      the template cannot pass its own gate
==  =======================================================  ==========================

The exclusions in P1 are data-driven, not an allow-list: an entry with no ``phase``
(``execution-log.md``) is outside the node-artifact contract because the manifest itself
says so, and a ``pathPattern`` ending in ``/`` is a directory of design artifacts, not a
gated file.

Pure filesystem reads through the compiled graph — no network, no subprocess — so this
exercises the same contract the runtime does. Skipped when the plugin tree is absent, as
``test_docs_parity.py`` is, so a source distribution shipping ``cli/`` alone still passes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Set, Tuple

import pytest
import yaml

from the_loop.graph.frontmatter import sections, split_front_matter
from the_loop.graph.model import artifact_names, load_graph, shipped_graph_path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / ".the-loop" / "manifest.yaml"
TEMPLATES = REPO_ROOT / "skills" / "the-loop" / "templates"

pytestmark = pytest.mark.skipif(
    not MANIFEST.is_file() or not TEMPLATES.is_dir(),
    reason="plugin tree not present (source distribution)",
)

#: ``docs/specs/<id>/requirements.md`` → ``requirements.md``. A pattern ending in ``/``
#: is a directory (the design-artifacts folder) and never matches.
_SPEC_FILE = re.compile(r"^docs/specs/<id>/(?P<name>[^/]+\.[^/]+)$")


def _graph():
    return load_graph(shipped_graph_path())


def _accepted(node) -> Set[str]:
    """Every artifact name a node's ``produces`` accepts."""
    return {name for entry in node.produces for name in artifact_names(entry)}


def _work_item_artifacts() -> List[Mapping[str, Any]]:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}
    return [e for e in (data.get("workItemArtifacts") or []) if isinstance(e, Mapping)]


def _tracked() -> List[Tuple[str, str]]:
    """``(name, phase)`` for every manifest artifact inside the node contract."""
    out: List[Tuple[str, str]] = []
    for entry in _work_item_artifacts():
        phase = str(entry.get("phase") or "").strip()
        match = _SPEC_FILE.match(str(entry.get("pathPattern") or ""))
        if phase and match:
            out.append((match.group("name"), phase))
    return out


def _required_sections(node) -> Set[str]:
    """The sections a node's ``validate-artifacts`` exit hook demands."""
    wanted: Set[str] = set()
    for spec in node.exit:
        if isinstance(spec, Mapping) and spec.get("hook") == "validate-artifacts":
            wanted.update(
                str(s) for s in (spec.get("with") or {}).get("sections") or []
            )
    return wanted


def _front_matter_phase(text: str) -> str:
    """The ``phase:`` of a template's front matter, comments stripped."""
    if not text.startswith("---"):
        return ""
    _, _, rest = text.partition("---")
    body, _, _ = rest.partition("\n---")
    for line in body.split("\n"):
        key, sep, value = line.partition(":")
        if sep and key.strip() == "phase":
            return value.split("#")[0].strip()
    return ""


def _producers() -> Dict[str, List[Any]]:
    """Artifact name → every node that produces it."""
    out: Dict[str, List[Any]] = {}
    for node in _graph().ordered():
        for name in _accepted(node):
            out.setdefault(name, []).append(node)
    return out


def test_p1_every_tracked_artifact_is_accepted_by_its_phase_node() -> None:
    """The manifest tracks it at a phase; that phase's node must accept the name.

    This is the assertion issue-124 needed: ``.the-loop/manifest.yaml`` has tracked
    ``docs/specs/<id>/bugfix.md`` at ``requirements-definition`` since before the graph
    existed, and the graph's node for that phase accepted only ``requirements.md``.
    """
    by_phase: Dict[str, Set[str]] = {}
    for node in _graph().ordered():
        if node.phase and node.produces:
            by_phase.setdefault(node.phase, set()).update(_accepted(node))

    unmet = [
        f"{name} (manifest phase {phase!r}; that phase's node(s) accept "
        f"{sorted(by_phase.get(phase, set())) or 'nothing'})"
        for name, phase in _tracked()
        if name not in by_phase.get(phase, set())
    ]
    assert not unmet, (
        "the manifest tracks work-item artifacts the shipped graph will not accept, so a "
        "work item that follows the documented shape cannot clear its own gate: "
        + "; ".join(sorted(unmet))
    )


def test_p2_every_gated_name_is_tracked_by_the_manifest() -> None:
    """The reverse: nothing gates a file the project inventory does not know about."""
    tracked = {name for name, _ in _tracked()}
    untracked = sorted(set(_producers()) - tracked)
    assert not untracked, (
        "the graph gates artifacts that .the-loop/manifest.yaml does not track, so "
        "/the-loop:init and /the-loop:upgrade-the-loop do not know they exist: "
        + ", ".join(untracked)
    )


def test_p3_every_gated_name_has_a_template_that_can_satisfy_it() -> None:
    """An agent authors from the bundled template; the template must be able to pass.

    Names, and sections. Issue-124's second half was ``templates/bugfix.md`` offering
    ``## Acceptance criteria (EARS)`` where ``requirements-definition`` requires a
    ``Requirements`` heading — so even once the filename was accepted, a spec authored
    from the shipped template blocked on a missing section.
    """
    problems: List[str] = []
    for name, nodes in sorted(_producers().items()):
        template = TEMPLATES / name
        if not template.is_file():
            problems.append(f"{name}: the graph gates it, but no template authors it")
            continue

        text = template.read_text(encoding="utf-8")

        phases = {node.phase for node in nodes if node.phase}
        declared = _front_matter_phase(text)
        if phases and declared not in phases:
            problems.append(
                f"{name}: template declares phase {declared or '(none)'!r}, but it is "
                f"produced at {sorted(phases)}"
            )

        # The gate's own parser, not a regex of our own: `validate-artifacts`
        # resolves sections through `frontmatter.sections`, which ignores headings
        # inside fences. A looser reader here could call a template compliant on
        # the strength of a heading in an example block — parity with the gate
        # means parity with how the gate actually reads.
        headings = set(sections(split_front_matter(text)[1]))
        for node in nodes:
            for section in sorted(_required_sections(node)):
                if section not in headings:
                    problems.append(
                        f"{name}: node {node.id!r} requires a {section!r} section the "
                        "template does not offer"
                    )

    assert not problems, (
        "a bundled template cannot satisfy the gate it is authored for: "
        + "; ".join(problems)
    )


def _config_phases(path: Path) -> List[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [str(p) for p in (data.get("workflow") or {}).get("phases") or []]


@pytest.mark.parametrize(
    "config_path",
    [
        REPO_ROOT / ".the-loop" / "harness-config.yaml",
        REPO_ROOT / "skills" / "the-loop" / "templates" / "harness-config.yaml",
    ],
    ids=["own-config", "template-config"],
)
def test_p4_the_graph_defines_the_phase_sequence(config_path: Path) -> None:
    """P4 (issue-148, R6.2) — one source of truth for the process.

    The graph's ordered ``phase:`` values must appear, in the same order,
    within ``workflow.phases`` — and the complement is pinned: the only phase
    a config may declare that no node carries is ``not-started``, the
    pre-graph state. Anything else is the prose and the graph drifting into
    two processes, which is the defect issue-148 exists to close.
    """
    if not config_path.is_file():
        pytest.skip(f"{config_path} not shipped in this distribution")
    graph = load_graph(repo=REPO_ROOT)
    graph_phases: List[str] = []
    for node in graph.ordered():
        if node.phase and node.phase not in graph_phases:
            graph_phases.append(node.phase)
    config_phases = _config_phases(config_path)

    positions = []
    for phase in graph_phases:
        assert phase in config_phases, (
            f"the graph carries phase {phase!r} that {config_path.name} does not "
            "declare in workflow.phases"
        )
        positions.append(config_phases.index(phase))
    assert positions == sorted(positions), (
        f"{config_path.name} orders workflow.phases differently from the graph: "
        f"graph {graph_phases} vs config {config_phases}"
    )

    extras = set(config_phases) - set(graph_phases)
    assert extras <= {"not-started"}, (
        "workflow.phases declares phases no graph node carries (only "
        f"'not-started' may be): {sorted(extras)}"
    )
