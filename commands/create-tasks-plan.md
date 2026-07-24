---
description: Create tasks.md (a DAG of tasks) for a work item from its approved requirements.md and design.md (Phase 3 of the loop).
argument-hint: "<ticket-id | spec-dir> (e.g. 42 | issue-42)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: create-tasks-plan `$ARGUMENTS`

Break the approved requirements + design into a **DAG of tasks** — Phase 3 of the 3-phase
spec workflow. A slice of `/the-loop:work-on`; `work-on` remains the superset.

**Read the `the-loop` skill and `reference/workflow.md` first.** Load
`.the-loop/harness-config.yaml`.

## Steps

1. **Locate the spec.** Resolve `$ARGUMENTS` to `docs/specs/<id>/` and read both
   `requirements.md` and `design.md`. Both should be approved; if not, say so and stop.

2. **Write `tasks.md`** from `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/tasks.md`
   (`${CLAUDE_PLUGIN_ROOT}` = the installed plugin's root; same in Cursor): small,
   verifiable tasks as a **DAG**, each `- [ ]` referencing the requirement(s) it
   satisfies and its dependencies, plus checkpoints (tests to run). Include the explicit
   dependency graph.

3. **Advance the phase.** Set the ticket label to `<phaseLabelPrefix>tasks-breakdown` and
   mirror `phase: tasks-breakdown`.

4. **Reference on the ticket** (link the checked-in `tasks.md`) and **request human
   review**. Do not start implementation until approved — record the approver.

5. **Next step:** `/the-loop:execute-tasks <id>`.
