---
type: execution-log
workItem: issue-21
phase: needs-review
status: in-progress
---

# Execution Log: Publish the-loop to PyPI

> Append-only log of progress for the user's visibility. Checked in alongside the spec at
> `docs/specs/issue-21/execution-log.md`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-04 | @MadaraUchiha-314 (issue #21) | Trusted Publisher pre-registered → params fixed |
| design | 2026-07-04 | @MadaraUchiha-314 (issue #21) | distribution-only rename; OIDC; decision-019 |
| tasks-breakdown | 2026-07-04 | @MadaraUchiha-314 (issue #21) | 5-task DAG |
| implementation | 2026-07-04 |  | rename + lock + release.yml + docs |
| needs-review | 2026-07-04 |  | awaiting PR approval (sensitivePath: workflows) |
| complete |  |  | on first successful `v<version>` Release publish |

## Progress entries

### 2026-07-04 — Packaging + release workflow implemented

- **Phase:** implementation → needs-review
- **Did:**
  - Renamed the distribution to `the-loopy-one` in `cli/pyproject.toml` (import package
    `the_loop` and `the-loop` console script unchanged); added trove classifiers + Issues
    URL. Re-locked `uv.lock` (`the-loop` → `the-loopy-one`).
  - Added `.github/workflows/release.yml`: `build` job (uv build + tag/version guard,
    artifact upload) and `publish-pypi` job (`environment: pypi`, `id-token: write`,
    `pypa/gh-action-pypi-publish`, `if: release`); `workflow_dispatch` builds only.
  - Docs: `cli/README.md` install-from-PyPI, `decision-019` (+ index), architecture &
    roadmap notes, this spec.
- **Checkpoint/tests:**
  - `uv build --package the-loopy-one` → `the_loopy_one-0.1.0.tar.gz` + `...-py3-none-any.whl`.
  - Wheel inspection: METADATA `Name: the-loopy-one`; contains `the_loop/`; entry point
    `the-loop = the_loop.__main__:main`. **PASS** (R1).
  - `uv version --package the-loopy-one --short` → `0.1.0` (tag guard basis). **PASS** (R3).
  - `uv lock` re-locked; `grep the-loopy-one uv.lock` present. **PASS** (R4).
  - `make check` (lint, format-check, typecheck, validate, test) — see final validation.
- **Next:** human PR review (`.github/workflows/**` is a `sensitivePaths` entry → tier
  human-approves-pr). After merge, cut a `v0.1.0` Release to perform the first publish.
- **Blockers:** first real publish requires a maintainer to publish a GitHub Release.

## Review cycles

| Cycle | Type (self/critic) | Reviewer | Outcome | Link |
|-------|--------------------|----------|---------|------|
| 1 | self | the-loop | build + wheel-metadata verification passed | this log |

## Final validation evidence

- **R1 (name):** wheel METADATA `Name: the-loopy-one`, packages `the_loop/`, console
  script `the-loop` — verified by inspecting the built wheel.
- **R2 (OIDC publish):** `release.yml` has `publish-pypi` with `environment: pypi`,
  `permissions: id-token: write`, `pypa/gh-action-pypi-publish`, and no token reference.
- **R3 (guard):** build job asserts `GITHUB_REF_NAME == v$(uv version --package
  the-loopy-one --short)` on Release events.
- **R4 (reproducible):** built with `uv`; `uv.lock` re-locked and committed.
- **R5 (questions answered):** scope + future-proofing convention recorded in
  `docs/decisions/decision-019.md` and `design.md`.
- **Repo gate:** `make check` output attached in the PR briefing.
