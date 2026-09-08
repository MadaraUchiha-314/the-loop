# Decision 109: the channel pipeline reads the graph through the dispatcher's own coupling, and a gate it cannot read is left to the ledger

- **Status:** proposed
- **Date:** 2026-09-08
- **Work item:** [issue-321](https://github.com/MadaraUchiha-314/the-loop/issues/321)
- **Deciders:** jc1993 (the report and its two fix options), the-loop (design);
  MadaraUchiha-314 (owner, at the PR)
- **Refines:** [decision-103](decision-103.md) (through the ledger, never around it;
  grants are event types), [decision-042](decision-042.md) (a classification is a fact,
  never a destination)

## Context

Issue-309 let a Slack reply answer a human gate: the pipeline classifies a reply as
`gate.feedback` when the work item's graph is parked at a human node, records it
**unmarked**, and the ledger's ingress judges it as it judges any typed comment. Every
other reply is a `work-item.reply`: a **marked** mirror on the ticket, delivered straight
into the session. The marker is load-bearing on that record — the pipeline already
delivered the text, and an unmarked copy would be delivered again by the ingress.

@jc1993 found that an authorized approval from Slack was recorded as the marked kind and
so was never read by the gate. The root cause (`bugfix.md`) is that the pipeline built
its graph reader without the control store the dispatcher hands its own, so under the
default control policy the reader could not read any graph at all and reported every
work item as "not at a gate". Two more paths — no session record, any read fault — gave
the same answer for the same reason: the pipeline turned *cannot tell* into *not at a
gate*, and *not at a gate* into the one record shape no reader ever accepts.

The ticket offered two fixes: never mark an inbound human reply; or make the gate read
authoritative and fail *toward* `gate.feedback`.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The pipeline's reader is the dispatcher's construction.** `RoutingConfig.from_mapping(routing, layout)` → the registry at `registry_dir`, the `ControlStore` on `portable_dir`, `GraphLink(graph, control, store, authorized_users)` — the same arguments, in the same order, from the same config the call was given. A test pins the two together. | The bug was a second construction that drifted from the first. A reader with *fewer* guards was considered and refused: `_guarded`'s start requirement and ownership check exist so the daemon never reads a spec directory it has not proved is the work item's own (decision-044), and a classification that reads a foreign checkout's graph is a worse bug than one that reads none. |
| D2 | **The read has three answers, and "cannot tell" is one of them.** `True` at a human gate; `False` when the graph says so or the coupling is off; `None` for no record, no checkout, no context, a fault. | `bool` forced the third answer into the second, and the second is what chose the marked record. Naming the state is what lets the next step choose differently for it — and lets the event log say `gate: unknown` instead of nothing. |
| D3 | **`None` defers to the ledger when the channel may answer gates, and stays a reply when it may not.** With `gate.feedback` granted the reply is recorded unmarked (attributed as a *reply*, not as an answer to a gate the pipeline never saw) and delivered by nothing but the ingress; without the grant it is the marked mirror with direct delivery, exactly as before. | The authority on whether a comment answers a gate is the ingress, which consults the graph it actually keeps (decision-103 D1). When the pipeline cannot consult it, the only fail-closed choice is to hand the reply to that authority — the closed outcome for an approval is *refused by the gate*, never *hidden from it*. The grant bounds the deferral: a reply-only channel can still never produce anything the gate reads (issue-309 R2.3, "dropped, never downgraded"), so nothing widens. The cost is one ingress hop of latency for a reply the pipeline could not place, the same cost issue-309 already states for every relayed answer. |
| D4 | **A `work-item.reply` record keeps its marker.** Option 1 of the ticket — never stamp an inbound human reply — is not taken as written. | The pipeline delivers that reply into the session itself; an unmarked mirror would be delivered a second time by the ingress, which is exactly what the marker prevents (issue-309 D6). Option 1's intent — an authorized answer must never wear the-loop's "ignore me" — is met by D3 for the case where the marker was hiding one. |

## Consequences

**Good.** An approval from Slack locks the gate under the daemon's default policy; a
reply the pipeline cannot place is judged by the reader that can, instead of by nobody;
the event log says what the read returned; the two constructions of the coupling cannot
drift apart unnoticed.

**Costs, accepted.** A reply on a gate-granted channel for a work item the pipeline
cannot see reaches the session one ingress hop later than a direct delivery would have —
for a work item with no session record that delivery would have failed anyway, and for
a live one the hop is seconds (webhook) or a poll interval. The pipeline now imports
`webhook.dispatcher` lazily on the first reply, which the poll watcher and
`channels listen` did not before.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Never mark an inbound human reply (the ticket's option 1, as written) | The ingress would deliver an unmarked mirror into the session the pipeline already delivered it to (issue-309 D6); the marker on a `work-item.reply` is the loop-prevention half of direct delivery |
| Let the ingress read the envelope and accept a marked `work-item.reply` record at the gate | Makes the envelope authority rather than provenance (decision-103 D4) and lets a reply-only channel's record answer a gate — the grant would no longer bound what a message may become |
| A reader with no start requirement or ownership check | Reads graphs in checkouts the daemon has not proved are the work item's (decision-044, issue-113 A6) |
| `None` → `gate.feedback` regardless of the grant | A reply on a default-grant channel would be **dropped** as `unpublishable-event` whenever the read fails — a regression for every operator who never granted the gate |
| `None` → `work-item.reply` regardless of the grant (13.3.0) | The bug: the one record shape no reader accepts, chosen for exactly the case where the pipeline knows least |
| Remove direct delivery on gate-granted channels and relay everything | Every reply on such a channel pays the ingress hop, and the pipeline's ask → reply round trip (issue-245) was designed around direct delivery |
