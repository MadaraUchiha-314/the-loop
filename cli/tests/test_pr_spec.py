"""Unit tests for PR-scoped specs (issue-543): testing-plan rows T1 and T8."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from the_loop.graph import prspec

REQUIREMENTS = """---
type: requirements
status: approved
---

# Requirements: demo

## Requirements

### Requirement 1 — First

#### Acceptance criteria (EARS)

1. WHEN a THEN b.
2. WHEN c THEN d
   continued.

### Requirement 2 — Second

#### Acceptance criteria (EARS)

1. WHEN e THEN f.
"""

DESIGN = """---
type: design
status: approved
---

# Design: demo

## Security design

Text.

## Testing strategy

```text
## Not a heading
```
"""

TESTING_PLAN = """---
type: testing-plan
status: approved
---

# Testing plan

## Test matrix

| # | Type | Applies? | Scope | Where |
|---|---|---|---|---|
| T1 | Unit | yes | x | y |
| T2 | E2E | n/a | none | |
"""

TASKS = """---
type: tasks
---

# Tasks

- [ ] 1. First
- [x] 2. Second
"""


def write_chain(spec_dir: Path, *, tasks: bool = True) -> Path:
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "requirements.md").write_text(REQUIREMENTS, encoding="utf-8")
    (spec_dir / "design.md").write_text(DESIGN, encoding="utf-8")
    (spec_dir / "testing-plan.md").write_text(TESTING_PLAN, encoding="utf-8")
    if tasks:
        (spec_dir / "tasks.md").write_text(TASKS, encoding="utf-8")
    return spec_dir


# -- task 1: digest and key/path ---------------------------------------------


def test_digest_is_sha256_and_stable(tmp_path):
    spec = write_chain(tmp_path / "s")
    digest = prspec.chain_digest(spec)
    assert digest.startswith("sha256:") and len(digest) == len("sha256:") + 64
    assert prspec.chain_digest(spec) == digest


def test_digest_ignores_front_matter(tmp_path):
    spec = write_chain(tmp_path / "s")
    before = prspec.chain_digest(spec)
    text = (spec / "design.md").read_text(encoding="utf-8")
    (spec / "design.md").write_text(
        text.replace("status: approved", "status: approved\napprovedBy: [x]"),
        encoding="utf-8",
    )
    assert prspec.chain_digest(spec) == before


def test_digest_changes_with_body(tmp_path):
    spec = write_chain(tmp_path / "s")
    before = prspec.chain_digest(spec)
    with (spec / "design.md").open("a", encoding="utf-8") as fh:
        fh.write("\nA new paragraph.\n")
    assert prspec.chain_digest(spec) != before


def test_digest_changes_when_tasks_appear(tmp_path):
    spec = write_chain(tmp_path / "s", tasks=False)
    before = prspec.chain_digest(spec)
    (spec / "tasks.md").write_text(TASKS, encoding="utf-8")
    assert prspec.chain_digest(spec) != before


def test_digest_accepts_bugfix_for_requirements(tmp_path):
    spec = write_chain(tmp_path / "s")
    before = prspec.chain_digest(spec)
    (spec / "requirements.md").rename(spec / "bugfix.md")
    assert prspec.chain_digest(spec) == before


def test_digest_changed_files_names_the_file(tmp_path):
    spec = write_chain(tmp_path / "s")
    parts = prspec.chain_parts(spec)
    with (spec / "design.md").open("a", encoding="utf-8") as fh:
        fh.write("\nchanged\n")
    assert prspec.changed_files(parts, prspec.chain_parts(spec)) == ["design.md"]


def test_key_in_origin_is_the_id():
    assert prspec.pr_spec_key("octo/origin", "octo/origin", "issue-15") == "issue-15"


def test_key_elsewhere_is_qualified_by_the_origin():
    assert (
        prspec.pr_spec_key("octo/origin", "octo/api", "issue-15")
        == "octo__origin__issue-15"
    )


def test_key_with_no_pr_repo_is_the_origin():
    assert prspec.pr_spec_key("octo/origin", "", "issue-15") == "issue-15"


def test_pr_spec_dir():
    assert prspec.pr_spec_dir("issue-15", 12) == "docs/specs/issue-15/pr-12"


@pytest.mark.parametrize(
    "origin,pr_repo,item_id",
    [
        ("octo/origin", "octo/..", "issue-15"),
        ("octo/origin", "octo/api", "../x"),
        ("octo/origin", "octo/api", ""),
        ("octo/origin", "octo/api", ".hidden"),
        ("octo/origin", "octo/api", "a/b"),
        ("../origin", "octo/api", "issue-15"),
        ("octo", "octo/api", "issue-15"),
    ],
)
def test_abuse_path_parts_refused(origin, pr_repo, item_id):
    with pytest.raises(ValueError):
        prspec.pr_spec_key(origin, pr_repo, item_id)


def test_pr_spec_dir_refuses_non_positive_number():
    with pytest.raises(ValueError):
        prspec.pr_spec_dir("issue-15", 0)


# -- task 2: citations -------------------------------------------------------


def test_citation_tokens_are_parsed():
    text = "Uses [wi:R2] and [wi:R1.2], [wi:design#security-design], [wi:TP-T1] [wi:task-2]."
    assert prspec.citation_tokens(text) == [
        "R2",
        "R1.2",
        "design#security-design",
        "TP-T1",
        "task-2",
    ]


def test_citation_index_resolves_all_five_forms(tmp_path):
    index = prspec.ChainIndex.load(write_chain(tmp_path / "s"))
    for token in (
        "R1",
        "R2",
        "R1.1",
        "R1.2",
        "R2.1",
        "design#security-design",
        "design#testing-strategy",
        "TP-T1",
        "TP-T2",
        "task-1",
        "task-2",
    ):
        assert index.resolves(token), token


def test_citation_unknown_targets_do_not_resolve(tmp_path):
    index = prspec.ChainIndex.load(write_chain(tmp_path / "s"))
    for token in (
        "R3",
        "R1.3",
        "R2.2",
        "design#not-a-heading",
        "design#nope",
        "TP-T9",
        "task-3",
        "garbage",
        "R",
    ):
        assert not index.resolves(token), token


def test_citation_unresolved_reports_file_and_line(tmp_path):
    index = prspec.ChainIndex.load(write_chain(tmp_path / "s"))
    files = {"design.md": "ok [wi:R1]\nbad [wi:R9]\n"}
    findings = prspec.unresolved_citations(files, index)
    assert [(f.file, f.line) for f in findings] == [("design.md", 2)]
    assert "R9" in findings[0].text


def test_citation_missing_requirement_entry():
    files = {
        "requirements.md": "# R\n\n### PR-R1 — cites [wi:R1]\n\ntext\n\n### PR-R2 — none\n\ntext\n",
    }
    findings = prspec.missing_citations(files)
    assert [(f.file, f.line) for f in findings] == [("requirements.md", 7)]


def test_citation_requirement_entry_may_cite_in_its_body():
    files = {"requirements.md": "### PR-R1 — title\n\nbody cites [wi:R1.1]\n"}
    assert prspec.missing_citations(files) == []


def test_citation_missing_task_line():
    files = {
        "tasks.md": "- [ ] 1. a [wi:task-1]\n- [ ] 2. b\n  - detail [wi:R1]\n- [x] 3. c\n"
    }
    findings = prspec.missing_citations(files)
    assert [(f.file, f.line) for f in findings] == [("tasks.md", 4)]


def test_citation_missing_in_scope_matrix_row_only():
    files = {
        "testing-plan.md": (
            "## Test matrix\n\n| # | Type | Applies? | Scope | Where |\n|---|---|---|---|---|\n"
            "| T1 | Unit | yes | x [wi:TP-T1] | y |\n"
            "| T2 | Unit | yes | x | y |\n"
            "| T3 | E2E | n/a | none | |\n"
        )
    }
    findings = prspec.missing_citations(files)
    assert [(f.file, f.line) for f in findings] == [("testing-plan.md", 6)]


def test_citation_ignored_inside_fences(tmp_path):
    index = prspec.ChainIndex.load(write_chain(tmp_path / "s"))
    files = {"design.md": "```\n[wi:R99]\n```\n"}
    assert prspec.unresolved_citations(files, index) == []


# -- task 3: applicability and the record -------------------------------------


def pr_row(repo, number, **extra):
    row = {"ref": f"github:{repo}#{number}", "repository": repo, "number": number}
    row.update(extra)
    return row


def test_applicability_no_prs_is_single():
    assert prspec.applicability([], [], "octo/origin") == "single-pr"


def test_applicability_one_origin_pr_is_single():
    rows = [pr_row("octo/origin", 2)]
    assert prspec.applicability(rows, [], "octo/origin") == "single-pr"


def test_applicability_two_origin_prs_is_multi():
    rows = [pr_row("octo/origin", 2), pr_row("octo/origin", 3)]
    assert prspec.applicability(rows, [], "octo/origin") == "multi-pr"


def test_applicability_one_foreign_pr_is_multi():
    rows = [pr_row("octo/api", 2)]
    assert prspec.applicability(rows, [], "octo/origin") == "multi-pr"


def test_applicability_declared_foreign_repo_is_multi():
    rows = [pr_row("octo/origin", 2)]
    assert prspec.applicability(rows, ["octo/api"], "octo/origin") == "multi-pr"


def test_applicability_declared_origin_only_is_single():
    rows = [pr_row("octo/origin", 2)]
    assert prspec.applicability(rows, ["octo/origin"], "octo/origin") == "single-pr"


def test_applicability_self_rows_do_not_count():
    rows = [pr_row("octo/origin", 2), pr_row("octo/origin", 3, self=True)]
    assert prspec.applicability(rows, [], "octo/origin") == "single-pr"


def test_applicability_closed_rows_do_not_count():
    rows = [pr_row("octo/origin", 2), pr_row("octo/origin", 3, state="closed")]
    assert prspec.applicability(rows, [], "octo/origin") == "single-pr"


def test_applicability_unknown_origin_counts_as_foreign():
    rows = [pr_row("octo/origin", 2)]
    assert prspec.applicability(rows, [], "") == "multi-pr"


def record_dict(**over):
    data = {
        "version": 1,
        "pullRequest": "github:octo/api#12",
        "required": True,
        "reason": "multi-pr",
        "path": "docs/specs/octo__origin__issue-15/pr-12",
        "headSha": "a" * 40,
        "sourceRevision": "b" * 40,
        "chainDigest": "sha256:" + "c" * 64,
        "citations": 3,
        "disclosure": None,
        "stillValid": None,
        "recordedAt": "2026-11-19T00:00:00+00:00",
    }
    data.update(over)
    return data


def test_record_round_trips():
    rec = prspec.PrSpecRecord.from_dict(record_dict(), expected_pr="github:octo/api#12")
    assert rec.as_dict() == record_dict()


@pytest.mark.parametrize(
    "over",
    [
        {"version": 2},
        {"pullRequest": "github:octo/api#13"},
        {"chainDigest": "sha256:short"},
        {"chainDigest": "md5:" + "c" * 64},
        {"reason": "because"},
        {"required": "yes"},
        {"required": False, "reason": "multi-pr"},
        {"required": True, "reason": "single-pr"},
    ],
)
def test_forged_record_is_rejected(over):
    with pytest.raises(ValueError):
        prspec.PrSpecRecord.from_dict(
            record_dict(**over), expected_pr="github:octo/api#12"
        )


def test_forged_record_not_a_mapping_is_rejected(tmp_path):
    path = tmp_path / "pr-spec.json"
    path.write_text(json.dumps([1, 2]), encoding="utf-8")
    with pytest.raises(ValueError):
        prspec.PrSpecRecord.load(path, expected_pr="github:octo/api#12")


def test_record_not_required_reasons_load():
    for reason in ("single-pr", "spec-only"):
        rec = prspec.PrSpecRecord.from_dict(
            record_dict(required=False, reason=reason), expected_pr="github:octo/api#12"
        )
        assert rec.required is False


# -- task 4: secret scan ------------------------------------------------------


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_" + "A" * 36,
        "gho_" + "b" * 36,
        "ghs_" + "c" * 36,
        "github_pat_" + "d" * 40,
        "xoxb-1234-5678-abcdef",
        "AKIA" + "ABCDEFGHIJKLMNOP",
        "Authorization: Bearer abc.def.ghi",
        "Bearer abcdefghijklmnop",
        "Cookie: session=abc",
        "Set-Cookie: id=1",
        "someone@example.com",
    ],
)
def test_abuse_seeded_token_is_finding(secret):
    files = {"design.md": f"line one\nhere {secret} there\n"}
    findings = prspec.scan_secrets(files)
    assert [(f.file, f.line) for f in findings] == [("design.md", 2)]
    assert secret not in findings[0].text


def test_secret_scan_ignores_digests_and_shas():
    files = {
        "requirements.md": (
            "chainDigest: sha256:" + "a" * 64 + "\nsourceRevision: " + "f" * 40 + "\n"
        )
    }
    assert prspec.scan_secrets(files) == []
