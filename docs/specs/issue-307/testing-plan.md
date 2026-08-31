---
type: testing-plan
phase: test-planning
workItem: "issue-307"
status: locked
approvedBy: []
overrides: {}
---

# Testing plan: per-work-item collaborators

> Derived from the locked `requirements.md` and `design.md`, **before** `tasks.md`.
> Authored at `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit — the login grammar | yes | `normalize_login` accepts GitHub's shape and rejects everything else (leading/trailing/double hyphen, 40 chars, dots, slashes, spaces, paths, argv fragments, empty); `parse_logins` takes the `@login` run and stops at prose | `cd cli && uv run pytest tests/test_collaborators.py` |
| T2 | Unit — the store | yes | add/remove/list round-trip; idempotent add and no-op remove report themselves; case-insensitive identity; provenance fields recorded; `permits` is per-ref and answers "any of these refs"; `clear`; the section survives beside `control`/`poll`/`graph` and a record with only a roster is not deleted | `cd cli && uv run pytest tests/test_collaborators.py` |
| T3 | Unit — the parser | yes | both keywords parse with their logins; several logins and a repeated keyword; a keyword with no login yields the command and no subjects; ambiguity with an existing command; disabling by empty keyword; whole-token boundaries (`the-loop add-collaborators`, `xthe-loop add-collaborator`) | `cd cli && uv run pytest tests/test_control.py` |
| T4 | Unit — the dispatcher's control seam | yes | an authorized user's `add-collaborator` writes the roster, emits `control.command` naming the login and settles the delivery; `remove-collaborator` revokes; a body with no login is refused `missing-collaborator` and writes nothing; no `ControlStore` record is written by either | `cd cli && uv run pytest tests/test_dispatcher_control.py` |
| T5 | Unit — the dispatcher's spawn seam | yes | a named actor outside `authorizedUsers` cannot spawn (`collaborator-no-spawn`, settled, not retried); an actor-less presence event still spawns on a recorded start (decision-074 regression) | `cd cli && uv run pytest tests/test_dispatcher_spawn.py` |
| T6 | Integration — webhook ingress | yes | a collaborator's comment on their work item is delivered to that item's session; the same comment from a stranger is dropped; the same collaborator on *another* work item is dropped; a collaborator's `the-loop stop` is refused, not executed and not forwarded | `cd cli && uv run pytest tests/test_webhook_routing_integration.py` |
| T7 | Integration — poll ingress | yes | the poller forwards a collaborator's comment; it does **not** arm a spawn from one; a collaborator's control keyword is not treated as a pending command | `cd cli && uv run pytest tests/test_poller_integration.py` |
| T8 | Regression — the human gates | yes | `classify-feedback`, `classify-phase-selection`, `goal-definition` and the review brief ignore a work-item collaborator's comment exactly as they ignore any other non-authorized author (A5) | `cd cli && uv run pytest tests/test_graph_review.py tests/test_graph_hooks*.py` |
| T9 | Unit — lifecycle | yes | closing the work item clears the roster with the control record; `sessions reset` drops the section; a cleared roster stops permitting | `cd cli && uv run pytest tests/test_collaborators.py tests/test_reset.py` |
| T10 | Unit / integration — the CLI | yes | `add-collaborator`/`remove-collaborator` apply the grant, post the keyword **with** the login carrying the self-marker, report an unchanged roster honestly, survive a failing `gh` without failing the grant, and exit 2 on a malformed login or ref | `cd cli && uv run pytest tests/test_collaborators_cli.py` |
| T11 | Config / schema | yes | both copies of the CLI-config schema accept the two new keywords and still reject an unknown one; the shipped template and this repo's own config validate; `ControlConfig.from_mapping` honours a configured and an emptied keyword | `cd cli && uv run pytest tests/test_configschema.py tests/test_control.py` |
| T12 | Contract (OpenAPI) | n/a — no route, request or response shape is added or changed (R5.5, design §5) | | |
| T13 | Security / abuse case | yes | A1 self-grant refused; A2 collaborator's control keyword refused **and** not forwarded; A3 injection through the login argument (T1's rejections, plus a body whose "login" is a path/argv fragment reaching nothing); A4 cross-item grant refused; A5 gates unchanged; A6 no spawn; A8 a removal takes effect on the next comment | T1, T4, T5, T6, T7, T8 |
| T14 | Lint / typecheck / tests | yes | the commands CI runs, at the pinned versions | `cd cli && uv run ruff check . && uv run pyright && uv run pytest`; `markdownlint` over the changed docs |
| T15 | UI / visual | n/a — no dashboard surface is added (design §5) | | |
| T16 | Performance | n/a — one extra JSON read per event, on the path that already reads that record for the control section | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R4.2, A3 | `@dana` parses; `@-dana`, `@dana-`, `@da--na`, a 40-character login, `@dana/../etc`, `@dan a`, `--flag` do not |
| T1 | R4.3 | `the-loop add-collaborator @a @b please help` yields `a`, `b` and ignores the prose |
| T2 | R1.1, R1.3, R1.7 | a grant round-trips through the portable record with login, grantor, timestamp, surface and comment URL |
| T2 | R1.4 | adding twice reports "already"; removing an absent login reports "not on the roster" |
| T2 | R1.5 | `@Dana`, `dana`, `@dana` are one entry and one identity |
| T2 | R1.2, R3.7, A4 | `permits` is true for the granted ref and for an event naming it beside a linked PR; false for any other ref |
| T3 | R4.1, R4.5, R4.6 | both keywords; `add-collaborator` + `stop` in one body is ambiguous; `""` disables |
| T4 | R4.4, R4.7, R6.1, R6.2 | the refusal, the settle, and an event log naming the login and nothing else from the body |
| T4 | R1.6 | the two verbs write no `ControlStore` record |
| T5 | R3.2, A6 | a named unauthorized actor's comment on an armed, unstarted item does not spawn |
| T5 | R3.3 | decision-074's authorized-start-on-an-unauthorized-author's-item still spawns |
| T6 | R3.1 | delivery of a collaborator's comment to the work item's session |
| T6 | R2.2, R3.4, A1, A2 | a collaborator's `the-loop add-collaborator @self` and `the-loop stop` are refused and not forwarded |
| T7 | R3.1, R3.3 | the poller forwards, and does not arm |
| T8 | R3.5, A5 | every human gate ignores a collaborator |
| T9 | R1.6, A8, A9 | closure, `reset`, and a revocation taking effect |
| T10 | R5.1–R5.4 | the CLI's four behaviours and its two exit-2 cases |
| T11 | R4.1, R4.6 | schema parity and keyword configuration |
| T14 | — | lint, types, the full suite, markdownlint |

## Verification results

Recorded at `verification` in [`evidence/verification.md`](evidence/verification.md).
