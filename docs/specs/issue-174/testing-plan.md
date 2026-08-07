---
type: testing-plan
phase: test-planning
workItem: "174"
status: approved
approvedBy: [MadaraUchiha-314]
overrides: {}
---

# Testing plan: the public docs describe two loops, and describing them becomes a gate

> Derived from the approved `requirements.md` and `design.md`, **before** `tasks.md` —
> each task's `_Test:_` names a row of the matrix below. Authored at the `test-planning`
> node and **completed at the `verification` node**.
>
> **This file is executable content.** It names commands an agent will run. Credentials
> appear by reference only; this work item needs none.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | The graph-parity suite: P5c proves the newly gated `Documentation` section exists in the bundled `execution-log.md` template, over **both** shipped loops; P5a/P5b prove the gate still resolves an artifact the manifest tracks; P4 proves the phase sequence the README and site copy | `uv run --project cli pytest cli/tests/test_graph_parity.py -v` |
| T2 | Integration (scenario) | **yes — replanned at implementation** | Originally `n/a`, on the reasoning that one element of a `sections:` list has no integration surface. Wrong: `test_graph_review_chain_integration.py` evaluates the **shipped** graph's review-chain nodes end to end against real execution logs, and adding a second section failed it. The row now proves the gate's real behaviour — neither gated section stands in for the other | `uv run --project cli pytest cli/tests/test_graph_review_chain_integration.py -v` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — the control-plane API is untouched; no path, body or response changes | | |
| T4 | End-to-end | n/a — no runtime path changes; the daemon, the dispatcher and both loops' edges are byte-identical apart from one list element T1 covers | | |
| T5 | UI / visual (product) | n/a — the-loop has no product UI (`design.uiArtifacts.format: html`, none authored). The documentation site is rendered markdown, checked by T6. The README's *diagram* is visual and is covered by T13 | | |
| T6 | Docs lint & render | yes | Every changed markdown file passes `markdownlint` — the repo's docs linter, run by the same pre-commit hooks CI runs — and the site's rendering constraints hold (no raw HTML, no em dash in a heading) | `pre-commit run markdownlint --all-files` |
| T7 | Performance / load | n/a — one additional string comparison per `capability-docs` evaluation | | |
| T8 | Security / abuse case | yes | Fail-closed: an execution log **missing** the newly gated section does not pass `capability-docs`. Proved by the same resolver/gate assertions T1 runs, plus the full suite's existing `validate-artifacts` absent-section coverage | `uv run --project cli pytest cli/tests/test_graph_parity.py cli/tests/test_graph_hooks.py -v` |
| T9 | Accessibility | n/a — no UI; the site's own accessibility is VitePress's and is unchanged | | |
| T10 | Migration / upgrade | yes | The in-flight-work-item consequence `design.md` §Error handling states is real and bounded: every execution log in this repository is checked for the new section, so "which work items would this newly block" is answered with a command rather than an assumption | `grep -L '^## Documentation' docs/specs/*/execution-log.md` |
| T11 | Manual exploratory | yes | Read the rendered README and the three changed site pages as a first-time reader: does R1's ordering hold, does every link resolve, does the phase list match the graph | manual, evidence recorded |
| T13 | UI / visual (the diagram) | **yes — added at review** | R5's diagram: the exported SVG is rendered in a browser and read against both shipped graph YAMLs (node names, the inner loop's start node, the steps it omits), and checked for self-containment — Virgil embedded as a data URI, no external URL, no scripting construct. The `.excalidraw` scene must parse and the SVG must carry the embedded scene payload | headless Chromium screenshot + `grep`, evidence recorded |
| T12 | Whole-suite regression | yes | The full CLI suite still passes — the graph is package data, so a malformed edit fails at graph-compile time in tests far from `test_graph_parity.py` | `make check` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R4.2, R4.4, R4.5 | P5c over both shipped loops: every section a node gates exists in that artifact's bundled template |
| T1 | R1.4, R3.3 | P4: the graph defines the phase sequence the prose renders |
| T2 | R4.2, R4.3 | `Scenario: a node gating two sections is not satisfied by one of them` — the capability docs written, the user-facing docs not, and the node blocks (asserted in both directions) |
| T2 | R4.4 | `Scenario: the template an agent authors from can pass all six gates` — the unedited bundled template clears the new gate too |
| T6 | R1.*, R2.*, R3.* | markdownlint passes on `README.md`, `docs/index.md`, `docs/guide/*.md`, `docs/capabilities/*.md` and this spec chain |
| T8 | R4.3 (fail closed) | A gated section that is absent blocks the node; a content gate that resolves no artifact blocks non-retriably (decision-063, unchanged) |
| T10 | design §Error handling | No execution log in the repository is left silently newly-blocked |
| T11 | R1.1–R1.3, R2.1–R2.4, R3.1–R3.2 | A first-time reader meets the graph before the plugin, the two loops before the phase list, and a working link out to the site |
| T13 | R5.1, R5.2 | The rendered diagram names the same nodes as `pdlc-work-item-loop.yaml` and `pdlc-pr-loop.yaml`, starts the inner loop at `implementation`, and omits the two nodes the inner loop does not declare |
| T13 | R5.3, R5.4, R5.5, R5.6 | One diagram in the README (no mermaid twin); the SVG is self-contained and script-free; both artifacts re-open in Excalidraw; the generator is committed |
| T13 | R5.7 | The site embeds the same SVG: `bun run docs:build` succeeds and emits the asset, and the built page references it at the correct base path |
| T12 | all | No regression in the 1400+ test suite |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none.
- **Fixtures & data:** none — the parity suite reads the shipped graph YAMLs, the bundled
  templates and `.the-loop/manifest.yaml` off the filesystem.
