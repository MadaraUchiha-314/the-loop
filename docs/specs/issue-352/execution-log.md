---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#352"
phase: needs-review
status: in-progress
---

# Execution Log: audit how `harness-config.yaml` is used and whether it is required

> Append-only log for issue-352. Ticket:
> [#352](https://github.com/MadaraUchiha-314/the-loop/issues/352). Deliverable:
> [`docs/reports/harness-config-audit.md`](../../reports/harness-config-audit.md).

## How this session ran the loop

One cloud session, one pass. No authorized `the-loop execute` reaches a cloud session,
so `phase-selection` was recorded on the ticket rather than answered as a gate. Tier 2
(documentation only, `autonomous-complete`), so the chain is `requirements.md` plus this
log; `design`, `test-planning` and `tasks-breakdown` were declared away — the design of a
report is its outline, and its test is the docs lint plus the parity tests that read the
files it touches.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-11 | — | Tier 2. Skipped: brainstorming (the ticket enumerates its own questions), design, test-planning, tasks-breakdown. Recorded on the ticket |
| requirements-definition | 2026-09-11 | | [`requirements.md`](requirements.md) — three requirements, eight acceptance criteria |
| implementation | 2026-09-11 | | The report, its `docs/reports/index.md` and sidebar entries, a pointer from `docs/config/harness-config.md` |
| verification | 2026-09-11 | | `markdownlint` on the changed files; `test_harness_config.py` and `test_docs_parity.py` (they read `docs/config/harness-config.md`, which gained a sentence) |
| needs-review | 2026-09-11 | | PR raised; findings summarised on the ticket |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| `claude/github-issue-352-un79kv` | the whole work item | open |

## Progress entries

### 2026-09-11 — orientation

- **Phase:** requirements-definition
- **Did:** read the ticket, `CLAUDE.md`, the skill, `harness_config.py` and its test,
  decision-032 and decision-044, `docs/config/harness-config.md`, the schema's
  `x-onboarding` groups, the five shipped graphs, `hooks/hooks.json`, `rules/the-loop.mdc`
  and `scripts/validate_config.py`. Then a per-key search across the skill, the commands
  and the CLI source for every top-level schema key and every sub-key the ticket's
  question turns on.
- **Findings that shaped the report:**
  - decision-044 already answered the narrow question and pinned the CLI's read surface
    (`READS`, eight keys) with a four-way parity test. The wide question — every reader —
    had not been asked.
  - `workflow.phases` is read by nothing in the CLI; `test_graph_parity` P4 forces the
    config to mirror the graph; `/init` creates labels from it. Redundant, as the ticket
    says, with one job to reassign.
  - `reviews.critics[]` describes the operator's harnesses and binaries and is executable
    config in a committed file. Decision-044's CI-checkout argument does not apply to
    `critic run`; its "skill reads the same entries" argument reduces to
    `the-loop critic list`. The counts stay; the roster should move.
  - The CLI validates nothing against the harness-config schema at run time; the schema
    is not shipped in the wheel. The Cursor rule still looks for the pre-rename
    `config.yaml`.
- **Next:** write the report.

### 2026-09-11 — the report, verified, handed to review

- **Phase:** implementation → verification → needs-review
- **Did:** `docs/reports/harness-config-audit.md` — the four questions answered in one
  table, a reader diagram, a 34-row per-key verdict table, the two named keys examined,
  the removal question walked through six consequences, five move candidates, five
  delete candidates, three defects, seven follow-ups with tiers. Registered in
  `docs/reports/index.md` and the VitePress sidebar; one pointer sentence in
  `docs/config/harness-config.md`.
- **Capability docs:** none change behaviour. `docs/config/harness-config.md` (the
  config reference, not a capability doc) gained the pointer.
- **Checkpoint/tests:** see the verification row above; results recorded in the PR.
- **Next:** the owner decides which of the seven follow-ups to raise.
- **Blockers:** none.
