---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#242"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: the-loop diagnoses its own failures and files the bug itself

> Derived from `requirements.md` and `design.md`, **before** `tasks.md` — each task's
> `_Test:_` names a row below. Authored at `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the pure core: candidate policy, fingerprint normalization, dossier allow-list + caps, scrubber masks, keyword defang, config parsing, rate cap and retry/abandon arithmetic | `uv run --project cli python -m pytest cli/tests/test_selfdiagnosis.py cli/tests/test_redact.py` |
| T2 | Integration (scenario) | yes | the whole pipeline end-to-end through fake subprocess seams: an error record in a real log file → dossier → fake agent envelope → composed body → fake `gh` argv; Gherkin-documented | `uv run --project cli python -m pytest cli/tests/test_selfdiagnosis_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API route is added; `the-loop diagnose` is CLI-only (requirements § Out of scope) | | |
| T4 | End-to-end (real agent + real GitHub) | n/a — needs a live harness binary and write access to a real repository; the subprocess boundary is exercised with fakes in T2 and the argv is asserted byte-for-byte, which is what a live run would consume | | |
| T5 | UI / visual | n/a — no user-facing surface beyond CLI text | | |
| T6 | Snapshot | n/a — the state file is asserted structurally in T1/T2; no serialised artefact needs byte-stability | | |
| T7 | Performance / load | n/a — a scan is one bounded file read; the agent runs at most once per new fingerprint, capped daily | | |
| T8 | Security / abuse case | yes | the redaction and no-arming contracts: paths/usernames/hostnames/emails/tokens masked; fields off the allow-list (work_item, cwd, tmux_target) never reach a body; control keywords defanged so `parse_command` finds nothing; the marker present; no auto-execute label in the `gh` argv; disabled config runs nothing | `uv run --project cli python -m pytest cli/tests/test_selfdiagnosis.py cli/tests/test_redact.py cli/tests/test_selfdiagnosis_integration.py -k "redact or defang or arm or disabled or allow"` |
| T9 | Accessibility | n/a — no user-facing surface | | |
| T10 | Migration / upgrade | n/a — the config section and state file are both new and optional; an older config (no section) means disabled, asserted in T1; nothing existing changes shape | | |
| T11 | Manual exploratory | yes | `the-loop diagnose --dry-run` against this repo's own event log: the printed report is read by a human for redaction quality — the one judgement a fixture cannot make | run locally; outcome + (redacted) output recorded in evidence |
| T12 | Whole-suite regression | yes | the daemons' wiring changes break nothing; docs/schema parity gates (P1–P5, schema byte-parity, configschema keyword guard) pass with the new section, command and event types | `make test` (or `uv run --project cli python -m pytest cli/tests`) |
| T13 | Lint / format / types | yes | the repo's own gates | `make lint`, `make format-check`, `make typecheck` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.3 | error-level and `will_retry: false` records are candidates; `diagnosis.*` and plain info records are not |
| T1 | R1.2 | three retries of one defect, differing only in digits/paths/ids, are one fingerprint |
| T1 | R2.1, R2.3 | absent section and `enabled: false` parse to disabled; `from_mapping` defaults match the schema |
| T1 | R3.3 | attempts count up per failure; the fingerprint moves to `abandoned` at `maxRetries` and is never retried |
| T1 | R4.1 | a record with extra fields (work_item, cwd, tmux_target, a future unknown) yields a dossier containing none of them |
| T1 | R4.2 | scrub masks home dir, username, hostname, absolute paths, `~` paths, e-mails, hex/base64 tokens, sensitive env values |
| T1 | R5.4 | the fourth candidate in a rolling day is deferred, and posts once the window rolls |
| T1 | R6.2 | a body containing `the-loop start` (and each configured keyword) defangs so `control.parse_command` returns nothing |
| T2 | R1.1, R3.1–4, R4.3, R5.1–3 | `Scenario: A harness failure in the event log becomes one redacted, labeled issue` — end-to-end with fake agent + fake gh |
| T2 | R1.5, R2.2 | `Scenario: A dry run prints the redacted report and posts nothing` |
| T2 | R1.6 | `Scenario: A second concurrent scan is skipped while the lock is held` |
| T2 | R1.4 | `Scenario: The watcher thread scans on its interval and stops with its daemon` |
| T8 | R6.1, R6.3 | the `gh` argv carries only the configured label — never `routing.autoExecuteLabel`; the body parses as self-authored and carries no control command |
| T8 | R2.1 | with the feature disabled, `start_watcher` returns None and `scan` is never reached from the daemons |
| T11 | R4 (judgement) | a human reads the dry-run output of this repo's real log |
| T12 | all | full CLI suite + parity gates |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. T2 uses real temp files for the log and state;
  subprocess boundaries (`agent`, `gh`) are injected fakes returning
  `subprocess.CompletedProcess`.
- **Fixtures & data:** in-repo (`cli/tests/conftest.py` autouse hermetic eventlog;
  per-test `FakeRun` doubles, the house pattern from `test_comments.py`).
- **Credentials:** none. No test reaches GitHub or spawns a real harness.
- **Bring-up:** `uv sync` (implicit in `uv run`) · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8 | red-before/green-after runs of the new tests | `red.md`, `unit-and-integration.md` |
| T11 | the dry-run transcript, itself redacted | `dry-run.md` |
| T12 | full-suite output with counts | `unit-and-integration.md` |
| T13 | lint, format-check and typecheck output | `lint-and-typecheck.md` |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest cli/tests/test_selfdiagnosis.py cli/tests/test_redact.py`
- [x] T2 — `uv run --project cli python -m pytest cli/tests/test_selfdiagnosis_integration.py`
- [x] T8 — the `-k "redact or defang or arm or disabled or allow"` selection above
- [ ] T11 — `the-loop diagnose --dry-run` on this repo's log, human-read
- [x] T12 — `uv run --project cli python -m pytest cli/tests -q`
- [x] T13 — `make lint && make format-check && make typecheck`
- [x] Red-first — the new tests fail before the implementation exists

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| Red-first | run the three new test modules before the implementation exists | 3 modules fail at import — nothing they guard exists | [`red.md`](evidence/red.md) |
| T1 | `pytest cli/tests/test_selfdiagnosis.py cli/tests/test_redact.py` | 37 passed | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T2 | `pytest cli/tests/test_selfdiagnosis_integration.py` | 12 passed | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T8 | the `-k "redact or defang or arm or disabled or allow"` selection | 22 passed | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T11 | `the-loop diagnose --dry-run` on a seeded #240-style log with planted secrets, through the **real** `claude` one-shot | see [`dry-run.md`](evidence/dry-run.md) — no planted value survived redaction | [`dry-run.md`](evidence/dry-run.md) |
| T12 | `pytest cli/tests -q` | 2274 passed, 1 skipped | [`lint-and-typecheck.md`](evidence/lint-and-typecheck.md) |
| T13 | `make lint`, `make format-check`, `make typecheck` | clean | [`lint-and-typecheck.md`](evidence/lint-and-typecheck.md) |

**Not executed:** none. Every applicable row ran; T11 ran in a stronger form than
planned (a real agent one-shot rather than an agent-unavailable preview — see the
execution log).

## Review comments

*None yet.*
