# Capability: testing-and-contracts

> How a work item is **proved**: a planned, gated testing plan and a verification node
> that executes it with committed evidence; integration-test coverage that is *queryable*
> (Gherkin scenario docstrings); and API contracts that are *declarative* (spec-first
> OpenAPI / GraphQL SDL).

## What it is

The loop's answer to "is this actually done?" — planned before the code is written and
gated after it is: `testing-plan.md` decides which kinds of testing apply to a work item,
the `verification` node runs them and records the evidence, and two standing conventions
make correctness self-describing (every integration test names the scenario it proves,
every API is authored contract-first with docs generated from the contract).

## Current behaviour

### The testing plan and the verification node (issue-163)

- A work item SHALL carry a `testing-plan.md` in its spec folder, derived from
  `design.md` and locked at the **`test-planning`** phase — **before** `tasks.md`, because
  each task's `_Test:_` names a row of the plan's matrix.
- The plan SHALL be **reviewed at the same human gate as the design it derives from**:
  `test-planning` sits between `design` and `design-approval`, so one approval covers both
  artifacts, feedback is recorded into each, and `changes-requested` returns to `design`,
  which re-derives the plan.
- The plan SHALL present a **test matrix** whose rows are candidate testing types (unit,
  integration, contract, end-to-end, UI/visual, snapshot, performance, security/abuse-case,
  accessibility, migration/upgrade, manual exploratory, plus anything the work item needs).
  **No type is mandatory in itself — the matrix is work-item dependent** — but every row
  SHALL carry a decision: a type that does not apply is marked `n/a` **with a written
  reason**. A trust boundary named in `design.md` §Security design SHALL have its negative
  test named here.
- The plan SHALL declare its **verification environment** — repositories, services,
  fixtures, bring-up/tear-down commands, and credentials **by reference only** (env var
  name / secret-store key, never a value). the-loop SHALL NOT introduce a runner,
  orchestrator or environment manager of its own: it *facilitates* verification by
  declaring what is needed and running the project's own commands, and links the operator's
  registered `customInstructions` docs rather than restating them.
- A testing plan names commands an agent will run, so it SHALL be reviewed as **executable
  content**, on the same footing as `reviews.critics[]` entries
  ([decision-043](../decisions/decision-043.md)).
- WHEN implementation completes THEN the **`verification`** node SHALL execute the plan and
  re-gate the same artifact: every activity ticked (`checkmarks: complete`) and a non-empty
  **Verification results** section recording, per activity, the exact command or procedure,
  the outcome and a link to the evidence.
- IF a planned activity cannot be executed THEN it SHALL NOT be ticked: the reason is
  recorded and the matrix replanned (with the reason) or the item escalated. IF the
  environment cannot be brought up THEN the loop SHALL escalate rather than pass the gate.
- Evidence SHALL be **committed** under `docs/specs/<id>/evidence/` — a link to a CI run
  that expires or to a local path is not evidence. WHEN textual evidence is written THEN
  it SHALL be **markdown (`.md`), never `.txt`** — titled, one section per command, raw
  output in fenced blocks, and linted like every other markdown file; binary captures keep
  their own formats and are referenced from it. WHEN UI verification runs THEN it SHALL
  capture screenshots of each verified state and an **animated capture (GIF or equivalent)
  when the behaviour under test is a *flow*** rather than a state. Evidence SHALL be
  redacted (tokens, cookies, personal data, internal hostnames) before it is committed,
  because that directory is as public as the repository; a capture that cannot be redacted
  is not committed and the results row says so.
- The later `evidence` node SHALL **summarise** the verification results against the
  acceptance criteria rather than re-deriving them.

### Scenario docstrings and contract-first APIs

- Every integration test SHALL carry a Gherkin-syntax docstring
  (`Feature:` / `Scenario:` / Given-When-Then) naming the scenario under test, with a
  `Requirement:` link when tied to a spec's `requirements.md`
  (`testing.gherkinDocstrings: required`, `testing.linkRequirements`).
- Integration tests SHALL be discovered via `testing.integrationTestGlobs`.
- `the-loop scenarios` SHALL extract and tabulate all covered scenarios
  (`--format table|markdown|json`) so a harness or reviewer can query coverage.
- RESTful API specs SHALL be authored in `specs/openapi/` (OpenAPI); GraphQL schemas
  SHALL be SDL-first under `specs/graphql/`; documentation SHALL be generated from
  those contracts, never hand-written (`config.apiSpecs`; not exercised in this repo —
  the-loop ships a CLI + docs, not an API).

## Design

[`reference/testing.md`](../../skills/the-loop/reference/testing.md) ·
[`docs/specs/issue-163/design.md`](../specs/issue-163/design.md) ·
[`docs/specs/issue-11/design.md`](../specs/issue-11/design.md) ·
[process-graph](process-graph.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-163 | Testing became part of the process rather than an assumption: the `testing-plan.md` artifact and the `test-planning` / `verification` nodes, the test-type matrix with `n/a`-with-a-reason, the declared-not-managed verification environment, and committed, redacted evidence (screenshots and GIFs for UI flows) | [spec](../specs/issue-163/), [decision-060](../decisions/decision-060.md), [process-graph](process-graph.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/163) |
| issue-165 | Textual evidence is markdown (`.md`), never `.txt` — titled, one section per command, output in fenced blocks, linted like every other markdown file | [spec](../specs/issue-165/), PR #168 |
| issue-11 | Introduced Gherkin scenario docstrings, the `scenarios` command and contract-first API conventions | [spec](../specs/issue-11/), [decision-014](../decisions/decision-014.md) |
