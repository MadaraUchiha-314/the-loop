---
description: Create tasks.md (a DAG of tasks) for a work item from its approved requirements.md, design.md and testing-plan.md.
argument-hint: "<ticket-id | spec-dir> (e.g. 42 | issue-42)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: create-tasks-plan `$ARGUMENTS`

Break the approved requirements + design + testing plan into a **DAG of tasks** — the
last spec artifact. A slice of `/the-loop:work-on`; `work-on` remains the superset.

**Read the `the-loop` skill and `reference/workflow.md` first.** Load
`.the-loop/harness-config.yaml`.

## Steps

1. **Locate the spec.** Resolve `$ARGUMENTS` to `docs/specs/<id>/` and read
   `requirements.md`, `design.md` and `testing-plan.md`. All should be approved; if not,
   say so and stop.

2. **Write `tasks.md`** from `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/tasks.md`
   (`${CLAUDE_PLUGIN_ROOT}` = the installed plugin's root; same in Cursor): small,
   verifiable tasks as a **DAG**, each `- [ ]` referencing the requirement(s) it
   satisfies and its dependencies, plus checkpoints (tests to run). Each task's `_Test:_`
   **names a row of `testing-plan.md`'s matrix**, so the DAG and the plan cannot describe
   different work. Include the explicit dependency graph.

3. **Advance the phase.** Set the ticket label to `<phaseLabelPrefix>tasks-breakdown` and
   mirror `phase: tasks-breakdown`.

4. **Reference on the ticket** (link the checked-in `tasks.md`). `tasks-breakdown` has
   **no approval gate** (issue-281): the DAG is derived mechanically from the pair the
   human just approved at `design-approval`, so do **not** request a human review or
   wait for one — never set `status: approved` yourself; the graph advances on the
   artifact's shape alone.

5. **Next step:** `/the-loop:execute-tasks <id>`.
