---
description: Create design.md for a work item from its approved requirements.md (Phase 2 of the loop).
argument-hint: "<ticket-id | spec-dir> (e.g. 42 | issue-42 | docs/specs/issue-42)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: create-design `$ARGUMENTS`

Produce the **design** for a work item from its approved requirements — Phase 2 of the
3-phase spec workflow. A slice of `/the-loop:work-on`; `work-on` remains the superset.

**Read the `the-loop` skill and `reference/workflow.md` first.** Load
`.the-loop/config.yaml`.

## Steps

1. **Locate the spec.** Resolve `$ARGUMENTS` to `docs/specs/<id>/` and read
   `requirements.md`. It should be approved; if not, say so and stop (do not design
   ahead of approved requirements).

2. **Write `design.md`** from `${CLAUDE_PLUGIN_ROOT}/.the-loop/templates/design.md`
   (`${CLAUDE_PLUGIN_ROOT}` = the installed plugin's root; same in Cursor),
   derived from the requirements: overview, architecture, components/interfaces, data
   models, error handling, testing strategy. Map each requirement to a component. RULE:
   all diagrams are **mermaid** (`config.userInteraction`).

3. **Produce UI/UX design artifacts — if the work item has a user-facing surface.**
   `design.md` (markdown + mermaid) captures architecture/HLD/LLD; **visual** UI/UX design
   is tracked as first-class artifacts under `docs/specs/<id>/design/`
   (`design.uiArtifacts.dir`): self-contained **HTML+CSS+JS prototypes**
   (`design.uiArtifacts.format: html`, Claude-artifact style — inline CSS/JS, no external
   deps) and/or a linked **Figma** file. Fill in the *UI/UX design* inventory in
   `design.md`. **Iterate each artifact with the `designer` persona until locked**
   (`status: approved`) — review the **rendered** output, feedback as ticket comments,
   capture screenshots as evidence. Skip this step (write `N/A`) for backend/CLI/infra
   work with no UI. **Read `reference/design-artifacts.md`** for the full pattern.

4. **Advance the phase.** Set the ticket label to `<phaseLabelPrefix>design` and mirror
   `phase: design` in the spec/execution log.

5. **Reference on the ticket** (link the checked-in `design.md` and any `design/`
   artifacts; edits go to the files, not new comments) and **request human review** — the
   designer reviews the UI/UX artifacts. Do not proceed until approved — record the
   approver (paper trail).

6. **Next step:** `/the-loop:create-tasks-plan <id>`.
