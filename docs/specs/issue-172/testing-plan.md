---
type: testing-plan
phase: test-planning
workItem: issue-172
status: approved              # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: proving the record survives what derivation does not

> Phase 3 of 4. Derived from the locked [`bugfix.md`](bugfix.md) and
> [`design.md`](design.md); revised with them after owner review on
> [PR #173](https://github.com/MadaraUchiha-314/the-loop/pull/173). Ticket:
> [issue #172](https://github.com/MadaraUchiha-314/the-loop/issues/172).
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. No credentials are involved: this work item makes no network call and reads no
> secret store.

## Test matrix

**The proof is a sequence, not a state.** A single event routing correctly proves nothing —
it already does today. What has to be shown is that the *second* event still lands after
the linkage the first one used has gone — now, into the PR's own recorded session.

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the store: `link_pull_request` records on the work item's record, is idempotent, refuses self; `record_owning`/`session_for` ordering (own record first, endpoint vs collapsed mode); `close_endpoint` leaves the record live; per-endpoint `touch`; per-entry degradation and one-level nesting; endpoints survive close/reopen | `uv run --directory cli pytest tests/test_routing.py` |
| T2 | Integration (scenario) | yes | **the ticket's reproduction**: a session registered against the issue, a PR event carrying the linkage (→ the PR's endpoint spawns under the issue's record), then a PR event carrying none — delivered into that endpoint, no record ever minted for the PR. Plus: spawn-path recording, the R2.3 both-records re-link case (collapsed mode), control-command resolution, and both close scenarios. Gherkin-documented | `uv run --directory cli pytest tests/test_webhook_routing_integration.py` |
| T2b | Integration (poll path) | yes | the same defect on the **poll** ingress: per-endpoint retry accounting (`done` for an id on the PR's endpoint; dedup does not leak between conversations) and first-sight detection treating a recorded PR as owned | `uv run --directory cli pytest tests/test_poller.py tests/test_routing.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API surface change; `sessions list --format json` returns the record verbatim, which now includes `pullRequests`, but the endpoint's schema is the record's own shape (additive field) | | |
| T4 | End-to-end | n/a — the shell-level path is unchanged; T2 drives the same receiver→router→dispatcher→tmux chain in-process | | |
| T5 | UI / visual | n/a — no product UI | | |
| T6 | Snapshot | n/a — the record's serialized shape is pinned by round-trip equality assertions in T1 | | |
| T7 | Performance / load | n/a — the added cost is one scan of live records for refs with no record of their own, and (by default) one harness process per active PR, which is a deliberate product behaviour, not overhead | | |
| T8 | Security / abuse case | yes | the boundaries `design.md` § Security design names: a hand-edited entry is skipped per entry and never fatal; a nested tree is flattened on read; a self-recording is refused; an unspawnable endpoint falls back to the record | `uv run --directory cli pytest tests/test_routing.py` |
| T10 | Migration / upgrade | yes | a record written before issue-172 (no `pullRequests` key) round-trips byte-identically and behaves identically; `sessions reset` removes the entries with the record (no new piece); `GENERATED_PATHS` unchanged | `uv run --directory cli pytest tests/test_reset.py tests/test_state_portability.py` |
| T12 | Unit + integration (the two loops) | yes | both graphs compile and are named; the inner loop skips the outer-only nodes and keeps `security-review` required; `await-inner-loops` (vacuous pass / wait naming pending PRs / corrupt state holds); `state_subpath` keeps inner state under `pr-loops/pr-<n>/` while artifacts resolve against the one spec chain; graphlink enters/advances the inner loop only, merge forces `complete` (audited), unmerged close leaves the pointer | `uv run --directory cli pytest tests/test_graph_loops.py` |
| T11 | Manual exploratory | yes | the failure the ticket describes, driven end to end against the un-fixed and fixed resolver, with the registry directory and record contents shown | § Verification results |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.3, R1.4, R1.5 | recorded on the work item's file; idempotent; self refused; readable by a fresh instance |
| T1 | R1.6 | an unparseable entry is skipped; a nested tree is flattened |
| T1 | R2.1, R2.2, R2.3 | endpoint preferred, collapsed mode collapses, own record wins over the scan |
| T1 | R2.4 | a closed endpoint falls back to the work item's session |
| T1, T2b | R2.7 | per-endpoint deliveries and dedup |
| T2 | R2.1, R5.1, R5.2 | `Scenario: A PR event still reaches its work item after the linkage is removed` |
| T2 | R1.1, R1.2 | recording on the delivery path and on the spawn path |
| T2 | R2.2, R2.3 | collapsed-mode delivery; a re-linked PR delivers to both records |
| T2 | R2.6 | `the-loop stop` on an unlinked PR stops the owning record |
| T2 | R3.1, R3.2 | a PR close ends its endpoint and keeps the record; a PR with its own record still auto-closes |
| T2b | R2.7 | poll retry accounting and first-sight detection through the record |
| T8 | R1.5, R1.6 | the abuse cases |
| T10 | R4.1, R4.2 | pre-issue-172 records unchanged; reset needs no new piece |
| T12 | R6.1–R6.4, R2.9 | the loops, the seam, the state split, the one-way flow, merge-as-forced-complete |
| P5 (parity) | R6.6 | the content-gate assertions hold over both shipped graphs |

## Verification environment

Nothing beyond this repository and its own toolchain. The change is a Python package plus
checked-in markdown and one JSON-schema entry.

- **Repositories:** this repo only.
- **Services / containers:** none. Integration tests drive a live receiver on
  `127.0.0.1` with an injected `FakeTmux` — no real tmux, no harness, no GitHub.
- **Fixtures & data:** none checked in; registries under pytest's `tmp_path`.
- **Credentials:** none.
- **Bring-up:** `uv sync --directory cli` · **Tear-down:** none.
- **If bring-up fails:** record it here, leave dependent activities unticked, escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T2b, T8, T10 | full `pytest` run — counts, the new tests named | `tests.md` |
| T2/T2b (negative) | the seven regression tests against the **unfixed** resolver | `tests.md` |
| T11 | the reproduction driven through the dispatcher, before and after, with the record's contents | `reproduction.md` |
| all | `ruff`, `pyright`, `markdownlint`, `validate_config.py` | `lint-and-types.md` |

Nothing captured can contain a token, a cookie, personal data or an internal hostname:
the outputs are pytest summaries, linter findings, and JSON holding `github:octo/repo#N`
refs, uuids and tmux names. Committed as markdown, as the rule requires.

## Verification activities

- [x] T1 — `uv run --directory cli pytest tests/test_routing.py -q`
- [x] T2 — `uv run --directory cli pytest tests/test_webhook_routing_integration.py -q`
- [x] T2b — `uv run --directory cli pytest tests/test_poller.py -q`
- [x] T2/T2b — all seven regression tests against the **unfixed** resolver (the check
      that the checks check something)
- [x] T8 — the abuse cases, in `tests/test_routing.py`
- [x] T10 — `uv run --directory cli pytest tests/test_reset.py tests/test_state_portability.py -q`
- [x] T12 — `uv run --directory cli pytest tests/test_graph_loops.py -q`
- [x] T11 — the reproduction, driven end to end, record contents shown before and after
- [x] Full suite — `uv run --directory cli pytest -q`
- [x] Lint + types — `ruff check`, `ruff format --check`, `pyright`, `markdownlint`,
      `validate_config.py`

## Verification results

Every activity ran, twice over: once for the link-record version this PR first carried,
and again after the owner-review rebuild to the endpoint model. The counts below are the
rebuild's.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `pytest tests/test_routing.py -q` | pass — 106 tests | [`evidence/tests.md`](evidence/tests.md) |
| T2 | `pytest tests/test_webhook_routing_integration.py -q` | pass — 22 tests | [`evidence/tests.md`](evidence/tests.md) |
| T2b | `pytest tests/test_poller.py -q` | pass — 107 tests | [`evidence/tests.md`](evidence/tests.md) |
| T2/T2b (negative) | seven regression tests against a registry whose `record_owning` is the bare `find_by_work_item` and recording a no-op | **7 failed, as they must** — the second PR event reaches nothing, the poller arms a spawn against the PR | [`evidence/tests.md`](evidence/tests.md) |
| T8 | the abuse cases in `tests/test_routing.py` | pass — a corrupt entry is skipped per entry, a tree is flattened, a self-recording refused | [`evidence/tests.md`](evidence/tests.md) |
| T10 | `pytest tests/test_reset.py tests/test_state_portability.py -q` | pass — 32 tests; no new generated path, no new reset piece | [`evidence/tests.md`](evidence/tests.md) |
| T12 | `pytest tests/test_graph_loops.py -q` | pass — 13 tests, all new | [`evidence/tests.md`](evidence/tests.md) |
| T11 | the ticket's reproduction through a real dispatcher | before: the second event reaches nothing and the registry holds one bare file. After: the PR is on the record with its own session, and the second event lands in it | [`evidence/reproduction.md`](evidence/reproduction.md) |
| Full suite | `pytest -q` | pass — 1416 passed, 1 skipped (pre-existing; baseline before this work item was 1379 passed, 1 skipped) | [`evidence/tests.md`](evidence/tests.md) |
| Lint + types | `ruff check`, `ruff format --check`, `pyright`, `markdownlint-cli2`, `validate_config.py` | clean | [`evidence/lint-and-types.md`](evidence/lint-and-types.md) |

**Not executed:** none.

## Review comments

Recorded on the pull request. Self-review and critic-review findings, and their
dispositions, are in [`execution-log.md`](execution-log.md) § Review cycles.
