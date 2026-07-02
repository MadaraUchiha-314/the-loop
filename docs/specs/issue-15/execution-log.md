---
type: execution-log
workItem: issue-15
phase: needs-review
status: in-progress
---

# Execution Log: GitHub events trigger a harness session programmatically

> Append-only log of progress. Issue #15 asks for the detailed design and the task
> breakdown; implementation follows once the spec is approved.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-02 | @MadaraUchiha-314 (PR #16) | Distilled from issue #15 |
| design | 2026-07-02 | @MadaraUchiha-314 (PR #16) | MCP vs webhook decision → `decision-016` |
| tasks-breakdown | 2026-07-02 | @MadaraUchiha-314 (PR #16) | 10-task DAG |
| implementation | 2026-07-02 | — | approved via "Let's implement it now." on PR #16 |
| needs-review | 2026-07-02 |  | all 10 tasks done; PR #16 updated |
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

### 2026-07-02 — Implementation: tasks 1–10 executed

- **Phase:** implementation → needs-review
- **Did:** Executed the DAG in order 1 → {2,4,5,6,7} → 3 → 8 → 9 → 10.
  Red→green evidence per task:
  - Task 1: `validate_config.py` INVALID (`'routing' was unexpected`) → schema
    extended → VALID.
  - Tasks 2/4/5/6/7: `pytest cli/tests/test_routing.py` collection error
    (`No module named 'the_loop.harness'`) → modules implemented → 32 passed.
  - Task 3: `pytest -k sessions_command` 5 failed (command missing) → 5 passed.
  - Task 8: integration tests 3 failed (`--route` unknown; on_event lacked the
    delivery id) → wired → 57 passed total; scenarios queryable via
    `the-loop scenarios` (4 rows, Requirement-linked).
  - Tasks 9/10: docs (CLI README, automation.md, architecture.md), records
    (decision-016 accepted, roadmap item shipped), markdownlint 0 errors.
- **Checkpoint/tests:** `make check` green (ruff · pyright · validate ·
  57 pytest · markdownlint).
- **Next:** Human review of PR #16 (autonomy tier 3: human-approves-pr).
- **Blockers:** none.

### 2026-07-02 — CI red: ruff-format drift; gate parity fixed

- **Phase:** needs-review
- **Did:** CI (pre-commit) failed on `ruff format` for the new files — `make check`
  did not include a format check, so local was green while CI was red (exactly the
  tooling drift the-loop forbids). Applied the formatter, and added a `format-check`
  target to `make check` so the gap cannot recur.
- **Checkpoint/tests:** `uv run pre-commit run --all-files` all hooks Passed;
  `make check` (now incl. format-check) green.
- **Next:** CI green on the re-push; human review.
- **Blockers:** none.

## Review cycles

| Cycle | Type (self/critic) | Reviewer | Outcome | Link |
|-------|--------------------|----------|---------|------|
| 1 | self | harness | Fixed: EARS phrasing, DAG edges, untrusted-payload handling made explicit | — |
| 2 | human | @MadaraUchiha-314 | Fixed: MCP-notifications rationale sharpened; optional Claude SDK adapter added | PR #16 comment |
| 3 | human | @MadaraUchiha-314 | Decision applied: CLI-only triggering for both harnesses; SDK adapter removed | PR #16 comment |
| 4 | self | harness | Fixed: router and dispatcher now share one Deduper (router's early duplicate check was inert); design §3 protocol snippet aligned with implemented signatures | — |

## Final validation evidence

- `make check` green: ruff · pyright · `validate_config.py` (schema + both configs) ·
  **57 pytest** (16 pre-existing + 41 new) · markdownlint (0 errors) — the same
  commands CI runs.
- Acceptance mapping: R2 → registry + `sessions` command tests; R3 →
  router/dispatcher tests + the three Gherkin integration scenarios
  (`the-loop scenarios` lists them with `Requirement:` links); R4 → adapter tests
  against stub `claude`/`cursor-agent` binaries (argv + cwd asserted); R5 →
  same-session FIFO / cross-session parallelism dispatcher tests; R1 →
  `decision-016` (accepted).
