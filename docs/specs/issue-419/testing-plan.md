---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#419"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
riskTier: 3
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: one verbosity switch over the whole trace, defaulting to quiet

> Derived from [bugfix.md](bugfix.md) and [design.md](design.md), before `tasks.md`.
> Authored at `test-planning`, completed at `verification`.

## What is testable here, and what is not

Everything this change adds is pure or rendered, and both are already driven by the
suite: `model.test.ts` calls exported functions directly, and `App.test.tsx` drives the
whole dashboard against the demo transport. So the matrix is automated apart from one
row — how the quieter panel *looks* — which needs a stylesheet jsdom does not apply. That
row is a browser pass on the dev server, recorded with a screenshot.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `isReadable` over every `ThreadRow` kind (malformed kept, tool result dropped, meta by its text, a tools-only assistant turn dropped) and `isBookkeeping` over the classification table (each hidden family, each kept family, `level=error` in a hidden family, an unclassified family, an empty event name) | `bun run test src/api/model.test.ts` |
| T2 | Integration (scenario) | yes | `TranscriptView` and `EventTrail` rendered both ways round: quiet drops the tool groups, the empty meta rows and the plumbing events; verbose restores every one; the error event survives quiet; the hidden-count line appears only when filtering emptied a non-empty source | `bun run test src/components/Transcript.test.tsx` |
| T3 | Contract (OpenAPI / GraphQL) | n/a — no API surface changes; the panel reads the same two routes with the same fields. | | |
| T4 | End-to-end | yes | The dashboard on demo data: the switch is off at load, the stream carries the agent's prose and the malformed line and no tool group, and turning it on brings the tool calls back — from the mouse and the keyboard | `bun run test src/App.test.tsx` |
| T5 | UI / visual | yes — **manual, browser** | The quiet panel reads as a conversation rather than a log, and the hidden-count line sits where an empty state would | `bun run dev`, screenshot into `evidence/` |
| T6 | Snapshot | n/a — the rows are asserted by their text and their `data-entry` / `data-tools` hooks in T2 and T4, which is the snapshot with the reasons attached. | | |
| T7 | Performance / load | n/a — two predicates over the ≤200 rows the routes already cap; no measurable budget. | | |
| T8 | Security / abuse case | yes | The abuse case from `design.md` § Security design: an event in a hidden family carrying `level=error` still renders, so nothing hides itself by its name | `bun run test src/api/model.test.ts src/components/Transcript.test.tsx -t "error"` |
| T9 | Accessibility | yes | The switch keeps `role="switch"`, an `aria-checked` that tracks its state, and an `aria-label` that is no longer `Tool calls`; `Enter` and space both toggle it | `bun run test src/App.test.tsx` |
| T10 | Migration / upgrade | yes | Nothing persisted changes: `the-loop:settings:v1` gains no key, and the whole existing UI suite still passes unchanged apart from the three tests that asserted the old copy and the old default | `bun run test` |
| T11 | Manual exploratory | yes | Against a real service with a long-polled work item: the trail that motivated the issue, before and after | an operator's machine; not available in this environment |
| T12 | Documentation parity | yes | The control-plane capability doc describes the switch by its new name and scope; markdownlint passes | `make lint`, or its markdownlint half directly where `uv` cannot run |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.2, R1.3 | `Scenario: a stream row is readable when it carries prose, thinking, a summary or a drifted line` |
| T1 | R1.4 | `Scenario: an assistant turn whose only content was tool calls is not readable` |
| T1 | R1.2, R2.2 | `Scenario: an event is plumbing when its family is, and is kept when nobody classified it` |
| T1, T8 | R2.1 | `Scenario: an error-level event in a hidden family is never plumbing` |
| T2 | R1.1, R1.2 | `Scenario: the quiet stream drops the tool groups, the empty meta rows and the plumbing events` |
| T2 | R3.1 | `Scenario: the verbose stream renders every row the quiet one hid` |
| T2 | R4.1, R4.2 | `Scenario: a trail emptied by the filter names its hidden count and the switch` |
| T2 | R4.3 | `Scenario: a source that is empty for its own reasons keeps its own empty state` |
| T4 | R1.1 | `Scenario: the trace panel loads with the switch off and no tool group in the stream` |
| T4 | R3.1, R3.3 | `Scenario: turning the switch on brings the tool calls back, from the mouse and the keyboard` |
| T9 | R3.2 | `Scenario: the switch names the whole stream's verbosity, not the tool calls` |

## Verification environment

The `ui/` workspace on this machine: `bun install --frozen-lockfile`, then `bun run test`
(vitest + jsdom + Testing Library), `bun run lint` (oxlint, type-aware) and
`bun run build` (which runs `tsc --noEmit` first). These are the same three commands
`.github/workflows/ci.yml`'s `ui` job runs, so local equals CI. The Python side is
untouched; `make check` is run once to prove it.

## Evidence to capture

Under `docs/specs/issue-419/evidence/`:

- `verification.md` — each row of this matrix with its command, its outcome and the
  counts from the run.
- `self-review.md` — the review cycles and every finding's disposition.
- `security-review.md` — the abuse case above, and the fail-open argument.
- `documentation.md` — the capability doc updated in this PR.
- the T5 screenshot, or the reason it did not run.

## Verification results

Recorded at the `verification` node in
[evidence/verification.md](evidence/verification.md): T1, T2, T4, T5, T8, T9, T10 and T12
pass; T3, T6 and T7 are `n/a` as planned; T11 did not run for want of a live service, and
the Python half of T10 (`make check`) could not run because this container's `uv` predates
the version `pyproject.toml` requires — the change touches no Python, and CI runs it on
the pull request.

## Activities checklist

- [x] T1 unit tests written red, then green
- [x] T2 component tests written red, then green
- [x] T4 / T9 dashboard tests updated for the new default and copy
- [x] T10 full `bun run test` green
- [x] T5 browser pass, or its absence recorded with a reason
- [x] T12 markdownlint green over the changed Markdown and the capability doc updated
      (`make lint` itself could not run here — see the verification record)
- [x] Evidence committed
