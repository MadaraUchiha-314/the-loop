---
type: testing-plan
phase: test-planning
workItem: issue-186
status: approved              # draft | in-review | approved
approvedBy: []                # pending — human gate on the PR (risk tier 4)
overrides: {}
---

# Testing plan: clean up after a work item is closed

> Derived from [requirements.md](requirements.md) and [design.md](design.md). Each task
> in [tasks.md](tasks.md) names a row below.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `cleanup.cleanup_work_item` order, per-piece reporting, partial-failure isolation, dry run, portable record untouched (R1.1–1.4, R1.6, R4.1–4.3); `control.parse_command` accepts the new keyword and still refuses ambiguity (R2.1) | `uv run pytest cli/tests/test_cleanup.py cli/tests/test_control.py` |
| T2 | Integration (scenario) | yes | The three triggers end to end — authorized comment, close event with and without a `sender`, retroactive with no session record — against a real registry and a real `Workspace` on a temp git repo (R2.2, R3.1–3.4, R4.1–4.2, R6) | `uv run pytest cli/tests/test_cleanup_integration.py` |
| T3 | Contract (OpenAPI) | yes | `POST /sessions/control` accepts `verb: cleanup`; the documented verb list and `CONTROL_VERBS` agree (R2.5) | `uv run pytest cli/tests/test_api_routers_integration.py cli/tests/test_docs_parity.py` |
| T4 | End-to-end | n/a — an end-to-end run needs a live tmux server, a real harness CLI and a GitHub repo; T2 covers the same flow with the two native deps faked at their existing seams | | |
| T5 | UI / visual | n/a — the-loop has no product UI | | |
| T6 | Snapshot | n/a — no rendered artifact is asserted byte-for-byte | | |
| T7 | Performance / load | n/a — cleanup is a per-work-item, human-triggered action | | |
| T8 | Security / abuse case | yes | The four abuse cases from `requirements.md`: unauthorized commenter, close with no actor, PR merge on an open item, ambiguous comment | `uv run pytest cli/tests/test_cleanup_integration.py -k abuse` |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | yes | A pre-issue-186 session record and a pre-issue-186 `graph-state.json` (no `cleanup` node ever entered) clean up without migration; a config with no `keywords.cleanup` gets the default | `uv run pytest cli/tests/test_cleanup.py -k legacy` |
| T11 | Manual exploratory | n/a — every path is reachable from the seams the suites already inject | | |
| T12 | Graph contract | yes | `cleanup` compiles in `pdlc-work-item-loop` and `pdlc-contribution-loop`, is absent from `pdlc-pr-loop`, and `Runtime.cleanup` enters it / is idempotent / no-ops without it (R5.1, R5.2, R5.4) | `uv run pytest cli/tests/test_graph_cleanup.py cli/tests/test_graph_contract.py` |
| T13 | Docs & schema parity | yes | Every new config key is documented and every documented key exists; the phase vocabulary agrees across schema, config and template (R5.3) | `uv run pytest cli/tests/test_docs_parity.py cli/tests/test_harness_gate.py` |

## Verification environment

- **Runtime:** Python 3.11+, `uv` for dependency resolution, `pytest` as the runner.
- **Native dependencies:** none are required. `tmux` is faked at the existing
  `TmuxRunner` seam the dispatcher suites already use; `git` **is** exercised for real in
  T2 against a throwaway repository under `tmp_path`, because the worktree removal path is
  precisely what must be proved.
- **Network:** none. No GitHub call is made — the graph integrations resolve to the fake
  the graph suites already provide.
- **Commands:** `make check` (lint + typecheck + the full suite) is the gate; the
  per-row commands above are what a task-level red→green cycle runs.

## Evidence plan

| Row | Evidence | Where |
|---|---|---|
| T1, T2, T8, T10, T12 | `pytest` output for the new suites | `evidence/pytest-cleanup.txt` |
| T3, T13 | `pytest` output for the parity suites | `evidence/pytest-parity.txt` |
| all | Full `make check` transcript | `evidence/make-check.txt` |

## Verification results

Executed at the `verification` node, on the branch's final state.

| # | Command | Outcome | Evidence |
|---|---------|---------|----------|
| T1 | `uv run pytest cli/tests/test_cleanup.py cli/tests/test_control.py` | **pass** — 69 passed | `evidence/pytest-cleanup.txt` |
| T2 | `uv run pytest cli/tests/test_cleanup_integration.py` | **pass** — 16 passed | `evidence/pytest-cleanup.txt` |
| T3 | `uv run pytest cli/tests/test_api_routers_integration.py cli/tests/test_core_sessions.py` | **pass** — 15 passed | `evidence/pytest-cleanup.txt` |
| T8 | `uv run pytest cli/tests/test_cleanup_integration.py -k abuse` | **pass** — 5 passed (the four abuse cases plus the unauthorized-closer one) | `evidence/pytest-cleanup.txt` |
| T10 | `uv run pytest cli/tests/test_cleanup.py -k legacy` | **pass** — 2 passed | `evidence/pytest-cleanup.txt` |
| T12 | `uv run pytest cli/tests/test_graph_cleanup.py cli/tests/test_graph_contract.py` | **pass** — 23 passed | `evidence/pytest-cleanup.txt` |
| T13 | `uv run pytest cli/tests/test_docs_parity.py cli/tests/test_harness_gate.py` | **pass** — 28 passed | `evidence/pytest-parity.txt` |
| all | `make check` (ruff, markdownlint, ruff format, pyright, config validation, full suite) | **pass** — 0 lint findings, 0 pyright errors, 6 configs valid, 1629 passed / 1 skipped | `evidence/make-check.txt` |

One row was proved **red before green** beyond its own task's cycle, and is worth naming:
the GitHub Enterprise regression in T2
(`test_a_github_enterprise_work_item_finds_its_own_checkout`). It was written after a
self-review pass spotted that the checkout lookup reconstructed the repository from
`full_name` alone — resolving every work item to the configured default host, and so
missing the worktree of any item on another host. Reverting the fix reproduces the failure
against `…/workspace/.worktrees/ghe.corp.example/octo/repo/…`; restoring it passes.
