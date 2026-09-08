# Decision 110: an instance is a named, scoped `cli-config.yaml`; new work reaches it by mode and by address

- **Status:** proposed
- **Date:** 2026-09-08
- **Work item:** [issue-322](https://github.com/MadaraUchiha-314/the-loop/issues/322)
- **Deciders:** MadaraUchiha-314 (the ask and its three questions), the-loop (design);
  MadaraUchiha-314 (owner, at the PR)
- **Refines:** [decision-032](decision-032.md) (the CLI config is the daemon's, not a
  repository's), [decision-040](decision-040.md) (the label arms, an authorized start
  runs), [decision-046](decision-046.md) (portable vs local state)

## Context

Every instance of the-loop was the same instance: one `cli-config.yaml` describes one set
of daemons, and every daemon judges every labelled event the same way. Two instances
watching one repository both spawn for one `the-loop start`. The issue asks for several
instances in isolated environments, each scoped to its own work items, with a way to say
which work item goes where and a way to lock an instance — and asks whether the scope is
a new file, and how one talks to an instance.

Two later additions are named as constraints, not deliverables: a manager instance that
serves the same API aggregated across instances, and an instance managed from a ticket.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The scope lives in `cli-config.yaml`, under a top-level `instance` block** — no second file. | An instance *is* a running CLI config (decision-032): the file already names the daemons, the state root, the authorized users. It is hot-reloaded by both daemons and the service and editable from the dashboard, so a scope edit is live without a restart. A second file would be a second thing to find, back up, reload and document — for three keys. |
| D2 | **The managed set is derived, not kept**: the declared list ∪ live session records ∪ control records. | The instance already writes a record for every work item it acts on (decision-046's portable half, and the local registry). "What am I managing?" is a question those records answer; a second list would drift from them. The declared list is the one thing the records cannot know: what the operator wants *added*. |
| D3 | **Three modes, not a boolean**: `open` (13.3.1 — take any armed, authorized start), `addressed` (take only what names me), `locked` (take nothing new; the declared list is the door). | The issue's "lock" is the closed end. But two instances need a steady state that is neither wide open nor frozen: `addressed` is the multi-instance normal, where every start says which instance runs it. `open` stays the default so a lone instance that names itself changes nothing. |
| D4 | **An address token in the comment** — `instance:<name>`, grammar-validated, beside any keyword — rather than a per-instance keyword vocabulary. | Keywords are already configurable per config, so `laptop-b start` could be done today by renaming eleven keywords on each instance; it would also split the thread's vocabulary and every doc. One token composes with every command, is validated like the collaborator `@login` (issue-307), and is what a future ticket-managed instance would type. |
| D5 | **An explicit address is authoritative** — it wins over the managed set, and an address never unlocks a locked instance. | The human named the instance; a managed-set override would let two instances both act on one steer. Locked means locked: the only door is the config (the issue's own wording). |
| D6 | **A refusal leaves no mark**: no reaction, no comment, no record — an event-log line and a settled delivery. | Another instance may own the work item. A non-owner that reacts or comments is noise on the thread, and a non-owner that records a `stop` is a second daemon steering the item. |
| D7 | **Unknown or impossible scope config narrows**: an unknown mode and `addressed` without a name both resolve to `locked`, with a warning. | A scope typo must not make an instance take on work it was not meant to. `locked` is loud in `status` and the event log; `open` would be silent and wrong. |
| D8 | **The future manager is a client, not a peer protocol.** Each instance serves one identical surface, `GET /api/v1/instance` names it and lists its managed set, `control.instance` is on every portable record; instances share nothing and never talk to each other. | Aggregation over N base URLs is exactly what the dashboard already does for one; a peer protocol would add a second trust boundary and a discovery problem this work item has no requirement for. |
| D9 | **`instance.ticket` is reserved, not added.** | An instance managed from a ticket is a loop of its own (which events, which keywords, which gates); designing the binding before that loop is guessing. The token (D4) and the block (D1) are where it attaches. |

## Consequences

**Good.** Two instances on one repository stop spawning for the same start once either
is `addressed` or `locked`; an operator can pin a work item to an instance by config or by
one word on the ticket; the thread and the portable record say which instance took an
item; a session knows its instance (`THE_LOOP_INSTANCE`); an unnamed open instance is
byte-for-byte 13.3.1.

**Costs, accepted.** Two `open` instances still clash — the design makes the steady state
reachable, not automatic, and the guide says so. A work item declared on two instances is
managed by both; that is the operator's declaration, honoured. A comment consumed by a
refusal is not re-judged when the scope changes — the operator claims it with
`the-loop sessions start` on the instance, which is the addressed form.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| A separate `instance.yaml` / `scope.yaml` | A second file with three keys, outside the reload and the dashboard; the issue's own question, answered: no |
| A registry of "my work items" the instance appends to on claim | Drifts from the records that already say the same thing (D2); a second write on every claim path |
| A boolean `locked` only | No steady state for several instances short of freezing them (D3) |
| Per-instance keywords (`laptop-b start`) | Splits the vocabulary per instance across eleven keywords and every doc; composes with nothing (D4) |
| `@name` as the address | Pings a GitHub user of that name |
| Claim by label (`the-loop: instance/laptop-b`) | A label is a fact about the item, not a steer for one command; every instance would need label-write rights and a race on who labels first |
| The managed set wins over an explicit address | Two instances act on one steer when both manage an item (D5) |
| Reacting or commenting on a refusal | Marks from a non-owner (D6) |
| Unknown mode → `open` | Fails open on a typo (D7) |
| A gossip / lease protocol between instances | A second trust boundary and a discovery problem with no requirement behind it (D8) |
