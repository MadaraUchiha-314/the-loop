---
description: Report the current status of a work item by reading its spec files (requirements/design/tasks) and execution log. Read-only.
argument-hint: "<ticket-id | spec-dir> (e.g. 42 | issue-42 | PROJ-42)"
allowed-tools: Read, Bash, Glob, Grep
---

# the-loop: work-status `$ARGUMENTS`

Report where a work item stands. **Read-only** — this command inspects and summarizes; it
does not change anything.

**Read the `the-loop` skill and `reference/workflow.md` for the phase model.**

## Steps

1. **Locate the spec.** Resolve `$ARGUMENTS` to `docs/specs/<id>/`. If nothing is found,
   check for a `draft-*` folder (pre-ticket) and say so.

2. **Read the artifacts** (whichever exist): `requirements.md`/`bugfix.md`, `design.md`,
   `tasks.md`, `execution-log.md`. Also read the ticket's current phase label if the
   ticketing integration is available.

3. **Summarize:**
   - **Phase** — from the execution log's front-matter and the ticket label (flag any
     mismatch).
   - **Spec status** — which of requirements/design/tasks exist and their `status`
     (draft / approved) and approvers.
   - **Task progress** — count of `- [x]` vs `- [ ]` in `tasks.md` (the-loop keeps these
     current as tasks complete), and which tasks are outstanding.
   - **Latest activity** — the most recent execution-log entries and any pending
     review/human action.
   - **Next step** — the command to move forward (`create-design` / `create-tasks-plan` /
     `execute-tasks` / `finish-tasks`).

4. **Present** it as a concise, prioritized summary (mermaid where a diagram helps —
   `config.userInteraction`). Do not modify any file or ticket.
