---
type: evidence
workItem: "issue-543"
---

<!-- Written per the `the-loop:writing` skill. -->

# Critic review: PR-scoped specs for multi-PR work items

## The short version

Codex ran one counted round (`criticReviewCount: 1`) and raised eight findings. All eight
are fixed, test first. Three were authorization holes that failed open. Two of them sit
where self-review's F1 had already been fixed incompletely, so the briefing asks the owner
to confirm the tightened rules. One earlier attempt was **unavailable**, because the critic
ran in the wrong checkout, and does not count.

## Review cycles

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| — | codex/gpt-6.1-sol | **unavailable** | The critic ran in its configured `cwd`, another repository, and reviewed nothing ("this checkout is … devbox"). Re-run with `--cwd` set to this worktree. | — |
| 1 | codex/gpt-6.1-sol | new findings (8) | See the table below. All eight are fixed. 7199 tests pass, and ruff, pyright and pre-commit are clean. | this file |

### Round 1 findings

| # | Severity | Finding | Disposition |
|---|----------|---------|-------------|
| C1 | high | `commands/derive-pr-spec.md` said to push the PR spec before the verb checked the disclosure. Following it published private content before consent (abuse case 1). | **Fixed.** The order is now commit, record, then push. The command and `reference/workflow.md` say to push nothing to a more visible repository until the grant is recorded. |
| C2 | high | `--still-valid` accepted any authorized comment on the PR, even "Do not merge; the scope needs revision". | **Fixed.** The comment must carry the line `pr-spec still-valid` on its own. A negated, quoted or questioning mention is refused. **This repeats self-review F1's area, so it is raised for the owner.** |
| C3 | medium | A declaration written after the record but before the chain change was accepted, because time was compared only with the record. | **Fixed.** The comment must be newer than both the record and the chain's last commit. An uncommitted chain change is refused. **This repeats F1, so it is raised for the owner.** |
| C4 | high | The disclosure grant matched as a substring, so "Do not `allow-disclosure octo/api`" granted it. | **Fixed.** The grant counts only when `allow-disclosure <owner>/<repo>` stands on a line of its own (optional backticks and full stop). Quoted (`>`) and negated mentions are refused. |
| C5 | medium | Uncommitted files in the working tree were accepted, so the record passed while reviewers could see no PR spec (R4.3). | **Fixed.** The four files must be tracked and unmodified in the checkout. Pushing is the agent's next step and is not checked here, because the verb must run before the push (C1). |
| C6 | medium | A `spec-only` record survived code added to the PR later. | **Fixed.** The hook accepts a `spec-only` record only when it is newer than the PR's inner `implementation` run. A PR with no inner loop (`sessions: never`) still trusts the record. That limit is stated in the briefing. |
| C7 | medium | `sourceRevision` was only checked to be non-empty ("Fail closed" in requirements). | **Fixed.** Each file's `sourceRevision` must be a hex commit id that resolves in the origin repository. Shapes like option strings are refused. |
| C8 | medium | Generic credentials (`api_key: …`) escaped the secret scan (R6.5). | **Fixed.** Added a credential-assignment pattern (`token`, `secret`, `password`, `api_key`, `access_key`, `private_key`, `credential` followed by `:`/`=` and a value of 8 or more characters). Digests and SHAs are still ignored. |

**Tests added:**
- `test_abuse_still_valid_comment_before_the_chain_change_refused`
- `…_with_uncommitted_chain_change_refused`
- `…_comment_that_does_not_declare_refused` (3 cases)
- `test_abuse_negated_or_quoted_disclosure_grant_refused` (4 cases)
- `test_disclosure_grant_on_its_own_line_accepted` (3 cases)
- `test_abuse_uncommitted_pr_spec_refused`
- `test_abuse_edited_after_commit_pr_spec_refused`
- `test_abuse_unresolvable_source_revision_refused` (3 cases)
- `test_hook_spec_only_recorded_before_implementation_blocks`
- `…_after_implementation_passes`
- 3 new credential cases in `test_abuse_seeded_token_is_finding`

**Design note:** the approved `design.md` is unchanged. The table rows for authorizing a comment and for the verb's checks are now stricter in code than in the design. `decision-153.md`, the command and the CLI reference describe the code as built.
