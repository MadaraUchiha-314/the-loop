---
type: tasks
phase: tasks-breakdown
workItem: "issue-302"
status: locked
approvedBy: []
overrides: {}
---

# Tasks: a pull request appears once on the board

> Phase 3 of 3. Small, verifiable tasks; each `_Test:_` names a row of
> `testing-plan.md`.

## Task list

- [x] 1. One notion of a treeless loop
  - `ui/src/api/model.ts`: extract `treeless(record)` over `TREELESS_LOOPS`; `sessionTree`
    calls it instead of reading `record.graph?.loop` inline.
  - _Depends on:_ none
  - _Requirements:_ R4.2
  - _Test:_ `T9 — the existing sessionTree cases stay green`

- [x] 2. The claim
  - `ui/src/api/model.ts`: `pullRequestClaims(sessions, recordByRef)` — treeless owners do
    not claim, self-claims are ignored, a claim by a claimed ref is discarded.
    `buildWorkItemViews` skips a claimed ref.
  - Security-relevant (abuse case A1): the last two rules _are_ the mitigation.
  - _Depends on:_ 1
  - _Requirements:_ R1.1, R1.2, R1.3, R1.4
  - _Test:_ `T1, T11 — bun run test -- src/api/model.test.ts`

- [x] 3. The fold
  - `ui/src/api/model.ts`: `PullRequestView` gains `record`, `attention`, `question`,
    `lastActivity`; `buildPullRequests` takes the record and attention maps and the
    awaiting map; `sessionTree` reads `pr.lastActivity`.
  - _Depends on:_ 2
  - _Requirements:_ R2.1
  - _Test:_ `T2 — bun run test -- src/api/model.test.ts`

- [x] 4. The fold reaches the inbox and the row
  - `ui/src/api/model.ts`: `collapseByKind` extracted from `attentionEntries`;
    `attentionEntries` emits a PR's question and collapsed attention against the owner's
    ref with the PR's short ref, suffixed `· PR`; `rowFlag` raises `needs input` for a
    PR's open question and nothing else.
  - _Depends on:_ 3
  - _Requirements:_ R2.2, R2.3, R2.4
  - _Test:_ `T2 — bun run test -- src/api/model.test.ts`

- [x] 5. A nested endpoint is a session
  - `cli/the_loop/core/attention.py`: the liveness map includes each record's nested
    `pullRequests`, a ref's own record still winning.
  - _Depends on:_ none
  - _Requirements:_ R3.1, R3.2
  - _Test:_ `T4, T11 — uv run pytest tests/test_core_attention.py`

- [x] 6. Tests
  - `ui/src/api/model.test.ts`: the T1 and T2 cases.
  - `ui/src/App.test.tsx`: the sidebar draws the PR once (T3, T8).
  - `cli/tests/test_core_attention.py`: the T4 cases.
  - _Depends on:_ 4, 5
  - _Requirements:_ all
  - _Test:_ `T1, T2, T3, T4, T8`

- [x] 7. Verification and evidence
  - Both suites, both linters, typecheck and production build; a Chromium screenshot of
    the sidebar against a fixture holding both identities. Results in
    `evidence/verification.md`.
  - _Depends on:_ 6
  - _Requirements:_ R4.1
  - _Test:_ `T7, T10`

- [x] 8. Docs in the same PR
  - `docs/capabilities/control-plane.md`: the reconciliation and a history row.
  - _Depends on:_ 7
  - _Requirements:_ —
  - _Test:_ `markdownlint`
