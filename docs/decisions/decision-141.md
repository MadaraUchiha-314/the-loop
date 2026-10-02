# Decision 141: a work item is registered on the instance that accepted it, session or not

- **Status:** proposed (the owner decides at the PR)
- **Date:** 2026-10-02
- **Work item:** [issue-453](https://github.com/MadaraUchiha-314/the-loop/issues/453)
- **Deciders:** MadaraUchiha-314 (the ask), the-loop (design)
- **Refines:** [decision-140](decision-140.md) D8 (every lifecycle act needs a work item
  registered on the executing instance) · [decision-113](decision-113.md) (the `ended`
  stamp) · issue-322 (the control record names the instance that wrote it)

## Context

Decision-140 D8 made every lifecycle act — `pr create`, `pr merge`, `pr resolve-thread`,
`ticket close` — conditional on a work item registered on the executing instance, and
read "registered" off the session registry alone: a live session for the ref, a live
session recording the ref as its pull request, or an ad-hoc `the-loop do` item naming
it. Since issue-358 the daemon parks a started work item at its first human gate
**without** a session, and issue-450 made that parking survive. Such an item is accepted
by the instance (`sessions start` answered `waiting`, the control record says
`start_requested`) and yet, by D8's reading, belongs to nobody: the operator could not
close it through `the-loop ticket close`, used `gh`, and then had to `sessions stop` by
hand so the start would not fire later.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **Registered means accepted.** Beside the registry, the guard reads the work item's control record: when this instance wrote it (its `instance` equals the config's declared name — an unnamed instance owns unnamed records only) and the portable record is not stamped `ended`, the item is this instance's. | The record is what the instance wrote when it took the item; it already defines the managed set for `instances` and the locked-mode gate (issue-322). Reading it needs no new file, no session and no spawn. |
| D2 | **The control-record source reaches the work item itself only.** The pull-request scan stays over live sessions. | A parked item has recorded no pull request, so there is nothing for it to own; widening to "any PR" would re-create the generic authority D8 refused. |
| D3 | **The command is not inspected; `ended` wins.** A stopped-but-open item is still tracked here; an ended one is not, whatever its record says. | A `ticket close` after a close must still be authorized to be idempotent, and the daemon's closure path clears the record and stamps `ended` anyway; `ended` is the one fact that says the item is over. |
| D4 | **`ticket close` on a parked item records the `stop`** — source `cli`, this instance's name, the `work_item_start` mark cleared — and says `startCancelled`. A live session's closure stays the daemon's. | It is exactly what the operator typed by hand; writing the same record through `ControlStore.record` means the spawn gate reads it the same way, so a closure can never become a launch. |
| D5 | **The config's name is the reference, never the record's.** | A portable record is a file like any other; a record cannot name itself into an instance. |

## Consequences

**Good.** The operator closes or cancels a parked item in one act, through the CLI,
the route or the MCP tool. No session, tmux window or model spend is bought merely to
register. The refusal keeps its meaning: untracked refs, foreign records and ended
items are still refused with nothing sent.

**Costs, accepted.** One more small-file read per lifecycle act, taken only after the
registry said no. A stopped-but-open item an authorized user disarmed by comment on
this instance is also closable here, which is consistent with how the managed set is
already counted.
