---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#398"
status: approved
approvedBy: ["the-loop"]     # locked with design.md; tier 2
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: a logo for the-loop — the Ensō, chosen and adopted

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md).
> Planned at `test-planning`, results recorded at `verification` (below). Nothing here
> is code under test in the usual sense: the proof is that the generated files are what
> the generator makes and nothing more, that they render as intended in both schemes
> and at every size, and that a person has looked at the rendering.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes — as the generator's own checker | `generate.py --check`: every SVG and the gallery on disk are byte-identical to a fresh render (R3.3), well-formed XML with `<title>` and `<desc>` (R3.4), self-contained — for the HTML gallery: no script, foreignObject, image, iframe, `@import`, `src=`, `javascript:`, non-fragment `href` or `url(`, case-insensitively (R3.1, abuse case 1) — from the parsed tree: only allowlisted elements and attributes, fragment-only `mask`/`href`/`url` references, no `@import` — under 64 000 bytes (NFR, raised from 40 000 for round 2), and the render is deterministic within one process (R3.3) | `python3 docs/specs/issue-398/design/generate.py --check` |
| T2 | Integration (scenario) | n/a — no components interact; there is no runtime | | |
| T3 | Contract (OpenAPI) | n/a — no API | | |
| T4 | End-to-end (the adopted surfaces build) | yes — round 4 | **T4a** the docs site builds with the favicon, apple-touch icon, nav logo and hero image and the built output carries them; **T4b** the dashboard lints and builds with its favicon in `dist/` | `cd docs && bun install --frozen-lockfile && bun run docs:build` · `cd ui && bun install --frozen-lockfile && bun run lint && bun run build` |
| T5 | UI / visual | yes | the gallery renders in light and dark schemes; each standalone SVG, embedded as an `<img>` (the README/docs-site embedding), renders on paper under the light scheme and on slate under the dark scheme, so the file's own `prefers-color-scheme` rule is proved (R3.4, R2.2); the gallery shows each mark at 96/48/24/16 px and in the lockup (R3.2, R4.1) | `node docs/specs/issue-398/design/screenshots.mjs docs/specs/issue-398/design/screenshots` |
| T6 | Snapshot | yes — the byte-for-byte case of T1 | a regeneration leaves the working tree clean: the committed SVGs and gallery are the generator's exact output, so a hand edit or a drifting parameter shows as a diff | `python3 docs/specs/issue-398/design/generate.py && git diff --exit-code -- docs/specs/issue-398/design/` |
| T7 | Performance / load | n/a — static files; size is a T1 assertion | | |
| T8 | Security / abuse case | yes | an SVG embedded by a consumer executes and loads nothing: T1's allowlist check (parsed elements and attributes, fragment-only references), plus a negative probe that plants a `<script>`, an `onclick`, an external `<image>` and an `@import` and shows each refused | with T1; the probe in `evidence/automated-tests.md` § T8 |
| T9 | Accessibility | yes | every SVG has `<title>`/`<desc>` and `role="img"` (T1 checks the first two); the contrast of the ink on each ground is computed and recorded (9.9:1 on paper, 12.0:1 on slate) | with T1; contrast by the snippet recorded in `evidence/automated-tests.md` |
| T10 | Migration / upgrade | n/a — nothing existing changes | | |
| T11 | Manual exploratory | yes — the designer's review of the rendering | the owner looks at the gallery / screenshots and picks, or asks for changes, on the ticket (R4.3) | the ticket; outside this PR's verification |
| T12 | Lint | yes | markdownlint on the spec chain and — round 4, since the README, the guide and two capability docs changed — on **every** Markdown file, as the hook does; `ruff format --check` and `ruff check` on the generator (by hand — the hook scopes to `cli/`) | `npx --yes markdownlint-cli2@0.18.1 "**/*.md"` · `uv run ruff format --check --line-length 88 docs/specs/issue-398/design/generate.py && uv run ruff check --select E,F,W,I,UP,B --line-length 88 docs/specs/issue-398/design/generate.py` |
| T13 | UI / visual (adopted surfaces) | yes — round 4 | the built docs site's home page in both appearances, with the nav logo, hero image and favicon; the Slack-icon raster viewed at size | `node docs/specs/issue-398/design/screenshots.mjs --site http://127.0.0.1:4173/the-loop/` against `bun run docs:preview --port 4173`; the raster is `docs/assets/the-loop-logo-1024.png` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R3.1, R3.3, R3.4, NFR size, abuse case 1 | the six generated files match, parse, are titled, contain only allowlisted elements and attributes with fragment-only references, are under budget; a second render in the same process is identical |
| T8 | abuse case 1 | a planted `<script>`, `onclick`, `<image href="http…">` and `@import` each fail the allowlist; `href="#…"` and `url(#…)` pass |
| T1 (red first) | R3.3 | `--check` against an empty folder fails with one `missing` per file; after `generate.py` it passes — the red→green of the checker (recorded in the first commit) |
| T5 | R2.1, R2.2, R3.2, R3.4, R4.1, R4.2 | `gallery-light.png`, `gallery-dark.png`; `option-N-*-paper.png` (light scheme) and `option-N-*-slate.png` (dark scheme) for each of the five |
| T6 | R3.3, R4.3 | regenerate → no diff |
| T9 | R3.4 | title/desc present (T1); contrast table |
| T11 | R1.1–R1.3, R2, R4.3 | the owner's comment on the ticket |
| T12 | NFR lint | markdownlint and ruff clean |

