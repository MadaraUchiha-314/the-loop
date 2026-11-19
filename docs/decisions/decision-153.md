<!-- Written per the `the-loop:writing` skill. -->

# Decision 153: Each pull request of a multi-PR work item carries a derived, scoped PR spec

- **Status:** proposed (the owner decides at the PR)
- **Date:** 2026-11-19
- **Deciders:** MadaraUchiha-314 (the three resolved questions on PR #546, the approvals),
  the-loop (the mechanism)
- **Work item:** [issue-543](https://github.com/MadaraUchiha-314/the-loop/issues/543)
- **Spec:** [`docs/specs/issue-543/`](../specs/issue-543/)
- **Refines:** [decision-065](decision-065.md) D2 and D4. There is still one spec chain
  per work item, in the origin repository. A pull request now also carries a scoped,
  derived copy of the part it delivers.

## The short version

A work item delivered by several pull requests kept its one spec chain in the origin
repository. A maintainer reviewing one of those PRs, often in another repository, had to
leave the PR to learn what it was for. Now each delivery PR carries four short files in
its own branch, derived from the approved chain and citing it item by item. A verb
checks and records them once. An offline gate re-checks the record against the current
chain before implementation, before review, and before the work item leaves
implementation.

## Context

decision-065 kept artifacts at the work item and let a PR inherit them. That works when
the chain is in the PR's diff or on its base branch. It does not work for a PR in a
contributing repository, whose reviewer may have no access to the origin, and it is weak
for the second PR in one repository too. Inner-loop hooks run against the origin
checkout, the PR's checkout is somewhere else, and validation hooks must stay offline.

## Decision

1. **When.** A PR spec is required when the work item has two or more delivering PRs,
   or any PR or declared repository outside the origin. A single-PR work item needs
   none, and neither does the outer surface's spec-only PR. The origin repository's own
   delivery PR carries one too.
2. **What.** Four files named like the chain, at `docs/specs/<id>/pr-<n>/` in the origin
   repository or `docs/specs/<owner>__<repo>__<id>/pr-<n>/` elsewhere. Each opens with a
   Context section. Each carries `chainDigest` and `sourceRevision`, and no `status`:
   it is never approved on its own. It merges with the PR.
3. **Derived, not forked.** Every requirement entry, task line and in-scope test row
   cites the work-item item it comes from (`[wi:R2.3]` and four other forms). A
   citation that does not resolve is refused.
4. **Checked once, gated offline.** `the-loop graph pr-spec` reads the PR checkout and
   GitHub, then writes `pr-spec.json` beside the PR's inner-loop state. The
   `pr-spec-current` hook re-derives applicability and recomputes the chain digest on
   every evaluation, at three places: leaving the inner `pr-spec` node, leaving
   `reviewer-briefing`, and leaving the outer `implementation`.
5. **Stale means blocked.** A changed chain blocks the PR at `reviewer-briefing` until
   the PR spec is re-derived, or an authorized person declares on the PR that it still
   holds (`--still-valid`). Front-matter edits by the gates do not count as changes.
6. **No wider audience without consent.** When the PR's repository is more visible than
   the origin, or either visibility is unknown, recording needs a comment on the work
   item by an authorized user that says `allow-disclosure <owner>/<repo>`.
7. **Feedback routing.** Feedback within the PR's scope changes the PR spec on that PR.
   Feedback that would change the work item is raised on the work item. Nothing in the
   inner loop writes the chain.

## Consequences

- The inner loop gains a start node, `pr-spec`, which is its only skippable node. Inner
  states already past it load unchanged.
- One more verb on the control-plane API, `POST /api/v1/graph/pr-spec`, and two event
  types. No CLI-config key and no schema change.
- A multi-PR work item costs one derivation per PR, and another each time the chain
  changes under a PR not yet reviewed.

## Alternatives considered

- **A gate that reads the PR checkout.** The daemon and CI have no path to it.
- **A gate that fetches the PR spec from GitHub.** Breaks the offline rule for
  validation hooks.
- **A new control keyword for the disclosure grant.** A CLI-config schema change for a
  rare act, which would raise the item's risk tier.
- **Reusing the chain's templates.** They carry approval front matter and review
  sections, which would invite the gates to treat a PR spec as a chain.
