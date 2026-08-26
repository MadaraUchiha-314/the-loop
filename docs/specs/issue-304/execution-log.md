---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#304"
phase: needs-review
status: in-progress
---

# Execution Log: one Slack surface, two identity allow-lists

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-26 | — | Tier 4 (`human-approves-pr`): two config schemas, both matched by `autonomy.sensitivePaths`. Brainstorming skipped — the issue carries the audit table and states the removal exactly |
| requirements-definition | 2026-08-26 | | [`requirements.md`](requirements.md) — four requirement groups, three abuse cases |
| design | 2026-08-26 | | [`design.md`](design.md) — schema refusal for the repo file, versioned migration for the operator file; six alternatives recorded |
| test-planning | 2026-08-26 | | [`testing-plan.md`](testing-plan.md) — fourteen rows, eleven applicable |
| tasks-breakdown | 2026-08-26 | | [`tasks.md`](tasks.md) — ten tasks |
| implementation | 2026-08-26 | | On `claude/github-issue-304-1q1jeu` |
| verification | 2026-08-26 | | [`evidence/verification.md`](evidence/verification.md) — 2698/2698 tests, ruff + pyright + markdownlint clean, all seven shipped configs valid under real `jsonschema`, every new test failed against the unfixed tree first |
| needs-review | 2026-08-26 | | PR raised; awaiting the owner |
| complete | | | |

## What was delivered

Seven places to declare Slack- and collaborator-related config; three of them read by any
code. The four that were not are gone.

- **`collaborators.yaml` describes people, not delivery.** The per-collaborator
  `notifications` sub-object — an `enabled` switch, a channel `type`, a `via` transport and
  a `channel-list` — and the `notificationChannel` shape behind it are removed from the
  schema. `handle`, `kind` and `roles` are untouched: the loop still resolves a phase's
  reviewers and approvers by role, and that is a process layer, not notification config.
- **A retired key now says where the thing it configured went.** `additionalProperties:
  false` already refused the block, but as a bare `unknown key` — which tells an operator a
  key is wrong and nothing about the replacement. A small `RETIRED` table beside the
  validator turns each of the three retired paths into an answer naming `channels.slack`
  and `the-loop migrate-config`. It is a dict lookup on the already-failing path, it reads
  as documentation, and the next removal costs one row. An ordinary typo still gets plain
  `unknown key`: guessing at what somebody meant would be worse than silence.
- **The CLI config's two blocks are the fifth entry in the migration ledger.** Same shape
  as the four before it — site constant, `needs_migration` probe, `assert_current` refusal,
  `migrate_cli_config` removal — with `CURRENT_CONFIG_VERSION` at `0.6.0`. Detection is by
  **key**, not by the version the file claims, so a hand-edited config that stamps `0.6.0`
  while keeping the block is still refused. Nothing is converted, because a role list that
  resolved to no recipient has no equivalent under a channel that subscribes by event name
  — the report says what to configure instead, and only to an operator who had actually
  filled the block in.
- **Everything that promised per-collaborator delivery now says what is true.** The
  templates and this repo's own configs (commented examples included), the collaboration
  reference, the config pages, the upgrade command's migration checklist, and the capability
  doc. `docs/config/cli/observability-options.md` reduces to `eventLog` and gains a section
  saying where the notifications went; `decision-035` carries a `superseded in part by`
  marker, the convention decision-005, decision-021 and decision-030 already set.

Unchanged, and asserted so: `channels.slack` in shape and behaviour, both identity
allow-lists (`routing.authorizedUsers`, `channels.slack.authorizedUsers`), and
`harness-config.yaml`'s `notifications.events` as the `notify` hook's gate. No channel,
ingress, dispatch or session code was touched.

## Verification

Full results in [`evidence/verification.md`](evidence/verification.md): **2679 → 2698**
tests, ruff + `ruff format --check` + pyright clean, markdownlint clean over 876 docs, all
seven shipped configs `VALID` under real `jsonschema`, and every new test run against the
unfixed tree first and seen to fail there (15 failures, no pre-existing test disturbed).

## Documentation

- [`docs/capabilities/channels.md`](../../capabilities/channels.md) — two behaviour bullets
  (one Slack surface and two identity allow-lists; the retired shapes and how each is
  refused) and a History row.
- [`docs/config/cli/observability-options.md`](../../config/cli/observability-options.md) —
  reduced to `eventLog`, plus a "where the notifications went" section; the map row in
  [`docs/config/cli/index.md`](../../config/cli/index.md) follows it.
- [`docs/config/harness-config.md`](../../config/harness-config.md) — the Collaborators
  section drops the channel prose and gains a warning explaining the removal.
- [`docs/cli/commands/migrate-config.md`](../../cli/commands/migrate-config.md) — the fifth
  retirement, and the version in the worked example.
- `skills/the-loop/reference/collaboration.md`, `skills/the-loop/SKILL.md` — the
  paper-trail rule and the personas section say channel, not per-person.
- `commands/upgrade-the-loop.md`, `commands/init.md`, `commands/work-on.md`,
  `commands/execute-tasks.md` — the migration checklist and the notify instructions.
- [`docs/decisions/decision-035.md`](../../decisions/decision-035.md) — a
  `superseded in part by` marker naming exactly which of its decisions no longer stand.

## Decisions and open questions

No new decision record was minted. The call — remove rather than wire — is the ticket's own
and follows a standing one (issue-245/decision-094 deferred per-person routing explicitly);
what changed is that decision-035's points 1 and 2 no longer stand, which the supersession
marker records where a reader of that decision will find it.

Three things for the owner at the review gate:

1. **The ticket's own open question, answered as it proposed.** The four daemon event names
   (`work-item-spawned`, `dispatch-failed`, `session-died`, `event-dropped-unauthorized`)
   were **not** added to the channels `SUBSCRIBABLE_EVENTS` catalog. They never worked, and
   making them work is a feature wearing a removal's clothes. Worth filing separately; say
   the word and it gets a ticket.
2. **The ticket's note about `integrations.slack` needs no action.** That key was retired in
   0.5.0 (issue-245, decision-094) and `channels.slack` is its successor — which is what
   this work item keeps. Nothing here restores the incoming webhook. If the intent *was* to
   restore it, that contradicts decision-094 and is a different story.
3. **`uv.lock` carries one incidental line.** `uv run` refreshed the editable
   `the-loopy-one` version (11.5.0 → 11.6.0, matching the repo's own bump commit) and one
   dependency marker. Unrelated to this change; kept because any `uv sync` reproduces it
   and dropping it just moves it to the next PR.
