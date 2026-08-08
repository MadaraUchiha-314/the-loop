# Decision 068: Every phase is selectable — the floor moves from the graph to the human

- **Status:** proposed
- **Date:** 2026-08-08
- **Deciders:** @MadaraUchiha-314 (owner's direction on the ticket; pending PR review)
- **Work item:** issue-179
- **Spec:** `docs/specs/issue-179/`
- **Revises:** [decision-067](decision-067.md) D2 (the never-skippable floor) and the
  `required: true` markers [decision-063](decision-063.md) put on `security-review` and
  `human-approval`. Both stand in every other respect.

## Context

[Issue #179](https://github.com/MadaraUchiha-314/the-loop/issues/179) opens narrow: *"For
documentation related changes, there's no testing plan that's required. Make that phase
also optional and hence selectable from the phase selection step."* [Decision
067](decision-067.md) D2 had explicitly excluded `test-planning` — "every change keeps a
proof plan, however small the matrix" — so a doc fix that unticked its whole spec chain
still authored a locked `testing-plan.md` of `n/a` rows.

Asked how far the vocabulary should go — the narrow ask, everything-but-the-two-required-
gates, or everything — the owner chose **everything**. This decision records that, and the
one thing that had to be built alongside it for the surviving phases to keep meaning
anything.

## Decision

**Every node of the outer loop is `skippable: true` except `phase-selection` and the
terminals. The floor stops being a set of phases and becomes a single invariant.**

| Sub-decision | What was chosen | Why |
|---|---|---|
| **D1 — the vocabulary is every phase but the gate** | `test-planning`, `implementation`, `verification`, `self-review`, `critic-review`, `security-review`, `evidence`, `capability-docs` and `reviewer-briefing` and `human-approval` all gain `skippable: true`, each with its own `on: skipped` edge to its ordinary successor. Two shipped sets: `spec-chain` (now including `test-planning`) and `review-chain` | The process should fit the change. Once the mechanism exists and is human-driven, a fixed list of exceptions is the harness deciding on the human's behalf — which is what issue-177 set out to stop, applied in the other direction. |
| **D2 — `phase-selection` is the invariant** | It keeps `required: true`, carries no marker, and remains the graph's `start`. The compile rule refusing `required` × `skippable` is what enforces it | This is the whole safety story now. A work item cannot walk past the *act of choosing*, so every omission has a named, authorized human behind it, decided before any work started. "Everything is selectable" never becomes "the harness decided". |
| **D3 — `required: true` is traded, not quietly dropped** | `security-review` and `human-approval` lose the marker (a node cannot be both required and skippable), and the graph says at each node what was traded and why | Decision-063 put those markers there after `security-review` shipped for months silently skipping. What it actually fixed still holds: the node can no longer skip *itself* by resolving no artifact. It either runs and gates the log, or a person declared it away on the record. Silent and declared are different failures. |
| **D4 — a kept gate keeps a subject** | `validate-artifacts` gains `onlyWhenSkipped:`. `verification` gates `testing-plan.md` as before, and — when and only when that plan is a *planned absence* — gates the shared `execution-log.md` for a non-empty `Verification results` section instead. `templates/execution-log.md` offers that section | Without it, a work item that keeps `verification` and skips `test-planning` walks a gate with nothing to assert against: issue-177's planned-absence tolerance would report `skipped`, and a node would pass having run nothing — the issue-124/167 shape, for a third time. Skipping the plan removes the document, never the verifying. |
| **D5 — the parameter can only narrow** | `onlyWhenSkipped` consults nothing but `HookContext.skipped_artifacts`, which the runtime derives from declarations already filtered through the compiled `skippable` vocabulary, and it disables itself the moment the artifact exists | A conditional gate is a gate that can be switched off, so it is built so that the only reachable failure is an entry that never fires — more process, never less. |
| **D6 — the checklist says what it now means** | With no protected phase to list, the `phase-selection` comment says so: every phase is selectable, including the reviews, the security review and the approval gate, and each untick is an omission recorded against the declarer's name | The old comment's "these phases always run" block was where the honesty came from. Replacing it with an empty section would quietly drop the most important sentence on the page. |

## What this deliberately does not do

- **It does not give the harness a channel.** Unchanged and re-stated in `SKILL.md`: a
  session never answers the selection gate and never runs `the-loop graph skip`. The
  agent's own comments carry the self-authored marker and are dropped before
  authorization is considered, and it is not in `authorizedUsers`.
- **It does not touch the inner `pdlc-pr-loop`.** No `phase-selection`, no skippable node,
  `security-review` still `required: true` there. A PR's path is the work item's decision,
  taken once at the outer level.
- **It does not let a declaration reach backwards.** Only nodes still ahead of the pointer
  (decision-067 D4).
- **It does not weaken a gate over work that exists.** A present artifact is gated exactly
  as before, declarations or not.
- **It does not remove `force`.** The after-the-fact hatch stays what it was, for the item
  that did *not* declare the gate away up front.

## Consequences

- A documentation fix is one reply away from `implementation → verification →
  human-approval → complete`, and one token (`spec-chain`) does most of the unticking.
- **An authorized human can now declare a work item that skips its security review and its
  human approval and walks to `complete`.** Nothing in the graph prevents it. That is the
  point of the decision and the cost of it, and it should be read alongside
  `security.review.humanSignOffMinTier` — a tier that requires a named sign-off is a
  policy the *person* now upholds, not the graph.
- **The guarantee changed shape.** It was *"these phases always ran"*. It is now *"every
  phase that did not run has a name on it"* — provenance in `graph-state.json`, the frozen
  graph in the portable record, a confirmation comment on the ticket, `graph.node_skipped`
  events, and `the-loop check` reporting *skipped by declaration* forever after. Reviewing
  a lean PR now includes reviewing the decision to make it lean, which is exactly the
  review this mechanism asks for.
- **The residual is larger than it was.** decision-067 was honest that in-repo enforcement
  is *audit and floor*, not cryptography. The floor is gone, so it is *audit alone*: a
  forged declaration in `graph-state.json` is detectable (its claimed channel has no
  corroborating off-repo trail, and the frozen graph is the contemporaneous record to
  compare against) but no longer bounded by phases that run regardless. Anyone tightening
  this back up should re-mark nodes in the shipped graph — the vocabulary is package data
  precisely so that is a distribution change, not a repository's option.
- **`graph force` warns less.** Its "this force bypasses a guarantee the process treats as
  mandatory" warning fires on `required` nodes, so in the outer loop it now fires only for
  `phase-selection`. Forcing past `security-review` or `human-approval` is still refused
  without a `--reason`, still recorded with the actor, and still announced on the ticket —
  but it no longer carries that extra sentence. Anyone who wants the warning back wants
  the marker back, which is the same decision as narrowing the vocabulary.
- One new hook parameter (`onlyWhenSkipped`) and one new execution-log section. Both are
  additive: a graph that does not use them behaves exactly as before.
