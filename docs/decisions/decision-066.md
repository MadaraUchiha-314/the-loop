# Decision 066: user-facing documentation is a completion gate, on the node that already reads the log

- **Status:** proposed
- **Date:** 2026-08-07
- **Deciders:** MadaraUchiha-314
- **Work item:** [issue-174](https://github.com/MadaraUchiha-314/the-loop/issues/174)

## Context

**the-loop shipped a breaking change to its own process and left its front page describing
the process it replaced.** issue-172 split the PDLC into two loops, issue-163 added a
fourth spec artifact, and issue-109 turned the whole thing into an executable graph — yet
`README.md` and the site's entry pages still described one loop, three artifacts and a
plugin.

That is not carelessness; it is the predictable result of where the gates are. Capability
docs stay current because the `capability-docs` node reads the execution log's
`## Capability docs` section before a work item can complete, and issue-167 established
exactly how a node gates a section of an artifact it did not author (`validates:`). The
README and the site are gated by nothing at all, so they drift until someone notices.

The forces:

- **Every gate costs something.** A new node costs an edge, a `stage:` key, a phase
  question and a place in both loops' entry chains.
- **A structural check cannot judge prose.** Whatever is gated, the mechanism can only
  prove a section exists — not that what it says is true.
- **The two doc kinds are not the same audience.** Capability docs serve a reader who
  already uses the project; the README and the site are what everyone else meets first.
- **Adding a required section to a shared artifact is breaking** for any work item whose
  log predates it.

## Decision

**`## Documentation` joins `## Capability docs` on the outer loop's existing
`capability-docs` node**, and the ready-to-ship gate gains the matching item: the
user-facing documentation a change made wrong — `README.md`, the site under `docs/`, and
the operating-model skill with its `reference/` docs — is updated **in the same pull
request** as the change.

Four sub-decisions:

1. **No new node.** One element in an existing `sections:` list, plus one heading in the
   bundled `execution-log.md` template so the P5c parity assertion holds. No hook, runtime
   or schema change.
2. **The node keeps its id, stage and phase.** `stage: capability-docs` is a public key in
   operators' `tokenEconomy.modelRouting.stages` and `thinkingEffort.stages` maps; renaming
   it to `documentation` would silently drop their configuration on upgrade for a cosmetic
   gain.
3. **Two sections, not one widened section.** Folding user-facing docs into the capability
   row would lose which of the two was skipped.
4. **The inner `pdlc-pr-loop` gates neither.** A work item's documentation is decided once,
   at the outer level, for the same reason its requirements are.

Alongside it, the README is rewritten to **delegate**: it summarises and links the
documentation site rather than restating it. Two copies of a fact is one copy that rots,
and the gate says "update what the change made wrong", not "restate everything everywhere".

## Consequences

**Easier.** The next process change cannot reach `complete` with the front page describing
the previous one — the same way capability docs have been protected since issue-167. The
record is a table naming documents, so a reviewer can check the claim against the diff. The
README shrinks, so there is one less place for a fact to rot.

**Harder, and stated rather than mitigated.** Every execution log authored before this
change fails `capability-docs` the next time it runs, until someone adds the heading. That
is one heading and one sentence, and it is precisely the work the gate is asking for.
Automatic backfill was rejected: a hook that writes the section it is about to check would
report success without running — the exact defect issue-167 was raised to remove.

**Unchanged.** The check is structural. A `## Documentation` heading holding placeholder
text passes, exactly as `docs/capabilities/process-graph.md` already records for every
section gate. The gate proves the record exists; the reviewer judges whether the
documentation is any good. Claiming more would be claiming more than the mechanism
delivers.

## Alternatives considered

- **A dedicated `documentation` node** — rejected. Four structural costs (an edge, a stage
  key, a phase question, a place in the entry chains of both loops) to gate one heading in
  a file another node already opens.
- **Rename `capability-docs` to `documentation`** — rejected. Breaks operators'
  stage-keyed model-routing and thinking-effort configuration silently, on upgrade, for a
  naming improvement.
- **Widen `## Capability docs` to mean all documentation** — rejected. One row cannot say
  which of two different audiences was served and which was skipped.
- **A docs-freshness test** (assert the README states the current phase sequence) —
  rejected. It would pin wording rather than behaviour. What *is* mechanically checkable is
  already pinned: P4 asserts the graph defines the phase sequence the prose renders, and
  P5c asserts every gated section exists in its template.
- **Leave it to review discipline** — rejected by the evidence. Review discipline is what
  was in place while the front page went three releases out of date.
