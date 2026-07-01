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

**Read the `the-loop` skill and `reference/workflow.md` first** (phases, EARS, reviews).

## Steps

1. **Create a temporary spec folder.** Slugify `$ARGUMENTS` → `<slug>` and create
   `docs/specs/draft-<slug>/`. `draft-*` folders are the-loop's convention for a spec
   that has no ticket yet; `/the-loop:create-ticket` renames it to `docs/specs/<id>/`.

2. **Write `requirements.md`** from
   `${CLAUDE_PLUGIN_ROOT}/.the-loop/templates/requirements.md`: introduction, user
   stories, and EARS acceptance criteria (`WHEN <event> THEN the system SHALL
   <response>`). Set front-matter `phase: requirements-definition`, `status: draft`,
   `workItem: draft-<slug>`, and the required `collaborators`.

3. **Identify collaborators up-front** (see `reference/collaboration.md`).

4. **Request human review** of the requirements (`workflow.requireHumanReviewPerPhase`,
   default true). Because there is no ticket yet, review happens wherever the user
   prefers (PR/interactively); record the approver — paper trail.

5. **Point to the next step:** `/the-loop:create-ticket docs/specs/draft-<slug>/requirements.md`
   to mint the ticket and promote the folder out of `draft-`.

Do not create the ticket here — that is `/the-loop:create-ticket`.
