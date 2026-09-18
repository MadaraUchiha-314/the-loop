---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#378"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: a work item's whole life is told to every channel, and Slack can begin one

> Derived from `requirements.md` and `design.md`, **before** `tasks.md` — each task's
> `_Test:_` names a row of the matrix below. Authored at `test-planning`, completed at
> `verification`. See `reference/testing.md`.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. Nothing here needs credentials or the network: Slack is the fake client every
> channel test already uses, GitHub is the `post_comment` / `create_issue` seams, and the
> runtime walks a compiled in-test graph on `tmp_path`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the catalog: the three lifecycle rows are subscribable, not publishable, not recorded; `LIFECYCLE_EVENTS` names exactly them; the docs table lists them (R1.6, R3.4, R7.1) | `cli/tests/test_bus.py`, `cli/tests/test_channels.py` (existing docs pin) |
| T2 | Unit | yes | the publisher: no `channels` section publishes nothing and builds no event; a raising bus never escapes; `record` is forced off; the reloadable form reads the getter per call (R1.7, R6.1) | `cli/tests/test_bus.py` |
| T3 | Unit | yes | the runtime, through a fake subscriber: `start` publishes `phase.started` for the first phase; an edge into a different phase publishes `completed` then `started` with outcome/to; two nodes sharing a phase publish nothing between them; an approval node without a phase inherits its author's; a terminal node completes; `cleanup` starts with `from`; `force` publishes nothing; a human node says it waits on a person (R1.1–R1.5, R2.2) | `cli/tests/test_graph_lifecycle.py` |
| T4 | Regression | yes | every existing runtime, graph, cleanup and hook suite passes unmodified — a config with no `channels` publishes nothing (R1.7) | `cli/tests/test_graph_*.py` |
| T5 | Parity | yes | every `actor: human` node of the outer loop carries a phase or a `notify` hook on its entry chain (R2.1) | `cli/tests/test_graph_lifecycle.py` |
| T6 | Integration | yes | the dispatcher: an `issues/closed` for a tracked work item publishes `work-item.closed` with state/reason/actor **before** the declaration is cleared (the fake channel still sees the room); a merged PR that is the work item publishes `merged`; a delivering PR's end publishes nothing; a dispatcher without a publisher publishes nothing (R3.1–R3.5, A7) | `cli/tests/test_lifecycle_integration.py` |
| T7 | Integration | yes | `/the-loop new o/r: title` — authorized, granted — creates the issue through the ledger with the declared slug and labels, opens the thread in the home channel with `origin: kickoff`, replies with the link and the Start button, answers ephemerally with the link (R4.1, R4.2) | `cli/tests/test_channels_commands.py` |
| T8 | Integration | yes | `/the-loop new` refusals: no prefix and no `kickoff.repo`, an unknown qualified prefix, an ambiguous bare prefix, a prefix and nothing else, an empty text — each answered with the kickoff's refusal text and nothing created; without the grant, refused and named; an unlisted member dropped before parsing; a duplicate trigger dropped (R4.3–R4.5, A1–A4) | `cli/tests/test_channels_commands.py` |
| T9 | Integration | yes | `/the-loop new` when the thread cannot be opened: the issue exists, the answer says so, nothing binds (R4.6) | `cli/tests/test_channels_commands.py` |
| T10 | Unit | yes | `usage()` and `help` name the verb and its grant (R4.5) | `cli/tests/test_channels_commands.py` |
| T11 | Integration | yes | a declared room: the first post opens the room as the conversation (one top-level message, record `thread: ""`, `mode: channel`) and the event is a top-level message; `open` is idempotent; a second event posts top-level and opens nothing (R5.1, R5.2, R5.7) | `cli/tests/test_channels_declared_integration.py` |
| T12 | Integration | yes | a thread bound in the central channel, then declared into a room: the room opens as a conversation, the old thread is told, and the old thread is unmapped (R5.4) | `cli/tests/test_channels_declared_integration.py` |
| T13 | Regression | yes | a work item with no declaration is byte-identical to today: root + reply in the central channel; a thread already bound inside a declared room keeps its shape (R5.3, R5.5) | `cli/tests/test_channels_declared_integration.py`, `cli/tests/test_channels*.py` (existing) |
| T14 | Unit | yes | the state: a record with `mode: channel` round-trips through the portable record, `conversation_for` answers `(channel, "")`, `thread_for` answers `None`, no thread-map entry is registered; a record without `mode` is a thread (R5.6) | `cli/tests/test_channels.py` |
| T15 | Integration | yes | inbound in a room conversation: a reply under one of the-loop's room messages reaches the work item (issue-375 R3.2 through the new shape) (R5.6, A8) | `cli/tests/test_channels_declared_integration.py` |
| T16 | Unit | yes | `channels threads` lists a room conversation with its mode; `channels status` counts it (R5.6) | `cli/tests/test_channels.py` |
| T17 | Unit | yes | the provider table: `load_channels` walks it; a registered fake provider is loaded beside Slack; a loader returning `None` contributes nothing; the fail-closed checks still precede the walk (R6.2) | `cli/tests/test_channels.py` |
| T18 | Integration | yes | a fake provider registered in the table receives `phase.started` from a runtime walk, with no Slack configured (R6.3) | `cli/tests/test_graph_lifecycle.py` |
| T19 | Unit | yes | the `notify` hook's skipped message names `channels.<name>.subscribe` (R6.4) | `cli/tests/test_bus.py` |
| T20 | Docs parity | yes | schema copies byte-identical; the docs table lists every subscribable event; `docs/config` pages state type and default (R7.1) | `cli/tests/test_config_schema_parity.py`, `cli/tests/test_channels.py`, `cli/tests/test_docs_parity.py` |
| T21 | Contract (OpenAPI) | n/a | — no control-plane route changes; the parity test compares paths and operationIds | — |
| T22 | Performance | n/a | — one bus publish per phase change, none without a `channels` section; no new call on any inbound path | — |
| T23 | Security / abuse | yes | A1–A4 in T8; A5 asserted by T3 and T6 (fixed words, no comment text in any lifecycle event); A6 by T1 (`is_recorded` false); A7 by T6's ordering; A9 by T12 (a record elsewhere is moved to the home) | as named |
| T24 | Manual / exploratory | yes | one real workspace: a channel subscribed to `phase.started`, `phase.completed`, `work-item.closed`; a work item run through `phase-selection` → `requirements-definition` and closed; a room declared; `/the-loop new` from a DM | recorded in `evidence/final-validation.md` |

## Verification environment

`uv run --project cli python -m pytest -q cli` on the repository checkout — no network, no
Slack token, no `gh`. Every external boundary is an injected callable the production code
already takes as a parameter.

## Evidence

- Red → green output for T3, T6, T7, T11 and T17 in `evidence/final-validation.md`.
- The full-suite run and `make check` in the same file.

## Activities

- [x] T1–T3 written red, then green
- [x] T5 pinned
- [x] T6–T10 written red, then green
- [x] T11–T16 written red, then green
- [x] T17–T19 written red, then green
- [x] T20 green after the docs
- [x] full suite and `make check`
- [x] T24 recorded (or its not-run stated with the reason)
