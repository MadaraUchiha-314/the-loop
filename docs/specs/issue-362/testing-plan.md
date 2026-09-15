---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#362"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: a DM is a channel like any other

> Derived from `bugfix.md` and `design.md`, **before** `tasks.md` — each task's `_Test:_`
> names a row of the matrix below. Authored at `test-planning`, completed at
> `verification`. See `reference/testing.md`.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. No credentials, no network: every Slack call is made through a substituted
> client, as the rest of `cli/tests/test_channels*.py` does.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | The manifest declares all four message events and their four history scopes (R1.1), and the guide's fence is still byte-identical to it (R1.3) | `uv run --project cli python -m pytest -q cli/tests/test_channels_dm.py cli/tests/test_channels_commands.py -k manifest` |
| T2 | Unit | yes | `kinds_from_id` maps `D…`/`G…`/`C…`/junk to the candidate kinds and `kind_from_info` to the authoritative one; `subscription_findings` produces a finding exactly when **every** candidate's scope is absent, and none when scopes are unreadable; `unchecked_advice` calls out a `D…` and nothing else (R2.1, R2.5, design D2/D3) | `uv run --project cli python -m pytest -q cli/tests/test_channels_dm.py -k "kind or finding or advice"` |
| T3 | Unit | yes | `probe_subscription` makes exactly two calls against a fake client, reads `x-oauth-scopes` in both header shapes, and returns `skipped` (never raises) with no token, no channel, or an API error (R2.2, R2.3, bugfix §AC3/§AC4) | `uv run --project cli python -m pytest -q cli/tests/test_channels_dm.py -k probe` |
| T4 | Unit | yes | `catchUpSeconds` parses: default 900, explicit 0 kept as 0, 1–59 clamped to 60 with a warning, junk falls back to the default (R3.2, design D5, bugfix §AC6) | `uv run --project cli python -m pytest -q cli/tests/test_channels_dm.py -k catch_up_seconds` |
| T5 | Integration (scenario) | yes | The listener, driven end to end against a fake Socket Mode client: it probes and logs the DM finding once at start (R2.4), a `message.im` envelope reaches `handle_socket_event` through the unchanged kind-agnostic filter (R1.2), the reconcile fires on its deadline and not before (R3.1), a raising cycle does not stop it (R3.3), and the stop event ends it within a tick | `uv run --project cli python -m pytest -q cli/tests/test_channels_dm_integration.py` |
| T6 | Unit | yes | `channels status` prints the kind line and the finding for a `D…` channel with no network call at all, prints the reconcile cadence, and `--probe` adds the probed line; a skipped probe still exits 0 (R2.1, R2.3) | `uv run --project cli python -m pytest -q cli/tests/test_channels_dm.py -k status` |
| T7 | Migration / upgrade | yes | A 0.9.0 config with no `catchUpSeconds` loads unchanged and gets the 900s default; `CURRENT_CONFIG_VERSION` is untouched (design D6) | `uv run --project cli python -m pytest -q cli/tests/test_channels_dm.py -k upgrade cli/tests/test_migrations.py` |
| T8 | Contract (OpenAPI / GraphQL SDL) | n/a — no control-plane API surface changes; `docs/api-specs/` untouched. The only "contract" here is the config schema, covered by T7 and the schema-parity test in T12 | | |
| T9 | End-to-end | n/a — an end-to-end proof needs a real Slack workspace, a real app installed from the new manifest and a real DM, none of which exist in CI or this container. The reporter's live instance is the end-to-end evidence for the *defect*; the manifest half of the fix is verified by the operator on import, and `evidence/verification.md` records that explicitly rather than claiming a run that did not happen | | |
| T10 | Security / abuse case | yes | The six abuse cases of `bugfix.md`: the allow-list still refuses an unauthorized DM author (§AC2), the probe and `status` print no token and no message content (§AC3), the probe calls only the two fixed endpoints (§AC4), a reconcile re-reading a processed ts drops it as `duplicate` (§AC5), and the 60s floor holds (§AC6) | `uv run --project cli python -m pytest -q cli/tests/test_channels_dm.py cli/tests/test_channels_dm_integration.py cli/tests/test_channels_integration.py` |
| T11 | UI / visual | n/a — no rendered UI (`design.md` §UI/UX). The two terminal surfaces are asserted as text at T6 | | |
| T12 | Repository gates | yes | The whole repository still passes what CI runs: ruff, ruff format, pyright, config validation, the full suite (including docs↔code parity P3/P4 for the new schema leaf and the two schema copies' byte parity), and markdownlint over every `**/*.md` — these artifacts included | `make check` |
| T13 | Performance / load | n/a — the reconcile's cost is bounded by configuration, not by measurement: the 60s floor and the `0` opt-out are the control, and `poll_once` already makes no call when nothing is bound. A load test would measure Slack's rate limiter, not the-loop | | |
| T14 | Accessibility | n/a — no rendered UI | | |
| T15 | Manual exploratory | n/a — the one thing a human could add is a live workspace, which is T9's reason. Everything else is asserted by T1–T7 | | |
| T16 | Snapshot | n/a — the finding sentence is asserted verbatim at T2, where it is legible beside the inputs that produce it | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1 | `test_the_manifest_subscribes_every_conversation_kind` (new) |
| T1 | R1.3 | `test_the_guide_reproduces_the_packaged_manifest` (existing — it now guards the new fence) |
| T2 | R2.1 | `test_channel_kind_reads_the_id_prefix`, `test_kind_from_info_is_authoritative` (new) |
| T2 | R2.5 | `test_a_dm_without_im_history_is_a_finding_that_names_all_four_facts` (new) |
| T2 | design D2 | `test_a_public_prefix_is_never_a_finding_when_either_candidate_is_granted`, `test_only_a_dm_is_called_out_before_anything_is_probed` (new) |
| T2 | design D3, risk 4 | `test_unreadable_scopes_are_never_a_finding`, `test_probe_with_unreadable_scopes_reports_none_and_finds_nothing` (new) |
| T3 | R2.2 | `test_probe_reads_the_kind_from_conversations_info_and_the_scopes_from_auth_test` (new) |
| T3 | R2.3 | `test_probe_skips_without_a_token_a_channel_or_on_an_api_error` (new) |
| T3 | bugfix §AC4 | `test_probe_calls_only_conversations_info_and_auth_test` (new) |
| T4 | R3.2 | `test_catch_up_seconds_defaults_to_900`, `test_zero_means_connect_only`, `test_a_junk_catch_up_seconds_falls_back_to_the_default` (new) |
| T4 | bugfix §AC6 | `test_catch_up_seconds_below_the_floor_is_clamped_to_60` (new) |
| T5 | R1.2 | `test_a_message_im_envelope_reaches_the_inbound_pipeline` (new, Gherkin docstring) |
| T5 | R2.4 | `test_the_listener_warns_once_about_the_dm_subscription`, `test_a_probe_that_raises_never_keeps_the_listener_from_listening` (new, Gherkin docstrings) |
| T5 | R3.1, R3.2, R3.3 | `test_the_listener_reconciles_on_its_deadline_and_survives_a_raising_cycle`, `test_zero_disables_the_reconcile_and_keeps_the_connect_read` (new, Gherkin docstrings) |
| T6 | R2.1 | `test_status_names_the_conversation_kind_without_calling_slack` (new — it substitutes a `build_client` that raises, so "calls nothing" is asserted, not assumed), `test_status_says_nothing_about_a_kind_it_cannot_derive` |
| T6 | R3.1 | `test_status_prints_the_reconcile_cadence` (new) |
| T6 | R2.2, R2.3 | `test_status_probe_prints_the_confirmed_finding`, `test_status_probe_that_cannot_run_still_exits_zero` (new) |
| T7 | design D6 | `test_a_config_without_catch_up_seconds_loads_and_gets_the_default` (new) |
| T10 | bugfix §AC2 | `test_an_unauthorized_dm_author_is_dropped` (new, Gherkin docstring) — a DM goes through the unchanged allow-list like any other conversation; the generic proof is the existing `test_unauthorized_reply_is_neither_mirrored_nor_delivered` |
| T10 | bugfix §AC3 | `test_probe_prints_no_token_value` (the result) and `test_status_probe_prints_the_confirmed_finding`'s own no-token assertion (stdout) |
| T10 | bugfix §AC5 | existing `test_a_socket_listener_catches_up_after_downtime` in `test_channels_integration.py` — a second catch-up processes nothing and a redelivery is `duplicate`; the reconcile is that same `poll_once`, so this is its proof |
| T12 | R4.1–R4.4 | `make check` — docs↔code parity for `read.catchUpSeconds`, schema byte parity, markdownlint over the guide, the options page, the capability doc and these artifacts |

## Verification environment

This container: `uv`, Python 3.11+, the repository's own test suite. **No Slack
credentials and no network** — `build_client` is substituted in every test, as the
existing channel tests do. `make check` additionally runs `npx markdownlint-cli2`, which
needs the npm registry once.

## Evidence to capture

- The red run: the new assertions failing against the unfixed tree (`evidence/red.md`).
- The green run: T1–T7, T10 (`evidence/verification.md`).
- `make check` in full (`evidence/verification.md`).
- What was **not** proved here and why: T9's absent workspace (`evidence/verification.md`).

## Activities checklist

- [x] T1 — manifest + guide parity
- [x] T2 — kind & findings, pure
- [x] T3 — the probe against a fake client
- [x] T4 — `catchUpSeconds` parsing
- [x] T5 — the listener, end to end (Gherkin docstrings)
- [x] T6 — `channels status` and `--probe`
- [x] T7 — an un-migrated config
- [x] T10 — the abuse cases
- [x] T12 — `make check`
- [x] Evidence recorded under `evidence/`

## Verification results

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
| The failing state: the new assertions against the unfixed tree | `pytest -q cli/tests/test_channels_dm.py cli/tests/test_channels_dm_integration.py` | fail (red, as designed) | [`evidence/red.md`](evidence/red.md) |
| T1–T4, T6, T7, T10 — the manifest, the kinds, the findings, the probe, the config key, `status` and `--probe`, the abuse cases | `pytest -q cli/tests/test_channels_dm.py` | 39 passed | [`evidence/verification.md`](evidence/verification.md) |
| T5 — the listener end to end: the `message.im` envelope, the start-up probe, the reconcile deadline, a raising cycle, `0` = connect-only | `pytest -q cli/tests/test_channels_dm_integration.py` | 5 passed | [`evidence/verification.md`](evidence/verification.md) |
| T1 (parity), T7, T12 — the guide's manifest fence, the two schema copies, docs↔code parity | `pytest -q cli/tests/test_channels_commands.py -k manifest cli/tests/test_config_schema_parity.py cli/tests/test_configschema.py cli/tests/test_docs_parity.py` | 55 passed | [`evidence/verification.md`](evidence/verification.md) |
| T12 — the whole suite, then every repository gate CI runs | `uv run --project cli python -m pytest -q cli`, then `make check` | 3674 passed, 1 skipped; `make check` pass | [`evidence/verification.md`](evidence/verification.md) |
| T9 — **not proved here**: no Slack workspace in CI or this container | — | n/a, with the reason recorded | [`evidence/verification.md`](evidence/verification.md) § What this did NOT prove |
