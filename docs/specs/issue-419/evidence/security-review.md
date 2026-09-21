---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#419"
---

# Security review: one verbosity switch over the whole trace, defaulting to quiet

> The security-review gate's record, per `reference/security.md`. Risk tier 3, so the
> autonomous review suffices and no named human security sign-off is required (that
> threshold is tier 4).

## Scope

Seven files: three under `ui/src`, three UI test files, one capability doc. No request,
route, payload, credential, stored setting or event type changes — `git diff --stat`
touches no Python and no `.the-loop/` path. The change is a render-time predicate over
data the panel already holds.

## Threat model

| Asset | Threat | Verdict |
|-------|--------|---------|
| the operator's view of a failure | a failure is hidden by the new default | **bounded** — `level=error` is never classified as plumbing, and the switch restores everything; the one thing that *is* newly hidden is a `warning` in a plumbing family, stated in `design.md` § What it costs |
| the operator's belief that they saw the whole trail | a filtered-to-empty panel looks like an empty trail | **bounded** — a view the filter emptied names its hidden count and the switch; a source empty for its own reasons keeps its own, different empty state |
| untrusted transcript and event text | the filter reads rendered content and could be steered by it | **not reachable** — the predicates read `row.kind`, `row.text`/`row.thinking` emptiness, `event.event` and `event.level` only; no payload field, no rendered markup |
| untrusted text rendering | escaping weakened | **unchanged** — every row still renders through React; `Transcript.test.tsx`'s attacker-shaped-tool-text case is untouched and passing |

## Abuse case

**An event crafted to hide itself.** An emitter that named its event `poll.something`
would have it hidden by default. Two things bound it. The emitters are the loop's own
processes appending to a local, append-only JSONL, so an attacker who can write that log
can already write anything into it — the classification adds no capability. And the
reader's escape hatches hold regardless of the name: `level=error` always renders, the
switch restores the whole trail, and a panel the filter emptied says so rather than
looking empty. A crafted name can make a row quiet; it cannot make the reader believe
nothing was there.

**Related, and deliberate:** the family list fails **open**. A plumbing family nobody has
classified is noisy until someone adds it, rather than silently dropped. That is the
direction the failure must point for an observability surface.

## Findings

None blocking. No finding required a security-relevant decision, so nothing escalated.
