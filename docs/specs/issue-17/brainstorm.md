---
type: brainstorm
phase: brainstorming
workItem: issue-17
status: approved
approvedBy: ["@MadaraUchiha-314 (issue #17 as authored)"]
collaborators: [product-manager, architect]
overrides: {}
---

# Brainstorm: a brainstorm phase for the-loop

> The root artifact for issue-17 — dogfooding the very feature it specifies. Locked; the
> chosen direction carries forward into `requirements.md`.

## Problem / opportunity

the-loop begins a work item at `requirements.md`. But not every work item is ready for
EARS acceptance criteria on day one — some start as a fuzzy idea that needs a scratchpad
to think in. And there's a deeper observation in issue #17: the loop's real engine is
*feedback + iteration on each artifact, advancing only when one is locked*. Requirements
is just the first place that engine runs today; it should be visible as a general rule
with an explicit **root artifact** at the top.

## Context & constraints

- Existing chain: `requirements → design → tasks → implementation`, each human-reviewed
  per phase (`requireHumanReviewPerPhase`).
- Phase state machine is tracked via ticket labels and mirrored in the execution log.
- Everything the-loop manages is enumerated in `.the-loop/manifest.yaml` and driven by
  `config.schema.json` / `config.yaml`.
- Must stay backwards compatible: existing specs have no brainstorm.

## Ideas & options

- **Option A — a separate optional `brainstorm.md` root artifact + `/brainstorm` command,
  converted to requirements by `new-requirement`.** Clean separation; rejected options
  stay in the scratchpad; conversion reuses an existing command. ✅ chosen.
- **Option B — a "scratch" section inside `requirements.md`.** Mixes throwaway exploration
  with the locked contract; muddies the single source of truth. ✗
- **Option C — mandatory brainstorm for every work item.** Too much ceremony for
  well-scoped work. ✗ (make it optional instead.)

## Open questions (resolved)

- *Mandatory or optional?* → **Optional.** Well-defined work starts at requirements.
- *New convert command or extend `new-requirement`?* → **Extend `new-requirement`** to read
  a sibling brainstorm; conversion is just "requirements from prior context".
- *Where in the state machine?* → after `not-started`, before `requirements-definition`.

## Leaning / working hypothesis

Add `brainstorming` as an optional Phase 0 with `brainstorm.md` as the root artifact, and
state the "iterate-until-locked, then advance" rule as a first-class principle applied at
every link of the artifact chain.

## Hand-off → requirements

Carries forward: the new artifact + template, the `/brainstorm` command, the conversion
path, the state-machine insertion, and the generalized iteration principle. Everything in
Options B/C stays here as the record of what was considered and rejected.
