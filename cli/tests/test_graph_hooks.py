"""The shipped validating hooks (issue-109, R5)."""

from __future__ import annotations

from pathlib import Path


from the_loop.graph.contract import BLOCK, PASS, SKIP, HookContext, WorkItem
from the_loop.graph.frontmatter import mermaid_blocks, sections, split_front_matter
from the_loop.graph.hooks.artifacts import enforces_boundaries_from, validate_artifacts
from the_loop.graph.hooks.lint import lint_artifacts

#: The phase-1 entry as the shipped graph declares it (issue-124).
PHASE_1 = "requirements.md|bugfix.md"


def _ctx(tmp_path: Path, produces, params=None, node=None):
    spec = tmp_path / "docs" / "specs" / "issue-1"
    spec.mkdir(parents=True, exist_ok=True)
    ctx = HookContext(
        work_item=WorkItem(ref="github:o/r#1", id="issue-1", spec_dir=spec),
        node={"id": "design", "produces": produces, **(node or {})},
        boundary="exit",
        repo=tmp_path,
    )
    ctx.params = params or {}
    return ctx, spec


# -- front-matter / section parsing -------------------------------------------


def test_a_section_owns_its_subsections():
    """A heading followed straight by sub-headings is not empty."""
    found = sections("## Requirements\n\n### Requirement 1\n\nbody\n")
    assert found["Requirements"].strip() != ""


def test_headings_inside_fences_are_not_sections():
    text = "## Real\n\nbody\n\n```markdown\n## Fake\n```\n"
    assert "Real" in sections(text)
    assert "Fake" not in sections(text)


def test_unterminated_front_matter_yields_no_metadata():
    front, _ = split_front_matter("---\nstatus: approved\nno terminator\n")
    assert front == {}


def test_mermaid_blocks_are_extracted_in_order():
    text = "```mermaid\nflowchart LR\n```\ntext\n```mermaid\ngraph TD\n```\n"
    assert [b.strip().split("\n")[0] for b in mermaid_blocks(text)] == [
        "flowchart LR",
        "graph TD",
    ]


# -- validate-artifacts --------------------------------------------------------


def test_missing_artifact_blocks(tmp_path):
    ctx, _ = _ctx(tmp_path, ["design.md"])
    result = validate_artifacts(ctx)
    assert result.status == BLOCK
    assert "missing" in result.messages[0].text


def test_unlocked_artifact_blocks_and_names_the_status(tmp_path):
    ctx, spec = _ctx(tmp_path, ["design.md"], {"locked": True})
    (spec / "design.md").write_text("---\nstatus: draft\n---\n\n# D\n")
    result = validate_artifacts(ctx)
    assert result.status == BLOCK
    assert "status: draft" in result.messages[0].text


def test_every_unmet_requirement_arrives_in_one_result(tmp_path):
    """R3.5 — the agent gets the whole list in a single round."""
    ctx, spec = _ctx(
        tmp_path,
        ["design.md"],
        {"locked": True, "sections": ["Architecture", "Security design"]},
    )
    (spec / "design.md").write_text("---\nstatus: draft\n---\n\n# D\n")
    result = validate_artifacts(ctx)
    assert result.status == BLOCK
    texts = " | ".join(m.text for m in result.messages)
    assert "status: draft" in texts
    assert "Architecture" in texts
    assert "Security design" in texts
    assert len(result.messages) == 3, "one result, three findings — not three rounds"


def test_an_empty_required_section_blocks(tmp_path):
    ctx, spec = _ctx(tmp_path, ["design.md"], {"sections": ["Security design"]})
    (spec / "design.md").write_text("# D\n\n## Security design\n\n## Next\n\nbody\n")
    result = validate_artifacts(ctx)
    assert result.status == BLOCK
    assert "empty" in result.messages[0].text


def test_unticked_tasks_block(tmp_path):
    ctx, spec = _ctx(tmp_path, ["tasks.md"], {"checkmarks": "complete"})
    (spec / "tasks.md").write_text("# T\n\n- [x] one\n- [ ] two\n- [ ] three\n")
    result = validate_artifacts(ctx)
    assert result.status == BLOCK
    assert "2 task(s) still unticked" in result.messages[0].text


def test_a_satisfied_artifact_passes(tmp_path):
    ctx, spec = _ctx(
        tmp_path, ["design.md"], {"locked": True, "sections": ["Architecture"]}
    )
    (spec / "design.md").write_text(
        "---\nstatus: approved\n---\n\n# D\n\n## Architecture\n\nreal content\n"
    )
    assert validate_artifacts(ctx).status == PASS


def test_a_node_with_no_artifacts_is_skipped(tmp_path):
    ctx, _ = _ctx(tmp_path, [])
    assert validate_artifacts(ctx).status == SKIP


