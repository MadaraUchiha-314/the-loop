---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#242"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Tasks: the-loop diagnoses its own failures and files the bug itself

> The last spec artifact. A DAG derived from the design and testing plan.

## Task list

- [x] 1. Write the failing tests for the pure core (redact + selfdiagnosis units)
  - Scrubber masks (home, username, hostname, paths, e-mails, tokens, sensitive env
    values); keyword defang defeats `control.parse_command`; candidate policy;
    fingerprint normalization; dossier allow-list drops unknown and known-sensitive
    fields; config parsing (absent/false/invalid → disabled or refusal); retry/abandon
    and rolling-day-cap arithmetic.
  - _Depends on:_ none
  - _Requirements:_ R1.1–3, R2.1, R3.3, R4.1–2, R5.4, R6.2
  - _Test:_ `T1`, `T8` (red)

- [x] 2. Write the failing integration scenarios (pipeline + watcher + verb)
  - End-to-end with fake agent and fake `gh`: log record → labeled issue argv; dry run
    prints and posts nothing; concurrent scan skipped under the lock; watcher scans on
    interval and stops with its daemon; no-arming assertions on the composed body and
    argv. Gherkin docstrings with `Requirement:` links.
  - _Depends on:_ none
  - _Requirements:_ R1.4–6, R2.2, R3.1–4, R4.3, R5.1–3, R6.1, R6.3
  - _Test:_ `T2`, `T8` (red)

- [x] 3. Capture the red run as evidence
  - _Depends on:_ 1, 2
  - _Requirements:_ (process — `tdd.mode: standard`)
  - _Test:_ `evidence/red.md`

- [x] 4. `redact.py` — the scrubber and the keyword defang
  - _Depends on:_ 3
  - _Requirements:_ R4.2, R6.2
  - _Test:_ `T1` (green: `test_redact.py`)

- [x] 5. `core/selfdiagnosis.py` — policy, fingerprint, dossier, state, compose, post
  - Everything up to but excluding the thread: `SelfDiagnosisConfig.from_mapping`,
    `_is_candidate`, `fingerprint`, `_dossier`, the synthetic-`Critic` agent run,
    `_compose`, `_create_issue` (comments.py contract), the state file with flock and
    atomic replace, `scan()` with dedup/retry/abandon/rate-cap.
  - _Depends on:_ 4
  - _Requirements:_ R1.1–3, R1.6, R3, R4, R5, R6.1–2
  - _Test:_ `T1`, `T2`, `T8` (green)

- [x] 6. `start_watcher` + the two daemon wiring points
  - Daemon thread on `stop_event.wait(interval)`; `poller/daemon.py _run_locked` and
    `webhook/daemon.py build_receiver`/`cleanup` start and stop it; `None` when
    disabled.
  - _Depends on:_ 5
  - _Requirements:_ R1.4, R2.1
  - _Test:_ `T2 -k watcher`, `T8 -k disabled` (green)

- [x] 7. `the-loop diagnose` command
  - `commands/diagnose_cmd.py` + registration import; `--dry-run` works while
    disabled; refusal names the config key; page under `docs/cli/commands/diagnose.md`
    (P1/P2 gate).
  - _Depends on:_ 5
  - _Requirements:_ R1.5, R2.2
  - _Test:_ `T2 -k dry_run`, `T12` (docs parity)

- [x] 8. The `selfDiagnosis` config section, both schema copies, dogfood yaml, docs
  - `.the-loop/cli-config.schema.json` + byte-copy `cli/the_loop/schemas/…`;
    `.the-loop/cli-config.yaml` block (enabled: false, commented); config reference
    page `docs/config/cli/self-diagnosis-options.md` (P3/P4/P5 gates).
  - _Depends on:_ 5
  - _Requirements:_ R2.1, R2.3
  - _Test:_ `T12` (schema parity, configschema guard, docs parity)

- [x] 9. Event types, state registry, observability reference
  - `eventlog.EVENT_TYPES` += `diagnosis.detected|posted|deferred|failed`;
    `state.GENERATED_PATHS` += the self-diagnosis state file;
    `skills/the-loop/reference/observability.md` mirrors the new types;
    `docs/cli/state.md` if it enumerates the layout.
  - _Depends on:_ 5
  - _Requirements:_ NFR (observability, state locality)
  - _Test:_ `T12`

- [x] 10. Run the full suite and the repo's own gates
  - _Depends on:_ 6, 7, 8, 9
  - _Requirements:_ all
  - _Test:_ `T12`, `T13`

- [x] 11. Manual dry run on this repo's own log, human-read for redaction quality
  - _Depends on:_ 10
  - _Requirements:_ R4 (judgement)
  - _Test:_ `T11` → `evidence/dry-run.md`

- [x] 12. Capability doc, decision record, user-facing docs
  - New `docs/capabilities/self-diagnosis.md` + index row; `decision-090` (opt-in
    self-diagnosis: detection over the event log, allow-list redaction, never-armed
    issues), indexed in `decisions.md`; README/docs-site touchpoint if the change makes
    either wrong; execution log `## Capability docs` + `## Documentation`.
  - _Depends on:_ 10
  - _Requirements:_ R1–R6 (the record of them)
  - _Test:_ `T12 — pytest cli/tests/test_docs_parity.py`, `T13`
