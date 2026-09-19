---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#389"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: the mention is the address, and three acts each end in the session

> Derived from the approved [`requirements.md`](requirements.md) and
> [`design.md`](design.md), **before** `tasks.md` — each task's `_Test:_` names a row of
> the matrix below. Authored at the `test-planning` node and **completed at the
> `verification` node**. Reviewed together with the design at `design-approval`.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. Credentials appear **by reference only**.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `verbs.parse_verb` / `compose_keyword` / `strip_mention`; the §1 input table as a pure decision; the snapshot renderer, its link composition and its cap; `parse_subjects`; the `listen` guard and `CollaboratorRecord.from_dict`; `mirror_body` for the two kinds; the two delivery frames; `records`' envelope filter | `cd cli && uv run python -m pytest -q tests/test_channels_mentions.py tests/test_channels_verbs.py tests/test_collaborators.py tests/test_workchannels.py tests/test_channels.py` |
| T2 | Integration (scenario) | yes | the listener's `handle` and `handle_socket_event` end to end with the fake Slack client and the fake ledger writer, Gherkin-documented per requirement (scenarios below); the CLI forms (`add-collaborator --slack`, `add-channel --listen`, `channels records`) through their commands | `cd cli && uv run python -m pytest -q tests/test_channels_mentions_integration.py tests/test_channels_shortcuts_integration.py tests/test_collaborators_cli.py tests/test_workchannels_cli.py tests/test_channels_records_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no HTTP API changes; the control plane's OpenAPI under `docs/api-specs/openapi` is untouched | | |
| T4 | End-to-end | n/a — a live Slack workspace cannot run in CI; T11 covers the real-workspace path by hand, and T2 drives the same code with Slack's payload shapes recorded as fixtures | | |
| T5 | UI / visual | n/a — no product UI; the decision modal is a Block Kit JSON literal pinned by T6, and its rendering is Slack's | | |
| T6 | Snapshot | yes | the decision modal view, the shipped manifest (scopes, event, shortcuts) and the guide's copy of it, the `help` text, the `channels status` lines for `mentions:` / `shortcuts:` | `cd cli && uv run python -m pytest -q tests/test_channels_commands.py tests/test_channels_dm.py tests/test_channels_shortcuts.py` |
| T7 | Performance / load | n/a — the mention gate adds no call and drops before any lookup; a snapshot is one paged `conversations.replies` bounded by the cap | | |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A12, named in `design.md` § Security design | `cd cli && uv run python -m pytest -q tests/test_channels_mentions_security.py` |
| T9 | Accessibility | n/a — no rendered surface of the-loop's own; the modal's labels are plain text and Slack owns its accessibility | | |
| T10 | Migration / upgrade | yes | a declaration without `listen` reads as `mentions`; a roster entry without `slack` keeps working and one without either id is skipped; a channel state file without `snapshots` loads; an app whose granted scopes lack `app_mentions:read` is reported by `status --probe` and at connect; both schema copies stay byte-equal; the docs pins pass | `cd cli && uv run python -m pytest -q tests/test_channels_upgrade.py tests/test_config_schema_parity.py tests/test_docs_parity.py tests/test_graph_parity.py tests/test_bus.py` |
| T11 | Manual exploratory | yes | against a real workspace: reinstall with the new manifest; a plain message in a `mentions` room leaves no trace; `@the-loop help`; `@the-loop record-context` in a thread → ticket record, `context.md` entry, thread reply, ✅; the *Add as context* shortcut; the decision shortcut, modal and `decision-<nnn>.md`; `@the-loop add-collaborator slack:U…` then that member adds context; `--listen all` on a room; a DM still works; `read.mode: poll` says nothing addressed can arrive | procedure in `evidence/manual.md` |
| T12 | Whole suite and the repository's own checks | yes | nothing else regressed; lint, format, types, markdown | `make check` (from the repository root: ruff, ruff format check, pyright, the schema validation, pytest, markdownlint) |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R3.1, R3.4 | `parse_verb` on each verb, `help`, a keyword's last word, prose; `strip_mention` removes the bot's token anywhere and leaves other mentions |
| T1 | R1.1–R1.3, R1.6, R2.2 | the §1 input table: (DM, message) → input; (all room, message) → input; (all room, app_mention) → duplicate; (mentions room / central / bound thread, message) → not-addressed; (…, app_mention) → input |
| T1 | R4.1, R4.5, A5, A9 | the snapshot renderer: names, links, the 150-message and 40,000-character caps, the scrub order, the size refusal |
| T1 | R5.1, R5.4 | `mirror_body` for `decision.recorded` and `context.added` carries the marker and the envelope and defangs keywords |
| T1 | R3.7 | the `context` and `decision` frames are composed from fixed words, ref, counts and URLs, and name the text untrusted |
| T1 | R7.1, A11, A12 | `parse_subjects`, `CollaboratorRecord.from_dict`, the `listen` guard |
| T2 | R1.1–R1.5 | `Scenario: a message without the mention leaves no trace` · `Scenario: a mention in a mentions room is input` · `Scenario: a mention under the-loop's own question is input and a plain reply there is not` · `Scenario: a mention with a keyword composes the configured keyword` · `Scenario: a mentioned top-level message in the central channel is a kickoff` · `Scenario: a redelivered mention is processed once` |
| T2 | R1.6, R1.7 | `Scenario: a DM hears a plain message` · `Scenario: poll mode reads no mention-gated conversation and moves no cursor` |
| T2 | R2.1–R2.4 | `Scenario: an all room hears a plain message` · `Scenario: add-channel --listen all is recorded with provenance and shown by channels threads` · `Scenario: a collaborator cannot switch a room` |
| T2 | R3.2, R3.3, R3.6, R3.7 | `Scenario: help answers ephemerally and records nothing` · `Scenario: a room's opening message carries the hint` · `Scenario: an accepted act is acknowledged and answered with the record's link` · `Scenario: a refused delivery leaves the record standing` |
| T2 | R4.1–R4.4, R4.6 | `Scenario: record-context snapshots a thread onto the ticket and into the session` · `Scenario: record-context on a top-level message snapshots that message` · `Scenario: a second record-context records only what is new` · `Scenario: record-context without the grant is dropped as unpublishable` |
| T2 | R5.1–R5.3, R5.5 | `Scenario: record-decision lands as a marked record and a decision frame` · `Scenario: an empty record-decision is refused with the grammar` · `Scenario: a collaborator may add context but not a decision` |
| T2 | R6.1–R6.5 | `Scenario: the context shortcut is the typed mention` · `Scenario: the decision shortcut opens the modal and the submission is the typed mention` · `Scenario: a shortcut acts once per trigger` |
| T2 | R7.1, R7.2, R7.4, R7.5 | `Scenario: add-collaborator by mention writes a Slack id` · `Scenario: a collaborator's record names the roster's ids` · `Scenario: a roster on one work item widens nothing on another` |
| T2 | R4.7, R5.6 | `Scenario: channels records lists the enveloped records of a work item` |
| T6 | R6.1, R1.8, R3.2, R6.6 | the manifest (scope, event, shortcuts) equals the guide's block; the modal view; the help text; the status lines |
| T8 | A1–A12 | the twelve negative tests named in `design.md` § Security design |
| T10 | R1.8, R2.1, R7.1, R8.1 | the upgrade cases in the matrix row |
| T11 | R1–R7 | the manual procedure, one step per requirement, in `evidence/manual.md` |
| T12 | R8 | `make check` green, which includes the docs pins |

