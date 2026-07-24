---
type: requirements
phase: requirements-definition
workItem: "issue-82"
status: approved
approvedBy: ["@MadaraUchiha-314"]
collaborators: [product-manager, architect, engineer]
overrides: {}
---

# Requirements: make the notification/escalation mechanism coherent

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/).
>
> **Provenance note (paper trail):** this spec was authored retroactively during PR #83
> review — the implementation initially bypassed the loop (the exact gap issue #73
> flagged). The requirements below transcribe the principles the work was actually
> driven by: the ticket body of issue #82 and the owner's principles comment on it,
> which the owner authored — hence `status: approved`.

## Introduction

the-loop's notification config was split-brained ([issue #82](https://github.com/MadaraUchiha-314/the-loop/issues/82)):
collaborators lived in `config.personas` **and/or** an unmanaged, schema-less
`collaborators.yaml`; channels were a flat global `messaging.channels` list not owned
by any collaborator; there was no per-user or per-channel enable/disable and no event
filtering. Decision-032's CLI-config split added the question of how the cross-repo
daemon — forbidden from reading any repo's plugin config — learns who to notify.

## Requirements

### Requirement 1 — collaborators.yaml is the single source for people + notification config

**User story:** As a repo steward, I want one file that defines who collaborates on the
project and how each of them is notified, so that people-config never drifts across
files.

#### Acceptance criteria (EARS)

1. WHEN a collaborator is defined THEN the system SHALL capture handle, kind
   (individual/group), roles, and their notification config in
   `.the-loop/collaborators.yaml` only (CODEOWNERS-like: the stewards of the repo).
2. IF notifications are configured THEN the system SHALL support a per-user
   `notifications.enabled` master switch AND a per-channel `enabled` switch.
3. WHEN a channel is declared THEN it SHALL carry a `type` (only `slack` supported for
   now), a `via` declaring how to interact with it using the-loop's existing
   primitives (`mcp` | `cli` | `api`, as in `externalTools.kind`), and
   channel-type-specific config — for slack: `channel-list: []`.
4. WHEN the harness needs to notify someone THEN channels SHALL be notification-only:
   the decision itself still lands as a ticket/PR comment (paper trail).
5. WHEN validating THEN `collaborators.yaml` SHALL have its own JSON schema and be
   managed by init/upgrade; the retired `config.personas`/`config.messaging` keys
   SHALL be removed from the harness config schema.

### Requirement 2 — harness config declares event filters over roles

**User story:** As a project owner, I want the per-repo config to declare which
harness-raised events notify which roles, so that who-gets-pinged is explicit and
tunable per project.

#### Acceptance criteria (EARS)

1. WHEN a harness-raised event occurs (decision pending, phase approval pending, PR
   review pending, security sign-off pending, conflict escalated, work item complete)
   THEN the system SHALL consult `notifications.events` in the per-repo config and
   notify the holders of the listed roles, resolved from `collaborators.yaml`.
2. IF an event is omitted from the filter THEN the system SHALL notify nobody for it.
3. WHEN referencing people THEN the per-repo config SHALL reference roles only — never
   individuals.

### Requirement 3 — CLI config declares its own recipients and daemon-side filters

**User story:** As a CLI operator running the daemon across repos, I want my own
notification recipients and daemon-event filters in my CLI config, so the daemon never
depends on any repo's collaborator file.

#### Acceptance criteria (EARS)

1. WHEN the daemon needs recipients THEN it SHALL read a `collaborators` array from
   `cli-config.yaml`, DECLARED by the operator — the CLI SHALL NOT read any repo's
   `collaborators.yaml` (decision-032 boundary preserved).
2. WHEN declaring CLI-side collaborators THEN the structure SHALL be the same as the
   repo-side collaborator structure (enforced by one shared schema definition).
3. WHEN a daemon-side event occurs (work item spawned, dispatch failed, session died,
   event dropped as unauthorized) THEN the daemon SHALL consult its own
   `notifications.events` filter — a taxonomy disjoint from the harness-side one.

### Requirement 4 — rename the plugin config to harness-config.yaml

**User story:** As a user reading `.the-loop/`, I want the plugin config's filename to
say whose config it is, so `config.yaml` vs `cli-config.yaml` is unambiguous.

#### Acceptance criteria (EARS)

1. WHEN the-loop ships this change THEN `.the-loop/config.yaml` /
   `.the-loop/config.schema.json` SHALL be renamed `harness-config.yaml` /
   `harness-config.schema.json`, with all living docs/templates/commands updated;
   historical records (decisions, specs, execution logs) SHALL keep the old name.
2. WHEN `/the-loop:upgrade-the-loop` runs on a pre-rename project THEN it SHALL
   migrate: rename preserving user values, move `personas`/`messaging` data into
   `collaborators.yaml`, and add the default `notifications` filters.
3. WHEN `the-loop scenarios` runs in a repo that has not upgraded THEN it SHALL still
   find `testing.integrationTestGlobs` via a pre-rename fallback read.

## Non-functional requirements

- All six config instances (three schemas × repo file + template) SHALL validate in
  `scripts/validate_config.py` (pre-commit + CI, same tooling).
- Config surface only: actual channel delivery (slack send) remains issue-1 task 21.

## Security considerations

No new attack surface. This change adds configuration only — no new network calls, no
credential storage (slack `channel-list` holds channel names, not tokens), and no new
input path into the daemon. The decision-032 trust boundary (the daemon never reads
repo-controlled config) is explicitly preserved: CLI-side recipients are declared in
the operator-owned `cli-config.yaml`, so a repo cannot inject notification targets
into the daemon. Notification content/delivery (where prompt-injection or data
exfiltration concerns could arise) is out of scope until task 21 lands and MUST carry
its own threat model then.