## Verification environment

- **Repositories:** this repository only, at the PR's head.
- **Services / containers:** none.
- **Fixtures & data:** none — the generator has no inputs.
- **Credentials:** none.
- **Bring-up:** for T5 only — the Chromium Playwright drives, as `ui/scripts/screenshots.mjs`
  already uses: `npm i --no-save playwright` in a directory above the script (or a
  `node_modules` link beside it), `CHROMIUM_PATH` pointing at a Chromium when Playwright
  did not download one, `CHROMIUM_NO_SANDBOX=1` only where Chromium cannot start
  sandboxed (a root container). **Tear-down:** remove the `node_modules` link.
- **If bring-up fails:** T5 stays unticked and the PR is not requested for review without
  its screenshots — the options are unreviewable without a rendering.

## Evidence plan

| Row | Evidence | Path under `evidence/` (or `design/`) |
|-----|----------|------------------------|
| T1, T6, T9, T12 | the commands and their raw output | `evidence/automated-tests.md` |
| T5 | one PNG per capture: the gallery in each scheme, each option on paper and on slate | `design/screenshots/*.png` (per `design.uiArtifacts.screenshotEvidence`), listed in `evidence/automated-tests.md` |
| T11 | the owner's ticket comment | the ticket; linked from `design.md`'s inventory once recorded |

## Verification activities

- [x] T1 — `python3 docs/specs/issue-398/design/generate.py --check`
- [x] T5 — `node docs/specs/issue-398/design/screenshots.mjs docs/specs/issue-398/design/screenshots`
- [x] T6 — `python3 docs/specs/issue-398/design/generate.py && git diff --exit-code -- docs/specs/issue-398/design/`
- [x] T8 — the negative probe against `svg_problems` / `EXTERNAL_REF`
- [x] T9 — title/desc (in T1) and the contrast snippet
- [x] T12 — markdownlint on every Markdown file; ruff format and check on the generator
- [x] T4a — `cd docs && bun install --frozen-lockfile && bun run docs:build`
- [x] T4b — `cd ui && bun install --frozen-lockfile && bun run lint && bun run build`
- [x] T13 — `screenshots.mjs --site` against the preview server; the 1024 px raster viewed
- [x] T11 — the owner's review of the rendering: three reviews on the PR, ending in the pick of colourway 5 (2026-09-21)

## Verification results

Recorded on the branch of the delivering PR — 2026-09-20 for rounds 1 and 2, and
**re-run for round 3** on 2026-09-21 after the owner's pick; raw output in
[`evidence/automated-tests.md`](evidence/automated-tests.md).

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `python3 docs/specs/issue-398/design/generate.py --check` | pass — `ok — 11 files match, well-formed, self-contained, titled` (round 1: red first, six `missing` before the first render; round 2: red first on the 40 kB budget, then green at 64 kB; round 3: green on the widened allowlist, ten SVGs of 42–53 kB) | `evidence/automated-tests.md` |
| T5 | `node docs/specs/issue-398/design/screenshots.mjs docs/specs/issue-398/design/screenshots` | pass — 22 round-3 captures; the dark-scheme `<img>` captures show the light ink and the running-dry ramp's dark fills, so each standalone file's own media rules hold; the sweep gradient renders on both grounds | `design/screenshots/` |
| T6 | regenerate, then `git diff --exit-code -- docs/specs/issue-398/design/` | pass — clean tree (round 3 files: 42–53 kB; the gallery 452 kB against the amended 500 kB budget) | `evidence/automated-tests.md` |
| T8 | the probe snippet in `evidence/automated-tests.md` § T8 | pass — six refusals for the planted constructs (round 3 also refuses a non-fragment `fill="url(…)"`), two passes for fragments | `evidence/automated-tests.md` |
| T9 | T1's title/desc assertion; contrast snippet | pass — ink 9.9:1 on paper, 12.0:1 on slate; accents 2.0–2.8:1 / 4.8–6.8:1 (decorative) | `evidence/automated-tests.md` |
| T12 | markdownlint on every Markdown file; ruff format --check; ruff check | pass — 1307 files, 0 errors; ruff clean | `evidence/automated-tests.md` |
| T4a | `cd docs && bun install --frozen-lockfile && bun run docs:build` | pass — build complete; `dist/` carries `favicon.svg`, `logo-light.svg`, `logo-dark.svg`, `apple-touch-icon.png`; `index.html` links the favicon and the logo | `evidence/automated-tests.md` |
| T4b | `cd ui && bun install --frozen-lockfile && bun run lint && bun run build` | pass — oxlint clean, built; `dist/favicon.svg` and the `<link rel="icon">` in `dist/index.html` | `evidence/automated-tests.md` |
| T13 | `screenshots.mjs --site` against `bun run docs:preview --port 4173`; the raster viewed | pass — `design/screenshots/site-home-light.png`, `site-home-dark.png`; the 1024 px icon reads on paper with its inset | `design/screenshots/`, `docs/assets/the-loop-logo-1024.png` |
| T11 | the owner's reviews on PR #403 | done — round 1 → "no character"; round 2 → the Ensō; round 3 → colourway 5 and the adoption ask | the PR's review threads |

**Not executed:** the Slack app icon upload (R5.5) — Slack's manifest carries no icon and
the app's settings are the owner's; the guide describes the step and the raster is
committed. The ticket rests at `loop:needs-review` until the owner merges and uploads.

## Review comments

None yet.
