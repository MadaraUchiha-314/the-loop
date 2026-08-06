---
type: execution-log
workItem: issue-163
phase: needs-review
status: in-progress
---

# Execution Log: test and verification as nodes in the PDLC

> Append-only log of progress. The-loop keeps the work item's `loop:<phase>` label in sync
> with the `phase` front-matter above.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-06 | *pending — on the PR* | Six requirements drawn from the ticket's six bullets. Risk tier raised to 4 by `autonomy.inferFromChange`: the change touches `.the-loop/harness-config.yaml` and `**/*schema*`, both `autonomy.sensitivePaths`. |
| design | 2026-08-06 | *pending — on the PR* | Six decisions (D1–D6); all three open questions from requirements resolved. Two nodes, one new artifact, no new runtime concepts. D1/D2 revised on PR #166: the plan is reviewed at the design gate. |
| test-planning | 2026-08-06 | *pending — on the PR* | 15-row matrix, 7 applicable + 8 `n/a`-with-reason. This work item is the first to carry the artifact it introduces. |
| tasks-breakdown | 2026-08-06 | *pending — on the PR* | 11 tasks; a 12th (the chain-semantics fix, T11) was added during implementation, see below. |
| implementation | 2026-08-06 | — | All tasks complete. |
| verification | 2026-08-06 | — | All 8 planned activities executed and ticked; results + evidence in `testing-plan.md`. |
| needs-review | 2026-08-06 | *pending* | Suite 1328 passed / 1 skipped; ruff, pyright, markdownlint, schema validation clean. Tier 4 (`human-approves-pr`) plus a named human security sign-off (`security.review.humanSignOffMinTier: 4`). |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#166](https://github.com/MadaraUchiha-314/the-loop/pull/166) | The whole work item — spec chain, graph nodes, template, configs, tests, docs | open, in review |

## Progress entries

