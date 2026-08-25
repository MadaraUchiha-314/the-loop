---
description: Start a work item with a brainstorm.md scratchpad BEFORE requirements — the optional root artifact. Iterate on it, then convert to requirements with /new-requirement.
argument-hint: "<short-title> (e.g. \"realtime-collab-editor\")"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: brainstorm `$ARGUMENTS`

Create a **brainstorm.md** scratchpad for a fuzzy idea that isn't ready to be pinned down
as requirements yet. Brainstorming is the **optional Phase 0** of the loop and the **root
artifact** every later artifact derives from: `brainstorm → requirements → design →
tasks → implementation`. If the work is already clear, skip this and go straight to
`/the-loop:new-requirement`.

**Read the `the-loop` skill and `reference/workflow.md` first** (phases, the
gate-owned-lock principle, reviews).

## Steps

1. **Create a temporary spec folder.** Slugify `$ARGUMENTS` → `<slug>` and create
   `docs/specs/draft-<slug>/` (the-loop's convention for a spec with no ticket yet;
   `/the-loop:create-ticket` later renames it to `docs/specs/<id>/`). Reuse the folder if
   it already exists.

2. **Write `brainstorm.md`** from
   `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/brainstorm.md`
   (`${CLAUDE_PLUGIN_ROOT}` = the installed plugin's root; same in Cursor): problem /
   opportunity, context & constraints, ideas & options, sketches, open questions, and a
   working hypothesis. Keep it free-form — this is a scratchpad, not a spec. Set
   front-matter `phase: brainstorming`, `status: draft`, `workItem: draft-<slug>`, and the
   `collaborators` you want to think with.

3. **Iterate with feedback until it converges.** The brainstorm is meant to *change*:
   gather feedback (interactively or via ticket comments — paper trail), refine the
   options, and resolve the open questions. The brainstorm has **no approval gate**
   (issue-281): never set `status: approved` or ask for a sign-off — it has converged
   when its author says the direction is settled, on the record.

4. **Point to the next step:** convert the converged brainstorm into requirements with
   `/the-loop:new-requirement <title>` (it reads the sibling `brainstorm.md` and derives
   `requirements.md` from it), then `/the-loop:create-ticket` to mint the ticket.

Do not write `requirements.md` here — that is `/the-loop:new-requirement`. Brainstorming
stays exploratory; the moment you're asserting acceptance criteria you've left this phase.
