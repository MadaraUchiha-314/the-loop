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
| tasks-breakdown | 2026-07-04 | @MadaraUchiha-314 (issue #21) | 6-task DAG (revised on PR #22) |
| implementation | 2026-07-04 |  | rename + lock + semantic release.yml + cz config + docs |
| needs-review | 2026-07-04 |  | awaiting PR approval (sensitivePath: workflows) |
| complete |  |  | on first auto-publish (`0.2.0`) when this PR merges to main |

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

### 2026-07-04 — Pivot to semantic auto-release (PR #22 review)

- **Phase:** needs-review (revision)
- **Did:** Owner asked on PR #22 for semantic-release from PR titles and for this PR's
  merge to publish. Confirmed approach via question: **commitizen `cz bump` on merge to
  main**, first publish **on merge of this PR**. Reworked the release model:
  - `.cz.toml`: added `version_files = ["cli/pyproject.toml:^version = "]` and
    `update_changelog_on_bump = false`.
  - `.github/workflows/release.yml`: trigger switched to `push: main`; `release` job runs
    `cz bump --yes --changelog` (exit 0 → release; 21/3 → no-op; else fail), pushes
    bump+tag to main, `gh release create --generate-notes`, `uv build`, uploads artifact;
    `publish-pypi` (env `pypi`, OIDC) gated on `released == 'true'`. `concurrency: release`;
    skips its own `bump:` commit.
  - Docs updated end-to-end (decision-019, requirements/design/tasks, README, architecture,
    roadmap).
- **Checkpoint/tests:**
  - `uv run cz bump --yes` → `0.1.0 → 0.2.0` (feat=MINOR); rewrote **both** `.cz.toml` and
    `cli/pyproject.toml`; created tag `v0.2.0`. Verified, then reverted. **PASS** (R3).
  - `release.yml` parses; `publish-pypi` has `environment: pypi` + `id-token: write`, no
    token. **PASS** (R2).
- **Next:** on merge, the release job publishes **`0.2.0`** (first PyPI release; `feat:`
  merge from `0.1.0` baseline).
- **Blockers/caveat:** the release job pushes to `main` — protected `main` must allow
  `github-actions[bot]` to bypass (or use a bot PAT). Flagged to the owner on PR #22.

### 2026-07-05 — First release run failed to publish; workflow fixed (follow-up)

- **Phase:** post-merge fixup (fresh change on the same branch)
- **Did:** PR #22 merged. The Release workflow ran on `main`, `cz bump` produced `0.2.0`,
  and the bump commit landed on `main` (so `github-actions[bot]` could push to `main` — the
  branch-protection caveat was moot). But it then **failed**: run
  [28758938779](https://github.com/MadaraUchiha-314/the-loop/actions/runs/28758938779) —
  `gh release create v0.2.0 --verify-tag` aborted with `tag v0.2.0 doesn't exist`, so
  nothing published. Root cause: `git push --follow-tags` pushes only annotated tags, but
  commitizen creates a lightweight one → the tag was never pushed. Confirmed `0.2.0` absent
  from PyPI (404) and no remote `v*` tags. Owner chose to roll forward to `0.2.1`. Fixes:
  (1) push the tag explicitly by ref; (2) a first-release baseline-bootstrap step so
  `cz bump` computes a patch (`0.2.0 → 0.2.1`) instead of scanning all history.
- **Checkpoint/tests:** `release.yml` re-parses with the new steps; bootstrap logic tags
  the in-repo version at `HEAD^` only when no `v*` tag exists (runs once). `make check`
  green on the fix branch.
- **Next:** on merge of the fix PR, the run bootstraps `v0.2.0`, bumps to `0.2.1`, pushes
  the tag, cuts the Release, and publishes **`0.2.1`** — the first PyPI upload.
- **Blockers:** none (all tag pushes happen inside the runner via `GITHUB_TOKEN`; the
  sandbox git proxy blocks tag/`main` pushes locally, which is why the fix is workflow-side).

## Review cycles

| Cycle | Type (self/critic) | Reviewer | Outcome | Link |
|-------|--------------------|----------|---------|------|
| 1 | self | the-loop | build + wheel-metadata verification passed | this log |
| 2 | self | the-loop | semantic-release rework: cz bump + workflow verified | this log |

## Final validation evidence

- **R1 (name):** wheel METADATA `Name: the-loopy-one`, packages `the_loop/`, console
  script `the-loop` — verified by inspecting the built wheel.
- **R2 (OIDC publish):** `release.yml` has `publish-pypi` with `environment: pypi`,
  `permissions: id-token: write`, `pypa/gh-action-pypi-publish`, and no token reference.
- **R3 (semantic versioning):** `cz bump --yes` computes `0.1.0 → 0.2.0` (feat=MINOR) and
  rewrites both `.cz.toml` and `cli/pyproject.toml` via `version_files`; the workflow
  classifies `cz` exit 0/21/3 so no-releasable-commit merges publish nothing.
- **R4 (reproducible):** built with `uv`; `uv.lock` re-locked and committed.
- **R5 (questions answered):** scope + semantic-release choice + future-proofing convention
  recorded in `docs/decisions/decision-019.md` and `design.md`.
- **Repo gate:** `make check` output attached in the PR briefing.
