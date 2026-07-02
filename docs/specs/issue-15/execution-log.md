---
type: execution-log
workItem: issue-15
phase: tasks-breakdown
status: in-progress
---

# Execution Log: GitHub events trigger a harness session programmatically

> Append-only log of progress. Issue #15 asks for the detailed design and the task
> breakdown; implementation follows once the spec is approved.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-02 | pending | Distilled from issue #15 |
| design | 2026-07-02 | pending | MCP vs webhook decision → `decision-016` |
| tasks-breakdown | 2026-07-02 | pending | 10-task DAG; implementation awaits approval |
| implementation |  |  | not started (out of scope for issue #15) |
| needs-review |  |  |  |
| complete |  |  |  |

## Progress entries

### 2026-07-02 — Spec drafted (requirements → design → tasks)

- **Phase:** tasks-breakdown
- **Did:** Researched the two candidate approaches. Confirmed the official
  `github/github-mcp-server` has no event-subscription capability (MCP transports are
  client-initiated; Claude.ai/code's PR-watching is Anthropic-hosted infrastructure) —
  recorded as `decision-016`. Confirmed the official programmatic surfaces:
  `claude -p --resume <session-id> --output-format json` (session id in the JSON
  output; resume scoped to the project directory) and `cursor-agent -p --resume
  <chat-id> --output-format json` (Cursor's official SDK is TypeScript-only — answers
  the issue's TODO). Drafted `requirements.md` (R1–R5 + NFRs), `design.md`
  (registry / router / dispatcher / adapters on top of the existing `gh-webhook`
  receiver) and the 10-task DAG in `tasks.md`.
- **Checkpoint/tests:** `make lint` (markdownlint) on the new docs.
- **Next:** Human review of the three phases; then execute the DAG.
- **Blockers:** Phase approvals (`workflow.requireHumanReviewPerPhase: true`); open
  questions raised on the ticket (label-gating for `spawnOnUnmatched`).

## Review cycles

| Cycle | Type (self/critic) | Reviewer | Outcome | Link |
|-------|--------------------|----------|---------|------|
| 1 | self | harness | Fixed: EARS phrasing, DAG edges, untrusted-payload handling made explicit | — |

## Final validation evidence

Pending — recorded when the implementation tasks execute.
