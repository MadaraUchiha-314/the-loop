# Decision 020: Capability docs are the organized view of specs (single source of truth for current behaviour)

- **Status:** accepted
- **Date:** 2026-07-07
- **Deciders:** @MadaraUchiha-314 (issue #25, PR #26 review)
- **Work item:** issue-25

## Context

Specs are produced per work item under `docs/specs/<id>/` — a chronological record.
Humans (and AI) read by topic: the current behaviour of a capability is smeared across
every spec that ever touched it, and the merge burden grows with every work item.
Issue #25 asked how to organize specs, where raw vs organized specs live, and whether
an "organized spec" is just documentation of the capability. All open questions were
answered by the reviewer in PR #26.

## Decision

Keep the raw record untouched and add an **organized layer**: living **capability
documentation** under `workflow.capabilitiesDir` (default `docs/capabilities/`,
indexed by `capabilities.md`, template `.the-loop/templates/capability.md`).

- **Raw vs organized:** raw specs are *deltas* (history); a capability doc is *state* —
  the **single source of truth for the capability's current behaviour**. The answer to
  the issue's closing question is "yes": the organized spec *is* the capability
  documentation — no third artifact kind — distinguished from plain docs by
  **traceability** (history rows linking specs/decisions/PRs) and a **gate**.
- **Taxonomy:** both product-feature and architecture shaped; minted emergently and
  evolved through PR-review feedback on the docs themselves.
- **Fold-in:** affected capability docs are updated **in the same PR** as the work
  item, enforced as a new **ready-to-ship gate item** ("none affected" is recorded in
  the execution log otherwise).
- **Backfill:** the layer was seeded from all existing specs (issues 1, 11, 12, 15,
  17, 18, 21 and 25).

## Consequences

- Readers get the current truth by topic in one hop; "why is it like this?" is one more
  hop via the history table.
- The single source of truth for *current* behaviour deliberately moves from the spec
  chain to the capability doc; drift risk is bounded by the same-PR gate and by
  reviewers seeing the capability-doc diff next to the change it documents.
- One more artifact per behaviour-changing work item; mitigated by keeping docs
  compact (consolidate behaviour, link everything else).
- `docs/architecture/` remains the "how it's built" view; the two layers link rather
  than duplicate.

## Alternatives considered

- **Physically reorganize `docs/specs/` by capability** — rejected: work items span
  capabilities, taxonomy churn forces link-breaking moves, and readers still merge N
  specs (brainstorm Option B).
- **Index only (capability → work-items table)** — rejected as the whole answer: solves
  discovery, not comprehension; survives as each doc's history table (Option C).
- **Rely on `docs/architecture/` as-is** — rejected: nothing forces it current per work
  item and it carries no requirements traceability (Option D).
