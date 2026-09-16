---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#370"
---

<!-- Authored per the the-loop:writing skill. -->

# Documentation: a pull request is tracked because the-loop recorded it

> The `capability-docs` node's proof, gating both sections (issue-174).

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `webhook-triggers.md` | The tracking/delivery split stated as a rule: the poller's ledger owner comes from the recorded binding alone, a routing decision writes the registry endpoint and no `work-item-state.json` row, and delivery is explicitly unchanged. The `link-pr` rule gained the `PostToolUse` hook as its primary path | yes (issue-370) |
| `process-graph.md` | A work-item review's `Pull requests:` scope is pre-filled from `pullRequests[]` then `pr-loops/`, and asks GitHub nothing; `linked-pulls` named as retired and why | yes (issue-370) |
| `cli.md` | `sessions link-pr` is the single writer of the work item's tracked pull requests, and the plugin's hook runs it | yes (issue-370) |
| `distribution.md` | `hooks/hooks.json` declares the Stop gate and the `PostToolUse` recorder; Cursor has a surface for the first and none for the second | no — the bullet it amends is the SessionStart/Cursor parity rule, and the change is carried in webhook-triggers' and cli's rows rather than duplicated |
| `review-loop.md` | **unaffected** — it describes the critic/self-review rounds and the design-critic node, not the review *loop's* brief gate, and names neither the linkage nor the pre-fill | n/a |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/cli/state.md` | `linkedBy` has one value the-loop writes, with the `"event"` rows kept as history; the session-record section now says why an endpoint is added by routing while a `work-item-state.json` row is not |
| `docs/cli/commands/sessions.md` | `link-pr` is also the only writer of `pullRequests[]`, and a tip that Claude Code runs it through the plugin hook |
| `skills/the-loop/reference/automation.md` | The record-every-PR rule leads with "in Claude Code this is automatic" and keeps the command as the fallback for a harness with no `PostToolUse`; the harness-hooks bullet lists all three shipped hooks and states the preference for a hook over a prose rule |
| `docs/decisions/decision-129.md` (+ index) | New: routing may guess, tracking may not |

## Not documented, deliberately

The `pr-loops/` pre-fill source can still surface a pull request that reached the work item
by inference, because delivery is unchanged. It is named in `design.md` § C3 as a known
consequence rather than written into a capability doc: the capability docs describe the
rule, and this is a residue of the boundary the rule deliberately stops at.