# -- lint-artifacts ------------------------------------------------------------


def test_a_backticked_mermaid_label_blocks(tmp_path):
    """The exact defect a reviewer caught on PR #110."""
    ctx, spec = _ctx(tmp_path, ["design.md"])
    (spec / "design.md").write_text(
        '# D\n\n```mermaid\nflowchart LR\n  A["`the-loop check` — pure"]\n```\n'
    )
    result = lint_artifacts(ctx)
    assert result.status == BLOCK
    assert "backtick" in result.messages[0].text


def test_a_mermaid_block_without_a_diagram_type_blocks(tmp_path):
    ctx, spec = _ctx(tmp_path, ["design.md"])
    (spec / "design.md").write_text("# D\n\n```mermaid\nA --> B\n```\n")
    result = lint_artifacts(ctx)
    assert result.status == BLOCK
    assert "diagram type" in result.messages[0].text


def test_valid_mermaid_passes(tmp_path):
    ctx, spec = _ctx(tmp_path, ["design.md"])
    (spec / "design.md").write_text(
        '# D\n\n```mermaid\nflowchart LR\n  A["plain label"] --> B\n```\n'
    )
    assert lint_artifacts(ctx).status == PASS


def test_an_optional_node_with_no_artifact_is_skipped_not_blocked(tmp_path):
    """A work item that never brainstormed did not fail the brainstorm gate."""
    ctx, _ = _ctx(
        tmp_path, ["brainstorm.md"], {"locked": True}, node={"optional": True}
    )
    assert validate_artifacts(ctx).status == SKIP


def test_an_optional_node_that_produced_an_artifact_is_still_gated(tmp_path):
    """Once it exists, every gate applies normally."""
    ctx, spec = _ctx(
        tmp_path, ["brainstorm.md"], {"locked": True}, node={"optional": True}
    )
    (spec / "brainstorm.md").write_text("---\nstatus: draft\n---\n\n# B\n")
    assert validate_artifacts(ctx).status == BLOCK


# -- one artifact, several accepted names (issue-124) ---------------------------
#
# the-loop has documented `bugfix.md` as a bug's phase-1 artifact since long
# before the graph existed, in the skill, the workflow reference, the manifest
# and a bundled template. The graph accepted only `requirements.md`, so an agent
# that followed the documented process was blocked by that same process for not
# having written a file it was told not to write.

_APPROVED_BUGFIX = (
    "---\nstatus: approved\n---\n\n# B\n\n## Requirements\n\nreal\n\n"
    "## Security considerations\n\nreal\n"
)

_PHASE_1_PARAMS = {
    "locked": True,
    "sections": ["Requirements", "Security considerations"],
}


def test_a_bugfix_spec_satisfies_the_phase_one_gate(tmp_path):
    """The headline defect of issue-124, inverted."""
    ctx, spec = _ctx(tmp_path, [PHASE_1], _PHASE_1_PARAMS)
    (spec / "bugfix.md").write_text(_APPROVED_BUGFIX)
    assert validate_artifacts(ctx).status == PASS


def test_a_requirements_spec_still_satisfies_the_phase_one_gate(tmp_path):
    """The common path is untouched — alternation is an addition, not a swap."""
    ctx, spec = _ctx(tmp_path, [PHASE_1], _PHASE_1_PARAMS)
    (spec / "requirements.md").write_text(_APPROVED_BUGFIX)
    assert validate_artifacts(ctx).status == PASS


def test_an_alternative_is_held_to_the_same_standard(tmp_path):
    """The name became flexible; the standard did not move."""
    ctx, spec = _ctx(tmp_path, [PHASE_1], _PHASE_1_PARAMS)
    (spec / "bugfix.md").write_text("---\nstatus: draft\n---\n\n# B\n")
    result = validate_artifacts(ctx)
    assert result.status == BLOCK
    texts = " | ".join(m.text for m in result.messages)
    assert "status: draft" in texts
    assert "Requirements" in texts
    assert "Security considerations" in texts


def test_neither_name_present_blocks_and_lists_every_accepted_name(tmp_path):
    """An agent cannot write the right file if the block does not name it."""
    ctx, _ = _ctx(tmp_path, [PHASE_1])
    result = validate_artifacts(ctx)
    assert result.status == BLOCK
    assert len(result.messages) == 1
    text = result.messages[0].text
    assert "requirements.md" in text and "bugfix.md" in text


