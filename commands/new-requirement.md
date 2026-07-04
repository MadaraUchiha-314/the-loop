---
description: Start a new work item by drafting a requirements.md BEFORE a ticket exists — in a temporary spec folder. Follow with /create-ticket.
argument-hint: "<short-title> (e.g. \"add-oauth-login\")"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: new-requirement `$ARGUMENTS`

Draft a requirements spec for work that has **no ticket yet**. Some work starts as an
idea; the-loop lets you define the requirements first, then mint the ticket from them
(`/the-loop:create-ticket`). This is a slice of `/the-loop:work-on` (Phase 1 only) —
`work-on` remains the superset.

If the idea was first explored in a **`brainstorm.md`** (the optional Phase 0 root
artifact from `/the-loop:brainstorm`), this command **converts** that locked brainstorm
into requirements rather than starting from a blank page.

**Read the `the-loop` skill and `reference/workflow.md` first** (phases, EARS, reviews).

## Steps

1. **Create or reuse the temporary spec folder.** Slugify `$ARGUMENTS` → `<slug>` and use
   `docs/specs/draft-<slug>/` (reuse it if `/the-loop:brainstorm` already created it).
   `draft-*` folders are the-loop's convention for a spec that has no ticket yet;
   `/the-loop:create-ticket` renames it to `docs/specs/<id>/`.

2. **Convert from a brainstorm if present.** If a sibling `brainstorm.md` exists in the
   folder, read it and **derive** the requirements from its locked direction — its chosen
   option becomes the introduction, its working hypothesis + hand-off become the user
   stories, and its resolved constraints become acceptance criteria. Do not proceed off an
   unlocked brainstorm (`status` not `approved`): lock it first, or say so and stop.
   Everything the brainstorm considered-and-rejected stays in `brainstorm.md` (the record);
   only the carried-forward direction lands in `requirements.md`.

3. **Write `requirements.md`** from
   `${CLAUDE_PLUGIN_ROOT}/.the-loop/templates/requirements.md`
   (`${CLAUDE_PLUGIN_ROOT}` = the installed plugin's root; same in Cursor): introduction, user
   stories, and EARS acceptance criteria (`WHEN <event> THEN the system SHALL
   <response>`). Set front-matter `phase: requirements-definition`, `status: draft`,
   `workItem: draft-<slug>`, and the required `collaborators`.

4. **Identify collaborators up-front** (see `reference/collaboration.md`).

5. **Request human review** of the requirements (`workflow.requireHumanReviewPerPhase`,
   default true). Because there is no ticket yet, review happens wherever the user
   prefers (PR/interactively); record the approver — paper trail.

6. **Point to the next step:** `/the-loop:create-ticket docs/specs/draft-<slug>/requirements.md`
   to mint the ticket and promote the folder out of `draft-`.

Do not create the ticket here — that is `/the-loop:create-ticket`.
