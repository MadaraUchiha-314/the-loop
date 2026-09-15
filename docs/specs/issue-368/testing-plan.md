---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#368"
status: approved             # draft | in-review | approved
approvedBy: ["@MadaraUchiha-314"]
overrides: {}
---

# Testing plan: one rule for where a work item's attributes live

> Derived from `requirements.md` and `design.md`, **before** `tasks.md` — each task's
> `_Test:_` names a row of the matrix below. Authored at `test-planning`, completed at
> `verification`. See `reference/testing.md`.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. Nothing here needs credentials or the network: every row is a filesystem
> read through the stores, the dispatcher with a fake provider, or the Slack transport
> with a fake client — the fixtures the suite already uses.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (parity) | yes | the `ATTRIBUTES` table names every top-level key each of the three writers produces, every kind sits in a file the rule allows, and `docs/cli/state.md`'s attribute table matches it (R1.1, R1.5, R9.1) | `uv run --project cli python -m pytest -q cli/tests/test_state_portability.py` |
| T2 | Unit | yes | `WorkItemState` v2: `sessionPerPr`, `model`, `effort`, `pullRequests[]` round-trip; `link_pr` is idempotent by ref; `set_pr_state` updates one entry; a bad `repository` or `ref` entry is skipped, the rest honoured (R2.1, R2.2, R4.1) | `uv run --project cli python -m pytest -q cli/tests/test_graph_state.py` |
| T3 | Unit | yes | a v1 file with a `session` block loads without it, the next save writes no `session`, and `resolve_session` never returns the checked-in id (R3.1, R3.3; abuse case 4) | `uv run --project cli python -m pytest -q cli/tests/test_graph_state.py cli/tests/test_graph_runtime.py -k session` |
| T4 | Unit | yes | `resolve_session` inherits the registry's live endpoint for the work item, and the PR endpoint for an inner loop; no registry → `fresh-with-artifacts` (R3.2) | `uv run --project cli python -m pytest -q cli/tests/test_graph_runtime.py -k inherit` |
| T5 | Integration | yes | the first routed event for a PR, and `sessions link-pr`, each write the local endpoint **and** the repository entry with `linkedBy`; a second call writes nothing; the entry alone never spawns (R2.1, R2.4; abuse case 3) | `uv run --project cli python -m pytest -q cli/tests/test_routing.py cli/tests/test_core_lifecycle.py -k link` |
| T6 | Integration | yes | `pull_request.closed` (merged and not) sets `pullRequests[].state` in the checkout and closes the endpoint; the work item's session runs on (R2.2) | `uv run --project cli python -m pytest -q cli/tests/test_routing.py -k closed` |
| T7 | Integration | yes | the Slack transport binds into the portable record, reads cursors from the local record, resolves `thread_ts` through the in-memory index, and never opens a second root for a bound work item; a post into an unjoinable thread is a `ChannelError` (R2.3, R5.1, R5.3; abuse case 6) | `uv run --project cli python -m pytest -q cli/tests/test_channels_slack_integration.py` |
| T8 | Integration | yes | a pre-change `channels/slack.json` binding is honoured until the work item's next write records it in the portable record; `pending` and `channel:*` cursors survive the rewrite (R5.4, R8.1) | `uv run --project cli python -m pytest -q cli/tests/test_channels_state.py -k legacy` |
| T9 | Security / abuse case | yes | the dispatcher reads `sessionPerPr`/`model`/`effort` from the checkout: an undeclared or refused model launches on the harness's own arguments and records the refusal; a fourth mode routes by the default; an unreadable file routes by the default (R4.3; abuse cases 1–2) | `uv run --project cli python -m pytest -q cli/tests/test_routing.py -k choices` |
| T10 | Integration | yes | a work item frozen before the change — keys absent in the state file, `graph` present in the portable record — routes by the portable copy, which is not rewritten; a work item frozen after it never writes `graph` (R4.2, R4.4, R8.1) | `uv run --project cli python -m pytest -q cli/tests/test_routing.py cli/tests/test_workitem.py -k frozen` |
| T11 | Unit | yes | `WorkItemStore.SECTIONS` drops `graph` and gains `channels`; `index.json.sections` follows; a record carrying only `channels` is kept, not dropped (R8.3) | `uv run --project cli python -m pytest -q cli/tests/test_workitem.py cli/tests/test_portable_index.py` |
| T12 | Unit | yes | `Session` round-trips `channels.slack.cursors`, absent rather than empty; a v2 record round-trips byte-identically (R5.1, R8.1) | `uv run --project cli python -m pytest -q cli/tests/test_state.py -k registry` |
| T13 | End-to-end (scenario) | yes | **the hand-off**: with the example work item (three PRs, three PR sessions, one thread), copy `docs/specs/` and `portable/` to a fresh state root; the daemon lists the three pull requests, routes a PR event to a fresh spawn without asking `gh`, and posts into the existing thread (R2.1–R2.3) | `uv run --project cli python -m pytest -q cli/tests/test_state_root_integration.py -k handoff` |
| T14 | Unit | yes | `cleanup` and `reset` keep their documented effect on each file: cleanup deletes the local record (cursors with it) and leaves `channels` in the portable record; reset clears the portable sections including `channels` (R7.2) | `uv run --project cli python -m pytest -q cli/tests/test_core_lifecycle.py -k "cleanup or reset"` |
| T15 | Documentation parity | yes | `docs/cli/state.md` classifies every file and attribute as the code does; `upgrade-the-loop` reports the three retired locations; no shipped doc still describes `graph` in the portable record or `session` in the state file (R8.2, R9.1, R9.2) | `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py cli/tests/test_writing_parity.py` + repository grep |
| T16 | Contract (OpenAPI) | n/a — `POST /api/v1/sessions/link-pr` keeps its request and response shape; the served schema is unchanged | | |
| T17 | UI / visual | n/a — the board changes only in where `nodes[]` comes from; no rendered surface changes | | |
| T18 | Snapshot | n/a — the JSON shapes are asserted field by field in T2, T11 and T12 | | |
| T19 | Performance / load | n/a — amended in implementation (design D6): the thread → work item index is **derived on each load** rather than cached at listener start, because the daemon and the listener are separate processes and a cached index would miss the other's bind. The cost is a scan of a handful of small local files per operation; there is no cache to measure | | |
| T20 | Accessibility | n/a — no rendered UI | | |
| T21 | Manual exploratory | n/a — this work item's own loop is the exploratory pass: this spec directory's state file, once the runtime writes it, carries no `session` block | | |
| T22 | Repository gates | yes | what CI runs: ruff, ruff format, pyright, config validation, the full suite, markdownlint over every `**/*.md` | `make check` |
| T23 | Integration | yes | one portable record per work item: a labelled PR the poller lists is ledgered under its owner (resolved through the registry, the portable maps, then the router's linkage); a PR with no owner keeps its own record; on merge the nested ledger is dropped and no `ended` is stamped on the PR; a pre-change PR record is read until the owner carries the ledger, then ignored, never deleted (R10.1–R10.4, R10.6) | `uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py cli/tests/test_workitem.py -k owner` |
| T25 | Unit | yes | a cursor with no session record to live in stays in the channel file, and a standing session's binding stays there (design D11, D12) | `uv run --project cli python -m pytest -q cli/tests/test_channels.py -k cursor` |
| T24 | Unit | yes | the local record is `sessions{ref → handles}`: a v1 file with top-level handles and `pullRequests[]` loads into the map and is rewritten as v2; no PR field but the ref survives; `record_owning`, `session_for`, `link_pull_request`, `close_endpoint` and `touch` behave as before against the map (R5.1, R8.1) | `uv run --project cli python -m pytest -q cli/tests/test_state.py -k sessions` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.5 | adding a key to `WorkItemState.as_dict` without an `ATTRIBUTES` entry fails; putting a `machine` kind under the repository file fails |
| T2 | R2.1, R2.2 | three PRs linked in order → three entries; re-link `octo/lib#7` → still three; `set_pr_state("github:octo/infra#3", "merged")` → one entry changed |
| T3 | R3.1, R3.3 | `{"session": {"id": "S0", "alive": true}}` on disk → `state.session` absent, `resolve_session` → `fresh-with-artifacts` when the registry has nothing, the resaved file has no `session` |
| T4 | R3.2 | registry has a live record → `("inherited", {id: harnessSessionId})`; PR endpoint live → its id for the inner loop |
| T5 | R2.1, R2.4 | first `pull_request.opened` for `octo/lib#7` → local endpoint + repository entry `linkedBy: event`; `link-pr` from the session → `linkedBy: session`; a state file listing a PR no event ever touched spawns nothing |
| T6 | R2.2 | `closed` with `merged: true` → `state: merged`; without → `closed`; the record's own session stays `active` |
| T7 | R2.3, R5.1, R5.3 | first event → root posted, binding in `portable/…channels.slack`, cursor in `local/…channels.slack.cursors`; second event → reply in that thread; `thread_ts` lookup resolves the work item with no file read |
| T8 | R5.4 | old `slack.json` binds `1726…001` → the first event for `#15` replies there and the portable record now carries the binding; `pending` intact |
| T9 | R4.3 | `model: "gpt-9"` (undeclared) → launched without `--model`, `session.model_refused` emitted; `sessionPerPr: "sometimes"` → operator's default |
| T10 | R4.2, R4.4 | portable `graph.sessionPerPr: always` + state file without the key → PR gets its own session; portable file unchanged after; a fresh freeze → no `graph` written |
| T13 | R2.1–R2.3 | the design's worked example, before → after, on two state roots |
| T25 | R5.1 (D11) | a work item with a bound thread and no session record here keeps its cursor in the channel file; a standing session's binding stays there too (D12) |
| T14 | R7.2 | after `cleanup`: `local/<slug>.json` gone, `portable/<slug>.json.channels` present; after `reset`: `channels` gone with the other sections |
| T23 | R10.1–R10.6 | poll lists `octo/lib#7` closing `#15` → `portable/…app-15.json.pullRequests["github:octo/lib#7"]` written, no `…lib-7.json`; a review PR with no owner → its own record; `pull_request.closed` merged → nested ledger dropped, `pullRequests[].state: merged` in the checkout, no `ended` on a PR record; an old `…lib-7.json` beside an owner that lacks the key → read once, then the owner carries it and the old file is untouched; `index.json` lists one entry naming three refs |
| T24 | R5.1 | v1 record with `pullRequests: [{workItem: {ref, owner, repo, number}, url, …}]` → `sessions["github:octo/lib#7"]` holds only handles; the resaved file has no `url`, `owner`, `repo` or `number` under any session |

## Verification environment

One checkout of this repository, Python via `uv` (workspace pinned by `uv.lock`), Node
for `markdownlint-cli2` through `npx`. No network beyond package resolution, no
credentials, no `claude`/`cursor-agent` binary, no Slack: the transport tests use the
suite's fake client and the routing tests the fake provider.

## Evidence plan

This work item has a testing plan, so the executed rows are recorded below at
`verification`. The security round goes to `evidence/security-review.md` (tier 4 —
a named human signs it), the acceptance summary to `evidence/final-validation.md`, the
docs touched to `evidence/documentation.md`, and the pull requests to
`evidence/pull-requests.md`. Command output is summarised; the commands above are
reproducible.

## Verification results

| Row | What was verified | Command | Outcome | Evidence |
|-----|-------------------|---------|---------|----------|
| T1 | the rule is data, every key is classified, no machine handle sits in a tracked file, and the page matches the code | `… -q cli/tests/test_state_portability.py` | pass (12) | four new assertions (S6–S10); S10 was red until `docs/cli/state.md` carried the attribute tables |
| T2 | `work-item-state.json` v2: the choices and the pull requests round-trip, `link_pr` is idempotent, `set_pr_state` updates one entry, a bad entry is skipped | `… -q cli/tests/test_graph_state.py` | pass (22) | eight new cases, including the two abuse cases on `repository` and `stateDir` |
| T3 | a legacy `session` block is never read and never rewritten | `… -q cli/tests/test_graph_state.py cli/tests/test_graph_drive.py -k session` | pass | red first: the old tests asserted the block was written |
| T4 | `session: inherit` inherits the registry's live session, and falls back with no registry | `… -q cli/tests/test_graph_drive.py -k gate_entry` | pass (23 in file) | the fallback case is new — it is what CI gets |
| T5 | a routed event and `sessions link-pr` each write the local endpoint and the repository entry | `… -q cli/tests/test_routing.py cli/tests/test_core_lifecycle.py` | pass (196, 19) | |
| T6 | a closing pull request records its upstream state and drops its ledger | `… -q cli/tests/test_routing.py -k closed` | pass | |
| T7 | the binding lands in the portable record, the cursor in the session record, and a second machine continues the conversation | `… -q cli/tests/test_channels.py` | pass (106) | four new cases; the second-machine one is the property the move buys |
| T8 | a pre-change binding is honoured and **moved** on the next write | `… -q cli/tests/test_channels_integration.py -k pre_issue_312` | pass | rewritten: the file stops carrying bindings, so a binding left only there would be lost |
| T9 | an undeclared model and a fourth `sessionPerPr` mode buy nothing | `… -q cli/tests/test_dispatcher_choice.py` | pass (22) | seven new cases |
| T10 | a work item frozen before the change routes by its portable copy, which is not rewritten | `… -q cli/tests/test_dispatcher_choice.py -k frozen` | pass | |
| T11 | the sections, `owner_of`, and the index naming each record's pull requests | `… -q cli/tests/test_workitem.py cli/tests/test_portable_index.py` | pass (20, 18) | four new cases |
| T12 | the registry round-trips the cursors and a v2 record | `… -q cli/tests/test_state.py` | pass (9) | |
| T13 | **the hand-off**: the branch and `portable/` carry the three pull requests, the choices, the arming, the roster and the thread; no handle travels | `… -q cli/tests/test_state_root_integration.py` | pass (13) | the design's worked example, executed |
| T14 | cleanup and reset keep their documented effect, now including `channels` and `pullRequests` | `… -q cli/tests/test_reset.py cli/tests/test_cleanup.py cli/tests/test_core_lifecycle.py` | pass | |
| T15 | the page, the capability docs and the upgrade report agree with the code | `… -q cli/tests/test_docs_parity.py cli/tests/test_writing_parity.py` | pass (16) | plus T1's S10 |
| T22 | what CI runs | `make check` equivalents: `ruff check`, `ruff format --check`, `pyright`, `validate_config.py`, the suite, `markdownlint-cli2 "**/*.md"` | pass | ruff clean; 304 files formatted; pyright **0 errors**; both configs valid; **3711 passed, 1 skipped**; markdownlint 0 errors |
| T23 | one portable record per work item; a PR with no owner keeps its own; an already-ledgered owner wins | `… -q cli/tests/test_poller.py -k "ledger or owner or delivers"` | pass (225 in file) | three new cases |
| T24 | the local record is a map of sessions keyed by ref, and a v1 record is rewritten as one | `… -q cli/tests/test_state.py -k sessions` | pass | the leak assertion names each field that must not be there |
| T25 | a cursor with no session record here, and a standing session's binding, stay in the channel file | `… -q cli/tests/test_channels.py -k "cursor or standing"` | pass (6) | both found in implementation (design D11, D12) |

Rows T16–T21 were declared `n/a` with their reasons in the matrix above and were not
executed. T19 became `n/a` during implementation, for the reason recorded there and in
design D6.
