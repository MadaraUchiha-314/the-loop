---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#362"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Tasks: a DM is a channel like any other

> Phase 3 of 3. Each task names the requirement it serves and the testing-plan row that
> proves it. TDD: the red root (task 1) is written and run **before** any of the three
> layers exists.

- [x] **1. Red root — assert all three layers before any of them exists.**
  New `cli/tests/test_channels_dm.py` carrying the manifest assertion (T1), the
  kind/findings cases (T2) and the `catchUpSeconds` parse cases (T4); new
  `cli/tests/test_channels_dm_integration.py` carrying the listener scenarios (T5) with
  their Gherkin docstrings. Run both and capture the failures verbatim as
  `evidence/red.md`.
  _Requirements: R1.1, R2.1, R2.5, R3.1, R3.2 — Test: T1, T2, T4, T5_

- [x] **2. Subscribe the manifest to every conversation kind.**
  `cli/the_loop/channels/slack-app-manifest.yaml`: `im:history` and `mpim:history` in
  `oauth_config.scopes.bot`, `message.im` and `message.mpim` in
  `settings.event_subscriptions.bot_events`, each with the one-line comment its
  neighbours carry.
  _Requirements: R1.1, R1.2 — Test: T1_

- [x] **3. Derive the conversation's kind, and say what it needs.**
  In `cli/the_loop/channels/slack.py`: `CONVERSATION_KINDS` (kind → id prefix, bot scope,
  bot event, human name), `channel_kind(channel_id)` from the prefix, `kind_from_info`
  from a `conversations.info` payload, and the pure `subscription_findings(kind, scopes)`
  returning the sentence of design D3 — no finding when the scopes are unknown.
  _Requirements: R2.1, R2.5 — Test: T2_

- [x] **4. Probe the installed app.**
  `probe_subscription(config, *, client_factory=build_client)`: `conversations.info` on
  the configured channel, `auth.test` for the granted scopes off the `x-oauth-scopes`
  response header (both header shapes), returning `{"skipped": why}` on every failure
  path and never raising.
  _Requirements: R2.2, R2.3 — Test: T3, T10_

- [x] **5. Parse `read.catchUpSeconds`.**
  `SlackChannelConfig.catch_up_seconds` (default 900; explicit `0` preserved; 1–59
  clamped to 60 with a warning; junk → the default), read explicitly rather than through
  the `or` idiom its neighbour uses.
  _Requirements: R3.2 — Test: T4_

- [x] **6. Add the schema leaf, in both copies.**
  `read.catchUpSeconds` in `cli/the_loop/schemas/cli-config.schema.json`, then `cp` to
  `.the-loop/cli-config.schema.json` so the byte-parity test holds. No version bump
  (design D6).
  _Requirements: R3.2 — Test: T7, T12_

- [x] **7. Probe once at listener start, and reconcile on a deadline.**
  `run_socket_listener`: log each finding at `warning` (a skipped probe at `info`) after
  `connect()`, then carry a `time.monotonic()` deadline through the existing 1-second
  wait loop so the stop event is still honoured within a tick.
  _Requirements: R2.4, R3.1, R3.3, R3.4 — Test: T5_

- [x] **8. Say it in `channels status`.**
  `cli/the_loop/commands/channels_cmd.py`: the reconcile cadence on the `read:` line, a
  `channel kind:` line and its `[!]` finding from the prefix alone, and a `--probe` flag
  that adds the probed kind, the granted scopes and the confirmed findings. Exit 0
  whatever the probe does.
  _Requirements: R2.1, R2.2, R2.3 — Test: T6, T10_

- [x] **9. Documentation that ships with the change.**
  `docs/guide/slack.md`: the manifest fence re-synced, the upgrade table's new row, a
  conversation-kind table, and the Downtime section's reconcile paragraph.
  `docs/config/cli/channels-options.md`: `read.catchUpSeconds` with Type and Default, and
  the sample YAML. `skills/the-loop/templates/cli-config.yaml`: the commented key.
  _Requirements: R4.1, R4.2, R4.3 — Test: T12_

- [x] **10. Capability doc + History row.**
  `docs/capabilities/channels.md`: the DM behaviour, the doctor and the reconcile as
  current behaviour, and a History row tracing all three to issue-362. Record it in
  `evidence/documentation.md`.
  _Requirements: R4.4 — Test: T12_

- [x] **11. Verify and record.**
  Run T1–T7, T10, then `make check`. Complete `testing-plan.md`'s results table and
  activities checklist; write `evidence/verification.md` (including what T9 did not
  prove and why) and `evidence/security-review.md` against the six abuse cases.
  _Requirements: all — Test: T12_
