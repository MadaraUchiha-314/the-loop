---
type: requirements
phase: requirements-definition
workItem: issue-163
status: approved              # draft | in-review | approved
approvedBy: []                # recorded on the PR review (paper trail)
collaborators: [engineer, architect, reviewer]
overrides: {}
---

# Requirements: test and verification as nodes in the PDLC

> Phase 1 of 3 (requirements → design → tasks). Ticket:
> [issue #163](https://github.com/MadaraUchiha-314/the-loop/issues/163).

## Introduction

the-loop can only claim a work item is done if it can *verify* the work item. Today
verification is implied rather than declared: `design.md` carries a one-paragraph
**Testing strategy**, `tasks.md` carries a `_Test:_` line per task, and the shipped
process graph (`cli/the_loop/graph/pdlc.yaml`) has an `implementation` node whose exit
chain runs `verify-tests` — a hook that is *skipped* unless a node declares a command.
Everything after implementation (`self-review` … `reviewer-briefing`) is about opinion,
not about proof.

The consequence is the one the ticket names: whether a work item was tested at all,
which *kinds* of testing applied, whether the plan was executed, and what the evidence
was, are all left to the agent's judgement at the moment of writing the PR. Nothing
gates them, so nothing guarantees them — the same defect shape as issue-124
(a gate reporting success without running) and issue-148 (prose describing a process the
graph did not execute).

This work item makes testing a **planned, gated, evidenced** part of the loop by adding
two nodes to the process graph:

- **`test-planning`** — derives a `testing-plan.md` artifact from the locked
  requirements and design: which kinds of testing apply to *this* work item, which
  explicitly do not and why, what environment/setup the verification needs, and what
  evidence will be captured.
- **`verification`** — after implementation, executes that plan, ticks it off, and
  records the results and evidence in the same artifact.

the-loop does **not** take ownership of a project's testing complexity (multi-repo
setups, bespoke harnesses, staging environments). It owns the *declaration* — the plan,
the gate, and the evidence — and delegates the mechanics to the project's own tooling
and to `customInstructions`.

## Requirements

### Requirement 1 — a testing plan is a first-class, locked artifact

**User story:** As an engineer working an item under the-loop, I want a `testing-plan.md`
alongside `requirements.md` and `design.md`, so that how the work will be *proved* is
decided and reviewed before code is written, not improvised afterwards.

#### Acceptance criteria (EARS)

1. WHEN a work item's `design.md` is locked THEN the loop SHALL derive
   `<specDir>/<id>/testing-plan.md` from the locked requirements and design before
   `tasks.md` is written.
2. The `test-planning` node SHALL block until `testing-plan.md` exists, is locked
   (`status: approved`), and carries a non-empty **Test matrix**, **Verification
   environment**, **Evidence plan** and **Verification results** section.
3. WHEN `tasks.md` is derived THEN each task's `_Test:_` SHALL name a row of the
   testing plan's matrix, so plan and DAG cannot describe different work.
4. IF a bundled template authors `testing-plan.md` THEN that template SHALL already
   satisfy every section its node gates on (the issue-124 rule: a template that cannot
   pass its own gate is a defect).

### Requirement 2 — the plan states which kinds of testing apply, and which do not

**User story:** As a reviewer, I want the plan to enumerate the candidate testing types
and record an explicit decision for each, so that "we didn't do performance testing" is
a recorded judgement rather than an omission I have to notice.

#### Acceptance criteria (EARS)

1. The testing plan SHALL present a **matrix** whose rows are testing types — at minimum
   unit, integration (scenario), contract, end-to-end, UI/visual, snapshot, performance,
   security/abuse-case, accessibility, migration/upgrade and manual-exploratory.
2. WHEN a testing type does not apply to the work item THEN the row SHALL be marked
   `n/a` **with a written reason**; an unmarked or reasonless row SHALL fail the gate's
   completeness expectation.
3. The matrix SHALL be **work-item dependent**: no type is mandatory in itself, and the
   loop SHALL NOT require a work item to run a kind of testing its change cannot exercise.
