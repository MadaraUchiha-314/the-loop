---
type: evidence
record: documentation
workItem: "github:MadaraUchiha-314/the-loop#368"
---

# Documentation: one rule for where a work item's attributes live

## Capability docs

| Doc | What changed |
|---|---|
| [`cli`](../../../capabilities/cli.md) | the attribute rule as a behaviour clause (three files, one per party; each attribute written once; a machine handle never in a tracked file; the classification declared as data and enforced), and the one-portable-record-per-work-item rule with the poller's owner resolution |
| [`process-graph`](../../../capabilities/process-graph.md) | the selection freezes into the work item's own file only; the daemon reads the choices from the checkout, with the portable `graph` section as the legacy fallback; `session: inherit` resolves through the session registry |
| [`interactive-sessions`](../../../capabilities/interactive-sessions.md) | the local record is a map of sessions keyed by ref, holding handles alone; cleanup's kept sections renamed |
| [`channels`](../../../capabilities/channels.md) | the binding moved to the work item's portable record, the cursor to its session record, and what remains in the channel file |
| [`control-plane`](../../../capabilities/control-plane.md) | one row per work item; why the issue-302 client-side join stays |
| [`webhook-triggers`](../../../capabilities/webhook-triggers.md) | the daemon reads the frozen choices from the checkout, records each routed pull request through the coupling, and stamps no `ended` on an owned pull request |
| [`spec-workflow`](../../../capabilities/spec-workflow.md) | the spec directory carries the work item's pull requests, and no session handle |

## Documentation

| Surface | What changed |
|---|---|
| [`docs/cli/state.md`](../../../cli/state.md) | a new section stating the rule with its mermaid diagram and the kind → home table; a new top-level section for `docs/specs/<id>/work-item-state.json` with an attribute table; the portable record's `graph` section replaced by `pullRequests` and `channels`; the session record's new shape; the channel file reduced to what belongs to no work item; the classification table's three rows re-worded |
| [`commands/upgrade-the-loop.md`](../../../../commands/upgrade-the-loop.md) | a new paragraph reporting the four locations that are no longer written — the `session` block, the portable `graph` section, the channel file's binding maps, and a pull request's own portable record — each as *"no longer written; read where it still matters"*, with **delete none of them** |
| [`docs/decisions/decision-128.md`](../../../decisions/decision-128.md) | the decision, and `decisions.md` indexes it |

A parity test now holds the first of these to the code: `test_the_attribute_table_is_documented`
fails when `ATTRIBUTES` names a key the page does not.

## Evidence

The spec chain's own artifacts are this work item's exploratory pass: the design's from →
to table and worked example are what the ticket asked for as its second report, and the
requirements' § Audit is the first.
