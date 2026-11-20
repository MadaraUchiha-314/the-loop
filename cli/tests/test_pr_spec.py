"""Unit tests for PR-scoped specs (issue-543): testing-plan rows T1 and T8."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

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
        "api_key: Abcd1234Efgh5678Ijkl9012",
        "DB_PASSWORD=hunter2hunter2",
        'client_secret = "s3cr3tValue99"',
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


# -- task 5: the offline hook --------------------------------------------------

from the_loop.graph.contract import HookContext, WorkItem  # noqa: E402
from the_loop.graph.hooks.pr_spec import pr_spec_current  # noqa: E402

ORIGIN = "octo/origin"


def hook_ctx(tmp_path, prs, *, repos=(), pr_ref="", node="reviewer-briefing"):
    """An origin checkout with a chain and an outer state naming ``prs``."""
    spec = write_chain(tmp_path / "docs" / "specs" / "issue-15")
    state = {
        "workItem": "github:octo/origin#15",
        "currentNode": "implementation",
        "pullRequests": prs,
        "repos": list(repos),
    }
    (spec / "work-item-state.json").write_text(json.dumps(state), encoding="utf-8")
    config = {"originRepo": ORIGIN}
    if pr_ref:
        config["prRef"] = pr_ref
    item = WorkItem(ref=pr_ref or "github:octo/origin#15", id="issue-15", spec_dir=spec)
    return HookContext(
        work_item=item, node={"id": node}, boundary="exit", repo=tmp_path, config=config
    )


def put_record(spec, repo, number, **over):
    from the_loop.graph.hooks.loops import inner_loop_state_dir

    data = record_dict(
        pullRequest=f"github:{repo}#{number}",
        chainDigest=prspec.chain_digest(spec),
        chainParts=prspec.chain_parts(spec),
    )
    data.update(over)
    target = inner_loop_state_dir(spec, number, repo) / prspec.PR_SPEC_RECORD
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data), encoding="utf-8")
    return target


TWO = [pr_row(ORIGIN, 2), pr_row("octo/api", 12)]


def test_hook_single_pr_passes_not_required(tmp_path):
    ctx = hook_ctx(tmp_path, [pr_row(ORIGIN, 2)], pr_ref="github:octo/origin#2")
    result = pr_spec_current(ctx)
    assert result.status == "pass"
    assert result.data["prSpec"] == "not-required"


def test_hook_multi_pr_without_record_blocks(tmp_path):
    ctx = hook_ctx(tmp_path, TWO, pr_ref="github:octo/api#12")
    result = pr_spec_current(ctx)
    assert result.status == "block"
    assert (
        "the-loop graph pr-spec issue-15 --pr 12 --pr-repo octo/api" in result.render()
    )


def test_hook_multi_pr_with_current_record_passes(tmp_path):
    ctx = hook_ctx(tmp_path, TWO, pr_ref="github:octo/api#12")
    put_record(ctx.work_item.spec_dir, "octo/api", 12)
    assert pr_spec_current(ctx).status == "pass"


def test_hook_finds_the_origin_pr_record_in_either_layout(tmp_path):
    from the_loop.graph.hooks.loops import inner_loop_state_dir

    ctx = hook_ctx(tmp_path, TWO, pr_ref="github:octo/origin#2")
    spec = ctx.work_item.spec_dir
    put_record(spec, ORIGIN, 2)  # qualified layout
    assert pr_spec_current(ctx).status == "pass"
    qualified = inner_loop_state_dir(spec, 2, ORIGIN) / prspec.PR_SPEC_RECORD
    plain = inner_loop_state_dir(spec, 2) / prspec.PR_SPEC_RECORD
    plain.parent.mkdir(parents=True)
    qualified.rename(plain)
    assert pr_spec_current(ctx).status == "pass"


def test_hook_stale_record_blocks_naming_changed_files(tmp_path):
    ctx = hook_ctx(tmp_path, TWO, pr_ref="github:octo/api#12")
    spec = ctx.work_item.spec_dir
    put_record(spec, "octo/api", 12)
    with (spec / "design.md").open("a", encoding="utf-8") as fh:
        fh.write("\nA change.\n")
    result = pr_spec_current(ctx)
    assert result.status == "block"
    assert "stale: chain changed since" in result.render()
    assert "design.md" in result.render()


def test_hook_lock_only_change_is_not_stale(tmp_path):
    ctx = hook_ctx(tmp_path, TWO, pr_ref="github:octo/api#12")
    spec = ctx.work_item.spec_dir
    put_record(spec, "octo/api", 12)
    text = (spec / "design.md").read_text(encoding="utf-8")
    (spec / "design.md").write_text(
        text.replace("---\n\n#", "approvedBy: [a]\n---\n\n#", 1)
    )
    assert pr_spec_current(ctx).status == "pass"


def test_hook_malformed_record_blocks(tmp_path):
    ctx = hook_ctx(tmp_path, TWO, pr_ref="github:octo/api#12")
    target = put_record(ctx.work_item.spec_dir, "octo/api", 12)
    target.write_text("{not json", encoding="utf-8")
    assert pr_spec_current(ctx).status == "block"


def test_forged_required_false_still_blocks(tmp_path):
    ctx = hook_ctx(tmp_path, TWO, pr_ref="github:octo/api#12")
    put_record(
        ctx.work_item.spec_dir, "octo/api", 12, required=False, reason="single-pr"
    )
    result = pr_spec_current(ctx)
    assert result.status == "block"
    assert "not required" in result.render()


def test_forged_spec_only_outside_the_origin_still_blocks(tmp_path):
    ctx = hook_ctx(tmp_path, TWO, pr_ref="github:octo/api#12")
    put_record(
        ctx.work_item.spec_dir, "octo/api", 12, required=False, reason="spec-only"
    )
    assert pr_spec_current(ctx).status == "block"


def test_hook_spec_only_origin_pr_passes(tmp_path):
    ctx = hook_ctx(tmp_path, TWO, pr_ref="github:octo/origin#2")
    put_record(ctx.work_item.spec_dir, ORIGIN, 2, required=False, reason="spec-only")
    assert pr_spec_current(ctx).status == "pass"


def _inner_implementation(spec, repo, number, **node):
    from the_loop.graph.hooks.loops import inner_loop_state_dir

    state = inner_loop_state_dir(spec, number, repo) / "work-item-state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"nodes": {"implementation": node}}), encoding="utf-8")


def test_hook_spec_only_recorded_before_implementation_blocks(tmp_path):
    ctx = hook_ctx(tmp_path, TWO, pr_ref="github:octo/origin#2")
    spec = ctx.work_item.spec_dir
    put_record(
        spec,
        ORIGIN,
        2,
        required=False,
        reason="spec-only",
        recordedAt="2026-11-19T00:00:00+00:00",
    )
    _inner_implementation(
        spec,
        ORIGIN,
        2,
        enteredAt="2026-11-19T01:00:00+00:00",
        exitedAt="2026-11-19T05:00:00+00:00",
    )
    result = pr_spec_current(ctx)
    assert result.status == "block"
    assert "spec-only before implementation ran" in result.render()


def test_hook_spec_only_recorded_after_implementation_passes(tmp_path):
    ctx = hook_ctx(tmp_path, TWO, pr_ref="github:octo/origin#2")
    spec = ctx.work_item.spec_dir
    put_record(
        spec,
        ORIGIN,
        2,
        required=False,
        reason="spec-only",
        recordedAt="2026-11-19T06:00:00+00:00",
    )
    _inner_implementation(
        spec,
        ORIGIN,
        2,
        enteredAt="2026-11-19T01:00:00+00:00",
        exitedAt="2026-11-19T05:00:00+00:00",
    )
    assert pr_spec_current(ctx).status == "pass"


def test_forged_record_for_another_pr_blocks(tmp_path):
    ctx = hook_ctx(tmp_path, TWO, pr_ref="github:octo/api#12")
    put_record(ctx.work_item.spec_dir, "octo/api", 12, pullRequest="github:octo/api#99")
    assert pr_spec_current(ctx).status == "block"


def test_hook_declared_skip_in_the_inner_state_passes(tmp_path):
    from the_loop.graph.hooks.loops import inner_loop_state_dir

    ctx = hook_ctx(tmp_path, TWO, pr_ref="github:octo/api#12")
    inner = inner_loop_state_dir(ctx.work_item.spec_dir, 12, "octo/api")
    inner.mkdir(parents=True)
    (inner / "work-item-state.json").write_text(
        json.dumps(
            {
                "workItem": "x",
                "currentNode": "implementation",
                "skips": {"pr-spec": {"via": "declared", "by": "@owner"}},
            }
        ),
        encoding="utf-8",
    )
    result = pr_spec_current(ctx)
    assert result.status == "pass"
    assert result.data["prSpec"] == "skipped"


def test_hook_outer_placement_blocks_listing_every_pr_without_record(tmp_path):
    ctx = hook_ctx(tmp_path, TWO, node="implementation")
    put_record(ctx.work_item.spec_dir, "octo/api", 12)
    result = pr_spec_current(ctx)
    assert result.status == "block"
    assert "github:octo/origin#2" in result.render()
    assert "octo/api#12" not in result.render()


def test_hook_outer_placement_passes_when_all_open_prs_recorded(tmp_path):
    rows = TWO + [pr_row("octo/api", 13, state="merged")]
    ctx = hook_ctx(tmp_path, rows, node="implementation")
    put_record(ctx.work_item.spec_dir, "octo/api", 12)
    put_record(ctx.work_item.spec_dir, ORIGIN, 2)
    assert pr_spec_current(ctx).status == "pass"


def test_hook_outer_placement_single_pr_passes(tmp_path):
    ctx = hook_ctx(tmp_path, [pr_row(ORIGIN, 2)], node="implementation")
    assert pr_spec_current(ctx).status == "pass"


def test_abuse_hook_writes_nothing(tmp_path):
    ctx = hook_ctx(tmp_path, TWO, pr_ref="github:octo/api#12")
    put_record(ctx.work_item.spec_dir, "octo/api", 12)

    def snapshot():
        return {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    before = snapshot()
    pr_spec_current(ctx)
    pr_spec_current(hook_ctx(tmp_path, TWO, node="implementation"))
    assert snapshot().keys() == before.keys()


# -- task 6: GitHub reads (stubbed) --------------------------------------------

from the_loop.authz import SELF_COMMENT_MARKER  # noqa: E402
from the_loop.ghapi import GhComment, GitHubApiError  # noqa: E402
from the_loop.graph import prspec_github as pg  # noqa: E402

WI_URL = "https://github.com/octo/origin/issues/15"
PR_URL = "https://github.com/octo/api/pull/12"


class StubGitHub:
    def __init__(self, visibility=None, comments=None, fail=False):
        self.visibility = visibility or {}
        self.comments = comments or {}
        self.fail = fail
        self.calls = []

    def repository(self, owner, repo, host=""):
        self.calls.append(("repository", owner, repo))
        if self.fail:
            raise GitHubApiError("boom")
        value = self.visibility.get(f"{owner}/{repo}")
        return {
            "full_name": f"{owner}/{repo}",
            **({"visibility": value} if value else {}),
        }

    def list_comments(self, owner, repo, number, is_pr, host=""):
        self.calls.append(("list_comments", owner, repo, number, is_pr))
        if self.fail:
            raise GitHubApiError("boom")
        return list(self.comments.get((f"{owner}/{repo}", number), []))


def comment(
    url, author="owner", body="allow-disclosure octo/api", at="2026-11-19T00:00:00Z"
):
    return GhComment(id="x", body=body, author=author, created_at=at, url=url)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("public", "public"),
        ("PRIVATE", "private"),
        ("internal", "internal"),
        (None, "unknown"),
        ("weird", "unknown"),
    ],
)
def test_visibility_values(raw, expected):
    gh = StubGitHub(visibility={"octo/api": raw} if raw else {})
    assert pg.repository_visibility(gh, "octo/api") == expected


def test_abuse_visibility_unknown_on_api_failure():
    assert pg.repository_visibility(StubGitHub(fail=True), "octo/api") == "unknown"


def test_narrowing_order():
    assert pg.narrows("private", "public")
    assert pg.narrows("private", "internal")
    assert pg.narrows("internal", "public")
    assert not pg.narrows("public", "private")
    assert not pg.narrows("private", "private")
    assert pg.narrows("unknown", "private")
    assert pg.narrows("public", "unknown")


def disclosure(gh, url):
    return pg.check_disclosure(
        gh,
        origin="octo/origin",
        target="octo/api",
        work_item="github:octo/origin#15",
        approval_url=url,
        authorized=["owner"],
    )


def test_abuse_disclosure_same_visibility_needs_no_grant():
    gh = StubGitHub(visibility={"octo/origin": "public", "octo/api": "public"})
    verdict, problem = disclosure(gh, "")
    assert (
        problem is None
        and verdict is not None
        and verdict["verdict"] == "same-or-narrower"
    )


def test_abuse_disclosure_private_to_public_without_grant_refused():
    gh = StubGitHub(visibility={"octo/origin": "private", "octo/api": "public"})
    verdict, problem = disclosure(gh, "")
    assert verdict is None and "private" in str(problem) and "public" in str(problem)


def test_abuse_visibility_unknown_is_refused():
    verdict, problem = disclosure(StubGitHub(fail=True), "")
    assert verdict is None and "visibility-unknown" in str(problem)


def test_abuse_disclosure_with_authorized_grant_recorded():
    url = WI_URL + "#issuecomment-1"
    gh = StubGitHub(
        visibility={"octo/origin": "private", "octo/api": "public"},
        comments={("octo/origin", 15): [comment(url)]},
    )
    verdict, problem = disclosure(gh, url)
    assert problem is None
    assert verdict == {
        "origin": "private",
        "target": "public",
        "verdict": "approved",
        "by": "@owner",
        "comment": url,
        "at": "2026-11-19T00:00:00Z",
    }


def test_abuse_disclosure_grant_by_unauthorized_author_refused():
    url = WI_URL + "#issuecomment-1"
    gh = StubGitHub(
        visibility={"octo/origin": "private", "octo/api": "public"},
        comments={("octo/origin", 15): [comment(url, author="mallory")]},
    )
    verdict, problem = disclosure(gh, url)
    assert verdict is None and "not authorized" in str(problem)


def test_abuse_comment_marked_as_agent_refused():
    url = WI_URL + "#issuecomment-1"
    gh = StubGitHub(
        visibility={"octo/origin": "private", "octo/api": "public"},
        comments={
            ("octo/origin", 15): [
                comment(url, body=SELF_COMMENT_MARKER + "\nallow-disclosure octo/api")
            ]
        },
    )
    verdict, problem = disclosure(gh, url)
    assert verdict is None and "the-loop's own" in str(problem)


def test_abuse_disclosure_grant_naming_another_repo_refused():
    url = WI_URL + "#issuecomment-1"
    gh = StubGitHub(
        visibility={"octo/origin": "private", "octo/api": "public"},
        comments={
            ("octo/origin", 15): [comment(url, body="allow-disclosure octo/api-two")]
        },
    )
    verdict, problem = disclosure(gh, url)
    assert verdict is None and "allow-disclosure octo/api" in str(problem)


@pytest.mark.parametrize(
    "body",
    [
        "Do not `allow-disclosure octo/api`",
        "Do not allow-disclosure octo/api, it is private.",
        "> allow-disclosure octo/api",
        "allow-disclosure octo/api? not yet",
    ],
)
def test_abuse_negated_or_quoted_disclosure_grant_refused(body):
    url = WI_URL + "#issuecomment-1"
    gh = StubGitHub(
        visibility={"octo/origin": "private", "octo/api": "public"},
        comments={("octo/origin", 15): [comment(url, body=body)]},
    )
    verdict, problem = disclosure(gh, url)
    assert verdict is None and "on a line of its own" in str(problem)


@pytest.mark.parametrize(
    "body",
    [
        "allow-disclosure octo/api",
        "Fine by me.\n\n`allow-disclosure octo/api`",
        "ALLOW-DISCLOSURE octo/api.",
    ],
)
def test_disclosure_grant_on_its_own_line_accepted(body):
    url = WI_URL + "#issuecomment-1"
    gh = StubGitHub(
        visibility={"octo/origin": "private", "octo/api": "public"},
        comments={("octo/origin", 15): [comment(url, body=body)]},
    )
    verdict, problem = disclosure(gh, url)
    assert problem is None and verdict is not None


def test_abuse_comment_on_another_issue_refused():
    url = "https://github.com/octo/origin/issues/16#issuecomment-1"
    gh = StubGitHub(
        visibility={"octo/origin": "private", "octo/api": "public"},
        comments={("octo/origin", 16): [comment(url)]},
    )
    verdict, problem = disclosure(gh, url)
    assert verdict is None and "not a comment on" in str(problem)
    assert not any(c[0] == "list_comments" for c in gh.calls)


def test_abuse_comment_url_not_found_refused():
    url = WI_URL + "#issuecomment-2"
    gh = StubGitHub(
        visibility={"octo/origin": "private", "octo/api": "public"},
        comments={("octo/origin", 15): [comment(WI_URL + "#issuecomment-1")]},
    )
    verdict, problem = disclosure(gh, url)
    assert verdict is None and "not found" in str(problem)


@pytest.mark.parametrize(
    "url",
    [
        "not a url",
        "https://github.com/octo/origin/issues/15",
        "http://github.com/octo/origin/issues/15#issuecomment-1",
        "https://github.com/octo/origin/issues/15#issuecomment-1x",
    ],
)
def test_abuse_comment_url_malformed_refused(url):
    problem = pg.authorize_comment(
        StubGitHub(), url, expected="github:octo/origin#15", authorized=["owner"]
    )[1]
    assert problem


def test_still_valid_comment_on_this_pr_authorized():
    url = PR_URL + "#issuecomment-5"
    gh = StubGitHub(comments={("octo/api", 12): [comment(url, body="still valid")]})
    found, problem = pg.authorize_comment(
        gh, url, expected="github:octo/api#12", authorized=["owner"]
    )
    assert problem is None and found is not None and found["by"] == "@owner"
    assert ("list_comments", "octo", "api", 12, True) in gh.calls


# -- task 7: the verb --------------------------------------------------------

import subprocess  # noqa: E402

from the_loop.graph.prspec_verb import (  # noqa: E402
    REQUIRED_SECTIONS,
    PrSpecRequest,
    record_pr_spec,
)

WI_REF = "github:octo/origin#15"
API_PR = "github:octo/api#12"


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def pr_checkout(tmp_path, repo="octo/api", branch="feature"):
    co = tmp_path / "pr-checkout"
    co.mkdir()
    git(co, "init", "-q", "-b", "main")
    git(co, "config", "user.email", "t@example.invalid")
    git(co, "config", "user.name", "t")
    git(co, "remote", "add", "origin", f"https://github.com/{repo}.git")
    (co / "README").write_text("x\n")
    git(co, "add", ".")
    git(co, "commit", "-q", "-m", "init")
    git(co, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(co, "checkout", "-q", "-b", branch)
    return co


def pr_spec_text(name, kind, digest, pr_ref=API_PR, cite="[wi:R1]", rev="abc1234"):
    extra = {
        "requirements.md": f"## Requirements\n\n### PR-R1 — the API part\n\nDelivers {cite}.\n",
        "design.md": f"## Design\n\nBuilt as in {cite} and [wi:design#security-design].\n",
        "testing-plan.md": (
            "## Test matrix\n\n| # | Type | Applies? | Scope | Where |\n|---|---|---|---|---|\n"
            f"| P1 | Unit | yes | proves {cite} [wi:TP-T1] | pytest |\n"
        ),
        "tasks.md": f"## Tasks\n\n- [ ] 1. Do it {cite} [wi:task-1]\n",
    }[name]
    return (
        f'---\ntype: {kind}\nworkItem: "{WI_REF}"\npullRequest: "{pr_ref}"\n'
        f'sourceRevision: "{rev}"\nchainDigest: "{digest}"\n---\n\n'
        f"# PR spec\n\n## Context\n\nPart of {WI_REF}; sibling github:octo/origin#2.\n\n{extra}"
    )


def write_pr_spec(co, spec, key="octo__origin__issue-15", number=12, **kw):
    target = co / "docs" / "specs" / key / f"pr-{number}"
    target.mkdir(parents=True, exist_ok=True)
    digest = prspec.chain_digest(spec)
    kw.setdefault("rev", origin_head(spec))
    for name, kind in prspec.PR_SPEC_FILES:
        (target / name).write_text(
            pr_spec_text(name, kind, digest, **kw), encoding="utf-8"
        )
    git(co, "add", "-A")
    git(co, "commit", "-q", "-m", "pr spec")
    return target


def origin_repo(spec):
    """Make the origin checkout above ``spec`` a git repo with the chain committed."""
    root = spec.parents[2]
    if not (root / ".git").exists():
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@example.invalid")
        git(root, "config", "user.name", "t")
    commit_chain(spec)
    return root


def commit_chain(spec, when=None):
    root = spec.parents[2]
    git(root, "add", "-A")
    env = None
    if when:
        import os

        env = {**os.environ, "GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when}
    subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "--allow-empty", "-m", "chain"],
        check=True,
        capture_output=True,
        env=env,
    )


def origin_head(spec):
    root = spec.parents[2]
    if not (root / ".git").exists():
        return "abc1234"
    done = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    return done.stdout.strip() or "abc1234"


class VerbGitHub(StubGitHub):
    def __init__(self, head="feature", base="main", **kw):
        super().__init__(**kw)
        self.head, self.base = head, base

    def get_pull(self, owner, repo, number, host=""):
        return {"head": {"ref": self.head}, "base": {"ref": self.base}}


def verb_request(tmp_path, co, **over):
    spec = tmp_path / "origin" / "docs" / "specs" / "issue-15"
    if not spec.exists():
        write_chain(spec)
        origin_repo(spec)
    fields: Dict[str, Any] = dict(
        work_item_id="issue-15",
        work_item_ref=WI_REF,
        pr_ref=API_PR,
        pr_repo="octo/api",
        pr_number=12,
        origin="octo/origin",
        spec_dir=spec,
        record_dir=spec / "pr-loops" / "octo__api" / "pr-12",
        checkout=co,
        pull_requests=TWO,
        authorized=["owner"],
        now="2026-11-19T00:00:00+00:00",
    )
    fields.update(over)
    return PrSpecRequest(**fields)


def rec(result):
    """The recorded record, narrowed for the type checker."""
    assert result.record is not None
    return result.record


PUBLIC = {"octo/origin": "public", "octo/api": "public"}


def test_verb_records_a_complete_pr_spec(tmp_path):
    co = pr_checkout(tmp_path)
    req = verb_request(tmp_path, co)
    write_pr_spec(co, req.spec_dir)
    result = record_pr_spec(req, VerbGitHub(visibility=PUBLIC))
    assert result.findings == [] and result.recorded
    data = json.loads((req.record_dir / "pr-spec.json").read_text())
    assert data["required"] is True and data["reason"] == "multi-pr"
    assert data["chainDigest"] == prspec.chain_digest(req.spec_dir)
    assert data["path"] == "docs/specs/octo__origin__issue-15/pr-12"
    assert data["sourceRevision"] == origin_head(req.spec_dir)
    assert data["citations"] == 7
    assert data["disclosure"]["verdict"] == "same-or-narrower"


def test_verb_record_then_hook_passes(tmp_path):
    co = pr_checkout(tmp_path)
    req = verb_request(tmp_path, co)
    write_pr_spec(co, req.spec_dir)
    record_pr_spec(req, VerbGitHub(visibility=PUBLIC))
    state = {"workItem": WI_REF, "currentNode": "implementation", "pullRequests": TWO}
    (req.spec_dir / "work-item-state.json").write_text(json.dumps(state))
    ctx = HookContext(
        work_item=WorkItem(ref=API_PR, id="issue-15", spec_dir=req.spec_dir),
        node={"id": "pr-spec"},
        boundary="exit",
        repo=tmp_path,
        config={"originRepo": ORIGIN, "prRef": API_PR},
    )
    assert pr_spec_current(ctx).status == "pass"


def test_verb_single_pr_records_not_required(tmp_path):
    co = pr_checkout(tmp_path, repo="octo/origin")
    req = verb_request(
        tmp_path,
        co,
        pr_repo="octo/origin",
        pr_ref="github:octo/origin#2",
        pr_number=2,
        pull_requests=[pr_row(ORIGIN, 2)],
        record_dir=tmp_path / "rec",
    )
    result = record_pr_spec(req, VerbGitHub())
    assert result.recorded and rec(result).reason == "single-pr"


def test_verb_spec_only_origin_pr_records_not_required(tmp_path):
    co = pr_checkout(tmp_path, repo="octo/origin")
    (co / "docs" / "specs" / "issue-15").mkdir(parents=True)
    (co / "docs" / "specs" / "issue-15" / "design.md").write_text("x\n")
    git(co, "add", ".")
    git(co, "commit", "-q", "-m", "spec")
    req = verb_request(
        tmp_path,
        co,
        pr_repo="octo/origin",
        pr_ref="github:octo/origin#2",
        pr_number=2,
        record_dir=tmp_path / "rec",
    )
    result = record_pr_spec(req, VerbGitHub())
    assert result.recorded and rec(result).reason == "spec-only"


def test_verb_code_change_on_origin_pr_is_not_spec_only(tmp_path):
    co = pr_checkout(tmp_path, repo="octo/origin")
    (co / "code.py").write_text("x = 1\n")
    git(co, "add", ".")
    git(co, "commit", "-q", "-m", "code")
    req = verb_request(
        tmp_path,
        co,
        pr_repo="octo/origin",
        pr_ref="github:octo/origin#2",
        pr_number=2,
        record_dir=tmp_path / "rec",
    )
    result = record_pr_spec(req, VerbGitHub())
    assert not result.recorded
    assert any("missing" in f.text for f in result.findings)


def test_verb_wrong_remote_refused(tmp_path):
    co = pr_checkout(tmp_path, repo="octo/other")
    result = record_pr_spec(verb_request(tmp_path, co), VerbGitHub())
    assert not result.recorded and "origin" in result.findings[0].text


def test_verb_wrong_branch_refused(tmp_path):
    co = pr_checkout(tmp_path)
    result = record_pr_spec(verb_request(tmp_path, co), VerbGitHub(head="other"))
    assert not result.recorded and "branch" in result.findings[0].text


def test_verb_unapproved_chain_refused(tmp_path):
    co = pr_checkout(tmp_path)
    req = verb_request(tmp_path, co)
    design = req.spec_dir / "design.md"
    design.write_text(design.read_text().replace("status: approved", "status: draft"))
    write_pr_spec(co, req.spec_dir)
    result = record_pr_spec(req, VerbGitHub(visibility=PUBLIC))
    assert not result.recorded
    assert any(
        f.file == "design.md" and "not approved" in f.text for f in result.findings
    )


def test_verb_skipped_gate_allows_unapproved_chain(tmp_path):
    co = pr_checkout(tmp_path)
    req = verb_request(tmp_path, co, skips={"design-approval": {"via": "declared"}})
    design = req.spec_dir / "design.md"
    design.write_text(design.read_text().replace("status: approved", "status: draft"))
    write_pr_spec(co, req.spec_dir)
    assert record_pr_spec(req, VerbGitHub(visibility=PUBLIC)).recorded


def test_verb_reports_every_finding_at_once(tmp_path):
    co = pr_checkout(tmp_path)
    req = verb_request(tmp_path, co)
    target = write_pr_spec(co, req.spec_dir, cite="[wi:R9]")
    (target / "tasks.md").unlink()
    text = (
        (target / "design.md")
        .read_text()
        .replace("---\n\n#", "status: draft\n---\n\n#", 1)
    )
    (target / "design.md").write_text(text)
    result = record_pr_spec(req, VerbGitHub(visibility=PUBLIC))
    texts = " | ".join(f.render() for f in result.findings)
    assert "tasks.md: missing" in texts
    assert "carries no `status`" in texts
    assert "[wi:R9]" in texts
    assert not (req.record_dir / "pr-spec.json").exists()


def test_verb_stale_front_matter_digest_refused(tmp_path):
    co = pr_checkout(tmp_path)
    req = verb_request(tmp_path, co)
    write_pr_spec(co, req.spec_dir)
    with (req.spec_dir / "design.md").open("a") as fh:
        fh.write("\nchanged\n")
    result = record_pr_spec(req, VerbGitHub(visibility=PUBLIC))
    assert any("chainDigest" in f.text for f in result.findings)


def test_verb_missing_section_refused(tmp_path):
    co = pr_checkout(tmp_path)
    req = verb_request(tmp_path, co)
    target = write_pr_spec(co, req.spec_dir)
    text = (target / "requirements.md").read_text()
    (target / "requirements.md").write_text(
        text.replace("## Context\n\nPart of", "## Context\n\n## Other\n\nPart of")
    )
    result = record_pr_spec(req, VerbGitHub(visibility=PUBLIC))
    assert any("`Context`" in f.text for f in result.findings)


def test_abuse_verb_private_to_public_refused_then_granted(tmp_path):
    co = pr_checkout(tmp_path)
    req = verb_request(tmp_path, co)
    write_pr_spec(co, req.spec_dir)
    vis = {"octo/origin": "private", "octo/api": "public"}
    refused = record_pr_spec(req, VerbGitHub(visibility=vis))
    assert not refused.recorded and "disclosure refused" in refused.findings[0].text
    url = WI_URL + "#issuecomment-1"
    gh = VerbGitHub(visibility=vis, comments={("octo/origin", 15): [comment(url)]})
    granted = record_pr_spec(verb_request(tmp_path, co, disclosure_approval=url), gh)
    assert granted.recorded and (rec(granted).disclosure or {}).get("by") == "@owner"


def test_abuse_verb_seeded_secret_refused(tmp_path):
    co = pr_checkout(tmp_path)
    req = verb_request(tmp_path, co)
    target = write_pr_spec(co, req.spec_dir)
    with (target / "design.md").open("a") as fh:
        fh.write("token ghp_" + "A" * 36 + "\n")
    result = record_pr_spec(req, VerbGitHub(visibility=PUBLIC))
    assert any("GitHub token" in f.text for f in result.findings)


def test_abuse_symlink_escape(tmp_path):
    co = pr_checkout(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (co / "docs").symlink_to(outside, target_is_directory=True)
    req = verb_request(tmp_path, co)
    result = record_pr_spec(req, VerbGitHub(visibility=PUBLIC))
    assert any("outside the checkout" in f.text for f in result.findings)


def test_abuse_writes_only_record(tmp_path):
    co = pr_checkout(tmp_path)
    req = verb_request(tmp_path, co)
    write_pr_spec(co, req.spec_dir)

    def files():
        return {p for p in tmp_path.rglob("*") if p.is_file() and ".git" not in p.parts}

    before = files()
    assert record_pr_spec(req, VerbGitHub(visibility=PUBLIC)).recorded
    assert files() - before == {req.record_dir / "pr-spec.json"}


STILL = "pr-spec still-valid"


def recorded_then_changed(tmp_path, changed_at="2026-11-20T08:00:00Z"):
    """A recorded PR spec (at 2026-11-19T00:00Z), then a chain change committed
    at ``changed_at``."""
    co = pr_checkout(tmp_path)
    req = verb_request(tmp_path, co)
    write_pr_spec(co, req.spec_dir)
    assert record_pr_spec(req, VerbGitHub(visibility=PUBLIC)).recorded
    with (req.spec_dir / "design.md").open("a") as fh:
        fh.write("\nchanged\n")
    commit_chain(req.spec_dir, when=changed_at)
    return co, req


def still_valid(tmp_path, co, body=STILL, at="2026-11-20T09:00:00Z", author="owner"):
    url = PR_URL + "#issuecomment-5"
    said = comment(url, body=body, at=at, author=author)
    gh = VerbGitHub(visibility=PUBLIC, comments={("octo/api", 12): [said]})
    return record_pr_spec(verb_request(tmp_path, co, still_valid=url), gh)


def test_verb_still_valid_rerecords_digest(tmp_path):
    co, req = recorded_then_changed(tmp_path)
    result = still_valid(tmp_path, co, body="Checked it.\n\n`pr-spec still-valid`")
    assert result.recorded, result.findings
    assert rec(result).chain_digest == prspec.chain_digest(req.spec_dir)
    assert (rec(result).still_valid or {}).get("by") == "@owner"


def test_abuse_still_valid_comment_older_than_record_refused(tmp_path):
    co, _ = recorded_then_changed(tmp_path)
    result = still_valid(tmp_path, co, at="2026-11-18T09:00:00Z")
    assert not result.recorded
    assert any(
        "before the PR spec was last recorded" in f.text for f in result.findings
    )


def test_abuse_still_valid_comment_before_the_chain_change_refused(tmp_path):
    # Recorded at T0, declared at T1, chain changed at T2: T1 is not about T2.
    co, _ = recorded_then_changed(tmp_path, changed_at="2026-11-21T08:00:00Z")
    result = still_valid(tmp_path, co, at="2026-11-20T09:00:00Z")
    assert not result.recorded
    assert any("before the chain last changed" in f.text for f in result.findings)


def test_abuse_still_valid_with_uncommitted_chain_change_refused(tmp_path):
    co, req = recorded_then_changed(tmp_path)
    with (req.spec_dir / "design.md").open("a") as fh:
        fh.write("\nmore\n")
    result = still_valid(tmp_path, co)
    assert not result.recorded
    assert any("commit the chain change first" in f.text for f in result.findings)


@pytest.mark.parametrize(
    "body",
    [
        "Do not merge; the scope needs revision.",
        "Is the pr-spec still-valid after this?",
        "> pr-spec still-valid",
    ],
)
def test_abuse_still_valid_comment_that_does_not_declare_refused(tmp_path, body):
    co, _ = recorded_then_changed(tmp_path)
    result = still_valid(tmp_path, co, body=body)
    assert not result.recorded
    assert any("on a line of its own" in f.text for f in result.findings)


def test_verb_still_valid_by_unauthorized_refused(tmp_path):
    co, _ = recorded_then_changed(tmp_path)
    assert not still_valid(tmp_path, co, author="mallory").recorded


def test_abuse_uncommitted_pr_spec_refused(tmp_path):
    co = pr_checkout(tmp_path)
    req = verb_request(tmp_path, co)
    target = write_pr_spec(co, req.spec_dir)
    git(co, "reset", "-q", "--soft", "HEAD~1")
    git(co, "rm", "-q", "--cached", "-r", str(target))
    result = record_pr_spec(req, VerbGitHub(visibility=PUBLIC))
    assert not result.recorded
    assert any("commit the PR spec" in f.text for f in result.findings)


def test_abuse_edited_after_commit_pr_spec_refused(tmp_path):
    co = pr_checkout(tmp_path)
    req = verb_request(tmp_path, co)
    target = write_pr_spec(co, req.spec_dir)
    with (target / "tasks.md").open("a") as fh:
        fh.write("\n- [ ] 2. More [wi:task-1]\n")
    result = record_pr_spec(req, VerbGitHub(visibility=PUBLIC))
    assert not result.recorded
    assert any("commit the PR spec" in f.text for f in result.findings)


@pytest.mark.parametrize("rev", ["deadbeef", "--output=x", "HEAD"])
def test_abuse_unresolvable_source_revision_refused(tmp_path, rev):
    co = pr_checkout(tmp_path)
    req = verb_request(tmp_path, co)
    write_pr_spec(co, req.spec_dir, rev=rev)
    result = record_pr_spec(req, VerbGitHub(visibility=PUBLIC))
    assert not result.recorded
    assert any("not a commit of the origin" in f.text for f in result.findings)


def test_required_sections_match_the_templates():
    root = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "the-loop"
        / "templates"
        / "pr-spec"
    )
    for name, headings in REQUIRED_SECTIONS.items():
        text = (root / name).read_text(encoding="utf-8")
        for heading in headings:
            assert f"\n## {heading}\n" in text, (name, heading)
        front, _ = __import__(
            "the_loop.graph.frontmatter", fromlist=["x"]
        ).split_front_matter(text)
        assert "status" not in front
        assert front["type"] == dict(prspec.PR_SPEC_FILES)[name]


def test_the_pr_briefing_links_the_pr_spec_first():
    """issue-543 R4.6: the PR spec is the first thing a reviewer is pointed at."""
    root = Path(__file__).resolve().parents[2] / "skills" / "the-loop" / "templates"
    text = (root / "pr-briefing.md").read_text(encoding="utf-8")
    card = text.split("## The short version", 1)[1].split("\n## ", 1)[0]
    first = next(
        line
        for line in card.splitlines()
        if line.strip() and not line.startswith(("<!--", "     "))
    )
    assert first.startswith("**This PR's spec:**")


def test_record_pull_request_matches_case_insensitively():
    """GitHub owner and repository names are case-insensitive: the ref the verb
    derives from a checkout's remote may differ in case from the daemon's."""
    data = record_dict(pullRequest="github:octo/API#12")
    assert prspec.PrSpecRecord.from_dict(data, expected_pr="github:Octo/api#12")


def test_verb_accepts_refs_that_differ_only_in_case(tmp_path):
    co = pr_checkout(tmp_path)
    req = verb_request(tmp_path, co, pr_ref="github:Octo/API#12")
    write_pr_spec(co, req.spec_dir)
    assert record_pr_spec(req, VerbGitHub(visibility=PUBLIC)).findings == []
