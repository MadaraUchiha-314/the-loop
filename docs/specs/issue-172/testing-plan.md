---
type: testing-plan
phase: test-planning
workItem: issue-172
status: approved              # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: proving a binding survives what derivation does not

> Phase 3 of 4. Derived from the locked [`bugfix.md`](bugfix.md) and
> [`design.md`](design.md), before `tasks.md`. Ticket:
> [issue #172](https://github.com/MadaraUchiha-314/the-loop/issues/172).
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. No credentials are involved: this work item makes no network call and reads no
> secret store.

## Test matrix

**The proof is a sequence, not a state.** A single event routing correctly proves nothing —
it already does today. What has to be shown is that the *second* event still lands after the
linkage the first one used has gone. T2 carries that; the rest fence the mechanism.

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the store: `link` writes and is idempotent, refuses a self-binding, preserves `createdAt` across a re-point; `resolve_link` is single-hop and returns `None` for absent/corrupt records; `links_to`/`unlink`; link records are **not** admitted by `list_sessions` and raise no "unreadable file" warning | `uv run --directory cli pytest tests/test_routing.py tests/test_core_sessions.py` |
| T2 | Integration (scenario) | yes | **the ticket's reproduction**: a session registered against the issue, a PR event carrying the linkage, then a PR event carrying none — the second is delivered into the issue's session, not dropped and not spawned against the PR. Gherkin-documented, linked to R5 | `uv run --directory cli pytest tests/test_webhook_routing_integration.py` |
| T2b | Integration (poll path) | yes | the same defect on the **poll** ingress: retry accounting reports a binding-resolved delivery `done` rather than re-forwarding it, and a polled PR with a stored binding is a known item rather than first sight (which would baseline its whole thread and arm a spawn) | `uv run --directory cli pytest tests/test_poller.py tests/test_routing.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API surface changes; `docs/api-specs/openapi` is untouched, deliberately (`bugfix.md` § Out of scope) | | |
| T4 | End-to-end | n/a — the shell-level path (`the-loop gh-webhook start`) is unchanged; T2 drives the same receiver→router→dispatcher→tmux chain in-process, which is where this repo's e2e coverage for routing lives | | |
| T5 | UI / visual | n/a — the-loop has no product UI (`design.uiArtifacts`, unused here) | | |
| T6 | Snapshot | n/a — no rendered output. The one serialized shape that must stay stable is the link record, pinned by an equality assertion in T1 rather than a snapshot file | | |
| T7 | Performance / load | n/a — one extra `Path.is_file()` per routed ref that has no session record, on a path that already opens files | | |
| T8 | Security / abuse case | yes | the boundaries `design.md` § Security design names: a hand-edited record holding a path/shell fragment is refused by `WorkItemRef.parse` and treated as absent; the file name cannot escape the registry directory; a binding whose target is itself bound is **not** followed; a self-binding is refused | `uv run --directory cli pytest tests/test_routing.py` |
| T9 | Accessibility | n/a — no user-facing surface | | |
| T10 | Migration / upgrade | yes | an installation with **no** link records behaves identically (every existing test is that assertion); `sessions reset` removes bindings in both directions and reports the new `link` piece; `GENERATED_PATHS` and `docs/cli/state.md` agree on the classification | `uv run --directory cli pytest tests/test_reset.py tests/test_state_portability.py` |
| T11 | Manual exploratory | yes | the failure the ticket describes, driven end to end against the un-fixed and fixed dispatcher, with the registry directory listed before and after — the binding is visible on disk | § Verification results |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.3, R1.5 | `link` writes a record; re-linking to the same target returns `None` and rewrites nothing; `source == target` is refused |
| T1 | R1.4 | a record written by one `SessionRegistry` instance is read by a fresh one (the restart property, as a filesystem fact) |
| T1 | R2.2, R2.3 | resolution order — own record wins over a binding; a binding whose target is itself bound is not followed |
| T1 | R4.1 | `list_sessions` ignores link records; no `warning` is logged for one |
| T1 | R4.5 | `session.linked` / `session.unlinked` are in `EVENT_TYPES` (covered structurally by `test_eventlog.py::test_every_emitted_event_type_is_documented`) |
| T2 | R2.1, R5.1, R5.2 | `Scenario: a PR event still reaches the linked issue's session after the linkage is removed` |
| T2 | R1.1, R1.2 | `Scenario: dispatching a PR event to a linked issue's session records the binding` (delivery path) and the spawn path's equivalent |
| T2 | R2.5 | `Scenario: a stored binding does not suppress a session the linkage still finds` — both sessions receive the event |
| T2 | R2.6 | with neither a record nor a binding, the spawn policy decides exactly as before |
| T2 | R2.7 | a `the-loop stop` commented on a PR with no linkage stops the bound session |
| T2b | R2.8 | `delivery_status` reports `done` for an id recorded on the bound session |
| T2b | R2.9 | a polled PR with a stored binding does not spawn and does not baseline as first sight |
| T2 | R3.1, R3.2 | a `pull_request` `closed` matched through a binding leaves the session open (`session.kept_open`); a PR with its own session is still auto-closed |
| T8 | R1.5, R2.3 | the abuse cases above |
| T10 | R4.2, R4.3, R4.4 | reset removes both directions and reports `link`; a `close` does **not** remove bindings; the classification agrees in code and docs |

## Verification environment

Nothing beyond this repository and its own toolchain. The change is a Python package plus
checked-in markdown.

- **Repositories:** this repo only.
- **Services / containers:** none. The integration tests drive a live receiver bound to
  `127.0.0.1` on an ephemeral port, in-process, with an injected `FakeTmux` — no real tmux,
  no real harness, no GitHub.
- **Fixtures & data:** none checked in. Registry directories are built under pytest's
  `tmp_path`.
- **Credentials:** none. No network call, no secret store, no `gh` invocation.
- **Bring-up:** `uv sync --directory cli` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T10 | full `pytest` run — counts, duration, the new tests named | `tests.md` |
| T2 | the regression test run against the **unfixed** dispatcher — the failure is the defect | `tests.md` |
| T11 | the reproduction driven through the dispatcher, with `ls` of the registry directory before and after, and the link record's contents | `reproduction.md` |
| all | `ruff`, `pyright`, `markdownlint` over the change | `lint-and-types.md` |

Nothing captured here can contain a token, a cookie, personal data or an internal hostname:
the outputs are pytest summaries, linter findings, and JSON holding two `github:octo/repo#N`
refs and two timestamps. All of it is committed as markdown, as the rule requires.

## Verification activities

- [x] T1 — `uv run --directory cli pytest tests/test_routing.py -q`
- [x] T2 — `uv run --directory cli pytest tests/test_webhook_routing_integration.py -q`
- [x] T2b — `uv run --directory cli pytest tests/test_poller.py tests/test_routing.py -q`
- [x] T2/T2b — all six regression tests against the **unfixed** resolver (the check that the
      checks check something)
- [x] T8 — the abuse cases, in `tests/test_routing.py`
- [x] T10 — `uv run --directory cli pytest tests/test_reset.py tests/test_state_portability.py -q`
- [x] T11 — the reproduction, driven end to end, registry directory listed before and after
- [x] Full suite — `uv run --directory cli pytest -q`
- [x] Lint + types — `ruff check`, `ruff format --check`, `pyright`, `markdownlint`,
      `validate_config.py`

## Verification results

Every planned activity ran. Nothing was left unexecuted.

**Planned narrower than it ran.** T2 was scoped to the webhook ingress. Self-review round 1
swept every remaining `find_by_work_item` call site rather than only the ones `design.md`
named, and found the same defect twice more on the **poll** path — retry accounting, and
first-sight detection. Those became T2b rather than being folded silently into T2, because
they are a different ingress with a different failure (a re-forwarded comment, and a
baselined thread) and deserve to be named as such.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `pytest tests/test_routing.py -q` | pass — 103 tests, 13 of them new | [`evidence/tests.md`](evidence/tests.md) |
| T2 | `pytest tests/test_webhook_routing_integration.py -q` | pass — 22 tests, 6 of them new | [`evidence/tests.md`](evidence/tests.md) |
| T2b | `pytest tests/test_poller.py -q` | pass — 107 tests, 1 of them new (plus `test_delivery_status_follows_a_binding` in T1's file) | [`evidence/tests.md`](evidence/tests.md) |
| T2/T2b (negative) | all six regression tests against a registry whose `session_for` is the bare `find_by_work_item` | **6 failed, 16 passed** — the second PR event is dropped, a successful delivery reports `unhandled`, and the poller arms a spawn against the PR. The 16 that still pass include both close scenarios, which this work item must **not** change | [`evidence/tests.md`](evidence/tests.md) |
| T8 | the four abuse cases in `tests/test_routing.py` | pass — a corrupt record reads as absent, a self-binding is refused, a chained binding is not followed, a traversal-shaped ref never becomes a path | [`evidence/tests.md`](evidence/tests.md) |
| T10 | `pytest tests/test_reset.py tests/test_state_portability.py -q` | pass — 36 tests, 4 of them new | [`evidence/tests.md`](evidence/tests.md) |
| T11 | the ticket's reproduction, driven through a real dispatcher | before the fix: the second event reaches nothing, and the registry holds one file. After: it is delivered into the issue's session, and `local/` holds `github-octo-repo-16.link.json` | [`evidence/reproduction.md`](evidence/reproduction.md) |
| Full suite | `pytest -q` | pass — 1404 passed, 1 skipped (pre-existing, unrelated; baseline before this change was 1379 passed, 1 skipped) | [`evidence/tests.md`](evidence/tests.md) |
| Lint + types | `ruff check`, `ruff format --check`, `pyright`, `markdownlint-cli2`, `validate_config.py` | clean | [`evidence/lint-and-types.md`](evidence/lint-and-types.md) |

**Not executed:** none.

## Review comments

Recorded on the pull request. Self-review and critic-review findings, and their
dispositions, are in [`execution-log.md`](execution-log.md) § Review cycles.
