---
type: requirements
phase: requirements-definition
workItem: "issue-304"
status: locked
approvedBy: []
collaborators: [architect, engineer]
riskTier: 4
overrides: {}
---

# Requirements: one Slack surface, two identity allow-lists

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). Tier 4 (`human-approves-pr`): the change edits two
> config schemas, which `autonomy.sensitivePaths` names — a schema is a contract with
> every operator who already wrote a config against it.

## Introduction

[Issue #304](https://github.com/MadaraUchiha-314/the-loop/issues/304): Slack and
collaborator notification config can be declared in **seven** places, and only three of
them are read by any code.

| Surface | Read by code? | Where |
|---------|---------------|-------|
| `cli-config.yaml → channels.slack` | **yes** | `channels/` — `ask` fan-out, the graph's `notify` hook, the reply pipeline |
| `cli-config.yaml → routing.authorizedUsers` | **yes** | `authz.py` — who may arm/command a work item on GitHub |
| `cli-config.yaml → channels.slack.authorizedUsers` | **yes** | `channels/` — whose Slack thread reply is acted on |
| `cli-config.yaml → collaborators[]` | **no** | nothing reads it |
| `cli-config.yaml → notifications.events` | **no** | the four daemon event names appear nowhere under `cli/the_loop/` |
| `collaborators.yaml → collaborators[].notifications` | **no** | declared-but-unread; deferred explicitly in the issue-245 design |
| `harness-config.yaml → notifications.events` | **partly** | the `notify` hook gates on it and prints the role names; roles never resolve to people or channels |

The duplication does not merely take up space — it **misinforms**. An operator who fills
in `collaborators[].notifications.channels[].config.channel-list` has every reason to
believe they configured Slack notifications. Nothing is delivered, nothing warns, and the
failure is silent in exactly the direction that matters: a phase-approval notification
that goes nowhere looks identical to a loop with nothing to approve.

Per-person routing stays **deferred scope** (the issue-245 design recorded it as such).
This work item removes the unread shapes rather than wiring them, and the removal must
leave the ground clean for a future per-person design rather than pre-committing it.

## Requirements

### R1 — The collaborator file describes people, not delivery

- R1.1 WHEN `collaborators.schema.json` is loaded THEN it SHALL define no `notifications`
  property on a collaborator and no `notificationChannel` shape.
- R1.2 WHEN a `collaborators.yaml` carrying `collaborators[].notifications` is validated
  THEN validation SHALL fail, and the failure SHALL name both `channels.slack` (where
  Slack is configured now) and `the-loop migrate-config` (how to move).
- R1.3 The collaborator shape SHALL keep `handle`, `kind` and `roles` unchanged: the skill
  resolves reviewers and approvers per phase by role, and that is a process layer, not
  notification config.
- R1.4 Spec front-matter `collaborators:` SHALL be untouched.

### R2 — The CLI config declares Slack once

- R2.1 WHEN `cli-config.schema.json` is loaded THEN it SHALL define no top-level
  `collaborators` and no top-level `notifications`.
- R2.2 WHEN a CLI config declaring either block is loaded by the runtime THEN loading
  SHALL refuse with a message naming the removed block, `channels.slack`, and the upgrade
  command — never load half-configured and never ignore the value silently.
- R2.3 `channels.slack` SHALL be unchanged in shape and behaviour: token env vars, channel
  id, the `events` allow-list, `verbosity`, `authorizedUsers` and the `read` transport.
- R2.4 `routing.authorizedUsers` SHALL be unchanged.
- R2.5 `harness-config.yaml → notifications.events` SHALL be unchanged and SHALL remain
  the `notify` hook's gate.

### R3 — The migration moves an operator's config, mechanically

- R3.1 WHEN `the-loop migrate-config` runs on a config carrying either retired block THEN
  it SHALL remove both, bump the config version, and **report** each removal.
- R3.2 WHEN the migration runs on a config carrying a collaborator with `notifications`
  under the top-level `collaborators` block THEN the whole block goes with it — there is
  no partial rescue of a shape nothing read.
- R3.3 WHEN the migration is run a second time on its own output THEN it SHALL report no
  change (idempotent), and the output SHALL be byte-identical.
- R3.4 WHEN the removed blocks carried a non-empty value THEN the report SHALL carry a
  note saying what to configure instead (`channels.slack`), because "removed" and
  "removed, and here is where it went" are different messages to an operator who set it.

### R4 — Nothing promises what no code delivers

- R4.1 The shipped templates (`templates/cli-config.yaml`, `templates/collaborators.yaml`)
  and this repository's own `.the-loop/` configs SHALL carry none of the retired shapes,
  commented examples included.
- R4.2 No doc under `docs/` or `skills/` SHALL promise per-collaborator delivery
  ("recipients resolved by role … delivered on each recipient's enabled channels"), and
  `grep -ri "channel-list" docs/ skills/` SHALL return no hit that promises it.
- R4.3 `docs/capabilities/channels.md` SHALL record the retirement in its History table.
- R4.4 Where a doc previously described per-collaborator delivery it SHALL say what is
  true instead: notifications go to a **channel**, subscribed by event name, and per-person
  routing is not built.

### NFR

- NFR1 The schema/docs drift tests (`test_docs_parity.py` P3/P4, `test_config_schema_parity.py`,
  `test_manifest_schemas.py`) and the pinned harness-config read-surface test
  (`test_harness_config.py`) SHALL pass without being weakened.
- NFR2 The full channels test suite SHALL pass unchanged — this work item touches no
  channel code.

## Security considerations

Trust boundaries touched: **one**, and only by removal.

- **T1 — the identity allow-lists.** `routing.authorizedUsers` (GitHub logins) and
  `channels.slack.authorizedUsers` (Slack member ids) decide who may drive this operator's
  daemon and whose thread reply is acted on. Neither is touched. The retired
  `collaborators[]` list was never an allow-list — nothing read it — so removing it cannot
  widen authorization. The requirement that protects this is R2.4, and T4 of the testing
  plan proves it against the schema rather than by inspection.
- **T2 — the migration writes the operator's config file.** It rewrites a file that names
  a webhook secret env var and an authorized-user list. The existing migration keeps a
  `.bak`; the removal must not touch any key outside the two named blocks.

### Abuse cases

- **A1 — a config that lies about its version.** A hand-edited config declaring
  `version: "0.6.0"` while still carrying `collaborators` must still be refused. The
  version stamp is a claim, not evidence: `needs_migration` and `assert_current` both
  check for the key itself, as they already do for `integrations.slack`.
- **A2 — a silent partial load.** A runtime that dropped the retired block and carried on
  would tell an operator their config was accepted. R2.2 is the mitigation: refuse, name
  the key, name the fix.
- **A3 — a migration that eats a neighbouring key.** The removal is two `pop`s on the
  top-level mapping; a round-trip test asserts every other key survives byte-identical.
