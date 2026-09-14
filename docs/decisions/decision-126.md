# Decision 126: absence of local state is not evidence of absence of work — a forgotten work item is refused, never restarted

- **Status:** proposed
- **Date:** 2026-09-14
- **Deciders:** the-loop (engineer), reported by @jc1993
- **Work item:** [issue-363](https://github.com/MadaraUchiha-314/the-loop/issues/363)

## Context

A devbox was destroyed and rebuilt. The new daemon came up against eighteen labelled work
items that had been running for days, and within ninety seconds it reset thirteen of them
to their first node, replayed sixty-four old comments — ten of them `the-loop execute`
commands — and spawned four of them twice. Forty-one of its forty-five posts were
byte-identical repeats of posts from days earlier; four humans re-approved gates they had
already approved; one agent redid a brainstorm and re-drafted an 8.7 KB requirements
document that already existed on the item's own pull request.

Nothing crashed. Every read behaved as documented. The three records that answer *where is
this work item?* — the graph pointer, the comment ledger, the control record — all lived on
the daemon's disk, all read as empty, and **empty meant "this work item has never started"
everywhere it was read**.

The graph pointer is the load-bearing one. `docs/specs/<id>/graph-state.json` is checked in
and its own docstring says so — but it is checked in on the work item's **branch**, and a
`clone`-strategy workspace for an *issue* work item is prepared with no branch at all. The
daemon already published the *frozen selection* to the portable record (issue-177), so a
portable channel existed; it simply carried which phases the item walks and not which one
it is on.

The question this raises is not "how do we find the file?" but: **what may a machine that
has forgotten a work item conclude about it, and from what?**

## Decision

**A machine that cannot prove a work item's position does not move it.** Absence of local
state is treated as absence of *memory*, never as absence of *work* — and the two durable
facts that distinguish them are facts the-loop itself wrote, on the work item rather than
on the machine: the ticket's `loop:<phase>` label, and the-loop's own self-authored
comments on the thread.

Four consequences, each failing in the direction that costs a human a re-post rather than a
rewind:

1. **Refuse, do not rewind.** When the local graph state is absent and the ticket carries a
   phase label other than the resolved graph's start node's, every pointer-moving action —
   `start` *and* `advance`, because `Runtime.advance` reads an empty state as the start node
   too — is refused (`graph.rewind_refused`). Nothing is entered, no label is written, no
   gate is re-asked, and the spawn still happens so a human can be told.
2. **Publish the position, restore it verbatim.** Every write to an outer loop's graph state
   is published to the portable record's `graph.position`, and a missing local state is
   restored from it before anything reads the state — after which `Runtime.start` is the
   no-op it already is for a work item with a pointer.
3. **Baseline the thread, including its commands.** A first sight of a work item whose
   thread shows the-loop has worked it, on a machine with no session and no control record,
   baselines everything — and says so once on the ticket, naming the instant before which
   nothing will be re-run.
4. **Tell the new session what it is.** A spawn into that state carries a notice that the
   conversation it is replacing is gone, and must locate the existing pull request, branch
   and artifacts and reconcile before producing anything.

## Alternatives rejected

**Adopt the phase from the label.** The obvious "fix": read `loop:implementation` and enter
the node with that phase. Rejected because a label names a *phase*, not a node, and says
nothing about which gates were approved, which phases the human declared away at selection,
which surface the item chose, or which model it was frozen to. Entering a node derived from
a label would fabricate all four, and it would make a label — writable by anyone with repo
write access — an input that *places* a pointer. The refusal fabricates nothing: a forged
`loop:complete` on a fresh ticket buys a refusal and a notice, and `the-loop graph force
<id> --to <node> --reason <why>`, which already demands an actor and a reason and is
audited, stays the only way to place one.

**Commit and push the portable directory from the daemon.** The ticket offers it. Rejected:
a daemon that pushes to a work item's repository on its own is a new write path with its own
failure modes — conflicts, a branch nobody asked for, force-push — and it would not have
helped the reporter anyway, whose nine missing records had never been committed by anything.
Publishing the position makes the record *complete*; whether an operator tracks it stays
their existing choice.

**Check out the work item's PR head branch for an issue work item.** Also offered. It would
make `graph-state.json` findable more often, but it changes what an issue work item's
workspace *is* for every item, started or not — a workspace-strategy change wearing a
recovery hat. Making the missing file harmless is the fix; finding it more often is a
separate improvement.

**Condition the no-replay rule on "a daemon start that finds zero session records"**, as the
ticket suggests. Rejected because a genuinely fresh install also finds zero session records,
and there issue-119's rule — a `the-loop execute` posted before the poller first saw the item
still starts it — must keep working. The distinction that actually holds is per work item:
*this thread shows the-loop has worked here, and this machine does not remember it.*

**Coalesce the presence spawn with same-cycle forwarded comments in the poller.** Rejected
as unnecessary once a booting session stops being read as a dead one: the comment waits for
the pane instead of racing it, which is the same outcome without reordering a poll cycle.

## Consequences

- A rebuilt machine is **quiet** about an advanced work item until an operator acts. That is
  deliberate and is the cost of the guarantee: thirteen wrong advances are worse than
  thirteen notices. The notice names both remedies (`the-loop check` to see what the
  artifacts say, `the-loop graph force` to place the pointer), and item 2 above means an
  operator who tracks `.the-loop/portable/` never reaches this path at all.
- **`the-loop reset` now means what it says.** Resetting a work item clears its control
  record — "disarmed" — and the old thread's `the-loop start` used to silently re-arm it on
  the next cycle. It no longer does. An operator who resets an item the-loop has posted on
  re-posts the command.
- A `loop:<phase>` label is now load-bearing, so a project that strips or rewrites those
  labels by hand loses the protection. It fails safe in the removing direction (no label,
  today's behaviour) and safe in the adding direction (a refusal), and never in a direction
  that moves a pointer.
- The portable record grows one key per work item, the graph state verbatim. It is written
  on every outer-loop transition, inside the lock that transition holds.
- Deliveries inside `routing.tmux.spawnGraceSeconds` (default 20) of a session's creation
  are released for retry instead of respawning. An operator who wants the old verdict sets
  it to `0`.
