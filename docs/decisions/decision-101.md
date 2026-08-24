# Decision 101: a review is a fifth loop, a guest, and bound to the pull request itself

- **Status:** proposed
- **Date:** 2026-08-24
- **Deciders:** @MadaraUchiha-314 (issue #279); shape proposed by the harness, pending PR review
- **Work item:** [issue-279](https://github.com/MadaraUchiha-314/the-loop/issues/279)
- **Spec:** `docs/specs/issue-279/`
- **Refines:** [decision-083](decision-083.md) (the ad-hoc loop and its conversational
  gate), [decision-070](decision-070.md) (the contribution loop and the guest posture),
  and [decision-068](decision-068.md) / issue-179 (every skipped phase carries a named
  human's declaration)

## Context

Issue #279 asks for first-class PR reviews: an authorized user comments
`the-loop review`, the-loop replies with a template the reviewer fills (their questions,
the angles they care about, the validations they want run), the review begins once the
template is answered, and the reviewer follows up as many times as they need. None of
the four shipped loops fits. The outer, ad-hoc and contribution loops all exist to
*change* a repository; the inner PR loop is the path of a pull request the-loop is
**delivering**. A review's product is judgement on the thread, its subject is the pull
request itself, and its definition of done is the reviewer's word.

## Decision

1. **A fifth shipped graph, `pdlc-review-loop`** — `review-brief → review → follow-up →
   complete` (+ `cleanup`/`escalated`) — armed by a ninth control keyword,
   `the-loop review`, exactly as `contribute` and `do` arm their loops. No `produces`,
   no `validate-artifacts`, no `phase-selection`: arming is the issue-177/179
   declaration, as decision-083 established for the ad-hoc loop.

2. **The brief gate is the loop's `required: true` invariant** — the structural mirror
   of `goal-definition`: no brief, no review. The fill-in template is **posted by the
   CLI hook and therefore lives in code** (`graph/hooks/review.py`), like the goal
   request and the phase-selection checklist — a copy under
   `skills/the-loop/templates/` would be a second source the daemon cannot read, so
   none is shipped. The parsed brief is frozen into `GraphState.decisions` with
   provenance, beside the frozen goal.

3. **The follow-up gate reuses `classify-adhoc-reply`** rather than minting a
   `classify-review-reply` twin. The semantics wanted are identical — the newest
   authorized, non-self-authored reply decides; a declaration of completion ends the
   item; anything else is another round; silence waits — and the hook's
   done-vocabulary (`lgtm`, `looks good`, `approved`) reads *more* naturally on a
   review. Duplicating it would create two copies of one behaviour that could drift
   (the exact failure `resolve_outer_loop` was built to end). The oddity of the name
   inside `pdlc-review-loop.yaml` is carried by a comment at the call site and pinned
   by a test.

4. **The review binds to the pull request itself.** The router orders a PR's linked
   work items first — right for delivery, where the ticket is the work item, wrong for
   a review, whose subject is the change. The control path special-cases `REVIEW`:
   `pr_work_item` (the router's own extraction) becomes the target for the record, the
   session lookup and the spawn. Deliberately **not** generalized to other keywords:
   issue-269 settled linked-first for them.

5. **A review is a guest.** The contribution loop's no-adopt carve-out is generalized
   to a named `GUEST_LOOPS` set instead of duplicated per call site; the spec-tree
   git-exclusion follows from staying unadopted (the existing `repoInitialized` seam).
   The session's contract, stated in the graph context and `/the-loop:review-pr`:
   change no code, commit nothing, push nothing, open no pull request. Findings worth
   fixing become new work items.

6. **No formal GitHub review verdict.** the-loop posts self-marked comments; approve /
   request-changes stays a human act. Reusing `stage: critic-review` for the review
   node (frontier routing, high thinking effort) instead of adding a `review` stage
   keeps the config schema untouched.

7. **A work item is reviewable too — one conversation across all its pull requests**
   (the owner's ruling on PR #280, worked back into R8). Armed on a work item, the
   same loop runs with one difference: the template also asks which pull requests the
   review spans, pre-filled with what the-loop detects — its own `pr-loops/` state
   first ("piggyback on that"), then the provider's linked pull requests (two new
   integration ops, `get-thread` and `linked-pulls`). Stated entries normalize to
   composed refs and junk is dropped; the frozen brief carries the scope. No new
   session machinery: binding to the work item already gives one session, and the
   existing linkage forwards the linked PRs' events to it.
