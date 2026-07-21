---
type: requirements
phase: requirements-definition
workItem: issue-34
status: draft
approvedBy: []
collaborators: [product-manager, architect, engineer]
overrides: {}
---

# Requirements: poll GitHub for labelled work and spawn/route harness sessions

> Phase 1 of 3 (requirements → design → tasks). Ticket:
> [issue #34](https://github.com/MadaraUchiha-314/the-loop/issues/34). This phase should
> be reviewed and approved before moving to design.

## Introduction

The webhook receiver (issue-15) is *push*: GitHub calls us. Sometimes it can't — the
host running the harness sits behind a firewall/NAT, on a laptop, or on infrastructure
GitHub cannot reach — so the events never arrive. This work item adds a *pull* ingress:
a `the-loop gh-poll` command that periodically asks GitHub (via the user's existing
`gh` CLI) which issues/PRs carry the-loop's auto-execute label, then feeds them through
the **same** routing/dispatch/session machinery the webhook receiver already uses.

The poller therefore owns only the ingress: discovery, an interval loop, and durable
cross-poll dedup. Spawning, one-session-per-work-item, the tmux runner, harness
adapters and prompt rendering are reused unchanged (decision-016/021).

## Requirements

### Requirement 1 — poll labelled GitHub issues/PRs and act on them

**User story:** As a developer whose harness host a webhook cannot reach, I want a
command that polls GitHub for work the-loop should act on, so that automation runs
without an inbound webhook.

#### Acceptance criteria (EARS)

1. WHEN `the-loop gh-poll start` runs THEN the system SHALL, every `intervalSeconds`,
   list the open issues and/or PRs in each configured repository that carry the
   configured label, using the `gh` CLI (inheriting the user's `gh` auth).
2. WHEN a labelled item has no active registered session THEN the system SHALL spawn one
   for it via the existing `spawnOnUnmatched` policy and session registry.
3. WHEN a labelled item already has an active session THEN the system SHALL NOT spawn a
   second one — the session registry (one active session per work item) is the source
   of truth.
4. WHEN `--once` is given THEN the system SHALL run exactly one poll cycle and exit
   (for cron/systemd timers); otherwise it SHALL loop until signalled to stop.
5. IF the `gh` binary is not available THEN `start` SHALL fail with an actionable error
   naming the missing dependency and SHALL NOT start the loop.

### Requirement 2 — configurable, label-gated monitoring scope

**User story:** As a maintainer, I want to configure which repositories and entity kinds
are polled and which label gates them, so that the poller only acts on opted-in work.

#### Acceptance criteria (EARS)

1. WHEN `polling.ghPoll` is present in `.the-loop/config.yaml` THEN its `repos`,
   `monitor.issues`, `monitor.pullRequests`, `intervalSeconds`, `label`, `stateFile`,
   `ghBinary` and `pidfile` SHALL supply defaults; CLI flags SHALL override them.
2. WHEN no `label` is configured for polling THEN the system SHALL fall back to
   `webhooks.ghWebhook.routing.autoExecuteLabel`, so one label configures both ingresses.
3. WHEN no repositories are configured or passed THEN the system SHALL fall back to
   `ticketing.github` (`owner`/`repo`); IF none can be determined THEN `start` SHALL
   fail with a message telling the user how to supply one.
4. WHEN an item does not carry the configured label THEN the system SHALL NOT act on it
   (label presence is read from the `gh` listing, which is already label-filtered).

### Requirement 3 — reuse routing/dispatch and never duplicate sessions

**User story:** As the-loop, I want polled events to behave exactly like webhook events,
so that there is one dispatch code path and one session per work item regardless of
ingress.

#### Acceptance criteria (EARS)

1. WHEN the poller acts on an item THEN it SHALL do so by handing a `RoutedEvent` to the
   existing dispatcher, reusing the session registry, harness adapters, runner
   (`process` or `tmux`) and prompt templates from `webhooks.ghWebhook.routing`.
2. WHEN `routing.runner` is `tmux` THEN a polled spawn SHALL create a tmux-hosted
   interactive session, identical to a webhook-spawned one (attachable via
   `the-loop sessions attach`).
3. WHEN a comment event maps to a PR whose head branch / closing keywords link an issue
   THEN it SHALL reach a session registered against either the PR or the linked issue
   (same work-item extraction as webhooks).
4. WHEN a payload excerpt is rendered into a prompt THEN it SHALL be marked as untrusted
   data (reusing the existing templates), never as instructions.

### Requirement 4 — durable, at-most-once comment forwarding

**User story:** As a work-item owner, I want a new comment on a labelled item to reach
its session exactly once, so that polling does not replay old discussion or double-fire.

#### Acceptance criteria (EARS)

1. WHEN the poller first sees an item THEN it SHALL baseline the item's current comments
   (record them as seen) WITHOUT forwarding them — matching webhook semantics where only
   activity after subscription is delivered.
2. WHEN a comment newer than the recorded baseline appears THEN the system SHALL forward
   exactly one event for it to the matched session and record it as seen.
3. WHEN the same comment is observed on a later cycle THEN the system SHALL NOT forward
   it again (dedup persists across cycles AND across process restarts via `stateFile`).
4. WHEN the poll-state file is missing or corrupt THEN the system SHALL treat every item
   as first-seen (safe re-baseline) rather than crash.

### Requirement 5 — lifecycle: start/stop like the receiver

**User story:** As an operator, I want to start and stop the poller the same way I manage
the webhook receiver, so that operating both is uniform.

#### Acceptance criteria (EARS)

1. WHEN `start` runs without `--once` THEN it SHALL write its PID to `pidfile` and remove
   it on exit.
2. WHEN `the-loop gh-poll stop` runs THEN it SHALL signal the recorded PID to shut down
   gracefully (draining in-flight dispatches), and report a stale/missing pidfile
   clearly.
3. WHEN the poller receives SIGINT/SIGTERM THEN it SHALL stop the loop, drain the
   dispatcher and exit 0.

## Out of scope (this iteration)

- **Jira / non-GitHub ticketing polling.** The config surface and `WorkItemRef` reserve
  the `jira:` provider, but only GitHub polling is implemented here ("for now let's
  support polling github using `gh`").
- **PR review (inline code) comment threads.** Conversation comments on issues and PRs
  are covered; review-thread polling is a follow-up.
