---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#475"
---

# Critic review: Jira as a first-class work-item source and update channel (issue-475)

> **One critic round, the operator's cap (`criticReviewCount: 1`): `codex/gpt-6.1-sol`. It
> raised three new findings, and all three are fixed.** The most important was C1: the
> self-review's checklist-forgery fix could still be bypassed through mirrored content. The
> round is posted on [#480](https://github.com/MadaraUchiha-314/the-loop/pull/480#issuecomment-6042201285)
> with each finding's disposition. The prompt listed every self-review finding so the
> critic would add to them rather than repeat them.
>
> The round ran on the third attempt. The first two did not review the code, and are not
> counted:
>
> 1. **Ran in the wrong directory.** `the-loop critic run`, routed through the running
>    service, ran codex in the *daemon's* working directory, a checkout of `main` without
>    this work. Codex reported that it could not find the branch (33 s).
> 2. **Timed out.** With `--root`/`--cwd` set to the worktree, the call timed out, because
>    the CLI's HTTP timeout to the service is 120 s while the critic's own timeout is 900 s.
>
> The counted round ran in-process (`THE_LOOP_SERVICE_LOCAL=1`). Both failures predate this
> work, so they are proposed as follow-ups.

## Review cycles

| Round | Critic | Outcome | Duration / usage | Findings → disposition |
|-------|--------|---------|------------------|------------------------|
| — | `codex/gpt-6.1-sol` (via service) | **unavailable**: ran in the daemon's working directory, reviewed nothing | 33.0 s | not counted |
| — | `codex/gpt-6.1-sol` (via service, absolute paths) | **unavailable**: the CLI→service HTTP request timed out at 120 s | — | not counted |
| 1 | `codex/gpt-6.1-sol` (in-process) | 3 new | 284.6 s; 128.8k input / 6.0k output tokens | **C1 (high, security)** service-account authorship promoted gate markers inside quoted, mirrored content (a Slack context snapshot became a checklist) → `9d18b86`: the Jira ledger and room channel break the-loop markers in mirrored text before posting, and a marker is read only as a standalone top-level paragraph at the start of the body. **C2 (medium)** comment reads fetched one page → `ddb13f1`: all pages are read (capped at 5,000, newest kept), a failed page raises so the cursor is kept, and the doorbell fetches its comment by id. **C3 (medium)** PR-vs-work-item repository comparisons used the Jira ref, not its mapped origin, so a same-repository PR spawned a separate session and the head-branch guard was skipped → `1a505a9`, which also fixes the claim prompt's `pr_repo`. |

After the fixes, the full gate passed: ruff, ruff-format, pyright, pytest, markdownlint and
the schema. The fix agent made temporary fixup commits with `--no-verify` while folding
format and type fixes into their commits. No git hook is installed in this worktree, so
nothing was skipped, and the full gate ran on the final commits.

## Proposed follow-ups (outside this work item)

- `the-loop critic run` through the service cannot finish a real round: the client's HTTP
  timeout (120 s) is shorter than the critic's (900 s).
- Commands routed through the service resolve relative paths in the daemon's working
  directory, which affected both `critic run` and `the-loop scenarios`.
