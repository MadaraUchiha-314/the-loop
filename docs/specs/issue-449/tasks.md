---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#449"
status: in-review
approvedBy: []
overrides: {}
riskTier: 4
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: Codex CLI as a hosting harness and critic

> Each task names the requirement it satisfies and the testing-plan row that proves it.
> Recorded retroactively during the PR #450 review; in review, not approved.

## Task list

- [x] **A1: adapter.** `CodexAdapter`: one-shot `codex exec --json`, interactive and
  resume argv, model and effort mapping. *Req:* R1 · *Test:* T14, T15
- [x] **A2: identity.** Launch marker, rollout discovery, native-id binding, cached
  lookups. *Req:* R2 · *Test:* T1–T3
- [x] **A3: instructions and hooks.** Managed `AGENTS.md` block, git exclusion of an
  untracked file, one Stop gate per Codex home. *Req:* R3.1–R3.3 · *Test:* T4–T6
- [x] **A4: trust.** `config.toml` trust writes, linked-worktree main root behind the
  too-broad guard, one `codex_home()` lookup. *Req:* R3.4, R3.5 · *Test:* T7, T8
- [x] **A5: configuration.** `harnessArgs` migration onto declared harnesses only;
  `mcp-call` through the adapter's one-shot argv. *Req:* R4 · *Test:* T9, T10
- [x] **A6: diagnostics.** Bypassed-default and filtered-item events reported once;
  read-only GraphQL retry. *Req:* R5 · *Test:* T11–T13
- [ ] **A7: end-to-end proof.** Run a ticket on `the-loop-testing` with a real Codex
  binary and record it under `evidence/`. *Req:* R1.1, R1.2 · *Test:* T15
- [x] **A8: tracked `AGENTS.md`.** Preserve tracked project instructions and place
  the managed block in Codex's global instructions. Verified against a real Codex
  binary. *Req:* R3.2 · *Test:* T5, T16
