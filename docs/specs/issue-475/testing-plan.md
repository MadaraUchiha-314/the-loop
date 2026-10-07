---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#475"
status: approved
approvedBy: ["MadaraUchiha-314"]
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: Jira as a first-class work-item source and update channel

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md), before
> `tasks.md`. Completed at the `verification` node. **This file names commands an agent
> will run; review it like code.** Credentials appear by env-var name only.

**Almost everything is proved offline against a `FakeJiraClient`, and one manual row
proves the rest against a real Jira Cloud site.** The fakes prove our logic. They
cannot prove what Jira does with our requests. Four facts fall in that gap:

- ADF renders as intended.
- `/search/jql` accepts our JQL.
- Jira signs webhooks the way C8 assumes.
- `myself` returns the comment author id.

Those four are the manual row T11. Because it needs a sandbox site only the operator can
provide, it is the one activity that may not run (see *Open question for the gate*).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit — refs & spec ids | yes | `JiraScheme` parse/render round-trip, grammar rejections, slug/url, `spec_id` disjointness (incl. key `ISSUE`), `derive_ref` inverse, `origin_repository`; the **unchanged** GitHub cases in `test_routing.py`, `test_graph_refs.py`, `test_graphlink.py`, `test_core_graphs.py` | `cli/tests/test_jira_refs.py` + existing files |
| T2 | Unit — client, labels, format | yes | `JiraApiConfig` per deployment (server URL, REST version, credentials read at call time); `jira_label` table and failures; Markdown→ADF, Markdown→wiki, ADF→Markdown golden files (taskList ⇄ `- [x]`, tables, code, links, `<details>` dropped); JQL building | `cli/tests/test_jira_api.py`, `test_jira_labels.py`, `test_jira_format.py` |
| T3 | Contract — provider suite | yes | `JiraProvider(client=FakeJiraClient())` in `ALL_PROVIDERS`: declared ops, `OperationUnsupported`, op set equals `OPERATIONS`; per-op return shapes match GitHub's | `cli/tests/test_integration_contract.py`, `test_jira_integration_provider.py` |
| T4 | Unit — ledger, channel, hooks | yes | `RoutedLedger` routes by ref provider and `channels.ledger` for `work-item.create`; `JiraLedger` bodies (ask, relay, mirror, stamped) carry the Jira self-marker; `JiraChannel` subscribe/publish/verbosity; `jira@PROJ-1` room ref parses, bad keys refused; `set-phase-label`/selection/goal/review hooks resolve the integration from the ref | `cli/tests/test_jira_channels.py`, `test_channels.py`, `test_graph_integrations.py` |
| T5 | Unit — poller & webhook | yes | `JiraPollProvider` listing/JQL/comments/closure/degraded scopes and back-off; doorbell route registration, signature handling, re-fetch, event mapping; `is_authorized_on("jira")` | `cli/tests/test_jira_poller.py`, `test_jira_webhook.py`, `test_jira_authz.py` (new) |
| T6 | Integration (Gherkin scenarios) | yes | end-to-end through router → dispatcher → session registry with fakes for Jira and tmux (the existing integration harness) | `cli/tests/test_jira_integration.py` |
| T7 | Security / abuse case | yes | one negative test per abuse case 1–10 and per trust boundary 1–6 in `design.md` §Security design | in the T2–T6 files; names listed in *Scenarios & requirement trace* |
| T8 | Migration / config | yes | `0.11.0 → 0.12.0`: the Jira stub (`transport`, `cli`, string `tokenEnv`, `baseUrl`) migrates; idempotent; a config with no Jira block is unchanged except the version; `assert_current` refuses an old Jira stub; schema patterns reject literal tokens/emails, bad keys, `cloud-scoped` without `cloudId`; the bundled and `.the-loop/` schema copies stay in parity | `cli/tests/test_migrations.py`, `test_config_schema_parity.py`, `test_jira_config.py` |
| T9 | Regression — full suite + repository hooks | yes | nothing GitHub-side changed: ruff, ruff format, pyright, the whole CLI suite, markdownlint, JSON artifacts | `uv run pre-commit run --all-files` |
| T10 | Snapshot — rendered Jira bodies | yes | committed ADF JSON + wiki output for: the phase-selection checklist, a gate request-review, an ask, the PR briefing template; reviewed by eye in the evidence and re-checked by T2's golden files | `evidence/jira-bodies.md` |
| T11 | Manual exploratory — real Jira Cloud | yes, **conditional on a sandbox** | against a sandbox site: create a ticket, comment (ADF renders), set/remove labels, phase-selection taskList ticked in Jira and read back, JQL `/search/jql` listing, transition to Done, a signed webhook delivery accepted and an unsigned one refused, `myself` equals the posted comment's author | procedure below |
| T12 | Contract — OpenAPI | n/a | the control-plane REST routes (`/work-items/*`) keep their shapes; a Jira ref is a string in the same fields. If PR 5 changes a route, that PR updates `docs/api-specs/openapi` and this row becomes yes | |
| T13 | End-to-end (live daemon + live GitHub + live Jira) | n/a | T6 drives the real router/dispatcher/registry with fakes at the network edge, and T11 covers the network edge itself; a full live run duplicates both at the cost of a long-lived public endpoint | |
| T14 | UI / visual, accessibility | n/a | no product UI; Jira's rendering of our comments is T10/T11 | |
| T15 | Performance / load | n/a as a test; checked by arithmetic | R-NFR rate limits: 10 projects at the default 60 s interval = 10 JQL calls + one comment call per armed issue per minute, far below Jira Cloud's per-user limits; recorded in the design note, no load rig | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1–R1.5, R2.1–R2.4 | `test_jira_ref_round_trips`, `test_jira_ref_rejects_bad_site_key_number`, `test_issue_project_key_never_collides_with_github`, `test_github_refs_unchanged` (the existing tests, unmodified), `test_moved_jira_key_refuses_second_spec_folder` |
| T2 | R3.4, R3.5, R4.4, R4.5 | `test_cloud_scoped_uses_gateway_url`, `test_data_center_uses_bearer_and_v2`, `test_jira_label_mapping_table`, `test_label_without_safe_form_fails_config`, golden files under `cli/tests/fixtures/jira/` |
| T3 | R3.1–R3.3, R3.7 | contract suite; `test_create_label_is_noop_on_jira`, `test_transition_done_picks_single_done_category`, `test_transition_ambiguous_lists_candidates_and_does_nothing` |
| T4 | R4.1–R4.3, R4.6 | `test_routed_ledger_records_jira_event_on_jira`, `test_pr_event_still_recorded_on_github`, `test_jira_ledger_stamps_visible_marker`, `test_set_phase_label_on_jira_keeps_one_loop_label`, `test_mirror_only_project_accepts_room_refuses_work_item`, `test_jira_channel_without_room_mirrors_nothing`, `test_comment_on_mirror_ticket_never_reaches_session` |
| T5 | R5.1–R5.6, R6.1–R6.3, R7.1–R7.3 | `test_jql_has_one_clause_per_auto_execute_label`, `test_done_status_category_is_closure`, `test_rate_limited_scope_keeps_cursor`, `test_doorbell_refetches_comment_and_issue`, `test_missing_actor_is_unauthorized_on_jira` |
| T6 | R5.3, R5.5, R6.3, R6.4, R8.1, R3.7/R8.2 | `Scenario: an authorized Jira comment resumes the work item's session` · `Scenario: the same Jira comment by webhook and by poll is delivered once` · `Scenario: a Jira phase-selection checklist ticked in place is read at execute` · `Scenario: a PR naming a registered Jira key routes to the Jira work item` · `Scenario: finish-tasks transitions the Jira ticket to Done` · `Scenario: the-loop comment on a Jira ref is recorded on the Jira ticket` |
| T7 | Security considerations, abuse cases 1–10 | `test_jira_webhook_rejects_bad_signature` (1) · `test_jira_webhook_absent_without_secret` (2) · `test_jira_comment_from_unlisted_author_is_ignored` (3) · `test_jira_self_comment_never_resumes` — marker **and** author-id variants (4) · `test_jira_label_alone_does_not_start` (5) · `test_jql_values_are_quoted`, `test_invalid_project_key_fails_config` (6) · `test_pr_naming_unregistered_jira_key_does_not_link`, `test_pr_in_other_repository_does_not_link` (7) · `test_ref_on_unknown_site_sends_no_credential` (8) · `test_jira_errors_and_logs_carry_no_secret` (9) · `test_jira_comment_is_framed_untrusted` (10) |
| T8 | R3.5, R3.6 | `test_migrate_jira_stub_to_0_12`, `test_migrate_is_idempotent`, `test_old_jira_stub_refused_with_hint`, `test_schema_rejects_literal_token` |
| T9 | NFR "no regression on GitHub" | full suite |
| T10 | R4.5, R5.5 | rendered bodies |
| T11 | R3.4, R4.5, R5.2, R5.4, R6.2, R4.6 | manual procedure |
| — | R8.3, R8.4, R9.1–R9.3 | proved by review, not tests: the decision record, capability docs, skill text and `/init` step are inspected at self/critic review and listed in `evidence/documentation.md` |

