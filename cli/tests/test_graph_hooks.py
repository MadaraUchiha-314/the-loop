"""The shipped validating hooks (issue-109, R5)."""

from __future__ import annotations

from pathlib import Path


from the_loop.graph.contract import BLOCK, PASS, SKIP, HookContext, WorkItem
from the_loop.graph.frontmatter import mermaid_blocks, sections, split_front_matter
from the_loop.graph.hooks.artifacts import validate_artifacts
from the_loop.graph.hooks.lint import lint_artifacts


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
