---
type: evidence
workItem: "issue-543"
---

<!-- Written per the `the-loop:writing` skill. -->

# Final validation: PR-scoped specs for multi-PR work items

## The short version

Every acceptance criterion is proved by a test that ran: seven verification activities
passed, and T11 ran in part, which the owner accepted. After the reviews tightened the
verb, `make check` was run again at `4372de01`. It exits 0, with 7200 tests passed,
pyright and markdownlint clean. This table summarises `testing-plan.md` § Verification
results and the review records. It does not re-derive them.

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| **R1 — which PRs carry a PR spec** (single-PR none; multi-PR all, including the origin's own PR; late multi-PR caught; `sessions: never` checked at the outer node; a declared skip recorded as skipped) | Unit tests of `applicability` and the hook's three placements. Integration scenarios 1 and 3. T10 (graph shape, only `pr-spec` skippable). Hardened in the security review: a PR outside the origin is always multi-PR. | [unit.md](unit.md), [integration.md](integration.md), [security-review.md](security-review.md) |
| **R2 — what a PR spec contains** (four files, Context first, front matter, no `status`, the path rule) | The verb's file checks, and `test_required_sections_match_the_templates`. T6 keeps the templates in the writing-parity set. | [unit.md](unit.md), [contract-and-snapshot.md](contract-and-snapshot.md) |
| **R3 — derived, not forked** (every item cites; unresolved citations refused; derived from an approved chain only) | Citation-grammar and `ChainIndex` tests, plus the verb's chain-approval check. After the critic review, `sourceRevision` must also resolve in the origin repository. | [unit.md](unit.md), [critic-review.md](critic-review.md) |
| **R4 — the inner loop derives, commits and gates** (`pr-spec` start node; record written once; offline gate) | Integration scenario 1 (blocks, then passes once recorded). T3 (API contract parity for `POST /graph/pr-spec`). After the critic review, files that are not committed are refused. | [integration.md](integration.md), [contract-and-snapshot.md](contract-and-snapshot.md) |
| **R5 — a stale PR spec is caught** (digest recomputed; changed files named; front-matter locks ignored; `--still-valid` by an authorized human) | Integration scenario 2 (stale, then `--still-valid`, then pass). Hook staleness tests. After the reviews, the declaration must carry `pr-spec still-valid` on its own line and postdate both the record and the chain change. | [integration.md](integration.md), [self-review.md](self-review.md), [critic-review.md](critic-review.md) |
| **R6 — feedback routing** | `/the-loop:derive-pr-spec` and `reference/workflow.md` § PR specs, checked by `test_graph_loops` (the assignment names the command, and the command names both verbs). Process text, so no runtime test applies. | [contract-and-snapshot.md](contract-and-snapshot.md) |
| **R7 — documentation and decision record** | `decision-153`, the `process-graph` and `spec-workflow` capability docs, `workflow.md`, `SKILL.md`, the commands reference and the graph CLI page. Checked in the capability-docs node. | `documentation.md` (next node) |
| **Security AC1–AC5** (disclosure consent, unknown visibility fails closed, the verb writes only its record, path safety, secret scan) | T8: 49 abuse and forgery tests at verification, with more added in review (negated or quoted grants, credential assignments, unresolvable revisions, uncommitted files). `/security-review`: pass. | [unit.md](unit.md), [critic-review.md](critic-review.md), [security-review.md](security-review.md) |
| **Dogfood (T11)** | `graph pr-spec` on PR #546 recorded `single-pr`, and the gate passes as `not-required`. It ran in part because of R1.2, and @MadaraUchiha-314 [accepted it as run](https://github.com/MadaraUchiha-314/the-loop/issues/543#issuecomment-7023255344). | [dogfood.md](dogfood.md) |
| **CI parity (T12)** | `make check`, exit 0: 7176 passed at verification, and 7200 passed at `4372de01` after the review fixes. | [ci-parity.md](ci-parity.md) |
