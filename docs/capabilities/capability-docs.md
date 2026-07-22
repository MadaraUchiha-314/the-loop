# Capability: capability-docs

> This layer itself: living capability documentation as the organized view of the
> per-work-item specs — dogfooded by documenting itself here.

## What it is

The knowledge layer under `workflow.capabilitiesDir` (default `docs/capabilities/`)
that answers "what does the product do *today*, by topic?" without making the reader
merge specs in ticket order. Raw specs are *deltas*; capability docs are *state*.

## Current behaviour

- Each capability SHALL have one living doc `<capabilitiesDir>/<capability>.md`
  (template `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/capability.md`) containing: narrative, current
  behaviour (normative), design pointers, and a history table.
- A capability doc SHALL be the **single source of truth for the capability's current
  behaviour**; the raw specs under `docs/specs/<id>/` remain the historical record.
- WHEN a work item changes a capability's behaviour THEN the loop SHALL update the
  affected capability doc(s) **in the same PR**, minting new docs for first-touched
  capabilities and updating the [`capabilities.md`](capabilities.md) index.
- WHEN the ready-to-ship gate is evaluated THEN it SHALL require the fold-in (or
  "none affected" recorded in the execution log).
- Every behaviour statement SHALL be traceable via the history table to the work-item
  spec, decision record(s) and PR that produced it.
- The taxonomy SHALL admit both product-feature and architecture shaped capabilities
  and SHALL evolve through PR-review feedback on the docs themselves.

## Design

[`docs/specs/issue-25/design.md`](../specs/issue-25/design.md) ·
[`reference/workflow.md` § capability docs](../../skills/the-loop/reference/workflow.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-25 | Introduced the layer: template, `workflow.capabilitiesDir`, fold-in gate, backfill of all existing capabilities | [spec](../specs/issue-25/), [decision-020](../decisions/decision-020.md), PR #26 |
