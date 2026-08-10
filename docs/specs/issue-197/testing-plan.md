---
type: testing-plan
phase: test-planning
workItem: issue-197
status: approved
approvedBy: []
overrides: {}
---

# Testing plan: the item's author gates spawning, and nothing else

> Derived from the approved `bugfix.md` and `design.md`, **before** `tasks.md` — each
> task's `_Test:_` names a row below. Authored at `test-planning`, completed at
> `verification`.
>
> **This file is executable content.** Every command in it runs offline against in-process
> doubles and a `tmp_path` control store: no credential appears here by value or by
> reference, and none is needed.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the three decisions of `_process_item` — forwarding, first-sight hold-back, presence arming — under every combination of item author and control record | `uv run --project cli python -m pytest -q cli/tests/test_poller.py` |
| T2 | Integration (scenario) | yes | a poll cycle end-to-end through the real `Dispatcher` control path: an authorized `the-loop contribute` on a stranger's item records the command and spawns | `uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API surface changes. `poll.unauthorized` is an event-log record, not a contract; `test_api_contract_parity.py` runs anyway inside T5. | | |
| T4 | Security / abuse case | yes | A1–A4 of `design.md` § Security design, each as a negative test | `uv run --project cli python -m pytest -q cli/tests/test_poller.py -k unauthorized or empty_allowlist or stop` |
| T5 | Regression (whole suite) | yes | the poll path feeds the dispatcher, the graph and the event log; nothing else may move from a 1731-passing baseline | `make test` |
| T6 | Prompt/template parity | yes | the bundled spawn template and the built-in fallback stay byte-identical, the interaction directive still precedes the untrusted block, and the new paragraph is present in both | `uv run --project cli python -m pytest -q cli/tests/test_interaction.py` |
| T7 | UI / visual | n/a — no user-facing surface; the only outputs are log lines, event-log records and a prompt, pinned by T1/T2/T6. | | |
| T8 | Snapshot | n/a — no serialized artifact whose whole shape is asserted. The one persisted record involved (`control`) is unchanged by this work item and is asserted field-by-field where it is read. | | |
| T9 | Performance / load | n/a — the change adds at most one `WorkItemStore` section read per item per cycle, for the same item the cycle already reads on the first-sight path, and removes work in the withheld case. Off any hot path. | | |
| T10 | Accessibility | n/a — no rendered UI. | | |
| T11 | Migration / upgrade | n/a — no persisted schema, config key or state-file shape changes. A ledger and a control record written by 9.5.1 are read identically; proved incidentally by T5, which reads fixture records from earlier versions. | | |
| T12 | Manual exploratory | n/a — the reproduction in `bugfix.md` needs a live GitHub repository, a second login and credentials. T2 reproduces the same sequence deterministically and offline against the real dispatcher, which is stronger evidence than one manual run. | | |
| T13 | Lint / typecheck / docs parity | yes | ruff, ruff-format, pyright, config validation and `test_docs_parity.py` over the changed docs | `make check` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1 | an authorized user's ordinary comment on a stranger-authored item, with a session live, is forwarded |
| T1 | R1.2 | on the same item, an unauthorized user's comment and a self-marked comment are baselined, not forwarded |
| T1 | R1.3 | first sight of a stranger-authored item whose thread carries an authorized `the-loop contribute`: the comment is held back from the baseline and forwarded on that cycle |
| T1 | R1.3 | the same first sight with the command from an **unauthorized** author: baselined, nothing forwarded (issue-119's own rule, unchanged) |
| T1 | R1.4 | empty `authorizedUsers`: nothing forwarded, nothing spawned, whoever authored what |
| T1 | R2.1 | stranger-authored item, no control record: no presence event (the pre-existing test, kept) |
| T1 | R2.2 | stranger-authored item with a recorded `start`: presence armed, one spawn |
| T1 | R2.3 | stranger-authored item whose last recorded command is `stop`: no presence |
| T1 | R2.4 | stranger-authored item with a live session: comments delivered, no second spawn |
| T1 | R3.1 | `poll.unauthorized` is emitted, with the item's author as actor, when the guard withholds a spawn |
| T1 | R3.2 | no `poll.unauthorized` once the item is armed |
| T2 | R1.1, R1.3, R2.2 | `Scenario: a maintainer starts the-loop on an outside contributor's issue` — one cycle forwards the command through the real dispatcher, which records it and spawns |
| T2 | R1.2 | `Scenario: an outside contributor cannot start the-loop on their own issue` — the same cycle, the command coming from the item's own author |
| T4 | A1, A2, A3, A4 | the four abuse cases, run as their own selection |
| T6 | R4.1, R4.2, R4.3 | the untrusted-work-item paragraph is in both copies, and precedes `$payload_excerpt` |
| T5 | all | the 1731-passing baseline must not regress |

## Verification environment

- **Repositories:** this one only (`MadaraUchiha-314/the-loop`), at the work item's branch.
- **Toolchain:** `uv` (the declared package manager), Python as pinned in `uv.lock`,
  `pytest`, `ruff`, `pyright`, `markdownlint-cli2` — all reached through `make`, which is
  what CI runs.
- **Network / credentials:** none. Every test uses in-process doubles (`FakeProvider`,
  `RecordingDispatcher` or a real `Dispatcher` with a stub harness) and a `tmp_path`
  state root. No `gh`, no tokens, no live repository.

## Evidence plan

Committed under `docs/specs/issue-197/evidence/`:

- `make-check.txt` — the full gate (lint, format, typecheck, validate, test).
- `red-before-fix.txt` — the new and rewritten tests run against the pre-fix source, to
  prove red→green rather than assert it.

Nothing captured here contains a token, a hostname or personal data: the output is pytest
summaries and tool findings over this repository's own files.

## Verification activities

- [ ] T1 — unit tests, run and green
- [ ] T2 — integration scenario, run and green
- [ ] T4 — abuse cases, run and green
- [ ] T5 — whole suite, no regression against the 1731-passing baseline
- [ ] T6 — template parity, run and green
- [ ] T13 — `make check` green
- [ ] Red→green evidence captured for every new/rewritten test
- [ ] Evidence committed and redaction-checked

## Verification results

_(Filled in at `verification`, with the exact command, the outcome and a link to the
committed evidence for every row above.)_

## Review comments

_(PR review findings on this plan and their resolutions are recorded here.)_
