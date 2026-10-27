---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#500"
---

# Security review: record-feedback appends duplicate sibling headings when a gate is approved twice on one day

> The `security-review` node's proof (`reference/security.md`). Risk tier **2**: one
> private helper in a graph hook. The change touches no sensitive path (`**/*schema*`,
> `.the-loop/**`, `.github/workflows/**`, `**/auth/**`, secrets or credentials) and no
> authorization or classification logic. No human security sign-off is required; the PR
> still waits for the `human-approval` gate.

## Security review (gate)

- **Mechanism:** the-loop's checklist below, verified against
  `git diff origin/main...HEAD -- cli`. Claude Code's built-in `security-review` was also
  run as a sub-agent briefed with the same boundary.
- **Outcome:** no findings from either ([PR comment](https://github.com/MadaraUchiha-314/the-loop/pull/526#issuecomment-6431653008)).
- **Checked and clean:**
  - **Heading text.** The heading is built from `date.today()`, the classifier's
    outcome and an integer the hook computes. The outcome comes from the closed set
    `OUTCOMES`, or the literal `reviewed`. No comment body or author reaches it.
  - **Bodies that look like headings.** A body recorded earlier may contain a
    `### <date> — approved` line, because bodies are verbatim (decision-089). That line
    counts as taken, so the next suffix moves up by one. It cannot make a heading repeat,
    rewrite an earlier record, or change who approved.
  - **Termination.** `taken` is a finite set built from the artifact's lines. The
    `while` loop runs at most `len(taken) + 1` times, so it is bounded by a file the
    hook already reads in full.
  - **Append-only.** The helper only reads. The write is unchanged: the hook appends at
    the end of the file.
  - **Authorization.** `classify-feedback` and `_authorized_comments` are untouched.

## Checklist (`reference/security.md`)

| # | Item | Result |
|---|------|--------|
| 1 | Every trust boundary in design §Security design enforced | pass — no untrusted input reaches the heading; authorization is untouched |
| 2 | Untrusted inputs constrained at ingress | pass — no new ingress; bodies are still recorded verbatim, only in the block body |
| 3 | Untrusted content cannot steer privileged behaviour | pass — a heading-shaped body can only raise the suffix number |
| 4 | No secrets in code/config/logs/fixtures | pass — none added |
| 5 | AuthZ fails closed | n/a — no authorization logic changed |
| 6 | Least privilege | pass — the hook still reads and writes only its configured `into:` artifact |
| 7 | Every abuse case has a passing negative test | n/a — the requirements name no abuse case (no new attack surface); the regression scenario proves headings stay distinct |
| 8 | New dependencies justified | n/a — none |

## Built-in review

Claude Code's `security-review`, as a sub-agent, found **no findings at confidence ≥ 8**. Its
own trace matches the checklist: commenters cannot set the heading text; the loop is
bounded by the artifact's lines; a reviewer's heading-shaped body is cosmetic and exposes
nothing the verbatim body did not already allow; nothing earlier is rewritten; the
authorization, classification and locking code is untouched; and the target path still
comes from graph config.
