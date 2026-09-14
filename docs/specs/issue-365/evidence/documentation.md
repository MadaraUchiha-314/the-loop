---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#365"
---

# Documentation: retire the execution log

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `spec-workflow.md` | The artifact list, the phase-tracking statement, the `repos:` home, the checkpoint rule and the PR list all re-pointed away from the execution log | issue-365 |
| `process-graph.md` | What `validates:` means and what the six review-chain gates read; the `onlyWhenSkipped` fallback; the force's three durable records; the entry chain's side effect | issue-365 |
| `review-loop.md` | Where a round is recorded — one file per gate, so no node passes on another's round | issue-365 |
| `capability-docs.md` | "none affected" is recorded in `evidence/documentation.md` | issue-365 |
| `documentation.md` | The `## Documentation` record moved into `evidence/documentation.md`, same gate | issue-365 |
| `token-economy.md` | Compaction no longer checkpoints to a log; the log itself is named as the lever removed | issue-365 |
| `process-graph.md` (review round) | The state file's name, and `phase-selection`'s fifth question | issue-365 (review) |
| `spec-workflow.md` (review round) | Where the multi-repo declaration lives and who may make it | issue-365 (review) |
| `testing-and-contracts.md` | The e2e conformance keys: `evidenceSections` replaces two execution-log keys | issue-365 |

## Documentation

| Document | What changed |
|----------|--------------|
| `README.md` | The phase sentence: the label plus `work-item-state.json`, no log to mirror |
| `CLAUDE.md` | This repository's own rule — keep the label in sync, write no progress log |
| `skills/the-loop/SKILL.md` | The phase statement, the documentation record, the `repos:` home, the self-check and checkpoint rules, the artifact inventory |
| `reference/workflow.md` | Nine passages: the kept gate, the design critic's record, `repos:`, the contribution loop, TDD evidence, implementation, resets, the fold-in, the ready-to-ship gate, resumability |
| `reference/context.md` | The durable ledger and the **checkpoint-then-reset protocol** rewritten — the largest single doc change, because the prose checkpoint was the protocol's second step |
| `reference/reviewing.md` | Where each round lands, the design-critic comparison table, the "no critic could run" gap |
| `reference/security.md` | The gate's subject and how a round is recorded |
| `reference/token-economy.md` | Filesystem-as-memory gains the lesson this ticket taught: state worth offloading is state something reads |
| `reference/tooling.md`, `automation.md`, `instructions.md`, `design-artifacts.md` | Four incidental "say so in the execution log" pointers → the PR briefing or the ticket |
| `commands/*.md` (10) | `work-on`, `work-status`, `execute-tasks`, `finish-tasks`, `verify-work`, `create-design`, `create-testing-plan`, `contribute-to`, `init`, and `upgrade-the-loop`'s new "no longer read, never deleted" note |
| `docs/guide/{what-is-the-loop,quickstart,how-it-works}.md` | The phase sentence, the spec-folder listing, the internal-templates list |
| `docs/reference/commands.md`, `docs/cli/commands/graph.md`, `docs/architecture/architecture.md`, `docs/config/harness-config.md` | `work-status`' inputs, the `repos:` example, the knowledge-tree listing, two "says so in the execution log" pointers |
| `docs/specs/index.md`, `docs/.vitepress/config.mts` | What a spec folder holds; the sidebar keeps `execution-log` so historical logs stay browsable |
| `.the-loop/manifest.yaml`, `.the-loop/harness-config.schema.json` | The role retired and eight `evidence/` entries added; the `onMissing` description |
| **Review round** — `docs/cli/state.md` | The portable record's `repos` field documented beside `sessionPerPr` |
| **Review round** — `docs/cli/commands/graph.md` | The multi-repo declaration example is now the checklist rows and the frozen JSON |
| **Review round** — `.gitignore`, `.github/workflows/the-loop-gate.yml`, `hooks/the-loop-gate.py`, `ui/src/**` | The renamed state file and lock, including the old lock name kept ignored |
| **Review round** — `skills/the-loop/templates/tasks.md` | The `repos:` front-matter key removed: the declaration is the gate's now |
