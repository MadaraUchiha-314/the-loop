# Green run — unit, CLI, contract and integration (issue-274)

Every activity in `testing-plan.md`, run after the change. Commands are the plan's,
verbatim.

## T1 — unit and CLI

```console
$ uv run --project cli python -m pytest -q cli/tests/test_core_sessions.py cli/tests/test_cli.py
68 passed in 0.97s

$ uv run --project cli python -m pytest -q cli/tests/test_routing.py -k link_pr
2 passed, 161 deselected in 0.36s
```

The 15 new unit cases (parameters counted individually) cover R1.2–R1.7 one for one: the happy path and its single
`session.pr_linked`, idempotence (no second event, no rewrite), the missing record
(exit 1, nothing written), the self-link refusal, four spellings of the pull request
(`6`, `#6`, ` 6 `, the full ref), a pull request in another repository, and six malformed
inputs. The two CLI cases prove `sessions link-pr` parses, reaches core through
`routed()`, and renders core's messages and exit codes (0 / 0 on re-run / 1 / 2).

## T2 — integration, the reproduction

```console
$ uv run --project cli python -m pytest -q cli/tests/test_webhook_routing_integration.py
29 passed in 15.14s
```

Two Gherkin-documented scenarios over one pull-request payload that carries **none** of
the router's inference sources — no `closingIssuesReferences`, a `loop/<id>-requirements`
head branch with no `issue-<n>` in it, and a body that only mentions the issue:

| Scenario | Asserts |
|---|---|
| `…_is_lost_without_the_binding` | the comment reaches **no** session — not the work item's, and no spawned one. The bug, held in place so the fix cannot be mistaken for a change in what happens to an *unrecorded* pull request |
| `…_reaches_the_session_once_recorded` | with the binding written by `core.sessions.link_pull_request`, the same comment is delivered into issue 15's existing session, no second session is spawned, and no record is created for the pull request's own ref |

## T3 — contract

```console
$ uv run --project cli python -m pytest -q cli/tests/test_api_contract_parity.py \
    cli/tests/test_api_routers_integration.py cli/tests/test_mcp_integration.py
18 passed in 3.11s
```

The authored `docs/api-specs/openapi/the-loop.v1.yaml`, the served schema and the
embeddable router all carry `POST /api/v1/sessions/link-pr` / `linkSessionPullRequest`.

## T8 — security / abuse cases

```console
$ uv run --project cli python -m pytest -q cli/tests/test_core_sessions.py -k link
16 passed, 34 deselected in 0.10s
```

Each negative case asserts the registry was not written, not merely that the call failed.

## T13 — docs ↔ code parity

```console
$ uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py \
    cli/tests/test_sdk_docs_parity.py cli/tests/test_writing_parity.py cli/tests/test_eventlog.py
35 passed in 0.88s
```

`test_sdk_docs_parity` is the one that had something to say: the new `sessions.link_pr`
namespace method is documented in `docs/sdk/reference.md` (P1) and delegates to a core
function that exists (P2).

## Full suite

```console
$ uv run --project cli python -m pytest -q cli
2501 passed, 1 skipped in 131.52s (0:02:11)
```

After rebasing onto `main` at `71e7dff` (issue-273 landed in between and brought its own
tests). Before the rebase, on `main` at `50c2a27`: 2495 passed, 1 skipped, up from 2476 —
the 19 this work item adds (18 red-first, plus the control that holds the bug in place).
