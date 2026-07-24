# Decision 035: collaborators.yaml is the single source for people + notification config; the plugin config is renamed harness-config.yaml

- **Status:** accepted
- **Date:** 2026-07-24
- **Deciders:** @MadaraUchiha-314 (issue #82)
- **Work item:** issue-82

## Context

the-loop's notification/escalation config was split-brained. Collaborators could live
in `config.personas` (schema-validated) **and/or** `.the-loop/collaborators.yaml`
(unmanaged, no schema) — neither authoritative. Notification channels were a flat
global list (`config.messaging.channels`), so a collaborator could not own their own
Slack channel list, and there was no per-user or per-channel enable/disable and no
event filtering. Meanwhile decision-032 had split the CLI daemon's config into its own
`cli-config.yaml`, raising the question of how the cross-repo daemon — forbidden from
reading any repo's plugin config — learns who to notify.

Issue #82 set the principles: collaborators.yaml is for the stewards of the repository
(CODEOWNERS-like); collaborators declare communication channels (the primary way the
harness notifies them — decisions still land as ticket/PR comments); each channel has a
type (slack only for now) and declares how to interact with it using the-loop's
existing primitives (mcp / cli / api); the CLI is not aware of repo collaborators but
has its own configuration for who to notify, in more-or-less the same structure.

## Decision

1. **`.the-loop/collaborators.yaml` is the single source for people AND their
   notification config.** Per-user `notifications.enabled`, per-channel `enabled`,
   typed channels (`slack`), a `via` field reusing the `externalTools.kind` primitives
   (`mcp`/`cli`/`api`), and channel-type-specific `config` (for slack:
   `channel-list`). It gets its own schema (`.the-loop/collaborators.schema.json`) and
   becomes managed (validated/reconciled by init/upgrade). The `personas` and
   `messaging` keys are retired from the harness config and migrated in.

2. **Configs stay separate; event filters exist on both sides, filtering disjoint
   event sets.** The harness config gains `notifications.events` — harness-raised
   events (decision-pending, phase-approval-pending, pr-review-pending,
   security-sign-off-pending, conflict-escalated, work-item-complete) mapped to
   ROLES; recipients resolve from collaborators.yaml by role. The CLI config gains its
   own `notifications.events` — daemon events (work-item-spawned, dispatch-failed,
   session-died, event-dropped-unauthorized) — plus an operator-declared
   `collaborators` array of the **same structure** (enforced by a cross-file `$ref`
   into collaborators.schema.json). Collaborators exist in two places by
   *declaration*, never by *lookup*: the daemon never reads any repo's
   collaborators.yaml, preserving decision-032's boundary.

3. **The plugin config is renamed `config.yaml` → `harness-config.yaml`** (schema
   likewise). Next to `cli-config.yaml`, a bare `config.yaml` no longer said whose
   config it was; "harness" is the established term of art. This yields a symmetric
   triple under `.the-loop/`: `harness-config.yaml` (how the-loop behaves in this
   repo), `collaborators.yaml` (who stewards it and how to reach them),
   `cli-config.yaml` (how the operator's daemon runs and who it notifies). The rename
   touches only the plugin side — the CLI never read the plugin config (decision-032);
   the one exception, `the-loop scenarios` (a repo-local utility, not the daemon),
   reads the new name and falls back to the old one. `/the-loop:upgrade-the-loop`
   migrates existing projects (rename preserving values; personas/messaging →
   collaborators.yaml), driven by `manifest.deprecated` entries.

## Consequences

- One schema definition (`collaborators.schema.json#/$defs/collaborator`) enforces the
  collaborator shape everywhere, so the harness-side and CLI-side structures cannot
  drift.
- Notification *sending* (task 21 of issue-1: the actual slack integration) now has a
  stable config surface to plug into; this decision deliberately ships config only.
- Historical documents (decision records, specs, execution logs) keep the old
  `config.yaml` name — they are records, not living docs.
