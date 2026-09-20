---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#398"
status: approved
approvedBy: ["the-loop"]     # locked with design.md; tier 2
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: a logo for the-loop — five hand-drawn SVG options to choose from

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md).
> Planned at `test-planning`, results recorded at `verification` (below). Nothing here
> is code under test in the usual sense: the proof is that the generated files are what
> the generator makes and nothing more, that they render as intended in both schemes
> and at every size, and that a person has looked at the rendering.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes — as the generator's own checker | `generate.py --check`: every SVG and the gallery on disk are byte-identical to a fresh render (R3.3), well-formed XML with `<title>` and `<desc>` (R3.4), self-contained — no script, foreignObject, image, iframe, `url(`, `@import`, `src=`, non-fragment `href` (R3.1, abuse case 1) — under 40 000 bytes (NFR), and the render is deterministic within one process (R3.3) | `python3 docs/specs/issue-398/design/generate.py --check` |
| T2 | Integration (scenario) | n/a — no components interact; there is no runtime | | |
| T3 | Contract (OpenAPI) | n/a — no API | | |
| T4 | End-to-end | n/a — nothing is deployed or embedded yet; embedding is the adoption follow-up | | |
| T5 | UI / visual | yes | the gallery renders in light and dark schemes; each standalone SVG, embedded as an `<img>` (the README/docs-site embedding), renders on paper under the light scheme and on slate under the dark scheme, so the file's own `prefers-color-scheme` rule is proved (R3.4, R2.2); the gallery shows each mark at 96/48/24/16 px and in the lockup (R3.2, R4.1) | `node docs/specs/issue-398/design/screenshots.mjs docs/specs/issue-398/design/screenshots` |
| T6 | Snapshot | yes — the byte-for-byte case of T1 | a regeneration leaves the working tree clean: the committed SVGs and gallery are the generator's exact output, so a hand edit or a drifting parameter shows as a diff | `python3 docs/specs/issue-398/design/generate.py && git diff --exit-code -- docs/specs/issue-398/design/` |
| T7 | Performance / load | n/a — static files; size is a T1 assertion | | |
| T8 | Security / abuse case | yes — abuse case 1 is T1's self-containment assertion | an SVG embedded by a consumer executes and loads nothing | with T1 |
| T9 | Accessibility | yes | every SVG has `<title>`/`<desc>` and `role="img"` (T1 checks the first two); the contrast of the ink on each ground is computed and recorded (9.9:1 on paper, 12.0:1 on slate) | with T1; contrast by the snippet recorded in `evidence/automated-tests.md` |
| T10 | Migration / upgrade | n/a — nothing existing changes | | |
| T11 | Manual exploratory | yes — the designer's review of the rendering | the owner looks at the gallery / screenshots and picks, or asks for changes, on the ticket (R4.3) | the ticket; outside this PR's verification |
| T12 | Lint | yes | markdownlint on the spec chain (the repository's hook); `ruff format --check` and `ruff check` on the generator (by hand — the hook scopes to `cli/`) | `npx --yes markdownlint-cli2@0.18.1 "docs/specs/issue-398/**/*.md"` · `uv run ruff format --check --line-length 88 docs/specs/issue-398/design/generate.py && uv run ruff check --select E,F,W,I,UP,B --line-length 88 docs/specs/issue-398/design/generate.py` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R3.1, R3.3, R3.4, NFR size, abuse case 1 | the six generated files match, parse, are titled, carry none of the forbidden tokens, are under budget; a second render in the same process is identical |
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
- [x] T9 — title/desc (in T1) and the contrast snippet
- [x] T12 — markdownlint on the spec; ruff format and check on the generator
- [ ] T11 — the owner's review of the rendering, on the ticket (not this PR's to tick)

## Verification results

Recorded on 2026-09-20 on the branch of the delivering PR; raw output in
[`evidence/automated-tests.md`](evidence/automated-tests.md).

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `python3 docs/specs/issue-398/design/generate.py --check` | pass — `ok — 6 files match, well-formed, self-contained, titled` (red first: six `missing` failures before the first render) | `evidence/automated-tests.md` |
| T5 | `node docs/specs/issue-398/design/screenshots.mjs docs/specs/issue-398/design/screenshots` | pass — 12 captures; the dark-scheme `<img>` captures show the light ink, so the standalone files' own media rule holds | `design/screenshots/` |
| T6 | regenerate, then `git diff --exit-code -- docs/specs/issue-398/design/` | pass — clean tree | `evidence/automated-tests.md` |
| T9 | T1's title/desc assertion; contrast snippet | pass — ink 9.9:1 on paper, 12.0:1 on slate; accents 2.0–2.8:1 / 4.8–6.8:1 (decorative) | `evidence/automated-tests.md` |
| T12 | markdownlint; ruff format --check; ruff check | pass | `evidence/automated-tests.md` |

**Not executed:** T11 — the designer's review is the owner's act on the ticket, requested
by the comment R4.3 requires; it is the reason the ticket rests at `loop:needs-review`
rather than `loop:complete`.

## Review comments

None yet.
