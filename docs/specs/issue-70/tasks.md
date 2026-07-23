---
type: tasks
phase: tasks-breakdown
workItem: issue-70
status: approved
approvedBy: ["@MadaraUchiha-314 (PR #71, 2026-07-23)"]
overrides: {}
---

# Tasks: documentation site for the-loop

> Phase 3 of 3 (requirements → design → tasks). Derived from the approved design.
>
> **Retroactive note:** reconstructed during PR #71 to document the work actually done
> (and the mid-PR restructure). "Test" for a docs/site work item is a build/render/lint
> verification, not a unit test — there is no runtime product code here.

## Task list

- [x] 1. Scaffold VitePress under `docs/` as the site root
  - `docs/package.json` (vitepress devDep + `docs:sync|dev|build|preview`),
    `docs/.vitepress/config.mts` (base `/the-loop/`, default theme, local search).
  - _Depends on:_ none
  - _Requirements:_ R1, R2
  - _Test:_ `bun run docs:build` succeeds.
- [x] 2. Author the hand-written site pages (Markdown)
  - `docs/index.md` (home hero), `docs/guide/*` (what-is/installation/quickstart/
    how-it-works), `docs/reference/*` (commands/configuration),
    `docs/operating-model/index.md`, `docs/contributing.md`.
  - _Depends on:_ 1
  - _Requirements:_ R1, R2
  - _Test:_ pages render in `dist`; internal links resolve in `docs:preview`.
- [x] 3. Build-time sync of the two non-relocatable sources
  - `docs/scripts/sync-content.mts` copies `cli/README.md` → `docs/cli.md` and
    `skills/the-loop/reference/*.md` → `docs/operating-model/reference/`, rewriting
    relative links; wired into `docs:sync` (prepended to dev/build).
  - _Depends on:_ 1
  - _Requirements:_ R3.2
  - _Test:_ after `docs:sync`, both destinations exist and render; git status shows them
    ignored.
- [x] 4. Render the existing `docs/` tree in place (no duplication)
  - Nav + sidebar point at `docs/architecture/`, `docs/capabilities/`, `docs/decisions/`
    directly.
  - _Depends on:_ 1
  - _Requirements:_ R3.1, R3.3
  - _Test:_ architecture/decisions/capabilities pages exist in `dist`.
- [x] 5. GitHub Pages deploy workflow
  - `.github/workflows/docs.yml`: on push to `main` (docs paths) + `workflow_dispatch`,
    `setup-bun` + `bun install --frozen-lockfile` + `docs:build`, first-party Pages actions, single-flight
    concurrency, OIDC scopes.
  - _Depends on:_ 1
  - _Requirements:_ R4
  - _Test:_ workflow validates (`actionlint`/CI parse); job graph build → deploy.
- [x] 6. Fit the existing quality gates
  - `.gitignore` (ignore `node_modules/`, `.vitepress/cache`, synced files),
    `.markdownlint-cli2.jsonc` (ignore dist/cache + synced copies), root `README.md`
    links to the site.
  - _Depends on:_ 2, 3, 4
  - _Requirements:_ R5
  - _Test:_ `pre-commit run --all-files` green; `docs:build` clean.
- [x] 7. Restructure from `docs-site/` → `docs/` (PR #71 review)
  - First revision put the site in a `docs-site/` folder that synced all of `docs/`
    into itself; owner rejected the duplication. Moved the site into `docs/`,
    reduced the sync to the two non-relocatable sources, updated workflow/gitignore/
    markdownlint/links accordingly.
  - _Depends on:_ 1–6
  - _Requirements:_ R3.1, R3.3
  - _Test:_ `docs:build` clean; `pre-commit run --all-files` green; no `docs-site`
    references remain.
- [x] 8. Backfill this spec (requirements/design/tasks/execution-log)
  - Document the work retroactively per the-loop's own dogfooding rule (PR #71 review).
  - _Depends on:_ 7
  - _Requirements:_ process conformance
  - _Test:_ four artifacts present under `docs/specs/issue-70/`; markdownlint green.
- [x] 9. Include specs & reports; remove stale roadmap (PR #71 review round 2)
  - Drop `srcExclude`; generate the `docs/specs/` sidebar from the filesystem
    (`specSidebarGroups()`); add `docs/specs/index.md` + `docs/reports/index.md` overview
    pages and Developer-nav entries. Delete `docs/roadmap.md` (owner: stale/misleading)
    and update the few active references (guide, architecture, contributing, sync script,
    this spec).
  - _Depends on:_ 8
  - _Requirements:_ R3.1, R3.4
  - _Test:_ every spec artifact + report renders in `dist`; specs sidebar lists all work
    items; no `/roadmap` route; `docs:build` clean; `pre-commit run --all-files` green.
- [x] 10. Move the toolchain to bun + TypeScript (PR #71 review round 3)
  - Owner: "NO JS. Only TS." and "use bun … as the package manager and to run the
    scripts." Convert `sync-content.mjs` → `sync-content.mts` (typed), switch
    `package.json` scripts to `bun run`, replace `package-lock.json` with `bun.lock`,
    switch `docs.yml` to `oven-sh/setup-bun` + `bun install --frozen-lockfile`, and update
    references (contributing, decision-033, this spec).
  - _Depends on:_ 9
  - _Requirements:_ R4, R5.4
  - _Test:_ `bun install` + `bun run docs:build` clean; no `.mjs` / `package-lock.json` /
    `npm` remain in the docs toolchain; `pre-commit run --all-files` green.

## Dependency graph (DAG)

`1 → {2, 3, 4, 5} → 6 → 7 → 8 → 9 → 10`

## Checkpoints

- After tasks 1–6: `bun run docs:build` + `pre-commit run --all-files` (initial PR #71).
- After task 7: same gates re-run post-restructure.
- After task 8: markdownlint over the new spec; final `docs:build`.
- After task 9: `docs:build` renders specs/reports, no `/roadmap`; gates green.
- After task 10: `bun install` + `bun run docs:build` clean; toolchain is bun + `.mts` only.
- No security-review escalation: risk tier is low (public static site, no secrets, no
  runtime surface); `security.review` satisfied by the Security design section of
  `design.md`.
