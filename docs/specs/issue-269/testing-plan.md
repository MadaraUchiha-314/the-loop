---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#269"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: a branch-derived work item must exist, and the record decides who owns the event

> Derived from the approved `bugfix.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | ref provenance (`work_item_sources`, `branch_derived_refs`), `WorkItemVerifier`'s answer classes and cache, `_verify_linkage`, `_target_work_item`, the announcer's 404 path | `make test` (`uv run pytest cli/tests`) |
| T2 | Integration (scenario) | yes | the ticket's reproduction end to end — start binds to the pull request, the session spawns for it, the ghost never reaches either — Gherkin-documented | `make test` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — the control-plane API is untouched; no path, schema or response shape changes | | |
| T4 | End-to-end | n/a — an E2E run needs a real GitHub repository, a real `gh` credential and a real tmux/harness; T2 drives the same dispatcher seams with an injected runner, which is what the-loop's own suite has always done for this path | | |
| T5 | UI / visual | n/a — no user-facing surface; the change is daemon-internal routing | | |
| T6 | Snapshot | n/a — no rendered artefact changes | | |
| T7 | Performance / load | n/a — the added work is one cached, bounded-timeout subprocess per *fabricated* ref; the common path adds a set lookup. Measured load testing would not distinguish it from noise | | |
| T8 | Security / abuse case | yes | the payload → `gh` argv boundary: hostile owner/repo coordinates are refused before a call and answered "unknown" (kept, not dropped); a non-default host is asked with `--hostname` | `make test` |
| T9 | Accessibility | n/a — no user interface | | |
| T10 | Migration / upgrade | n/a — no persisted state, config schema or on-disk format changes; an existing deployment gains behaviour with no migration | | |
| T11 | Manual exploratory | n/a — the reproduction needs two repositories and a live poller; it is mechanised as T2 instead, which is stricter (it asserts the recorded control target, not just the observed symptom) | | |
| T12 | Static analysis (lint + types) | yes | `ruff` and `pyright` over the changed modules, plus the repo's markdown lint | `make lint` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.4 | a branch-only ref is reported weak; one corroborated by `closingIssuesReferences` or a closing keyword is not |
| T1 | R1.2 | a 404 answer drops the ref and records `routing.linkage_dropped` |
| T1 | R1.3 | missing `gh`, timeout, `OSError`, 403 and 5xx each keep the ref |
| T1 | R1.5 | a ref with a live session record is never checked |
| T1 | R1.6 | a second question about the same ref makes no second call |
| T1 | R1.7 | an event whose every ref was dropped is dropped, and its delivery id stays marked |
| T1 | R2.1, R2.2, R2.4 | `_target_work_item` prefers the live record; falls back to the first surviving ref; `requireStartCommand` is asked about that same ref |
| T1 | R3.1, R3.2 | an announce failure naming HTTP 404 emits `session.work_item_missing` and feeds the verifier cache; a non-404 failure does neither |
| T2 | R1.2, R2.1, R2.2, R2.3 | `Scenario: a start on a cross-repository pull request does not spawn a session for a branch-invented work item` |
| T2 | R1.3 | `Scenario: an unverifiable work item keeps its place in the routing decision` |
| T8 | Security design | `Scenario: hostile repository coordinates never reach a gh argv` |
| T12 | R4 | lint and type checks pass over the changed modules |

## Verification environment

- **Repositories:** this repository only. The two-repository topology in the reproduction is
  synthesised in the payloads the tests build — no second checkout is needed.
- **Services / containers:** none. No tmux, no harness, no network: the dispatcher's tmux
  runner, workspace and `gh` runner are all injected fakes, as in `cli/tests/test_routing.py`
  and `cli/tests/test_webhook_routing_integration.py`.
- **Fixtures & data:** the existing dispatcher fixtures in `cli/tests`; a fake `gh` runner
  returning `CompletedProcess` objects with the exit codes and stderr real `gh` produces.
- **Credentials:** none. The verifier is driven through its injected `runner`; no real `gh`
  is invoked and no token is read.
- **Bring-up:** `make test` · **Tear-down:** none (pytest `tmp_path`).
- **If bring-up fails:** record it under Verification results, leave the dependent activities
  unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8 | red run — the new tests failing against `main` | `red.md` |
| T1, T2, T8 | green run — full suite summary and the per-file runs | `unit-and-integration.md` |
| T12 | `make lint` / type-check output | `lint-and-typecheck.md` |
| — | security review record (checklist or skill output) | `security-review.md` |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_linkage.py cli/tests/test_routing.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_webhook_routing_integration.py cli/tests/test_poller_integration.py`
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests/test_linkage.py -k "hostile or hostname or provider"`
- [x] T12 — `make lint` (`ruff check`, `ruff format --check`, `markdownlint-cli2`) and `uv run pyright cli`
- [x] Full suite — `make test`
- [x] Red run captured before the fix — `evidence/red.md`
- [x] Security review — the checklist in `reference/security.md`, against the diff

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|---|---|---|---|
| Red run | the new tests against `main`'s production code (`git stash push -u -- cli/the_loop`) | the reproduction fails on `main` with `assert 'github:octo/repo#285' == 'github:octo/repo#48'`; its control passes | [`evidence/red.md`](evidence/red.md) |
| T1 | `pytest -q cli/tests/test_linkage.py cli/tests/test_routing.py` | 176 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T2 | `pytest -q cli/tests/test_webhook_routing_integration.py cli/tests/test_poller_integration.py` | 49 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T8 | `pytest -q cli/tests/test_linkage.py -k "hostile or hostname or provider"` | 4 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| Full suite | `make test` | 2410 passed, 1 skipped (2408 before this change) | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T12 | `uv run ruff check cli hooks`, `uv run ruff format --check cli hooks`, `uv run pyright cli`, `markdownlint-cli2`, `scripts/validate_config.py` | clean after two ruff findings and four markdownlint findings were fixed | [`evidence/lint-and-typecheck.md`](evidence/lint-and-typecheck.md) |
| Security review | checklist (`reference/security.md`), effective risk tier 3 | pass, no unresolved findings | [`evidence/security-review.md`](evidence/security-review.md) |

Every planned activity ran. Nothing was replanned, and nothing is left unticked.
