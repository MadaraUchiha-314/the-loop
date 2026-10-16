---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#494"
---

# Security review: gate the brainstorm on its author's approval

> The `security-review` node's proof. See `reference/security.md`. Reviewed against
> `origin/main...HEAD` (merge base `584958c`), after the self-review and critic fixes
> (head `cce3f96`).

## Security review (gate)

- **Mechanism:** the built-in `security-review` skill, run over the branch diff by a
  fresh-context reviewer, together with the-loop checklist below. Each item was verified
  against the diff.
- **Outcome:** **pass.** The built-in review found no high-confidence vulnerabilities.
  It checked unauthorized commenters, repository `x-` hooks declaring `not-entered`,
  skip declarations, state-file and spec-file edits, path traversal through
  `whenPresent` and `gate`, injection, deserialization and data exposure. The
  checklist passes. The one security-relevant defect found during review, deleting
  `brainstorm.md` to get past the gate (self-review S2), was fixed in `40a63cc` before
  this round.
- **Effective risk tier: 3.** `bugfix.md` says tier 3. The diff
  (`git diff origin/main...HEAD --name-only`) touches no fixed sensitive path: no
  `*schema*`, `.the-loop/**`, `.github/workflows/**`, `auth`, `secret` or `credential`
  path. The autonomous review is enough, and no named sign-off is required.

### Checklist

| # | Item | Result | Evidence |
|---|------|--------|----------|
| 1 | Trust boundaries in `design.md` enforced | pass | The comment → classification boundary is the reused `classify-feedback`. It reads `authorizedUsers` only, drops self-authored comments and returns a closed outcome set. |
| 2 | Untrusted inputs validated at ingress | pass | The only untrusted input is comment text, and it reaches nothing new. `whenPresent`, `absentOutcome` and `gate` come from graph YAML (shipped, or the operator's own), which is trusted config. `whenPresent` goes through `resolve_produces`, the resolver every gate already uses. |
| 3 | Untrusted content cannot steer privileged behaviour | pass | Repository `x-` hooks cannot declare `not-entered`: `_disarm_routing` drops their outcomes. An unauthorized "approved" leaves the gate waiting (`test_a_written_brainstorm_waits_at_its_gate_across_comments`). |
| 4 | No secrets | pass | None added. The test fakes use no tokens. |
| 5 | AuthZ fails closed | pass | No reply, or an indecisive one, waits. Once the gate has been entered, a missing `brainstorm.md` **blocks** (`HookContext.visited`), and the gate has no `pass` edge (self-review S2, fixed `40a63cc`). |
| 6 | Least privilege | pass | No new permissions, scopes, file access or network calls. |
| 7 | Every abuse case has a passing negative test | pass | Unauthorized approval: `test_a_written_brainstorm_waits_at_its_gate_across_comments`. Deleting the artifact to get past the gate: `test_deleting_the_brainstorm_at_its_gate_does_not_open_it` and `test_deleting_the_brainstorm_after_changes_requested_does_not_skip_them`. Repository-hook routing: the existing `test_graph_extensions*.py`, which pass. |
| 8 | New dependencies justified | pass | None. |

### Residual risk

An agent session that can write the repository could still move the item past the gate
by editing `work-item-state.json`, or with `the-loop graph force`. Neither is new:
`graph force` is an audited override that requires a reason and posts on the ticket, and
`check --recompute` in CI re-derives the position from the artifacts. This change adds
no path around a human that did not already exist for every other approval gate.
