# Decision 083: an ad-hoc task is a fourth loop, not a stretched `contribute`

- **Status:** proposed
- **Date:** 2026-08-14
- **Deciders:** @MadaraUchiha-314 (issue #225); shape proposed by the harness, pending PR review
- **Work item:** [issue-225](https://github.com/MadaraUchiha-314/the-loop/issues/225)
- **Spec:** `docs/specs/issue-225/`
- **Refines:** [decision-070](decision-070.md) (joining existing work is a third loop — it
  is now four) and [decision-068](decision-068.md) / issue-179 (the selection-gate
  invariant, which this loop satisfies by having nothing to select).

## Context

Issue #225, verbatim: *"Sometimes a user needs to just trigger an ad-hoc task that doesn't
require an elaborate PDLC outer/inner loop … these tasks are mostly tactical and just
require the agent harness to do the task, ask any follow up (on the work item) and
continue until the user closes the work item and declares it as done. Does the
'contribute' feature fit for these use-cases? or do we need to define another command for
these ad-hoc tasks?"*

The question has a clean answer, and it is *no*, for a reason that is structural rather
than a matter of degree. `pdlc-contribution-loop` is **defined** by its two
`required: true` nodes:

- `goal-definition` refuses to begin until an authorized comment carries a `Goal:` line
  and a `Success criteria:` bullet list;
- `verification` blocks until every one of those frozen criteria is ticked and proved.

An ad-hoc task has content for neither. Its instruction *is* the work item, and its
definition of done is the requester saying so. Driving one through `contribute` forces a
choice between inventing success criteria for "fix this typo" so a gate will release, and
declaring every skippable phase away — which still leaves two gates firing before the
agent touches anything. Both put ceremony precisely where the issue says there must be
none.

The remaining loops fit no better. The outer loop's `phase-selection` is itself
unskippable and its `implementation` node gates a task DAG. The inner loop is a pull
request's, in service of a work item that walked one of the others.

## Decision

1. **A fourth shipped graph, `pdlc-adhoc-loop`** — same vocabulary, hooks, runtime and
   state files as the other three; a repository still cannot override it. Three walkable
   nodes, `work → review → complete`, plus the terminal `cleanup` and `escalated` every
   work-item-level loop declares. `review` routes **back** to `work` for as long as the
   requester keeps asking for more.
2. **It is defined by what it omits, declared in one file.** No `goal-definition`, no
   `phase-selection`, no `produces`, no `validate-artifacts`, no `skipSets`, no
   `skippable`/`required` node, no review chain. A reviewer checks that claim by reading
   the graph, not by tracing conditionals.
3. **The issue-177/179 invariant holds by construction.** That gate exists so every phase
   which does *not* run carries a named human's attribution. Here nothing is skipped,
   because the loop declares nothing to skip — and arming with the new `do` control
   keyword (default `the-loop do`) **is** that named, authorized, durably recorded
   declaration, resolved state-first exactly as `contribute` is (decision-070 §2).
4. **The conversation is an edge, not a prompt.** A new `classify-adhoc-reply` hook
   inverts `classify-feedback`'s default: a reply that declares completion is `done`,
   **any other** authorized reply is `more-work`, and silence keeps the gate open. Waiting
   until decisive is right for a review gate and wrong for a conversational one. The hook
   *calls* `feedback._authorized_comments` rather than re-implementing it, so
   self-authored comments are dropped before authorization is considered and an empty
   allowlist reads nothing. The **newest** authorized comment decides — scanning the whole
   thread would let "tell me when you're done" in the arming comment end the item before
   any work ran.
5. **"Until the user closes the work item" gets no new machinery.** A closed issue (or a
   merged/closed PR) already ends the session on the shared close path (issue-94); this
   loop inherits it.
6. **An ad-hoc item is not a guest.** Unlike a contribution, it is the requester's own
   work item in their own repository, so an unconfigured checkout is adopted exactly as
   the outer loop adopts it (issue-193, [decision-073](decision-073.md)). The harness
   config is what supplies the test and lint commands the ad-hoc session still runs —
   most of the value left once the gates are gone.
7. **The guardrail this loop removes is replaced by attribution, not by another gate.**
   No self-review, no critic review, no security-review gate. The mitigation is that the
   mode is selected only by an authorized user's explicit keyword, frozen in
   `graph-state.json`'s `loop` field, with the arming comment standing on the thread — so
   a reviewer of any resulting change can see that no review chain ran, and who decided
   that.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Use `contribute` as-is | Its two required gates *are* its definition; an ad-hoc task can satisfy neither honestly |
| Walk `pdlc-work-item-loop` with every phase declared away | `phase-selection` is itself unskippable, so the ceremony survives the skipping — and `implementation` gates a task DAG that does not exist |
| A `--adhoc` flag on `start` | Flags do not exist in the comment vocabulary; decision-070 already settled that the mode is a *word*, chosen and recorded per work item |
| Infer "this is tactical" from the item (size, labels, no spec dir) | The heuristic issue-177 removed from skips, reintroduced one level up. Joining *and* skipping the process are decisions, and decisions here get a named author |
| A `workflow.adhoc.enabled` toggle in the harness config | YAGNI, and the mode is per-work-item rather than per-repository (decision-069's argument). An operator who wants the word gone sets `routing.control.keywords.do: ""` |
| A `mode` parameter on `classify-feedback` instead of a new hook | Two opposite defaults behind one name is how a gate's behaviour stops being readable at the call site |
| A dedicated `adhoc` phase label | Every consuming repository's `workflow.phases` and every dashboard would change, for a label nobody queries separately. `implementation` → `complete` → `cleanup` already describe it |
| Keep `security-review` as a non-skippable node | It would be the only gate in a loop whose premise is that there are none, and it cannot run meaningfully without the artifacts the loop does not produce. The honest version is to omit it and make the omission legible |

## Consequences

The control vocabulary grows by one word (eight commands) and the cli-config schema by
one optional, defaulted property — a `sensitivePaths` match, additive, so an existing
config validates unchanged. `SHIPPED_LOOPS` gains a member and a new `OUTER_PATH_LOOPS`
appears beside it; `graph.model.resolve_outer_loop` becomes the single fail-closed
decision point that three copied "contribution or default" comparisons used to be
(`graphlink._outer_loop_name`, `core.graphs._recorded_loop`,
`bootstrap.build_runtime`) — narrower than what it replaces, since `build_runtime`
previously accepted any `SHIPPED_LOOPS` member and then special-cased the inner loop.

The CLI `sessions start` verb still arms only the outer loop; a CLI-side `do` verb is
deferred for the same reason decision-070 deferred `contribute`'s. `graph show` without a
work item still renders the shipped outer loop. Promotion of an ad-hoc item to the full
PDLC mid-walk is deliberately not modelled: if the task turns out to need the process,
the honest move is a new work item.
