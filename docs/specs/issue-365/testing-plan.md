---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#365"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: retire the execution log

> Derived from `requirements.md` and `design.md`, **before** `tasks.md` — each task's
> `_Test:_` names a row of the matrix below. Authored at `test-planning`, completed at
> `verification`. See `reference/testing.md`.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. This work item needs no credentials and touches no network: every assertion
> is a filesystem read through the compiled graph.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the `log-entry` hook is gone from the registry and no shipped graph references it (R1.4) | `uv run --project cli python -m pytest -q cli/tests/test_graph_hooks.py` |
| T2 | Unit | yes | `declared_repos` reads `tasks.md` front matter; absent file, absent key and non-list value are all *no declaration* (R3.1, R3.2) | `uv run --project cli python -m pytest -q cli/tests/test_graph_loops.py` |
| T3 | Unit (parity) | yes | P1–P3 and P5 still hold with the new names: every gated name is tracked by the manifest and has a template that can satisfy its sections, and every content gate resolves an artifact (R2.2, R2.5) | `uv run --project cli python -m pytest -q cli/tests/test_graph_parity.py` |
| T4 | Integration | yes | each review-chain node **blocks** when its `evidence/*.md` is missing and passes once the section is written (R2.1) | `uv run --project cli python -m pytest -q cli/tests/test_graph_review_chain_integration.py` |
| T5 | Integration | yes | declaring one review node away relaxes **only** that node's gate — a still-walked sibling still blocks (R2.3) | `uv run --project cli python -m pytest -q cli/tests/test_graph_skips.py` |
| T6 | Integration | yes | with `test-planning` declared away, `verification` blocks until `evidence/verification.md` § Verification results is written, and that file is never a planned absence (R2.4) | `uv run --project cli python -m pytest -q cli/tests/test_graph_verification_integration.py` |
| T7 | Integration | yes | `await-inner-loops` holds `implementation` for repositories declared in `tasks.md`, and blocks naming a malformed entry (R3.1, R3.3) | `uv run --project cli python -m pytest -q cli/tests/test_graph_multirepo_integration.py` |
| T8 | Integration | yes | an `execution-log.md` left on disk changes no gate's outcome and is never read (R5.3) | `uv run --project cli python -m pytest -q cli/tests/test_graph_review_chain_integration.py -k legacy` |
| T9 | End-to-end (scenario) | yes | the shipped outer loop walks happy-path, trivial-tier and ask-reply to `complete` with no execution log anywhere in the fixtures, asserting the evidence artifacts instead (A7) | `uv run --project cli python -m pytest -q cli/tests/test_pdlc_e2e_integration.py` |
| T10 | Unit | yes | `resolve_session`'s dead-session fallback seeds artifacts that exist after the removal (R4.2) | `uv run --project cli python -m pytest -q cli/tests/test_graph_parity.py cli/tests/test_graph_hooks.py` |
| T11 | Contract (OpenAPI / GraphQL SDL) | n/a — no API surface changes | | |
| T12 | UI / visual | n/a — no rendered surface; the docs site is prose only | | |
| T13 | Snapshot | n/a — the graph YAML diff is the record, and T3/T4 assert its behaviour directly | | |
| T14 | Performance / load | n/a — the change removes work from every node boundary; there is no hot path to regress | | |
| T15 | Security / abuse case | yes | the review gates still block on a missing proof (T4 is the abuse case: "delete the file to pass the gate"), and `security-review` in particular has a subject it blocks on | `uv run --project cli python -m pytest -q cli/tests/test_graph_review_chain_integration.py -k security` |
| T16 | Accessibility | n/a — no rendered UI | | |
| T17 | Manual exploratory | n/a — the loop's own dogfooding of this work item is the exploratory pass: this spec directory carries the new `evidence/` artifacts and no execution log | | |
| T18 | Repository gates | yes | the whole repository still passes what CI runs: ruff, ruff format, pyright, config validation, the full suite, and markdownlint over every `**/*.md` | `make check` |
| T20 | Unit | yes | the state file is `work-item-state.json`; one written under the pre-rename name is read and re-saved under the current one, and the current name wins when both exist (R7.1, R7.2) | `uv run --project cli python -m pytest -q cli/tests/test_graph_state.py` |
| T21 | Unit | yes | `the-loop graph repos` writes the declaration, reads it back without writing, replaces rather than appends, clears, and dedupes (R3.1, R7.4) | `uv run --project cli python -m pytest -q cli/tests/test_graph_repos.py` |
| T22 | Security / abuse case | yes | a declaration can only ever name a usable repository path inside the instance's own `repositories`; a traversal, an absolute path, a shell fragment and a bare name are each refused, and one bad entry writes nothing (R7.4) | `uv run --project cli python -m pytest -q cli/tests/test_graph_repos.py -k abuse` |
| T23 | Contract (OpenAPI) | yes | the served schema still matches the authored contract with `POST /api/v1/graph/repos` in it (decision-058, contract-first) | `uv run --project cli python -m pytest -q cli/tests/test_api_contract_parity.py` |
| T19 | Documentation parity | yes | no shipped surface (graphs, hooks, templates, manifest, commands, skill, docs) names an execution log except where it is deliberately recorded as retired (A1) | `uv run --project cli python -m pytest -q cli/tests/test_writing_parity.py` + repository grep, T18 |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.4 | `log-entry` absent from the hook registry; every shipped graph loads with no unknown-hook error |
| T2 | R3.1 | `repos:` in `tasks.md` front matter is returned in declaration order |
| T2 | R3.2 | no `tasks.md`, no `repos:` key, and `repos: "octo/repo"` (a string) each return `[]` |
| T3 | R2.5 | P5a: every `sections:` gate in both loops resolves `produces:` or `validates:` |
| T3 | R1.1, R1.2 | neither the manifest nor the template directory carries `execution-log.md` |
| T4 | R2.1 | `self-review`, `critic-review`, `security-review`, `evidence`, `capability-docs`, `reviewer-briefing` each block with an empty `evidence/`, and pass once their own file carries the required section |
| T5 | R2.3 | `self-review` declared skipped + `critic-review` walked ⇒ `critic-review` still blocks |
| T6 | R2.4 | `test-planning` declared skipped ⇒ `verification` blocks on `evidence/verification.md`; the file is produced by no node, so it never enters `skipped_artifacts` |
| T7 | R3.1, R3.3 | two declared repos, one inner loop started ⇒ `implementation` waits; `repos: ["../etc"]` ⇒ blocked naming the entry |
| T8 | R5.3 | a work item carrying a legacy `execution-log.md` with every old section still blocks at `self-review` until `evidence/self-review.md` exists |
| T9 | A7 | the three e2e scenarios' `artifacts/` carry `evidence/*.md`, not `execution-log.md` |
| T15 | R2.2 | deleting a written proof re-blocks the node on the next run (`status --recompute` derives from artifacts) |
| T20 | R7.1, R7.2 | `graph-state.json` on disk → the pointer is read, the next save writes `work-item-state.json`, and the old file is kept |
| T21 | R3.1, R7.4 | declare two → state carries both in order; re-declare → replaces; `--clear` → none; reading writes nothing |
| T22 | R7.4 | `../etc`, `..`, `/etc/passwd`, `octo/app;rm -rf /`, `octo/../../etc`, `octo`, `""`, a newline-smuggled second entry → each refused, nothing written; a repository outside the instance's `repositories` → refused naming the set |
| T23 | decision-058 | the route is authored in `docs/api-specs/openapi/the-loop.v1.yaml` before it is served |