## Verification environment

- **Repositories:** this repository only. Each of the five PRs is verified on its own
  branch, and the final verification runs on the top of the stack.
- **Toolchain:** Python through `uv`, with `uv sync --locked`. This is the same command
  CI runs (`.github/workflows/ci.yml`).
- **Services:** none for T1–T10. The integration harness runs the router, the dispatcher
  and the registry in-process, with `FakeJiraClient` and the existing fake tmux runner.
- **Fixtures:** golden ADF and wiki files under `cli/tests/fixtures/jira/`, plus recorded
  Jira webhook bodies. The recorded bodies are synthetic, written from Atlassian's
  documented payload shape, with fake account ids.
- **T11 sandbox (operator-provided), by reference only:**
  - `JIRA_SANDBOX_SITE`: the site host;
  - `JIRA_EMAIL` and `JIRA_API_TOKEN`: a dedicated service account;
  - `THE_LOOP_JIRA_WEBHOOK_SECRET`: the secret on a webhook registered against a
    tunnel (for example `cloudflared`) to a local `the-loop start`;
  - one throwaway project, `LOOPTEST`, mapped to a scratch GitHub repository.

  No value is ever written into this file or into the evidence.
- **Bring-up:** `uv sync --locked`. For T11, also run `the-loop start` with a CLI config
  that holds the sandbox `integrations.jira` block.
