---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#465"
---

# Security review: `the-loop pr ready` (issue-465)

- **Mechanism:** the-loop checklist (`reference/security.md`), checked against the diff.
- **Outcome:** pass.
- **Findings:** none.
  - *New write:* one GraphQL `markPullRequestReadyForReview` per call that takes a PR
    out of draft, through the existing `GitHubClient.graphql`. Readying notifies the
    PR's code owners, so it is gated as a lifecycle act.
  - *Who can call it:* the lifecycle guard (`_authority`, decision-140 D8) runs before
    any request. Only a PR recorded against a work item registered on the executing
    instance, or one an ad-hoc `the-loop do` work item names. A test asserts that an
    unowned PR causes no GitHub call.
  - *Trust boundary:* the mutation's id is the `node_id` GitHub returned for the
    resolved PR, never a request field, and `_NODE_ID_RE` checks it before the request.
    The host passes `_trusted`, the allow-list every issue-447 verb uses; an untrusted
    host is refused before a client is built (tested).
  - *Token:* unchanged. The daemon's when a service runs, `GH_TOKEN` in-process
    otherwise. GitHub's message is relayed on refusal; the token never is.
  - *Fail-closed:* a closed or merged PR, a refusal, or a still-draft answer makes no
    further write and exits 1. An already-ready PR is a no-op.
  - *Scope:* no new token scope. GitHub requires the pull-request write access that
    `pr create` and `pr merge` already need.
- **Risk tier:** 3 (a CLI verb that writes to GitHub; no sensitive path touched). That
  is below the tier-4 threshold for a named human security sign-off. The PR approval is
  the human gate.