### 2026-08-06 — spec chain drafted (requirements → design → testing plan → tasks)

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** Audited how testing actually reaches the loop today and confirmed the ticket's
  premise: `design.md` carries one paragraph of strategy, `tasks.md` a `_Test:_` per task,
  and the graph's only test hook (`verify-tests`) is a no-op unless a node binds a
  command — which no shipped node does. Everything after `implementation` is about
  opinion, not proof. Drafted `requirements.md` (R1 the plan is a locked artifact, R2 the
  type matrix with `n/a`-and-a-reason, R3 verification as a node, R4 evidence captured not
  described, R5 facilitate-don't-own, R6 one process described once), then `design.md`
  (D1–D6), then this work item's own `testing-plan.md`, then `tasks.md`.
- **Key design call (D3):** `verification` re-gates the *same* `testing-plan.md` rather
  than minting a `verification-report.md` — the produce-then-re-gate shape
  `tasks-breakdown` → `implementation` already uses for `tasks.md`. One artifact, one
  diff, intent beside outcome, and no new template/manifest/parity surface.
- **Checkpoint/tests:** none yet (no code).

### 2026-08-06 — implementation: two nodes, one artifact, and a defect found on the way

- **Phase:** implementation → verification
- **Did:** Executed the DAG.
  - **T1** `skills/the-loop/templates/testing-plan.md` — the four gated sections, the
    11-type catalogue, the activities checklist, and the two security rules
    (credentials by reference; redact evidence) written where the author will read them.
  - **T2** `pdlc.yaml` — `test-planning` (between `design-approval` and
    `tasks-breakdown`) and `verification` (between `implementation` and `self-review`),
    edges rerouted.
  - **T3/T4** manifest entries (`testing-plan.md` @ `test-planning`, `evidence/` optional
    directory); `workflow.phases` enum + default and both harness configs; `tokenEconomy`
    stage entries so routing does not fall through a hole.
  - **T5/T6** unit + integration coverage, the latter driving the **shipped** graph over a
    temp spec folder rather than a fixture graph, because what is under test is the node
    declarations themselves.
  - **T7–T10** the skill, `reference/workflow.md`, `reference/testing.md`,
    `reference/context.md`, three templates, five commands (two new:
    `create-testing-plan`, `verify-work`), README/guide/architecture phase sequences,
    the labels report, three capability docs and `decision-060`.
- **Defect found while writing T6 (not in the original task list):** `run_chain`
  short-circuited on the first result that was not `pass` — **including `skip`**. Two
  consequences: hooks *after* a skipping one never ran (`design`'s `lint-artifacts` sits
  behind an `enforces-boundaries-from` that skips whenever the upstream is absent), and a
  chain *ending* in a skip routed on the outcome `"skip"`, for which no edge is declared —
  so `implementation`, whose chain ends in a `verify-tests` that is a no-op unless a
  command is bound, parked at `no_edge` and escalated instead of advancing. The
  `implementation → verification` edge this work item adds would have been unreachable.
  Fixed in `graph/chain.py` (a skip is not a decision; the chain runs on past it),
  covered by `TestASkipIsNotADecision` and by
  `test_implementation_reaches_verification_rather_than_parking`, and recorded in
  decision-060. `NodeReport.satisfied` already treated skip as satisfied — the chain now
  agrees with it.
- **Deviation from design, with reason:** the design's node sketch listed `verify-tests`
  on the `verification` node as a declared seam; it is kept, and is now harmless because of
  the chain fix. Had the chain fix not landed, that hook alone would have made the new
  node unable to pass.
- **Checkpoint/tests:** full suite **1326 passed, 1 skipped**; ruff, pyright,
  markdownlint (406 files) and schema validation clean.

### 2026-08-06 — verification: the plan, executed

- **Phase:** verification
- **Did:** Ran all 8 planned activities from `testing-plan.md`, ticked each only after its
  evidence was recorded, and filled the plan's **Verification results** table with the
  command, outcome and evidence link per activity. Committed the evidence under
  `docs/specs/issue-163/evidence/` — test summaries, lint/typecheck/validate output, and
  the seven new scenario rows from `the-loop scenarios --format markdown`. Nothing captured
  touches a credential, hostname or personal data (the commands are local test runners over
  this repository), so no redaction was needed — recorded in the plan's evidence section.
  No activity went unexecuted.
- **Checkpoint/tests:** see `testing-plan.md` § Verification results.
- **Next:** self-review rounds, security review, capability-doc fold-in check, reviewer
  briefing on the PR.

### 2026-08-06 — owner feedback on PR #166, actioned

- **Phase:** needs-review
- **Did:** Owner answered all four open questions on
  [PR #166](https://github.com/MadaraUchiha-314/the-loop/pull/166):
  - **Labels** — `loop:test-planning` (`#6f42c1`) and `loop:verification` (`#1f883d`)
    created in this repository with the descriptions and colours
    `docs/reports/labels-and-dashboards.md` documents, so the report and the repository
    now agree.
  - **The skipping-gates gap** — filed as
    [issue-167](https://github.com/MadaraUchiha-314/the-loop/issues/167). Enumerating it
    for the ticket corrected the count I gave in round 1: it is **six** nodes, not four —
    `critic-review` and `security-review` are also affected, and `security-review` is
    `required: true`. A latent second defect rides along: `capability-docs` gates on a
    `Capability docs` section the execution-log template does not offer, invisible only
    because the node skips.
  - **Fail-closed upgrade behaviour** for in-flight items with no `testing-plan.md` —
    confirmed as intended.
  - **`uv.lock`** — accepted.
- **Checkpoint/tests:** no code change; `make lint` clean.

### 2026-08-06 — PR review: one gate for the design and the testing plan

- **Phase:** needs-review
- **Did:** Owner asked on [PR #166](https://github.com/MadaraUchiha-314/the-loop/pull/166)
  whether `testing-plan.md` could be produced with `design.md` so the design approval gate
  also covers the plan. Yes — implemented as a **reorder rather than a merge**:
  `design → test-planning → design-approval → tasks-breakdown`.
  - The plan is still its own node, so it keeps its `phase`, its `loop:test-planning`
    label and a `validate-artifacts` call whose `sections:` list is about *that* artifact.
    Folding it into the `design` node (the literal suggestion) would have given one
    sections list for two files, so a missing **Test matrix** and a missing
    **Architecture** would be indistinguishable in the block message.
  - `design-approval` now declares `record-feedback` **twice**, into `design.md` and into
    `testing-plan.md`: a reviewer's note about the test matrix belongs in the plan, and
    feedback travelling with the document it concerns is what the hook exists for.
  - `changes-requested` returns to **`design`**, not to `test-planning`, so a changed
    design re-derives the plan on the way back through — the plan can never be approved
    against a design that moved under it.
  - Nothing in the config, schema, manifest or template needed to change: node
    *declaration* order still puts `test-planning` between `design` and `tasks-breakdown`,
    which is all P4 reads, and `design-approval` carries no phase.
- **Spec updated, not re-stated:** requirements R1.1 / out-of-scope / open question 2,
  design D1–D2, decision-060 (D1, D2 and a new rejected alternative), the skill, the
  workflow and testing references, `create-design` / `create-testing-plan` / `work-on`,
  and three capability docs.
- **Checkpoint/tests:** three new assertions in `TestTestingIsPlannedAndVerifiedAsNodes`
  (the edge order, the `changes-requested` target, both feedback targets) — red→green.
  Full suite **1328 passed, 1 skipped**; lint, typecheck, format and validate clean.
  Evidence re-captured from this second pass.

### 2026-08-06 — self-review and the ready-to-ship gate

- **Phase:** needs-review
- **Self-review:** 3 rounds.
  1. *Correctness of the gates.* Checked that each new gate actually runs rather than
     skipping — which is how `verification` came to re-declare `produces`, and how the
     `skip` short-circuit was found. Re-read `validate-artifacts`: a node with no
     `produces` returns `skipped`, so **all six** post-implementation nodes that gate on
     execution-log sections (`self-review`, `critic-review`, `security-review`,
     `evidence`, `capability-docs`, `reviewer-briefing`) are *also* skipping today —
     `security-review` among them, despite `required: true`. **Deliberately left alone**
     — it is a pre-existing gap in issue-109/148 territory, and fixing it means deciding
     what these nodes validate against (their output is sections of the execution log,
     not a spec artifact). Not folded into a testing work item; filed as
     [issue-167](https://github.com/MadaraUchiha-314/the-loop/issues/167) at the owner's
     request on PR #166. This change neither worsens nor depends on it.
  2. *Blast radius of the chain fix.* The chain-semantics change touches every node
     evaluation in the product, which is why T6 (full suite) is in the matrix rather than
     just the graph suites. 1326 pass. Blocking and waiting semantics are untouched; only
     `skip` changed, and it changed in the direction `NodeReport.satisfied` already
     assumed.
  3. *Minimalism and docs.* No new dependency, no new hook, no new runtime concept — two
     node declarations and one template. Checked that no prose file now redefines the
     phase sequence: `SKILL.md` and `reference/workflow.md` both still defer to
     `pdlc.yaml`, and P4 enforces the configs against it. `reviews.critics` is empty in
     this repo's config, so no critic harness was run (recorded per config).
- **Security review (gate):** see below.
- **Capability docs:** folded in this PR — `testing-and-contracts.md` (the plan and the
  verification node), `spec-workflow.md` (the chain and the state machine),
  `process-graph.md` (the two nodes and the skip semantics), `capabilities.md` index.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | agent | new findings — `verification` needed `produces` or its gate would skip | fixed in `pdlc.yaml` |
| 2 | self | agent | new findings — `run_chain` short-circuits on `skip`; `implementation` cannot advance | fixed in `graph/chain.py` |
| 3 | self | agent | zero new actionable findings (converged); one pre-existing gap noted for its own ticket | — |
| — | critic | *unavailable* | `reviews.critics` is empty in `.the-loop/harness-config.yaml`, so no critic round ran — it does **not** count toward `criticReviewCount` | — |

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no
  security-review skill invocation was available in this session).
- **Outcome:** pass, with the boundaries recorded rather than mechanised.
  - **No new ingress.** Nothing in this change parses a payload, opens a socket or accepts
    remote input. The new nodes read checked-in markdown from the work item's own spec
    folder, through the existing `frontmatter` / `validate-artifacts` path.
  - **No gate weakened.** `security-review` remains `required: true`; the six
    post-implementation nodes are intact; `verification` sits *before* the review chain so
    a failed verification is visible to the reviewers. Asserted by
    `test_the_shipped_graph_splits_the_needs_review_label` and
    `test_the_verification_gate_is_not_a_silent_skip`.
  - **The chain-semantics change is the one item that warranted real scrutiny**, since it
    alters how *every* gate's verdict is computed. It only affects `skip`: `block` and
    `wait` still short-circuit, a raising hook is still a non-retriable block, and the
    change makes hooks *behind* a skipping one run that previously did not — strictly more
    gate coverage, never less. `design`'s `lint-artifacts` is the concrete beneficiary.
  - **Two boundaries are touched and handled by convention, not code**, which is stated
    plainly rather than implied: evidence under `evidence/` is repository-public and must
    be redacted before committing, and the plan names credentials by reference only. Both
    rules live in the bundled template where the author reads them, in
    `reference/testing.md`, and in both new commands. Automating redaction is explicitly
    out of scope (`requirements.md` § Out of scope) — a follow-up, not a silent omission.
  - **A testing plan is executable content** (it names commands an agent will run) and is
    reviewed as code, the same footing `reviews.critics[]` entries have had since
    decision-043. It reaches the repository only through PR review.
- **Human sign-off:** *pending* — effective risk tier 4 (raised by `inferFromChange`:
  `.the-loop/harness-config.yaml` and `.the-loop/harness-config.schema.json` are both
  `autonomy.sensitivePaths`), which is ≥ `security.review.humanSignOffMinTier: 4`.
  Requested with the PR review.

## Final validation evidence

Summarised from [`testing-plan.md`](testing-plan.md) § Verification results (the
`verification` node produced the raw record); committed evidence is under
[`evidence/`](evidence/).

| Requirement | Proved by | Result |
|---|---|---|
| R1 — the plan is a first-class, locked artifact, reviewed at the design gate | `test-planning` node + P1–P3 parity + 4 integration scenarios + the three shared-gate assertions | pass |
| R2 — the matrix records a decision per testing type | the bundled template's 11-row catalogue and the `n/a`-with-a-reason rule; this work item's own 15-row matrix is the worked example | pass (review-enforced by design, D5) |
| R3 — verification is a node executed against the plan | `verification` node, `checkmarks: complete` gate, 3 integration scenarios, `implementation → verification` reachability | pass |
| R4 — evidence is captured, not described | three committed evidence files under `evidence/`, referenced per activity in the results table | pass |
| R5 — facilitate without owning | no runner, orchestrator or dependency added; the environment is a declared markdown section | pass |
| R6 — one process, described once | P4 parity over both harness configs; `SKILL.md` and `reference/workflow.md` render the graph rather than redefining it; stage entries added for both new stages | pass |

Suite: **1328 passed, 1 skipped** (1322 before). ruff, pyright, `ruff format --check`,
markdownlint (406 files) and `scripts/validate_config.py` all clean.