4. WHILE the work item is security-relevant (a trust boundary named in `design.md`
   §Security design) the abuse-case row SHALL name the negative test proving the
   boundary, consistent with `reference/security.md`.

### Requirement 3 — verification is a node, executed against the plan

**User story:** As an operator, I want the loop to stop at a `verification` node after
implementation, so that "the tests were run" is a gate outcome and not a claim in prose.

#### Acceptance criteria (EARS)

1. The process graph SHALL contain a `verification` node between `implementation` and
   `self-review`, with its own phase label (`<phaseLabelPrefix>verification`).
2. The `verification` node SHALL gate on the **same** `testing-plan.md` artifact:
   every planned activity ticked (`- [ ]` → `- [x]`) and a non-empty
   **Verification results** section — the same produce-then-re-gate shape
   `tasks-breakdown` → `implementation` already uses for `tasks.md`.
3. IF a planned activity cannot be executed THEN the loop SHALL NOT tick it; it SHALL
   record the reason in **Verification results** and either replan (edit the matrix,
   with the reason) or escalate — silently dropping a planned activity is not permitted.
4. WHEN the verification gate passes THEN the loop SHALL advance to `self-review`, and
   the later `evidence` node SHALL summarise from the verification results rather than
   re-deriving them.

### Requirement 4 — evidence is captured, not described

**User story:** As a reviewer, I want to see what was actually run and what it produced,
so that I can trust the result without re-running it myself.

#### Acceptance criteria (EARS)

1. The **Verification results** section SHALL record, per executed activity, the exact
   command (or procedure), the outcome, and a link to the evidence.
2. WHEN verification produces file evidence (test output, screenshots, recordings,
   reports) THEN it SHALL be written under `<specDir>/<id>/evidence/` and referenced
   from the plan; the directory is optional and only exists when there is evidence.
3. WHEN the work item has a **user-facing surface** and UI verification runs THEN the
   evidence SHALL include rendered screenshots of the verified states, and an animated
   capture (GIF or equivalent) WHEN the behaviour under test is a *flow* rather than a
   state.
4. WHEN the change adds or alters integration behaviour THEN the reviewer briefing SHALL
   embed `the-loop scenarios --format markdown`, and the plan SHALL reference it rather
   than duplicating the scenario list.
5. Evidence SHALL be committed with the work item; a link to a transient location (a CI
   run that expires, a local path) is not evidence.

### Requirement 5 — the loop facilitates verification without owning it

**User story:** As an operator with a complex system (several repositories, a staging
environment, a bespoke harness), I want the-loop to make room for my setup rather than
model it, so that the loop stays useful without becoming my test runner.

#### Acceptance criteria (EARS)

1. The testing plan SHALL carry a **Verification environment** section declaring what
   the verification needs: repositories to check out, services to run, fixtures/data,
   credentials *by reference* (never values), and the commands that bring it up.
2. WHEN the setup is described by an operator document THEN the plan SHALL reference it
   through `customInstructions.docs` rather than restating it, and the loop SHALL read
   those docs before planning verification.
3. the-loop SHALL NOT introduce a runner, orchestrator or environment manager of its own
   for this purpose; the plan names the project's commands and the loop executes them.
4. IF the environment cannot be brought up THEN the loop SHALL record the failure in
   **Verification results**, mark the affected activities unexecuted, and escalate rather
   than passing the gate.

### Requirement 6 — one process, described once

**User story:** As a maintainer, I want the two new nodes to exist in the graph, the
config, the manifest, the templates and the prose *consistently*, so that the-loop does
not grow a second, divergent description of its own process.

#### Acceptance criteria (EARS)

