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

P5 (issue-167) is the same three questions asked of ``validates:`` — the artifacts a node
*asserts against* without authoring, which is how the six review-chain nodes gate their
sections of the shared ``execution-log.md``. It also asks the question whose absence let
issue-167 through in the first place: **a gate that declares content checks must resolve
something to check them against.** Six nodes declared ``sections:`` and no artifact at
all, so their ``validate-artifacts`` returned *skipped* on every run — including
``security-review``, which the graph itself calls "never skippable, at any risk tier".

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


def _loops():
    """Both shipped loops (issue-172): the P5 assertions hold of each.

    The inner loop's review nodes gate the same shared execution log through the
    same ``validates:`` vocabulary, so an authoring slip there would be the same
    issue-167 defect one graph over.
    """
    from the_loop.graph.model import PDLC_PR_LOOP

    return [load_graph(shipped_graph_path()), load_graph(name=PDLC_PR_LOOP)]


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


#: The ``with:`` params that make ``validate-artifacts`` an assertion rather than a
#: no-op. Mirrors ``hooks.artifacts._CHECKS`` — a gate declaring any of them needs an
#: artifact to apply it to.
_CHECKS = ("locked", "frontMatter", "sections", "checkmarks")


def _validate_entries(node) -> List[Mapping[str, Any]]:
    """Every ``validate-artifacts`` entry in a node's chains, as raw specs."""
    return [
        spec
        for boundary in (node.entry, node.exit)
        for spec in boundary
        if isinstance(spec, Mapping) and spec.get("hook") == "validate-artifacts"
    ]


def _sections(spec: Mapping[str, Any]) -> Set[str]:
    return {str(s) for s in (spec.get("with") or {}).get("sections") or []}


def _required_sections(node) -> Set[str]:
    """The sections a node demands **of its own ``produces``**.

    An entry carrying ``validates:`` is asking them of a *different* file, so its
    sections belong to that artifact's template, not to this node's — P5 checks those.
    """
    return {
        section
        for spec in _validate_entries(node)
        if not (spec.get("with") or {}).get("validates")
        for section in _sections(spec)
    }


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


def _validated() -> Dict[str, List[Tuple[Any, Set[str]]]]:
    """Artifact name → ``(node, demanded sections)`` for every ``validates:`` target."""
    out: Dict[str, List[Tuple[Any, Set[str]]]] = {}
    for graph in _loops():
        for node in graph.ordered():
            for spec in _validate_entries(node):
                target = (spec.get("with") or {}).get("validates")
                if not target:
                    continue
                for name in artifact_names(target):
                    out.setdefault(name, []).append((node, _sections(spec)))
    return out


def _declared_checks(spec: Mapping[str, Any]) -> Set[str]:
    """Which content checks an entry declares — what makes it an assertion."""
    return {check for check in _CHECKS if (spec.get("with") or {}).get(check)}


def test_p5a_every_content_gate_resolves_an_artifact_to_read() -> None:
    """The assertion whose absence let issue-167 through.

    Six nodes declared ``sections:`` and no artifact — so ``validate-artifacts``
    returned *skipped* on every run, and since a skip is not a decision the chain
    passed straight through them. One of them is ``security-review``, which the graph
    itself annotates "never skippable, at any risk tier".
    """
    inert = [
        f"{graph.name or 'graph'}:{node.id} "
        f"(gates on {sorted(_sections(spec)) or sorted(_declared_checks(spec))})"
        for graph in _loops()
        for node in graph.ordered()
        for spec in _validate_entries(node)
        if _declared_checks(spec)
        and not node.produces
        and not (spec.get("with") or {}).get("validates")
    ]
    assert not inert, (
        "these nodes gate on artifact content but name no artifact to read it from, so "
        "their validate-artifacts skips and the gate reports success without ever "
        "running — declare `produces:` on the node or `validates:` on the hook entry: "
        + "; ".join(sorted(inert))
    )


def test_p5b_every_validated_artifact_is_tracked_by_the_manifest() -> None:
    """P2's question, asked of the artifacts a node asserts against.

    Phase-insensitive on purpose: a validated artifact is *shared* — ``execution-log.md``
    is gated by six nodes and authored by none — which is exactly why the manifest tracks
    it without a ``phase`` and why P1/P2 exclude it. Tracked at all is the requirement.
    """
    tracked = {
        match.group("name")
        for entry in _work_item_artifacts()
        if (match := _SPEC_FILE.match(str(entry.get("pathPattern") or "")))
    }
    untracked = sorted(set(_validated()) - tracked)
    assert not untracked, (
        "the graph validates artifacts that .the-loop/manifest.yaml does not track: "
        + ", ".join(untracked)
    )


def test_p5c_every_validated_section_exists_in_that_artifacts_template() -> None:
    """P3's question, asked of the artifacts a node asserts against.

    This is the latent half of issue-167: ``capability-docs`` gates a ``Capability docs``
    section that ``templates/execution-log.md`` did not offer. Invisible while the node
    skipped — and a block for *every* work item the moment it stopped.
    """
    problems: List[str] = []
    for name, gates in sorted(_validated().items()):
        template = TEMPLATES / name
        if not template.is_file():
            problems.append(
                f"{name}: the graph validates it, but no template authors it"
            )
            continue
        headings = set(
            sections(split_front_matter(template.read_text(encoding="utf-8"))[1])
        )
        for node, wanted in gates:
            for section in sorted(wanted - headings):
                problems.append(
                    f"{name}: node {node.id!r} requires a {section!r} section the "
                    "template does not offer"
                )
    assert not problems, (
        "a node gates a section of a shared artifact that the bundled template does not "
        "offer, so every work item authored from the template blocks there: "
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
        # The CLI's built-in default (issue-193): the config a repository that never ran
        # `/the-loop:init` is worked under. A phase list the graph does not walk would be
        # a process the-loop invents for exactly the repositories least able to notice.
        REPO_ROOT / "cli" / "the_loop" / "harness-config.default.yaml",
    ],
    ids=["own-config", "template-config", "packaged-default"],
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