- **Credentials:** none. This work item reads and writes checked-in markdown and YAML only.
- **Bring-up:** `make install-dev` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate — do not pass the gate on an environment that never
  came up.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8 | parity + gate-integration + hook test output (counts, names, duration), and the red→green transition | `tests.md` |
| T6 | markdownlint output over all files | `lint-and-types.md` |
| T10 | the migration sweep's command and its full output | `tests.md` |
| T11 | the reader's pass: the link/anchor inventory and the phase-list comparison | `docs-review.md` |
| T13 | the rendered diagram (PNG), the node-by-node comparison against both graphs, the self-containment greps, and the committed generator | `diagram.md`, `diagram/workflow-rendered.png`, `diagram/generate-scene.py` |
| T12 | `make check` output (ruff, pyright, schema validation, pytest totals) | `lint-and-types.md` |

Nothing captured here can contain a secret: the outputs are test names, lint findings and
markdown paths. Each file is titled, sectioned per command, with raw output in fenced
blocks.

## Verification activities

- [x] T1 — `uv run --project cli pytest cli/tests/test_graph_parity.py -v`
- [x] T2 — `uv run --project cli pytest cli/tests/test_graph_review_chain_integration.py -v`
- [x] T6 — `npx markdownlint-cli2@0.18.1 "**/*.md"` (the exact command `make lint` runs)
- [x] T8 — `uv run --project cli pytest cli/tests/test_graph_review_chain_integration.py cli/tests/test_graph_hooks.py -q`
- [x] T10 — `grep -L '^## Documentation' docs/specs/*/execution-log.md`
- [x] T11 — manual read of `README.md`, `docs/index.md`, `docs/guide/what-is-the-loop.md`, `docs/guide/how-it-works.md`
- [x] T13 — headless-Chromium render of `docs/assets/the-loop-workflow.svg` + self-containment greps
- [x] T13b — `bun run docs:build` (the site build, to prove the shared asset resolves)
- [x] T12 — `make check`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| red→green | `pytest …test_graph_parity.py -k p5c` before, then after, the template change | **red then green** — the red names the node, the artifact and the section | [`evidence/tests.md`](evidence/tests.md) |
| T1 | `uv run --project cli pytest cli/tests/test_graph_parity.py -v` | **pass** — 8 passed; P5a/b/c over both shipped loops, P4 in both config variants | [`evidence/tests.md`](evidence/tests.md) |
| T2 | `uv run --project cli pytest cli/tests/test_graph_review_chain_integration.py -v` | **pass** — 25 passed, including the new both-directions negative test | [`evidence/tests.md`](evidence/tests.md) |
| T6 | `npx markdownlint-cli2@0.18.1 "**/*.md"` | **pass** — 451 files, 0 errors (4 MD049 findings raised and fixed during implementation) | [`evidence/lint-and-types.md`](evidence/lint-and-types.md) |
| T8 | `pytest test_graph_review_chain_integration.py test_graph_hooks.py -q` | **pass** — 67 passed; a log missing either gated section blocks, and an absent log blocks non-retriably | [`evidence/tests.md`](evidence/tests.md) |
| T10 | `grep -L '^## Documentation' docs/specs/*/execution-log.md` | **pass, with a finding recorded** — 55 of 56 logs lack the section, but all 55 belong to closed work items; the only other open item has no spec directory at all | [`evidence/tests.md`](evidence/tests.md) |
| T11 | manual read of the README and the three changed site pages | **pass** — ordering per R1, all 20 links resolved to files, phase sequence identical to the graph's | [`evidence/docs-review.md`](evidence/docs-review.md) |
| T13 | headless-Chromium render + `grep` for scripts, external URLs, embedded font and scene payload | **pass** — every node matches the shipped graphs; 0 scripting constructs; the only URL is the SVG namespace; 1 data-URI `@font-face`; scene payload present; scene parses (72 elements) | [`evidence/diagram.md`](evidence/diagram.md) |
| T13b | `bun run docs:build` | **pass** — build complete in 46s; the SVG is emitted to `assets/the-loop-workflow.<hash>.svg` at its full 143 002 bytes and the built page references it as `/the-loop/assets/…`, so the shared asset resolves under the site's base path | [`evidence/diagram.md`](evidence/diagram.md) |
| T12 | `make check` | **pass** — ruff, ruff-format, markdownlint, pyright (0 errors), schema validation (6 files VALID), 1424 passed / 1 skipped | [`evidence/lint-and-types.md`](evidence/lint-and-types.md) |

**Not executed:** none. Every row the matrix marks `yes` ran; every `n/a` row carries its
reason there. Two rows changed after the plan was locked, and both changes are recorded
rather than edited out:

- **T2 was replanned during implementation.** Planned `n/a`, it turned out to have real
  coverage; it was promoted to `yes`, executed, and the reasoning that got it wrong is
  still in the matrix.
- **T13 was added at PR review**, when the owner's comments produced R5. A new requirement
  gets a new row; it does not get folded into a neighbouring one.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed.
