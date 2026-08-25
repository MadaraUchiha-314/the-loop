---
description: Create testing-plan.md for a work item from its approved requirements.md and design.md — how the item will be proved, before the task DAG.
argument-hint: "<ticket-id | spec-dir> (e.g. 42 | issue-42 | docs/specs/issue-42)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: create-testing-plan `$ARGUMENTS`

Decide **how this work item will be proved**, before the task DAG that references it —
the `test-planning` node, which sits between `design` and `design-approval` so the plan
is reviewed *with* the design it derives from. A slice of `/the-loop:work-on`; `work-on`
remains the superset.

**Read the `the-loop` skill and `reference/testing.md` first.** Load
`.the-loop/harness-config.yaml`, and read every doc registered in
`customInstructions.docs` — an operator's own testing/environment conventions are exactly
what this artifact should reference rather than restate.

## Steps

1. **Locate the spec.** Resolve `$ARGUMENTS` to `docs/specs/<id>/` and read
   `requirements.md` (or `bugfix.md`) and `design.md`. The requirements should be locked
   (`status: approved` — written by the `requirements-approval` gate); the design should
   be **complete** (its gated sections filled) but is still a draft, because its human
   approval comes after this step, at the `design-approval` gate that reviews — and
   locks — the pair together (issue-281). Stop only if either is missing or the
   requirements are unlocked.

2. **Write `testing-plan.md`** from
   `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/testing-plan.md`
   (`${CLAUDE_PLUGIN_ROOT}` = the installed plugin's root; same in Cursor):

   - **Test matrix** — one row per candidate testing type (unit, integration, contract,
     e2e, UI/visual, snapshot, performance, security/abuse-case, accessibility,
     migration, manual exploratory, plus anything else this item needs). **Nothing is
     mandatory in itself**, but every row gets a decision: a type that does not apply is
     `n/a` **with a written reason**. A trust boundary named in `design.md` §Security
     design must have its negative test named here.
   - **Scenarios & requirement trace** — matrix rows → requirement ids → the Gherkin
     `Scenario:` titles the integration tests will carry.
   - **Verification environment** — repositories, services, fixtures, bring-up/tear-down
     commands. **Credentials by reference only** (env var name / secret-store key), never
     values. Where an operator doc already describes the setup, link the registered
     `customInstructions` doc instead of copying it. the-loop runs the project's own
     commands; it brings no runner of its own.
   - **Evidence plan** — what will be captured per activity and where under
     `docs/specs/<id>/evidence/`. For a user-facing surface: screenshots of each verified
     state, plus an animated capture (GIF) when the behaviour is a *flow*.
   - **Verification activities** — the checklist the `verification` node ticks.
   - **Verification results** — author the heading now holding `_Not yet executed._`; the
     gate treats an empty section as unmet, and `verification` fills it later.

3. **Leave it a draft.** Never set `status: approved` yourself — the `design-approval`
   gate locks the plan together with the design on the human's one approval
   (issue-281). The plan **names commands an agent will run**, so it is executable
   content — review it like code (decision-043).

4. **Advance the phase.** Set the ticket label to `<phaseLabelPrefix>test-planning` and
   mirror `phase: test-planning` in the execution log.

5. **Reference on the ticket** (link the checked-in `testing-plan.md`; later changes are
   edits to that file, not new comments) and **run `the-loop graph complete`** so the
   pointer reaches `design-approval` — the graph's own gate posts the review request:
   one gate, **both artifacts**, `design.md` and this plan. The gate records reviewer
   feedback into each of them, locks both on an approval (recording the approver), and
   `changes-requested` returns to `design`, which re-derives the plan. Do not post a
   review request of your own (issue-281).

6. **Next step:** `/the-loop:create-tasks-plan <id>` — each task's `_Test:_` names a row
   of this matrix.
