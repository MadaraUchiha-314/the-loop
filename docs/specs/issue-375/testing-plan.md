---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#375"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: a work item names the room it is worked in

> Derived from `requirements.md` and `design.md`, **before** `tasks.md` — each task's
> `_Test:_` names a row of the matrix below. Authored at `test-planning`, completed at
> `verification`. See `reference/testing.md`.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. Nothing here needs credentials or the network: the Slack boundary is the
> injected client factory every channel test already uses, the GitHub boundary is the
> `post_comment` / `create_issue` seams the pipeline already takes, and the declarations
> are real files under `tmp_path`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the grammar: both spellings canonicalise to one, and a name, an unknown type, a lower-case id, a path fragment and an argv fragment are each refused with a reason (R1.2–R1.5, A1) | `cli/tests/test_workchannels.py` |
| T2 | Unit | yes | the store: a declaration carries its provenance; a second of one type replaces the first and says so; a held channel raises; remove and clear (R1.1, R1.6, R1.7, R3.4) | `cli/tests/test_workchannels.py` |
| T3 | Unit | yes | the reverse lookup: a room names its work item, a contested room names nobody, an unreadable entry declares nothing (R3.4, A2) | `cli/tests/test_workchannels.py` |
| T4 | Integration | yes | the CLI: `add-channel` writes and posts the keyword back marked as the-loop's own and re-parsing to the same command; the refusals exit 2 having written and posted nothing; `--no-comment`; a failing `gh` keeps the declaration (R1.9) | `cli/tests/test_workchannels_cli.py` |
| T5 | Integration | yes | outbound: with a declaration the thread root is opened in the declared room and the binding records it; `open` resolves the same home (R2.1) | `cli/tests/test_channels_declared_integration.py` |
| T6 | Integration | yes | outbound: a declaration made after the conversation started moves it — a root in the new room, `origin: declared`, a pointer in the thread it left, and the old thread unmapped (R1.8, R2.2) | `cli/tests/test_channels_declared_integration.py` |
| T7 | Integration | yes | inbound (socket): a top-level message in a declared room is recorded on that work item and delivered, and opens no issue — including when the declared room is the operator's own channel (R3.1) | `cli/tests/test_channels_declared_integration.py` |
| T8 | Integration | yes | inbound (socket): an unbound thread in the room reaches the work item; a **bound** thread in the room wins; an unauthorized member is still dropped; an undeclared room is still `unmapped`; a removed declaration goes quiet (R1.6, R3.2, R3.3, R3.5) | `cli/tests/test_channels_declared_integration.py` |
| T9 | Integration | yes | inbound (poll): a room is baselined on first sight and nothing is delivered from its backlog (R3.6, A6) | `cli/tests/test_channels_declared_integration.py` |
| T10 | Integration | yes | inbound (poll): a room message is processed exactly once across repeated cycles — the room cursor advances (R3.6) | `cli/tests/test_channels_declared_integration.py` |
| T11 | Regression | yes | a work item that declared nothing posts to the central channel and binds it, byte-identically to today; the kickoff still opens work items in an undeclared central channel (R2.3) | `cli/tests/test_channels_declared_integration.py`, `cli/tests/test_channels.py` (existing), `cli/tests/test_channels_kickoff*.py` (existing) |
| T12 | Unit | yes | the control vocabulary: the two keywords are declared like every other, carry the channel they named, match as whole tokens, and put nothing but a channel in `subjects`; the paper-trail comment spells a channel without an `@` prefix (R1.1, R1.3, A1) | `cli/tests/test_control.py` |
| T13 | Integration | yes | the dispatcher: an authorized comment declares and is acknowledged 🎉; a name, an unknown type and a held channel are each refused 😕 having written nothing; an unauthorized author declares nothing; two keywords in one body declare nothing (R1.1–R1.5, R3.4, A3) | `cli/tests/test_workchannels_integration.py` |
| T14 | Integration | yes | the dispatcher: declaring neither arms nor spawns — no session, no control record (R1.1) | `cli/tests/test_workchannels_integration.py` |
| T15 | Unit | yes | the gate: the section names what is declared or how to declare one, carries **no checkbox**, and the confirmation names the channels in both directions (R4.1–R4.3) | `cli/tests/test_selection_choices.py` |
| T16 | Regression | yes | the new portable section is classified, documented, cleared by `reset` and seen by the poller's tracked-item scan (R1.10) | `cli/tests/test_state_portability.py`, `cli/tests/test_reset.py` (existing) |
| T17 | Docs parity | yes | both commands have a page, both keywords have an option entry, the schema copies are byte-identical, and `docs/cli/state.md` describes the section (R5.1, R5.2) | `cli/tests/test_docs_parity.py`, `cli/tests/test_config_schema_parity.py`, `cli/tests/test_state_portability.py` |
| T18 | Performance | n/a | — the added work is one directory read per outbound post and per inbound message, on the same files the bindings already come from, and no path gained a network call | — |
| T19 | Contract (OpenAPI) | n/a | — no control-plane route is added: the two verbs run in-process, like `add-collaborator` (decision-102) | — |
| T20 | Manual / exploratory | yes | one real Slack workspace: declare a room on a live work item, confirm the root lands there, type in it, confirm the comment appears on the ticket and the session receives it | recorded in `evidence/final-validation.md` |

## Verification environment

`uv run --project cli python -m pytest -q cli` on the repository checkout — no network, no
Slack token, no `gh`. Every external boundary is an injected callable that the production
code already takes as a parameter; nothing here monkeypatches a private function.

## Evidence to capture

- the full suite's result, with the count, in `evidence/final-validation.md`;
- `make check` (lint, format, typecheck, config validation, tests) in the same file;
- the review records in `evidence/self-review.md` and `evidence/security-review.md`;
- what changed in the user-facing docs in `evidence/documentation.md`.

## Activities checklist

- [x] T1–T3 unit tests for the grammar, the store and the reverse lookup
- [x] T4 the CLI verbs
- [x] T5–T11 the Slack outbound and inbound paths, including the regressions
- [x] T12–T14 the control vocabulary and the dispatcher
- [x] T15 the gate
- [x] T16–T17 state portability and docs parity
- [ ] T20 manual validation in a real workspace (operator-run; not reproducible in CI)