- **Tear-down:** for T11, delete the `LOOPTEST` tickets and the webhook, and stop the
  daemon.
- **If bring-up fails** (or no sandbox is provided), record it under *Verification
  results*, leave T11 unticked, and escalate on the PR. The gate is not passed with T11
  silently skipped.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1–T5, T7, T8 | pytest summary per file group (counts, duration), with the red→green note for each test written first | `unit.md` |
| T6 | `the-loop scenarios --glob 'cli/tests/test_*_integration.py' --format markdown` (Jira rows) + run output | `integration.md` |
| T9 | `pre-commit run --all-files` output | `regression.md` |
| T10 | ADF JSON and wiki text of the four bodies, in fenced blocks | `jira-bodies.md` |
| T11 | step log; **redacted** screenshots of the ticket (comment rendering, ticked checklist, labels, Done status) and of the webhook log lines; site host, account ids and emails replaced with placeholders | `manual-jira.md`, `jira/*.png` |
| all | the per-activity results table below | `verification.md` (linked from here) |

## Verification activities

- [x] T1 — `cd cli && uv run python -m pytest -q tests/test_jira_refs.py tests/test_routing.py tests/test_graph_refs.py tests/test_graphlink.py tests/test_core_graphs.py`
- [x] T2 — `cd cli && uv run python -m pytest -q tests/test_jira_api.py tests/test_jira_labels.py tests/test_jira_format.py`
- [x] T3 — `cd cli && uv run python -m pytest -q tests/test_integration_contract.py tests/test_jira_integration_provider.py`
- [x] T4 — `cd cli && uv run python -m pytest -q tests/test_jira_channels.py tests/test_channels.py tests/test_graph_integrations.py`
- [x] T5 — `cd cli && uv run python -m pytest -q tests/test_jira_poller.py tests/test_jira_webhook.py tests/test_jira_authz.py`
- [x] T6 — `cd cli && uv run python -m pytest -q tests/test_jira_integration.py` and `uv run the-loop scenarios --glob 'cli/tests/test_*_integration.py' --format markdown`
- [x] T7 — `cd cli && uv run python -m pytest -q -k "jira and (reject or absent or unlisted or self_comment or alone or quoted or invalid_project or does_not_link or unknown_site or no_secret or untrusted)"`, with every name listed in T7 of the trace above passing
- [x] T8 — `cd cli && uv run python -m pytest -q tests/test_migrations.py tests/test_config_schema_parity.py tests/test_jira_config.py`
- [x] T9 — `uv run pre-commit run --all-files --show-diff-on-failure`
- [x] T10 — generate and commit the four rendered bodies (`evidence/jira-bodies.md`)
- [ ] T11 — run the manual procedure against the sandbox:
  1. Register `jira:<sandbox>/LOOPTEST-1` with `the-loop sessions register`.
  2. Post with `the-loop comment` and check the ADF rendering.
  3. Set and remove a label through `set-phase-label`.
  4. Post the phase-selection checklist, tick boxes in Jira, then reply `the-loop execute`.
  5. Confirm the poller lists the armed issue through `/search/jql`.
  6. Send one signed and one unsigned webhook and confirm the unsigned one gets 401.
  7. Run `the-loop ticket close` and confirm the status is Done.

  Record each step's outcome.

