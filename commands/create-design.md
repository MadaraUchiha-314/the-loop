---
description: Create design.md for a work item from its approved requirements.md (Phase 2 of the spec chain).
argument-hint: "<ticket-id | spec-dir> (e.g. 42 | issue-42 | docs/specs/issue-42)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: create-design `$ARGUMENTS`

Produce the **design** for a work item from its approved requirements — Phase 2 of the
spec chain. A slice of `/the-loop:work-on`; `work-on` remains the superset.

**Read the `the-loop` skill and `reference/workflow.md` first.** Load
`.the-loop/harness-config.yaml`.

## Steps

1. **Locate the spec.** Resolve `$ARGUMENTS` to `docs/specs/<id>/` and read
   `requirements.md`. It should be approved; if not, say so and stop (do not design
   ahead of approved requirements).

2. **Write `design.md`** from `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/design.md`
   (`${CLAUDE_PLUGIN_ROOT}` = the installed plugin's root; same in Cursor),
   derived from the requirements: overview, architecture, components/interfaces, data
   models, error handling, the testing **strategy** (a paragraph; the executable detail
   belongs to `testing-plan.md`), the **Module structure** section — the tree of paths this
   work item creates, changes or removes, with a one-line responsibility and requirement
   per entry, so the reviewer sees where the code will land before approving the design
   (gated; a work item that changes no code says so in one sentence, per the template) —
   plus the **Security design** section —
   how each trust boundary from the requirements' Security considerations is enforced
   (`security.design.required`; a boundary left unenforced fails the gate, see
   `reference/security.md`). Map each requirement to a component. RULE:
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
   artifacts; edits go to the files, not new comments). **Do not request review yet** —
   the testing plan is derived from this design and reviewed *with* it at the single
   `design-approval` gate.

6. **Next step:** `/the-loop:create-testing-plan <id>`, which derives the plan and then
   requests the one human review covering both artifacts.