1. `workflow.phases` (schema default, this repo's config and the bundled template config)
   SHALL declare `test-planning` and `verification` in graph order, and the existing P4
   parity test SHALL enforce it.
2. `.the-loop/manifest.yaml` SHALL track `docs/specs/<id>/testing-plan.md` at phase
   `test-planning` and `docs/specs/<id>/evidence/` as an optional directory, and the
   existing P1–P3 parity tests SHALL hold graph, manifest and template together.
3. `SKILL.md`, `reference/workflow.md`, `reference/testing.md`, the execution-log
   template and the capability docs SHALL render the new sequence; none of them SHALL
   redefine it.
4. `tokenEconomy.modelRouting.stages` and `tokenEconomy.thinkingEffort.stages` SHALL
   carry entries for the two new stages, so routing does not fall through a hole.

## Non-functional requirements

- **No new runtime dependency.** The change is declarative (graph, schema, manifest,
  templates, prose) plus tests; the minimalism ladder forbids a test-orchestration
  dependency for a problem the project's own tooling already solves.
- **Backwards behaviour for in-flight items.** A work item whose spec folder predates
  this change has no `testing-plan.md`; the new gate blocks it at `test-planning`
  exactly as any missing artifact does, and the operator either writes the plan or uses
  the audited `the-loop graph force` escape hatch. No silent skip.
- **Cost.** Two more nodes means two more agent stages; both are routed at
  `standard`/`economy` tiers so the added cost is bounded (`reference/token-economy.md`).

## Security considerations

> Threat-model-lite (`security.threatModel.required`). See `reference/security.md`.

- **Actors & trust:** the actors are unchanged — the operator (trusted), the agent
  running the loop (semi-trusted; it authors the artifacts), and, on the daemon path,
  GitHub webhook payloads (untrusted). This change adds no ingress: nothing here parses
  a payload, opens a socket, or accepts remote input. The new node data comes from
  checked-in markdown in the repository's own spec folder.
- **Trust boundaries & data:** two boundaries are *touched*, not created.
  1. **Evidence is repository content.** `<specDir>/<id>/evidence/` is committed, so
     anything captured there is as public as the repository. Test output, screenshots of
     an authenticated UI and environment dumps routinely contain tokens, cookies,
     customer data and internal hostnames.
  2. **The verification environment describes credentials.** A plan that names what the
     setup needs is one edit away from a plan that *contains* what the setup needs.
- **Abuse cases (EARS):**
  1. WHEN verification captures output containing a secret, token, cookie or personal
     data THEN the loop SHALL redact it before committing the evidence, and SHALL NOT
     commit a capture it cannot redact.
  2. WHEN the **Verification environment** section is authored THEN credentials SHALL be
     named **by reference** (env var name, secret-store key) and never by value; a literal
     secret in the plan SHALL be treated as a leaked secret (rotate, do not merely edit).
  3. WHEN a testing plan names a command to run THEN it SHALL be reviewed as executable
     content, like `reviews.critics[]` entries already are (decision-043) — a plan is a
     committed file that instructs an agent to run something, so it is code for review
     purposes.
  4. WHEN the graph gains a node THEN that node SHALL NOT weaken an existing gate:
     `security-review` stays `required: true`, and `verification` sits *before* the
     review chain so a failed verification is visible to it.
- **Fail closed:** an activity that was not executed is not ticked; a plan that cannot
  be read, is unlocked, or has an empty **Verification results** section blocks the node.
  The graph's own contract already fails closed on a missing artifact — this work item
  adds no bypass, and the only override remains the audited `the-loop graph force`.

## Out of scope

- A test runner, environment orchestrator or multi-repo checkout mechanism owned by
  the-loop (R5.3 is explicit that this stays with the project).
- Automated redaction tooling for evidence — the rule is stated and reviewed; enforcing
  it mechanically is a separate work item.
- A human-approval node for the testing plan. `tasks-breakdown` has none either; the plan
  is reviewed with the PR that carries it.
- Retro-fitting testing plans onto completed work items.
- Changing `the-loop scenarios`, the Gherkin docstring rule, or the contract-first API
  conventions — the plan *references* them.

## Open questions

1. Should `test-planning` sit before or after `tasks-breakdown`? **Resolved in design
   (D1):** before, so `tasks.md` can reference matrix rows.
2. Should the testing plan get its own human-approval node? **Resolved (D2):** no —
   consistent with `tasks-breakdown`, reviewed on the PR.
3. Should `verification` produce a separate `verification-report.md`? **Resolved (D3):**
   no — it re-gates `testing-plan.md`, mirroring how `implementation` re-gates `tasks.md`.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
