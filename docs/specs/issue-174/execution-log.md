---
type: execution-log
workItem: "174"
phase: needs-review
status: in-progress
---

# Execution Log: the public docs describe two loops, and describing them becomes a gate

> Append-only log of progress for the user's visibility. Checked in alongside the spec at
> `docs/specs/issue-174/execution-log.md`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-07 | MadaraUchiha-314 (issue body) | The issue states the owner's requirements directly; `requirements.md` renders them as EARS |
| design | 2026-08-07 | MadaraUchiha-314 | Two halves: the editorial rewrite, and one element added to a `sections:` list |
| test-planning | 2026-08-07 | MadaraUchiha-314 | Reviewed with the design, per the single design-approval gate |
| tasks-breakdown | 2026-08-07 | MadaraUchiha-314 | 7 tasks; 1+2 are the red→green pair |
| implementation | 2026-08-07 | | Tasks 1–6 |
| verification | 2026-08-07 | | Testing plan executed; one row replanned mid-flight |
| needs-review | 2026-08-07 | pending | Awaiting the human gate on the PR |
| complete | | | |

## Pull requests

> A work item may be delivered by several PRs; every one is listed here.

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#175](https://github.com/MadaraUchiha-314/the-loop/pull/175) | Tasks 1–7 — the whole work item, one PR, one session (no inner loops started) | open |

## Progress entries

### 2026-08-07 — spec chain authored

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** wrote `requirements.md`, `design.md`, `testing-plan.md` and `tasks.md`. Read the
  shipped graphs, the parity suite and the bundled templates first, so the design reuses
  issue-167's `validates:` machinery rather than adding a node.
- **Checkpoint/tests:** none — no code changed.
- **Next:** task 2 (gate the section, capture the red), then task 1 (the template, green).
- **Blockers:** none.

### 2026-08-07 — implementation (tasks 1–6)

- **Phase:** implementation
- **Did:** gated `## Documentation` on the outer loop's `capability-docs` node and added the
  section to the bundled execution-log template; wrote the rule into `SKILL.md` and
  `reference/workflow.md`; rewrote `README.md` around the graph, the two loops and the CLI
  (265 → 174 lines); brought `docs/index.md` and the two guide pages current; recorded
  decision-066 and folded in `documentation.md` and `process-graph.md`.
- **Checkpoint/tests:** the red→green pair captured verbatim in `evidence/tests.md`. Then
  `make check` surfaced a second failure the plan had not anticipated — see the next entry.
- **Next:** fix the review-chain integration test, then task 7.
- **Blockers:** none.

### 2026-08-07 — the testing plan was wrong about T2, and was replanned

- **Phase:** implementation → verification
- **Did:** `testing-plan.md` marked T2 (integration) `n/a`, reasoning that one element of a
  `sections:` list has no integration surface. `make check` disproved it:
  `test_graph_review_chain_integration.py` evaluates the **shipped** graph end to end and
  encoded "one gated section per node" in a `GATED` map, so `capability-docs` began failing
  its pass-case. Rather than delete the row, T2 was promoted to `yes` with the wrong
  reasoning left visible: `GATED` now maps a node to a tuple of sections, and a new test —
  `test_capability_docs_blocks_when_only_one_of_its_two_sections_is_written` — asserts in
  both directions that neither section stands in for the other. That is the property R4.2
  actually needs, and the plan had not been asking for it.
- **Checkpoint/tests:** 25 passed in `test_graph_review_chain_integration.py`; 1424 passed /
  1 skipped over the full suite (1423 on `main` — the one addition is that test).
- **Next:** execute the remaining activities and commit the evidence.
- **Blockers:** none.

### 2026-08-07 — verification (task 7)

- **Phase:** verification
- **Did:** ran T1, T2, T6, T8, T10, T11 and T12; ticked each activity only after it ran;
  filled `testing-plan.md` §Verification results; committed three evidence files.
