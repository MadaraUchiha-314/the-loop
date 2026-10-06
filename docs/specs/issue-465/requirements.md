---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#465"
status: in-review            # draft | in-review | approved — tier 3: the PR approval is the human gate
approvedBy: []
collaborators: [engineer]
overrides: {}
riskTier: 3                  # a new verb that changes a pull request's state on GitHub; no sensitive path touched
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: mark a draft pull request ready for review

> Phase 1 of 4 (requirements → design → testing plan → tasks). Tier 3
> (`human-approves-pr`): one new lifecycle verb on every seam the issue-447 verbs
> already use. No credential, configuration key or schema changes.

## Introduction

[Issue #465](https://github.com/MadaraUchiha-314/the-loop/issues/465): "the-loop has no
verb to mark draft PRs to ready."

**What is broken.** `the-loop pr create --draft` opens a draft pull request, but nothing
in the-loop can take it out of draft. Since issue-447 a session reaches GitHub only
through the-loop's verbs, so an agent that opened a draft has two bad options when the
work is ready: run `gh pr ready` (which the skill forbids, and which needs a `gh` login
the session may not have) or leave the PR a draft. A draft PR does not request
CODEOWNERS reviews and cannot be merged, so the second option silently stalls the
`human-approval` gate.

**What this changes.** `the-loop pr ready <pr>` marks a draft pull request ready for
review. Like `pr merge` and `pr resolve-thread`, it runs through the control-plane
service when one answers (the daemon's token), otherwise in-process; it is served as a
REST route and an MCP tool; and it acts only for a pull request recorded against a work
item registered on the executing instance.

## Requirements

### Requirement 1 — a verb that marks a draft pull request ready

**User story:** As an agent working a work item, I want to mark the draft pull request I
opened as ready for review through the-loop, so I never need `gh` to finish the
`needs-review` phase.

#### Acceptance criteria (EARS)

1.1 WHEN `the-loop pr ready <pr>` is run for an open draft pull request THEN the system
SHALL mark it ready for review on GitHub, print that it did, and exit 0.

1.2 The `<pr>` argument SHALL accept the same grammar every `pr` verb accepts: a ref
(`github:[HOST/]OWNER/REPO#N`), the pull request's URL, or a bare number with
`--work-item`.

1.3 WHEN the pull request is already ready for review (not a draft) THEN the system SHALL
make no write, say the pull request is already ready, and exit 0.

1.4 WHEN the pull request is not open (closed or merged) THEN the system SHALL make no
write, say why, and exit 1.

1.5 WHEN GitHub refuses the request, or answers that the pull request is still a draft,
THEN the system SHALL exit 1 with GitHub's message and the status, never the token.

1.6 The result SHALL carry `pullRequest`, `ready` (whether the pull request is now ready
for review) and `changed` (whether this call took it out of draft), beside the usual
`exitCode` and `messages`.

### Requirement 2 — the same verb on every seam

**User story:** As an operator, I want `pr ready` to behave like the other issue-447
verbs, so the session holds no token where a daemon runs and an MCP-first harness can
use it too.

#### Acceptance criteria (EARS)

2.1 The CLI SHALL route `pr ready` through the control-plane service when one answers
`/health`, and otherwise run it in-process with a note on stderr, never auto-starting a
service (decision-140).

2.2 The service SHALL serve `POST /api/v1/pull-requests/ready` (`markPullRequestReady`),
and the authored OpenAPI contract SHALL describe it.

2.3 The service's MCP endpoint SHALL offer the operation as the tool
`mark_pull_request_ready`, on a worker and a manager alike.

2.4 A manager SHALL run the operation on the member that manages the work item, as it
does for `pr merge` and `pr resolve-thread`.

2.5 WHEN the operation takes a pull request out of draft THEN the system SHALL emit
`work_item.pr_ready` (pull_request) to the event log.

### Requirement 3 — the agent knows to use it

**User story:** As the operator, I want the skill to tell the agent when to run
`pr ready`, so a PR opened as a draft never reaches the human gate as one.

#### Acceptance criteria (EARS)

3.1 The skill's "Reaching GitHub" verb table and its list of GitHub verbs SHALL name
`the-loop pr ready <pr>`.

3.2 The skill SHALL say that a pull request opened with `--draft` is marked ready with
`the-loop pr ready` before human review is requested.

## Security considerations

- **Untrusted actors.** Whoever can run the CLI or reach the service. The verb changes
  a pull request's state, and taking it out of draft notifies its CODEOWNERS, so it is a
  lifecycle act, not a read.
- **Trust boundaries.** The token stays where it is today: the daemon's process when a
  service runs, the session's `integrations.github.api.tokenEnv` otherwise. The host a
  ref or URL names must be github.com or the operator's own GitHub host (issue-447 A3).
- **Abuse cases.**
  - *Readying a stranger's draft* on a repository the token can write to. Mitigation:
    the lifecycle guard (`_authority`, decision-140 D8): only a pull request recorded
    against a work item registered on the executing instance, or one an ad-hoc `the-loop
    do` work item names. Refused before any GitHub request.
  - *A forged node id.* The mutation is addressed by the pull request's node id, which
    the verb reads from GitHub for the resolved PR; no caller-supplied id reaches the
    mutation.
  - *A token sent to an arbitrary host.* Refused by the trusted-host check before a
    client is built.
- **Fail-closed.** Any refusal (guard, host, GitHub) makes no write and exits 1. An
  already-ready PR is a no-op.
- **No new secret, scope or permission.** Marking ready needs the same `pull_requests:
  write` the token already holds for `pr create` and `pr merge`.