def test_both_names_present_blocks_as_ambiguous(tmp_path):
    """Fail closed. Two phase-1 artifacts have no defined source of truth, and a
    resolver that quietly preferred the first-declared name would approve a gate
    against whichever file the graph happened to list first."""
    ctx, spec = _ctx(tmp_path, [PHASE_1], _PHASE_1_PARAMS)
    (spec / "requirements.md").write_text(_APPROVED_BUGFIX)
    (spec / "bugfix.md").write_text(_APPROVED_BUGFIX)
    result = validate_artifacts(ctx)
    assert result.status == BLOCK
    assert "keep one" in result.messages[0].text


def test_a_single_name_node_reports_missing_exactly_as_before(tmp_path):
    """R1.3 — no alternation, no change. Pinned because this string is what an
    agent reads, and half the value of the gate is that the message is stable."""
    ctx, _ = _ctx(tmp_path, ["design.md"])
    message = validate_artifacts(ctx).messages[0]
    assert message.text == "required artifact is missing"
    assert message.path.endswith("docs/specs/issue-1/design.md")


def test_an_optional_node_with_alternatives_and_nothing_on_disk_is_skipped(tmp_path):
    ctx, _ = _ctx(tmp_path, [PHASE_1], {"locked": True}, node={"optional": True})
    assert validate_artifacts(ctx).status == SKIP


def test_lint_reaches_an_artifact_named_by_its_alternative(tmp_path):
    """The second hook that reads `produces`. It had its own private copy of the
    resolver, so the same defect lived here too — silently, since a file it never
    resolved is a file it never lints."""
    ctx, spec = _ctx(tmp_path, [PHASE_1])
    (spec / "bugfix.md").write_text("# B\n\n```mermaid\nA --> B\n```\n")
    result = lint_artifacts(ctx)
    assert result.status == BLOCK
    assert "diagram type" in result.messages[0].text


# -- enforces-boundaries-from --------------------------------------------------
#
# RC2 of issue-124, and the sharper half: the `design` node named its upstream
# `requirements.md`, so for a bug the hook took its "upstream absent" branch and
# returned SKIP. A skip passes the chain — meaning the check that every trust
# boundary raised in phase 1 is answered in the design has never once run for a
# bugfix work item, while reporting success. This hook had no tests at all.

_BOUNDARY_MARKERS = {"markers": ["trust boundary", "abuse case"]}


def _boundary_ctx(tmp_path, upstream, params=None):
    ctx, spec = _ctx(
        tmp_path,
        ["design.md"],
        {**_BOUNDARY_MARKERS, "upstream": upstream, **(params or {})},
    )
    return ctx, spec


def test_a_boundary_named_in_a_bugfix_is_enforced_in_the_design(tmp_path):
    ctx, spec = _boundary_ctx(tmp_path, PHASE_1)
    (spec / "bugfix.md").write_text("# B\n\nA trust boundary here.\n")
    (spec / "design.md").write_text("# D\n\nThe trust boundary is enforced.\n")
    assert enforces_boundaries_from(ctx).status == PASS


def test_a_boundary_a_bugfix_raises_and_the_design_drops_blocks(tmp_path):
    """Before issue-124 this returned SKIP — a silent pass on a security gate."""
    ctx, spec = _boundary_ctx(tmp_path, PHASE_1)
    (spec / "bugfix.md").write_text("# B\n\nA trust boundary, and an abuse case.\n")
    (spec / "design.md").write_text("# D\n\nOnly the trust boundary is answered.\n")
    result = enforces_boundaries_from(ctx)
    assert result.status == BLOCK
    assert "abuse case" in result.messages[0].text


def test_a_requirements_upstream_still_blocks_on_a_dropped_boundary(tmp_path):
    ctx, spec = _boundary_ctx(tmp_path, PHASE_1)
    (spec / "requirements.md").write_text("# R\n\nAn abuse case.\n")
    (spec / "design.md").write_text("# D\n\nNothing relevant.\n")
    assert enforces_boundaries_from(ctx).status == BLOCK


def test_a_genuinely_absent_upstream_is_still_skipped(tmp_path):
    """The skip branch is correct when there really is no upstream — it is only
    the *unreachable name* that made it fire wrongly."""
    ctx, spec = _boundary_ctx(tmp_path, PHASE_1)
    (spec / "design.md").write_text("# D\n\nNothing.\n")
    assert enforces_boundaries_from(ctx).status == SKIP


def test_a_declared_but_missing_downstream_still_blocks(tmp_path):
    """A downstream that does not exist answers nothing, so every upstream marker
    is unanswered. Pinned because resolving `produces` through `present` files
    alone would have quietly turned this block into a skip."""
    ctx, spec = _boundary_ctx(tmp_path, PHASE_1)
    (spec / "bugfix.md").write_text("# B\n\nA trust boundary.\n")
    assert enforces_boundaries_from(ctx).status == BLOCK
