---
description: Create a work-item ticket (GitHub issue / Jira) from an existing requirements.md, then promote its draft spec folder to docs/specs/<id>/.
argument-hint: "<path-to-requirements.md> (e.g. docs/specs/draft-add-oauth/requirements.md)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: create-ticket `$ARGUMENTS`

Turn an already-drafted `requirements.md` into a tracked work item. RULE: everything the
harness works on must have a ticket — this command creates it and wires the spec to it.

**Read the `the-loop` skill, `reference/collaboration.md` and `reference/workflow.md`.**
Load `.the-loop/harness-config.yaml` for `ticketing` (github | jira).

## Steps

1. **Read the requirements** at `$ARGUMENTS`. Use its introduction/user-stories to form
   the ticket title and body.

2. **Create the ticket** in the configured ticketing system using the available
   integration (GitHub via `gh`/GitHub MCP, or Jira via MCP):
   - Title from the requirement's summary; body links to the spec (do not paste the whole
     file — reference it, single source of truth).
   - Apply the initial phase label `<workflow.phaseLabelPrefix>requirements-definition`
     (labels are created by `/the-loop:init`).

3. **Promote the folder.** Derive the canonical id from the new ticket (e.g. `issue-42`,
   `PROJ-42`). If the requirements live under `docs/specs/draft-<slug>/`, rename that
   folder to `docs/specs/<id>/` — this carries any sibling `brainstorm.md` (the root
   artifact) along with it. Update the front-matter of every promoted file (`brainstorm.md`
   included): `workItem: <id>`, `status` as appropriate.

4. **Reference on the ticket.** Post/confirm a comment or description link pointing to
   the checked-in `docs/specs/<id>/requirements.md` (single source of truth; later
   changes are edits to the file, not new comments).

5. **Report** the ticket id/URL and the next step:
   `/the-loop:create-design <id>`.

If the ticket already exists, do not duplicate it — reference it and just promote/link
the spec.
