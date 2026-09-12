---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#354"
phase: needs-review
status: in-progress
---

# Execution Log: survey — the architecture of the-loop (CLI)

> Append-only log for issue-354. Ticket:
> [#354](https://github.com/MadaraUchiha-314/the-loop/issues/354). Pull request:
> [#355](https://github.com/MadaraUchiha-314/the-loop/pull/355).

## How this session ran the loop

One cloud session. The ticket is a **survey** — five architecture questions — so the
work item is a tier 2, documentation-only change (the skill's risk tiers): a
requirements record, this log, and the report
[`docs/reports/cli-architecture-survey.md`](../../reports/cli-architecture-survey.md).
No design, testing plan or task DAG is authored for a tier 2 item. No authorized
`the-loop execute` reaches a cloud session, so `phase-selection` is recorded here
rather than answered as a gate; the owner's review of the PR is the human decision the
loop records.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-12 | — | tier 2, documentation only; spec chain beyond requirements declared away by tier |
| requirements-definition | 2026-09-12 | | [`requirements.md`](requirements.md) — two requirements, one per deliverable property |
| implementation | 2026-09-12 | | the report, its index/sidebar/architecture links |
| verification | 2026-09-12 | | markdownlint on the changed files; every file:line reference re-checked against the tree |
| needs-review | 2026-09-12 | | PR raised; the answer summarised on the ticket |
| complete | | | |

## Progress entries

### 2026-09-12 — the survey

- **Phase:** requirements-definition → implementation → verification → needs-review
- **Did:** read the ticket, `CLAUDE.md`, the skill and `reference/workflow.md`, the five
  shipped graphs, `graph/runtime.py`, `graph/chain.py`, `graph/state.py`,
  `graph/hooks/*`, `graphlink.py`, `control.py`, the webhook and poller daemons, the
  dispatcher, the harness adapters and `hooks/the-loop-gate.py`. Traced `the-loop start`
  and `the-loop execute` end-to-end; enumerated every guardrail between
  `requirements-definition` and `design` and classified each as programmatic or prose.
  Wrote the report with one component diagram and three sequence diagrams; registered it
  in the reports index, the sidebar and the architecture index.
- **Next:** the owner's review of the PR.
- **Blockers:** none.

### 2026-09-12 — the owner's question on PR #355

- **Phase:** needs-review
- **Decision recorded:** the owner asked on the PR where the agent harness is told
  about the-loop CLI and the process around it. Answered on the thread and folded into
  the report as § 4 "Where the harness is told about the CLI and the process": the two
  prompt templates, the `$graph_context` and `$interaction_directive` blocks, the
  assignment paste, the SessionStart hook / Cursor rule, the slash commands and the
  skill — with the observation that the prompts name only the seam verbs and the skill
  carries the explanation.
- **Checkpoint/tests:** markdownlint clean on the report.
- **Next:** the owner's review of the PR.
- **Blockers:** none.

## Review cycles

Self-review: every file and line reference in the report was re-read against the tree
before the PR was raised; the guardrail table was checked against `runtime.advance`,
`chain.run_chain` and `the-loop-gate.py` so that no prose rule is presented as code.

## Security review (gate)

No new attack surface — documentation only. See the requirements record's Security
considerations.

## Final validation evidence

`npx markdownlint-cli2@0.18.1` over the five changed markdown files: 0 errors. Every Mermaid
block in the report parsed by Mermaid 11 (`mermaid.parse`, under jsdom): 4 of 4 ok. The CI
gate (`the-loop check issue-354 --recompute --fail-on block`) run locally: `WAIT` at
`phase-selection`, exit 0 — and green on the PR's first push.

## Capability docs

None affected: the report describes existing behaviour and changes none. Every
capability it touches on (`process-graph`, `cli`, `webhook-triggers`,
`interactive-sessions`) already documents that behaviour; the report links to them
rather than duplicating.

## Documentation

- `docs/reports/cli-architecture-survey.md` — new.
- `docs/reports/index.md`, `docs/.vitepress/config.mts` — the report registered.
- `docs/architecture/architecture.md` — links to the survey from the top-level
  architecture index.

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#355](https://github.com/MadaraUchiha-314/the-loop/pull/355) | the whole work item — spec record, the report, its registrations | open |
