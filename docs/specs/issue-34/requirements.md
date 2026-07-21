---
type: requirements
phase: requirements-definition
workItem: issue-34
status: draft
approvedBy: []
collaborators: [product-manager, architect, engineer]
overrides: {}
---

# Requirements: poll ticketing/PR systems for labelled work and spawn/route sessions

> Phase 1 of 3 (requirements → design → tasks). Ticket:
> [issue #34](https://github.com/MadaraUchiha-314/the-loop/issues/34). This phase should
> be reviewed and approved before moving to design.

## Introduction

The webhook receiver (issue-15) is *push*: GitHub calls us. Sometimes it can't — the
host running the harness sits behind a firewall/NAT, on a laptop, or on infrastructure
GitHub cannot reach — so the events never arrive. This work item adds a *pull* ingress:
a `the-loop poll` command that periodically asks each configured **provider** which of
its work items carry the-loop's auto-execute label, then feeds them through the **same**
routing/dispatch/session machinery the webhook receiver already uses.

The ingress is **provider-agnostic** (PR #45 review): the poller core and CLI carry no
GitHub-specific knobs; a `polling.sources` config entry selects a provider by name, and
the provider owns all provider-specific discovery and event construction. GitHub ships as
one provider; the system interfaces with it *only* through config. The poller therefore
owns only the agnostic ingress: discovery orchestration, an interval loop, and durable
cross-poll dedup. Spawning, one-session-per-work-item, the tmux runner, harness adapters
and prompt rendering are reused unchanged (decision-016/021).

## Requirements

### Requirement 1 — poll labelled work items and act on them

**User story:** As a developer whose harness host a webhook cannot reach, I want a
command that polls my ticketing/PR system for work the-loop should act on, so that
automation runs without an inbound webhook.

#### Acceptance criteria (EARS)

1. WHEN `the-loop poll start` runs THEN the system SHALL, every `intervalSeconds`, ask
   each configured provider for the work items in its scope that carry the configured
   label.
2. WHEN a labelled item has no active registered session THEN the system SHALL spawn one
   for it via the existing `spawnOnUnmatched` policy and session registry.
3. WHEN a labelled item already has an active session THEN the system SHALL NOT spawn a
   second one — the session registry (one active session per work item) is the source
   of truth.
4. WHEN `--once` is given THEN the system SHALL run exactly one poll cycle and exit
   (for cron/systemd timers); otherwise it SHALL loop until signalled to stop.
5. IF a provider's required tool (e.g. GitHub's `gh`) is not available THEN `start` SHALL
   fail with an actionable error naming the missing dependency and SHALL NOT start the
   loop.

### Requirement 2 — provider-agnostic, config-driven monitoring scope

**User story:** As a maintainer, I want the poller and its config to be agnostic of any
specific system, with each provider (e.g. GitHub) reached only through configuration, so
that no provider is hard-wired into the core.

#### Acceptance criteria (EARS)

1. WHEN the poller decides what to monitor THEN it SHALL read `polling.sources` from
   `.the-loop/config.yaml`; each entry SHALL name a `provider`, and the remaining keys
   SHALL be that provider's own settings (opaque to the core).
2. WHEN no `polling.sources` entries exist THEN `start` SHALL fail with a message telling
   the user to configure a source (nothing is polled by default).
3. WHEN the core, CLI flags, session registry, dedup state or run loop are examined THEN
   they SHALL contain no provider-specific vocabulary; provider specifics SHALL live only
   in the provider implementation selected by config.
4. WHEN a source names an unknown or missing `provider` THEN `start` SHALL fail with a
   message listing the known providers.
5. WHEN a source omits its `label` THEN the system SHALL fall back to
   `webhooks.ghWebhook.routing.autoExecuteLabel`, so one label configures both ingresses.
6. WHEN a GitHub source omits `repos` THEN the system SHALL fall back to
   `ticketing.github` (`owner`/`repo`); IF none can be determined THEN listing that
   source SHALL fail with an actionable message.

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
2. WHEN `the-loop poll stop` runs THEN it SHALL signal the recorded PID to shut down
   gracefully (draining in-flight dispatches), and report a stale/missing pidfile
   clearly.
3. WHEN the poller receives SIGINT/SIGTERM THEN it SHALL stop the loop, drain the
   dispatcher and exit 0.

### Requirement 6 — hot-reload the polling config without a restart

**User story:** As an operator, I want to add/remove sources or change the interval by
editing `.the-loop/config.yaml` while the poller runs, so that I don't have to restart it
to change what is monitored.

#### Acceptance criteria (EARS)

1. WHILE the poller is running, WHEN `.the-loop/config.yaml` changes THEN the system SHALL
   pick up the new `polling.sources` and `polling.intervalSeconds` on the next poll cycle,
   without a restart (reload granularity is one cycle).
2. WHEN the config file is unchanged between cycles THEN the system SHALL NOT rebuild the
   providers (change is detected by content, not on every cycle).
3. IF a reloaded config is invalid (parse error, unknown/missing `provider`) THEN the
   system SHALL log the error, keep running with the previously loaded config, and retry
   on the next change — a bad edit SHALL NOT take the poller down.
4. WHEN there is no config file THEN the system SHALL run with its start-time
   configuration and simply have nothing to hot-reload.

## Out of scope (this iteration)

- **Non-GitHub provider implementations (e.g. Jira).** The provider seam, config surface
  and `WorkItemRef` are provider-agnostic and reserve the `jira:` provider, but only the
  GitHub provider is implemented here ("for now let's support polling github using
  `gh`"). A new provider drops into the registry with no core changes.
- **Hot-reloading the shared dispatch config** (`webhooks.ghWebhook.routing`: harness,
  runner, spawn policy). The dispatcher owns worker threads and the in-memory dedup, so
  it is established once at start; changing those still needs a restart. Only the
  `polling` block hot-reloads.
- **PR review (inline code) comment threads.** Conversation comments on issues and PRs
  are covered; review-thread polling is a follow-up.