- **Checkpoint/tests:** all green. T10's sweep produced a finding worth stating rather than
  burying: **55 of 56 existing execution logs lack the newly gated section.** All 55 belong
  to closed work items whose PRs merged; the only other open issue (#157) has no spec
  directory at all, so it already blocks on a missing execution log and is unaffected. The
  migration surface is therefore this work item alone — which carries the section.
- **Next:** the review chain.
- **Blockers:** none.

## Review cycles

> Outcome is one of: new findings · zero (converged) · escalated · **unavailable** (the
> configured critic could not run — it does NOT count toward `reviews.criticReviewCount`).

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | agent | **new findings** — the testing plan's Verification results and the execution log's review/security/evidence sections had been drafted *before* the activities ran. Both were reverted to their unexecuted state and refilled only from real command output | this log |
| 2 | self | agent | **new findings** — T2 was mis-scoped `n/a`; the plan was replanned and a negative test added (entry above) | `evidence/tests.md` |
| 3 | self | agent | **new findings** — the README claimed a line count that had not been measured (guessed 148, actual 174); every quantitative claim in the spec and evidence was re-derived from a command | `evidence/docs-review.md` |
| 4 | critic | — | **unavailable** — `reviews.critics[]` is empty in this repository's harness config, so no critic round could be spawned. Per `reference/reviewing.md` this does **not** count toward `reviews.criticReviewCount`; the human gate on the PR is the next reviewer | `.the-loop/harness-config.yaml` |

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`), applied to the
  full diff.
- **Outcome:** **pass.** The change edits checked-in markdown, one bundled template, one
  test module and one element of a node's `sections:` list. No new ingress, parser,
  subprocess, network call, credential path or permission; `validate-artifacts` performs the
  same structural heading match on a file it already opens for five sibling gates. The one
  behavioural change is strictly **more** fail-closed than before: an execution log missing
  `## Documentation` now blocks where it previously passed. Redaction check: all three
  evidence files hold test names, lint findings, counts and repository-relative paths only —
  no tokens, cookies, personal data or internal hostnames, and none of the added
  documentation embeds a credential or a hostname. The one abuse case the requirements
  raised that this change does **not** defeat is stated rather than papered over: a
  `## Documentation` heading holding placeholder text passes the structural check, exactly
  as `docs/capabilities/process-graph.md` already records for every section gate.
- **Human sign-off:** n/a — effective risk tier 3, below
  `security.review.humanSignOffMinTier` (4). No `autonomy.sensitivePaths` glob matches this
  diff: `**/*schema*` does not match `pdlc-work-item-loop.yaml`, and no workflow or config
  schema file is touched.

## Final validation evidence

Acceptance criteria, each mapped to the thing that proves it.

| Requirement | Proved by | Evidence |
|-------------|-----------|----------|
| R1.1–R1.3 — README leads with the graph, names both loops and the seam, lists four artifacts | Section-by-section read against the requirement text | [`evidence/docs-review.md`](evidence/docs-review.md) |
| R1.4, R3.3 — the phase sequence matches the shipped graph | `test_p4_the_graph_defines_the_phase_sequence` (both config variants) + the sequence printed from config and compared | [`evidence/tests.md`](evidence/tests.md), [`evidence/docs-review.md`](evidence/docs-review.md) |
| R2.1–R2.4 — minimal, delegating, absolute site links, an explicit next step | 265 → 174 lines; a table of what moved where; all 20 links resolved to files | [`evidence/docs-review.md`](evidence/docs-review.md) |
| R3.1, R3.2 — the site's three entry pages current | Per-page check table; markdownlint over 451 files, 0 errors | [`evidence/docs-review.md`](evidence/docs-review.md), [`evidence/lint-and-types.md`](evidence/lint-and-types.md) |
| R4.1 — the ready-to-ship gate names user-facing docs | `reference/workflow.md` §User-facing docs + the gate list; `SKILL.md` operating principle | in-diff |
| R4.2 — `## Documentation` gated alongside `## Capability docs` | `test_capability_docs_blocks_when_only_one_of_its_two_sections_is_written`, asserted both directions | [`evidence/tests.md`](evidence/tests.md) |
| R4.3 — fail closed; "none" recorded with a reason | The absent-section block still holds (25 passed); the template preamble states the rule | [`evidence/tests.md`](evidence/tests.md) |
| R4.4 — the bundled template satisfies the gate it declares | P5c, plus `test_the_bundled_template_can_clear_every_gate_in_the_chain[capability-docs]` | [`evidence/tests.md`](evidence/tests.md) |
| R4.5 — the inner loop gates neither section | P5a/b/c iterate **both** shipped loops and stay green with `pdlc-pr-loop.yaml` unchanged | [`evidence/tests.md`](evidence/tests.md) |
| Non-functional — lint, types, schema, no regression | `make check`: ruff, ruff-format, markdownlint, pyright 0 errors, 6 configs VALID, 1424 passed / 1 skipped | [`evidence/lint-and-types.md`](evidence/lint-and-types.md) |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`documentation.md`](../../capabilities/documentation.md) | Two new behaviour sections: the root README's delegating contract (lead with the graph, link the site, absolute URLs, no version-status block), and the completion gate for user-facing documentation | issue-174 row added |
| [`process-graph.md`](../../capabilities/process-graph.md) | A node may gate several sections of one artifact; `capability-docs` now gates two, with the reasoning for one node rather than two and for keeping the id and `stage` | issue-174 row added |

## Documentation

> Which **user-facing** documents this work item changed — `README.md`, the documentation
> site under `docs/`, and the operating-model skill with its `reference/` docs. This section
> is what the `capability-docs` node gates on, alongside `## Capability docs` (issue-174,
> decision-066). A row names a **document**, never a token, a credential or an internal
> hostname.

| Document | What changed |
|----------|--------------|
| `README.md` | Rewritten. Leads with the executable process graph and the daemon; then the two loops with a mermaid diagram and the `await-inner-loops` seam; then the four-artifact chain including `testing-plan.md`; then the CLI; then the plugins. The per-command tables, install matrix, layout tree, rules list, v0 status block and roadmap are gone — delegated to the site or deleted as drift generators. 265 → 174 lines |
| `docs/index.md` | Hero tagline leads with the graph; the four feature cards become *Two loops, one process* · *The process is executable* · *A CLI that drives it* · *Gated, reviewed, documented* |
| `docs/guide/what-is-the-loop.md` | Both loops with their sequences and a mermaid diagram; the four-artifact table with `testing-plan.md`'s plan-then-record role; the "v0 foundation" status block removed; the rules list gained test-planning, security gating and the documentation rule |
| `docs/guide/how-it-works.md` | New leading section "The process is data" — both shipped graph YAMLs, the node/hook/edge model, and four consequences (internal to the-loop, gates read artifacts, a force never forges a verdict, the graph assigns). Repository layout refreshed with `cli/the_loop/graph/`, `docs/api-specs/`, `skills/writing/`, `testing-plan.md` and `evidence/` |
| `skills/the-loop/SKILL.md` | New operating principle: the user-facing docs ship with the change, recorded in the log's `## Documentation` section |
| `skills/the-loop/reference/workflow.md` | New "User-facing docs" fold-in section, and the ready-to-ship gate's documentation item |
| `skills/the-loop/templates/execution-log.md` | The `## Documentation` section the gate reads, with its preamble |
| `docs/decisions/decision-066.md` (+ index) | The decision record behind the gate, including the four rejected alternatives |
