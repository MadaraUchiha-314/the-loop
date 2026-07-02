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

### 2026-07-02 — Design review feedback addressed (MCP notifications, SDK adapters)

- **Phase:** tasks-breakdown
- **Did:** Addressed @MadaraUchiha-314's PR #16 review: (1) sharpened decision-016 —
  MCP *does* define in-session notifications (`resources/subscribe`, `listChanged`),
  but they only reach a connected client, the GitHub MCP server declares no event
  surface, and an event-pushing MCP server still needs a webhook receiver; (2) promoted
  the Claude Python-SDK adapter from "future work" to an explicit opt-in extra
  (`the-loop[claude-sdk]`, new optional task 10) — verified `claude-agent-sdk` carries
  runtime deps (`anyio`, `mcp`, `sniffio`) and drives the `claude` CLI over stdio, so
  the stdlib CLI adapter stays default; Cursor's TypeScript SDK would need a Node
  sidecar, so its adapter stays CLI-only.
- **Checkpoint/tests:** `make check` green.
- **Next:** Phase approvals.
- **Blockers:** none new.

### 2026-07-02 — Owner decision: CLI-only triggering for both harnesses

- **Phase:** tasks-breakdown
- **Did:** Applied @MadaraUchiha-314's decision on PR #16 ("let's use cli to trigger
  the harnesses not the sdks, for both cursor and claude"): removed the optional
  Claude Python-SDK adapter (former task 10) from the design and DAG; recorded the
  CLI-only decision in `design.md` trade-offs and `decision-016`. The `HarnessAdapter`
  contract still permits SDK implementations later (R4.5).
- **Checkpoint/tests:** `make check` green.
- **Next:** Phase approvals.
- **Blockers:** none.

## Review cycles

| Cycle | Type (self/critic) | Reviewer | Outcome | Link |
|-------|--------------------|----------|---------|------|
| 1 | self | harness | Fixed: EARS phrasing, DAG edges, untrusted-payload handling made explicit | — |
| 2 | human | @MadaraUchiha-314 | Fixed: MCP-notifications rationale sharpened; optional Claude SDK adapter added | PR #16 comment |
| 3 | human | @MadaraUchiha-314 | Decision applied: CLI-only triggering for both harnesses; SDK adapter removed | PR #16 comment |

## Final validation evidence

Pending — recorded when the implementation tasks execute.
