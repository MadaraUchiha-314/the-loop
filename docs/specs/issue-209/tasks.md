---
type: tasks
phase: tasks-breakdown
workItem: issue-209
status: draft
approvedBy: []
overrides: {}
---

# Tasks: `GET /api/v1/sessions/transcript`

> Derived from [`design.md`](design.md) and [`testing-plan.md`](testing-plan.md).
> Ticket: [#209](https://github.com/MadaraUchiha-314/the-loop/issues/209).

## Task list

- [x] 1. `get_transcript` in `core/sessions.py`
  - Endpoint resolution (closed + PR endpoints), harness gate, id validation,
    per-character munge + `CLAUDE_CONFIG_DIR`, fallback scan, containment check,
    bounded tail, malformed-line wrapping, the read-shaped return.
  - _Depends on:_ none
  - _Requirements:_ R1.1–R1.4, R2.1–R2.5
  - _Test:_ T1 — `test_core_sessions.py` (red→green)
- [x] 2. `GET /api/v1/sessions/transcript` route + contract
  - One delegation line, `operationId: sessionTranscript`, `tail` validated
    `ge=0`; the authored OpenAPI file gains the path.
  - _Depends on:_ 1
  - _Requirements:_ R2.6, R3.1
  - _Test:_ T2, T3 (red→green)
- [x] 3. `session_transcript` MCP tool
  - One-liner binding beside the other reads in `api/mcp.py`.
  - _Depends on:_ 1
  - _Requirements:_ R3.2
  - _Test:_ T2 (tool registration asserted in the existing MCP integration suite)
- [x] 4. Integration scenarios
  - `test_transcript_integration.py` with Gherkin docstrings: served tail, closed
    session, no-session/cursor/missing-file 404s, traversal + symlink negatives.
  - _Depends on:_ 2
  - _Requirements:_ R1, R2; abuse cases 1, 3, 4
  - _Test:_ T2, T8
- [x] 5. UI: the trace panel goes live
  - `types.ts` + `client.ts` `transcript()`, demo fixture + transport answer,
    `transcriptPath` munge fix, `transcriptTurns` projection, `WorkItemDetail.tsx`
    rows + fallback, stale copy removed (`App.tsx`, docstrings, `ui/README.md`),
    tests.
  - _Depends on:_ 2
  - _Requirements:_ R4.1–R4.4
  - _Test:_ T15
- [x] 6. Docs + decision
  - `docs/capabilities/control-plane.md` (current behaviour + history row),
    `ui/README.md` § Not yet served, `docs/decisions/decision-079.md` (the
    fail-closed file boundary; no redaction; no CLI verb; no Cursor).
  - _Depends on:_ 1–5
  - _Requirements:_ R3, R4.3
  - _Test:_ T12, T14
- [x] 7. Verification
  - Execute the plan, tick activities with evidence under `evidence/`.
  - _Depends on:_ 1–6
  - _Requirements:_ all
  - _Test:_ the plan itself
