---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#382"
---

<!-- Authored per the the-loop:writing skill. -->

# Documentation: the poll clocks are this machine's, not the repository's

> The `capability-docs` node's record: the capability docs and the user-facing docs this
> change makes wrong, updated in the same pull request.

## Capability docs

| Doc | What changed |
|---|---|
| [`docs/capabilities/webhook-triggers.md`](../../../capabilities/webhook-triggers.md) | the lazy closure rule now names where the window is measured — this machine's `poll-clocks.json`, not the ledger's own keys — and a history row records the move, its reason and its two consequences (the stale keys are read then stripped; a cycle that learns nothing writes no record) |
| [`docs/capabilities/control-plane.md`](../../../capabilities/control-plane.md) | the nested-PR rule said a moved row's age "falls back to `poll.lastPolledAt`"; it now says the read surface joins that value from this machine's clocks |

No other capability doc names either clock.

## Documentation

| Doc | What changed |
|---|---|
| [`docs/cli/state.md`](../../../cli/state.md) | the directory tree, the classification table (one new row) and a new **Poll clocks** section describing the file, its two fields, why it is local, what an upgraded record does, and what deleting it costs. The `poll` section's table loses both clocks and gains a paragraph saying where they went and that the control plane still serves them; the record's JSON example and the `pullRequests` prose drop them; the `sessions reset` table gains a row; the hand-off section says a new machine starting with no clocks is the design working |
| [`docs/decisions/decision-131.md`](../../../decisions/decision-131.md) (new) + `decisions.md` | the durable record: a poll clock is a machine reading, both clocks move, the split is at the storage boundary, the upgrade is a read-fallback, the record is written only when it changed, the control plane still serves them, no config key |
| [`ui/src/api/types.ts`](../../../../ui/src/api/types.ts) | `WorkItemRecord`'s doc comment says the served record is the portable file **plus** the serving machine's poll clocks, and `lastPolledAt`'s comment says where it is stored and when it is absent |

**Not changed, and why:** `README.md` and the documentation site's landing pages describe
what the-loop does, not where one generated file lives. The skill and its `reference/`
docs describe the PDLC, which this does not touch. No config key changed, so no
`docs/config/` page and no schema page is affected — `test_docs_parity.py` covers that
claim mechanically. `docs/reports/gh-queries.md` mentions that `PollState` records
`lastPolledAt`, which is still true; it is a dated report, not living documentation.