## Verification environment

- **Repositories:** this repository only, at the PR's head.
- **Services / containers:** none for T1–T10, T12: every Slack call goes through the fake
  client the channel tests already inject (`client_factory`), every ledger write through
  the fake writer (`post_comment`), and every session delivery through the injected
  `deliver`. For T11 a Slack workspace with the app re-imported from the shipped manifest
  and re-installed, one public channel declared as a room, and a running
  `the-loop start` with `read.mode: socket`.
- **Fixtures & data:** Slack payload shapes for `app_mention`, `message_action` and
  `view_submission` checked in as fixtures under `cli/tests/fixtures/slack/`; a
  pre-change declaration, roster entry and channel state file for T10.
- **Credentials:** **by reference only** — `THE_LOOP_SLACK_BOT_TOKEN` and
  `THE_LOOP_SLACK_APP_TOKEN` for T11 (the names `channels.slack.botTokenEnv` /
  `appTokenEnv` default to), and the operator's `gh` login for the ledger. None is
  written anywhere in this spec or in evidence.
- **Bring-up:** `cd cli && uv sync` · T11: `the-loop start` in a scratch config ·
  **Tear-down:** `the-loop stop`; the scratch room and issue are deleted after the
  evidence is captured.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate — do not pass the gate on an environment that
  never came up.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1 | test summary (counts, duration) | `unit.md` |
| T2 | `the-loop scenarios --glob 'cli/tests/test_*_integration.py' --format markdown` table + run output | `integration.md` |
| T6 | run output; the modal view JSON as committed | `snapshot.md` |
| T8 | run output, one section per abuse case | `security.md` |
| T10 | run output; the pre-change fixtures named | `upgrade.md` |
| T11 | the procedure with one section per step and its outcome; redacted screenshots of the room message, the ticket record, `context.md`, the modal and the decision file; an animated capture of the shortcut → modal → record flow | `manual.md`, `ui/*.png`, `ui/decision-shortcut.gif` |
| T12 | `make check` output | `checks.md` |

Redaction before commit: member ids, workspace URLs and channel ids in screenshots and
captured payloads are masked; a capture that cannot be redacted is described in the
results row instead of committed.

## Verification activities

- [ ] T1 — `cd cli && uv run python -m pytest -q tests/test_channels_mentions.py tests/test_channels_verbs.py tests/test_collaborators.py tests/test_workchannels.py tests/test_channels.py`
- [ ] T2 — `cd cli && uv run python -m pytest -q tests/test_channels_mentions_integration.py tests/test_channels_shortcuts_integration.py tests/test_collaborators_cli.py tests/test_workchannels_cli.py tests/test_channels_records_integration.py`
- [ ] T6 — `cd cli && uv run python -m pytest -q tests/test_channels_commands.py tests/test_channels_dm.py tests/test_channels_shortcuts.py`
- [ ] T8 — `cd cli && uv run python -m pytest -q tests/test_channels_mentions_security.py`
- [ ] T10 — `cd cli && uv run python -m pytest -q tests/test_channels_upgrade.py tests/test_config_schema_parity.py tests/test_docs_parity.py tests/test_graph_parity.py tests/test_bus.py`
- [ ] T11 — the manual procedure in `evidence/manual.md`, against the workspace named by the credentials above
- [ ] T12 — `make check`

## Verification results

_Not yet executed._

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |

**Not executed:** —

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