## Verification environment

One checkout of this repository, Python via `uv` (workspace pinned by `uv.lock`), Node for
`markdownlint-cli2` through `npx`. No network beyond package resolution, no credentials, no
`cursor-agent`/`claude` binary: every test in the matrix is a filesystem read through the
compiled graph or a docs lint.

## Evidence plan

This work item **has** a testing plan, so the executed rows are recorded below rather than
in `evidence/verification.md` — that file is the fallback for a work item that declared
`test-planning` away. The security round is in `evidence/security-review.md` and the
acceptance-criteria summary in `evidence/final-validation.md`, both under the shape this
change introduces. Command output is summarised rather than pasted wholesale — the commands
above are reproducible.

## Verification results

| Row | What was verified | Command | Outcome | Evidence |
|-----|-------------------|---------|---------|----------|
| T1 | `log-entry` is gone from the registry; every shipped graph still compiles | `uv run --project cli python -m pytest -q cli/tests/test_graph_hooks.py` | pass (46) | the fixtures that still named the hook failed to compile first — that is the red |
| T2 | `declared_repos` reads `tasks.md`; absent file / absent key / non-list are each *no declaration* | `… -q cli/tests/test_graph_loops.py` | pass (47) | `test_every_shape_of_absence_is_no_declaration_not_an_empty_one` is new |
| T3 | P1–P3, P5a–P5c hold with the new names | `… -q cli/tests/test_graph_parity.py` | pass (6) | red first: `_SPEC_FILE` excluded a `pathPattern` one directory down |
| T4 | each review-chain node blocks without its record and passes with it | `… -q cli/tests/test_graph_review_chain_integration.py` | pass (28) | file rewritten for the new subjects |
| T5 | a declared skip relaxes only its own node's gate | `… -k test_a_declared_skip_relaxes_only_its_own_nodes_gate` | pass | new |
| T6 | `verification` blocks on `evidence/verification.md` with the plan declared away | `… -q cli/tests/test_graph_verification_integration.py` | pass (10) | |
| T7 | `await-inner-loops` holds for repositories declared in `tasks.md` | `… -q cli/tests/test_graph_multirepo_integration.py` | pass | |
| T8 | a legacy `execution-log.md` on disk changes no outcome | `… -k legacy` | pass | new |
| T9 | the three e2e scenarios walk to `complete` with no execution log | `… -q cli/tests/test_pdlc_e2e_integration.py` | pass (15) | `ask-reply` blocked first on the missing `evidence/verification.md` — the kept gate working |
| T10 | the dead-session fallback seeds artifacts that still exist | covered by T1/T3 | pass | |
| T15 | the security gates still block on a missing proof | `… -k security` | pass | see `evidence/security-review.md` |
| T18 | the whole repository passes what CI runs | `make lint format-check typecheck validate test` | pass | ruff clean; markdownlint 1131 files, 0 errors; pyright 0 errors; **3609 passed, 1 skipped** |
| T19 | no shipped surface names an execution log except where it is deliberately recorded as retired | `… -q cli/tests/test_writing_parity.py` + repository grep | pass | the surviving hits are three "…until issue-365 retired it" notes, `upgrade-the-loop`'s operator guidance, the sidebar entry keeping old logs browsable, and this spec chain |
| T20 | the rename, and the pointer surviving it | `… -q cli/tests/test_graph_state.py` | pass (14) | five new cases; the legacy-name read is the one that matters |
| T21 | `the-loop graph repos` | `… -q cli/tests/test_graph_repos.py` | pass (16) | new file; the CLI was also exercised by hand end to end |
| T22 | a declaration can only name a usable, declared repository | `… -q cli/tests/test_graph_repos.py -k abuse` | pass | red first: `parse_repo_path` alone accepted `../etc`, so the filesystem boundary was added ahead of it |
| T23 | the contract carries the route | `… -q cli/tests/test_api_contract_parity.py` | pass (2) | contract authored first, then the route |

Rows T11–T14, T16 and T17 were declared `n/a` with their reasons in the matrix above and
were not executed.