## Verification results

Run on 2026-10-06 at `b5c1154`, the top of the stack. Every command was prefixed with
`env -u THE_LOOP_CLI_CONFIG -u THE_LOOP_WORK_ITEM -u THE_LOOP_GH_TOKEN`, because
those variables leak in from a daemon-spawned session and make 21 tests fail, on `main`
too. The full record is [`evidence/verification.md`](evidence/verification.md).

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | refs and spec-id test files | pass: 394 passed | [unit.md](evidence/unit.md#t1) |
| T2 | client, labels and format test files | pass: 78 passed | [unit.md](evidence/unit.md#t2) |
| T3 | contract suite and Jira provider | pass: 32 passed | [unit.md](evidence/unit.md#t3) |
| T4 | ledger, channel and hooks test files | pass: 173 passed | [unit.md](evidence/unit.md#t4) |
| T5 | poller, webhook and authz test files | pass: 115 passed | [unit.md](evidence/unit.md#t5) |
| T6 | `test_jira_integration.py` + `the-loop scenarios` | pass: 11 passed, 11 Jira scenarios listed (`--root` given absolute) | [integration.md](evidence/integration.md) |
| T7 | `-k "jira and (…)"` + the twelve named abuse-case tests | pass: 67 passed; all twelve names exist and pass | [unit.md](evidence/unit.md#t7) |
| T8 | migration, schema-parity and Jira config test files | pass: 108 passed | [unit.md](evidence/unit.md#t8) |
| T9 | `uv run pre-commit run --all-files --show-diff-on-failure` | pass: all six hooks; full suite 5950 passed | [regression.md](evidence/regression.md) |
| T10 | four rendered bodies, golden-file tests | pass: eight blocks equal the fixtures; 4 golden tests passed | [jira-bodies.md](evidence/jira-bodies.md) |
| T11 | manual procedure against a Jira Cloud sandbox | not executed | — |

**Not executed:** T11. No Jira Cloud sandbox is configured; escalated on the ticket
(see *Open question for the gate*).

## Open question for the gate

- **Will a Jira Cloud sandbox be provided for T11?** With one (project `LOOPTEST`, a
  service account, and the env vars above set on the machine running the-loop), T11
  runs as written. Without one, T11 cannot run. The plan is then to escalate at
  verification, not to tick it, and the four facts in the opening paragraph stay
  unproven until someone tries the integration against a real site.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.

### 2026-10-06 — approved

**@MadaraUchiha-314** wrote:

approved, go ahead.
