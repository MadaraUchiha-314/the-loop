---
type: tasks
phase: tasks-breakdown
workItem: "issue-300"
status: locked
approvedBy: []
overrides: {}
---

# Tasks: nesting work items and their PRs in the sidebar

> Phase 3 of 3. Small, verifiable tasks; each `_Test:_` names a row of
> `testing-plan.md`.

## Task list

- [x] 1. `sessionTree` gains the two fields a row needs
  - `ui/src/api/model.ts`: `SessionNode.label` (`prRepo ? shortRef : "#" + number`) and
    `SessionNode.lastActivity` (`endpoint.lastEventAt ?? ""`), set for both the outer
    node and each inner one. The doc comments stop naming the retired Sessions screen.
  - No new "this item's PRs" derivation anywhere else (R5.2).
  - _Depends on:_ none
  - _Requirements:_ R2.1, R2.2, R2.3, R5.2
  - _Test:_ `T1 — bun run test -- src/api/model.test.ts`

- [x] 2. The sidebar renders the tree
  - `ui/src/views/Work.tsx`: `sessionTree(sorted)`; each item wrapped in
    `.lp-side-item` with a named `<ul className="lp-side-prs">` of `PullRequestRow`s
    when it has any; `activeRef` resolves the hash (or the newest-item fallback) once,
    and drives `selected` on both levels plus `owner` on the parent.
  - _Depends on:_ 1
  - _Requirements:_ R1.1, R1.2, R1.3, R1.4, R1.5, R2.4, R3.3, R3.4
  - _Test:_ `T2, T6 — bun run test -- src/App.test.tsx`

- [x] 3. The route owns the viewed trace
  - `ui/src/views/WorkItemDetail.tsx`: `initialTraceRef` + `useState` → a `traceRef`
    prop and a derived `viewed`, with the ownership guard; the transcript fetch, the
    caption's session, the event-fallback filter and the **chat bar's target** all read
    `viewed`; the trace tabs become links on `hrefFor({ name: "work", ref })`.
  - Security-relevant (abuse cases A1, A2): the guard is the whole of R4.3, and one
    resolved value is the whole of A2.
  - _Depends on:_ 2
  - _Requirements:_ R3.1, R3.2, R4.1, R4.2, R4.3, R4.4
  - _Test:_ `T2, T7, T11 — bun run test -- src/App.test.tsx src/components/Transcript.test.tsx`

- [x] 4. The nesting's styling
  - `ui/src/styles/app.css`: `.lp-side-item`, `.lp-side-prs`, `.lp-side-pr` (indent +
    per-row gutter hairline + smaller ref) and `.lp-side-row.owner`.
  - _Depends on:_ 2
  - _Requirements:_ R1.1, R2.4, R3.4
  - _Test:_ `T5 — Chromium screenshots over the production build`

- [x] 5. Tests
  - `ui/src/api/model.test.ts`: the existing `sessionTree` expectation updated to the
    new shape, plus the foreign-repo label / `lastActivity` case.
  - `ui/src/App.test.tsx`: the nested-list case, the PR-row-opens-its-session case, and
    the trace tabs re-asserted as links.
  - _Depends on:_ 1, 2, 3
  - _Requirements:_ all
  - _Test:_ `T1, T2, T6, T7`

- [x] 6. Verification and evidence
  - Lint (at the lockfile's oxlint), the full vitest suite, `tsc --noEmit` + production
    build; Chromium screenshots of the sidebar and of a selected PR, against the demo
    fixture. Results in `evidence/verification.md`.
  - _Depends on:_ 5
  - _Requirements:_ R5.1
  - _Test:_ `T5, T8`

- [x] 7. Docs in the same PR
  - `docs/capabilities/control-plane.md`: the sidebar behaviour bullet and a history
    row. `ui/README.md`: the screen description and the layout note.
  - _Depends on:_ 6
  - _Requirements:_ —
  - _Test:_ `markdownlint`
