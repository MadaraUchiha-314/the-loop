---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#253"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: one owner per work item, one session per working tree

> Derived from `bugfix.md` and `design.md`, **before** `tasks.md` — each task's `_Test:_`
> names a row below. Authored at `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `_endpoint_for`'s ownership rule and `_endpoint_cwd`'s refusal, through the dispatcher's observable seam (the injected `FakeTmux`: what was spawned, what was delivered, and into which ref) | `uv run --project cli python -m pytest cli/tests/test_routing.py` |
| T2 | Integration (scenario) | yes | the same behaviour end-to-end from an HTTP webhook delivery through the receiver to the tmux seam, Gherkin-documented | `uv run --project cli python -m pytest cli/tests/test_webhook_routing_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API surface changes; the control plane's session shape is unchanged and `test_api_contract_parity.py` still covers it | | |
| T4 | End-to-end | yes | a real `git` workspace: a cross-repository endpoint gets a worktree of the **other** repository, at a different path from the work item's | `uv run --project cli python -m pytest cli/tests/test_workspace.py` |
| T5 | UI / visual | n/a — no user-facing surface; this is dispatch routing | | |
| T6 | Snapshot | n/a — no serialised artefact changes shape; registry records round-trip byte-identically | | |
| T7 | Performance / load | n/a — the change removes work (one fewer spawn per work item) and adds one tuple comparison per PR event | | |
| T8 | Security / abuse case | yes | the negative direction of the rule: a payload naming an unexpected repository can only reach the stricter outcome, and no branch spawns where the old code would not have — including the `shared-worktree` guard, which refuses whatever produced a path onto the record's tree | `uv run --project cli python -m pytest cli/tests/test_routing.py -k cross_repo` |
| T9 | Accessibility | n/a — no user-facing surface | | |
| T10 | Migration / upgrade | yes | a record written by the previous the-loop — an endpoint carrying `tmuxTarget` and the work item's `cwd` — is read forward and stops receiving events, with nothing torn down | `uv run --project cli python -m pytest cli/tests/test_routing.py -k even_once_it_has_a_record` |
| T11 | Manual exploratory | n/a — the reported defect is reproduced as T2; a manual repro would add a live GitHub app and two tmux processes to prove what the scenario test proves deterministically | | |
| T12 | Whole-suite regression | yes | nothing else depended on the collapsed behaviour; the routing change is visible to the whole CLI suite | `make test` (or `uv run --project cli python -m pytest cli/tests`) |
| T13 | Lint / format / types | yes | the repo's own gates | `make lint`, `make format-check`, `make typecheck` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.3 | `test_dispatcher_still_routes_pr_events_that_are_not_close` — a same-repo PR event delivers into the work item's session, spawns nothing, and is still recorded on the record with no `tmuxTarget` |
| T1 | R1.1 | `test_dispatcher_delivers_pr_events_into_the_work_items_session_when_collapsed` — `sessionPerPr: false` still collapses (unchanged) |
| T10 | R1.2 | `test_a_same_repo_pr_never_gets_a_session_even_once_it_has_a_record` — a pre-existing endpoint session stops being fed |
| T8 | R2.2, R2.3, R2.4 | `test_a_cross_repo_pr_without_a_workspace_is_declined_not_collided` — no checkout, so no session; the event lands in the work item's session and the binding is still recorded |
| T8 | R2.2 | `test_an_endpoint_checkout_that_lands_on_the_records_tree_is_refused` — a prepared checkout that resolves to the record's own tree is refused too |
| T4 | R2.1 | `test_a_cross_repo_pr_endpoint_spawns_in_its_own_checkout` — the endpoint's `cwd` is the *other* repository's worktree, keyed on the PR's slug, and differs from the record's |
| T2 | R1.1, R1.3 | `Scenario: A comment on a labelled PR reaches the linked issue's one session` |
| T2 | R1.4 | `Scenario: A PR event still reaches its work item after the linkage is removed` |
| T12 | R3.1 | the full CLI suite |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. The webhook integration tests bind a receiver on an
  ephemeral local port; T4 shells out to the `git` binary against bare repositories it
  creates under `tmp_path`.
- **Fixtures & data:** all in-repo (`cli/tests/conftest.py` — `FakeTmux`,
  `StubInteractiveAdapter`; `make_origin` in `test_workspace.py`).
- **Credentials:** none. No test reaches GitHub.
- **Bring-up:** `uv sync` (implicit in `uv run`) · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T8, T10 | red-before/green-after runs of each new test | `red.md`, `unit-and-integration.md` |
| T2, T4, T12 | full-suite and per-file run output with counts | `unit-and-integration.md` |
| T13 | lint, format-check and typecheck output | `lint-and-typecheck.md` |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest cli/tests/test_routing.py`
- [x] T2 — `uv run --project cli python -m pytest cli/tests/test_webhook_routing_integration.py`
- [x] T4 — `uv run --project cli python -m pytest cli/tests/test_workspace.py`
- [x] T8 — `uv run --project cli python -m pytest cli/tests/test_routing.py -k cross_repo`
- [x] T10 — `uv run --project cli python -m pytest cli/tests/test_routing.py -k even_once_it_has_a_record`
- [x] T12 — `uv run --project cli python -m pytest cli/tests -q`
- [x] T13 — `make lint && make format-check && make typecheck`
- [x] Red-first — all six new/rewritten tests fail with the fix reverted

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| Red-first | `git stash` the dispatcher change, run the six guarding tests | 6 failed — each names the behaviour it guards | [`red.md`](evidence/red.md) |
| T1 | `pytest cli/tests/test_routing.py` | 111 passed | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T2 | `pytest cli/tests/test_webhook_routing_integration.py` | 22 passed | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T4 | `pytest cli/tests/test_workspace.py` | 35 passed | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T8, T10 | `pytest cli/tests -k cross_repo`, `-k even_once_it_has_a_record` | 7 passed, 1 passed | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T12 | `pytest cli/tests -q` | 2172 passed, 1 skipped | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T13 | `make lint`, `make format-check`, `make typecheck` | clean | [`lint-and-typecheck.md`](evidence/lint-and-typecheck.md) |

**Not executed:** none. Every applicable row ran.

## Review comments

*None yet.*
