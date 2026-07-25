---
description: Finalize a work item after all tasks are done — cleanup (currently closing the ticket) and mark the work complete.
argument-hint: "<ticket-id | spec-dir> (e.g. 42 | issue-42)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: finish-tasks `$ARGUMENTS`

Wrap up a work item once **all tasks are complete and reviewed**. This is the cleanup step
of the loop; the cleanup set is intentionally **extensible** (more may be added later).

**Read the `the-loop` skill and `reference/workflow.md`.** Load `.the-loop/harness-config.yaml`.

## Steps

1. **Verify done.** Resolve `$ARGUMENTS` to `docs/specs/<id>/`. Confirm **every** task in
   `tasks.md` is checked (`- [x]`), **every PR** in the execution log's **Pull requests**
   table is merged or closed (a work item may be delivered by several), the required
   self/critic reviews and human review are recorded, and validated evidence has been
   presented. If anything is outstanding, stop and report what remains (point back to
   `/the-loop:execute-tasks <id>`).

2. **Mark complete.** Set the ticket phase label to `<phaseLabelPrefix>complete` and
   mirror `phase: complete` in the spec/execution log; add a final execution-log entry
   summarizing outcome + evidence.

3. **Cleanup (extensible):**
   - **Close the ticket(s)** for this work item (GitHub issue / Jira), referencing the
     merged PR(s) / evidence. Closing the ticket is also what ends the work item's
     harness session — one of its PRs merging does not (see `reference/automation.md`).
   - _Future cleanup steps are added here_ (e.g. archiving branches, releasing artifacts,
     notifying channels). Keep this list the single place cleanup grows.

4. **Report** the final status and links.
