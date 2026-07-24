---
type: brainstorm
phase: brainstorming
workItem: ""                 # ticket id (or draft-<slug> when no ticket exists yet)
status: draft                # draft | in-review | approved  (approved == "locked")
approvedBy: []               # handles/roles who locked this artifact (paper trail)
collaborators: []            # roles pulled in to brainstorm, e.g. [product-manager, architect]
overrides: {}                # per-work-item overrides of .the-loop/harness-config.yaml
---

# Brainstorm: <work item title>

> Phase 0 (optional) — the **root artifact**. A scratchpad for exploring the problem
> *before* committing to requirements. Free-form on purpose: capture the idea, the
> options and the open questions here, iterate on it with feedback, and once it is
> **locked** (`status: approved`) derive `requirements.md` from it
> (`/the-loop:new-requirement`). Skip this phase entirely when the work is already clear.

## Problem / opportunity

What are we trying to solve or improve, and why now? The itch that started this.

## Context & constraints

What's known: existing behaviour, prior art, constraints, deadlines, non-negotiables.

## Ideas & options

Brain-dump the candidate directions. Keep the ones worth carrying forward; strike the
rest with a note on *why* (a rejected option is itself a finding).

- **Option A —** … (pros / cons)
- **Option B —** … (pros / cons)

## Sketches & notes

Rough diagrams (mermaid), snippets, links, references. Nothing here is a commitment.

## Open questions

The things we don't yet know. These are what feedback rounds resolve — raise the ones a
human must answer as ticket comments (paper trail) and link them here.

## Leaning / working hypothesis

Where the thinking is trending and what the next artifact (`requirements.md`) will likely
assert. Filled in as the brainstorm converges.

## Hand-off → requirements

When this is locked, what carries forward into `requirements.md`: the chosen direction,
the user stories it implies, and the constraints that become acceptance criteria.
Everything not carried forward stays here as the record of what was considered.
