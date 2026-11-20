---
type: evidence
workItem: "issue-543"
---

<!-- Written per the `the-loop:writing` skill. -->

# Security review: PR-scoped specs for multi-PR work items

## The short version

Claude Code's built-in `/security-review` found no vulnerability at or above its
confidence bar of 8 out of 10. It noted three things below that bar. One was cheap and
matches R1, so it is fixed test first. The other two are accepted, for the reasons given.
Risk tier 3, so no human security sign-off is required.

## Security review (gate)

- **Mechanism:** the security-review skill (Claude Code `/security-review`), run over
  the production code in the diff against `origin/main`. It ran after the critic's eight
  fixes (`critic-review.md`), so it reviewed the hardened code.
- **Outcome:** pass. No finding cleared the reporting bar, and one hardening was applied.
- **Verified with no finding:**
  - **Every git subprocess** gets a list of arguments: no shell, and a timeout.
    `sourceRevision` must fully match `[0-9a-fA-F]{7,64}` before `git cat-file`, and the
    base ref is always prefixed `origin/`.
  - **Paths.** The PR-spec key and directory are validated against the ref grammar and
    must resolve inside the checkout, which catches a symlinked parent. A symlinked file
    is refused.
  - **Comment authorization** needs:
    - a full-URL match against the expected thread;
    - the comment, re-read through the API;
    - no self marker;
    - an author on the allowlist (an empty one authorizes nobody);
    - the phrase on a line of its own;
    - for `--still-valid`, a comment newer than both the record and the chain's last
      commit.
  - **Disclosure.** An unknown visibility counts as narrowing, which fails closed, and
    the grant must name the exact target repository.
  - **Records.** The secret scan never repeats a match. The record and the event carry
    no secret. `pr-spec.json` is parsed with `json.loads` and every field is validated.
    There is no unsafe YAML, `eval` or `pickle`.
- **Findings below the bar:**

  | # | Observation | Disposition |
  |---|-------------|-------------|
  | S1 | `applicability` ignored the PR's own repository. A PR in another repository that was missing from `work-item-state.json` was recorded as `single-pr`. | **Fixed.** The verb counts the PR's own repository as declared. Test: `test_abuse_cross_repo_pr_missing_from_state_is_still_multi_pr` (failed first). |
  | S2 | The agent can write `pr-spec.json`, `work-item-state.json` and commit dates itself, so a compromised agent could forge a record. | **Won't fix, as designed.** `design.md` § Security design ("Forged record") names this. The hook is a process gate, not a boundary against the agent, which could push to the target repository directly anyway. The human approval at `pr-approval` is the boundary. |
  | S3 | An agent posting under the operator's own login, without the loop-prevention marker, could write a grant line. | **Won't fix, not introduced here.** Every human gate in the-loop has the same exposure, and the marker plus the allowlist are the existing control. |

- **Human sign-off:** n/a (risk tier 3, below 4).
