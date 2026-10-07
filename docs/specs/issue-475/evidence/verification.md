---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#475"
---

# Verification (issue-475)

Run on 2026-10-06 on branch `feat/issue-475-jira-5-edges` at `b5c1154`, the top of the
five-PR stack, using uv 0.12.10. Jira is `FakeJiraClient` everywhere except T11, and the
suite's autouse fixture refuses any real socket.

T1–T10 passed. T11 first could not run (no sandbox); the operator then provided one, and
it ran on 2026-10-07 in replanned form and passed — see the T11 section.

## Environment note

Every command was prefixed with
`env -u THE_LOOP_CLI_CONFIG -u THE_LOOP_WORK_ITEM -u THE_LOOP_GH_TOKEN`. This session
was spawned by a running the-loop daemon, which sets those three variables. When they
leak into a test run, 21 tests fail, and they fail on `main` as well, so the failures
are older than this change. Removing the variables gives the clean environment CI has.

## Results

| Activity | Command | Outcome | Evidence |
|----------|---------|---------|----------|
| T1 | `cd cli && uv run python -m pytest -q tests/test_jira_refs.py tests/test_routing.py tests/test_graph_refs.py tests/test_graphlink.py tests/test_core_graphs.py` | pass: 394 passed | [unit.md](unit.md#t1) |
| T2 | `cd cli && uv run python -m pytest -q tests/test_jira_api.py tests/test_jira_labels.py tests/test_jira_format.py` | pass: 78 passed | [unit.md](unit.md#t2) |
| T3 | `cd cli && uv run python -m pytest -q tests/test_integration_contract.py tests/test_jira_integration_provider.py` | pass: 32 passed | [unit.md](unit.md#t3) |
| T4 | `cd cli && uv run python -m pytest -q tests/test_jira_channels.py tests/test_channels.py tests/test_graph_integrations.py` | pass: 173 passed | [unit.md](unit.md#t4) |
| T5 | `cd cli && uv run python -m pytest -q tests/test_jira_poller.py tests/test_jira_webhook.py tests/test_jira_authz.py` | pass: 115 passed | [unit.md](unit.md#t5) |
| T6 | `cd cli && uv run python -m pytest -q tests/test_jira_integration.py`, then `uv run the-loop scenarios --root <repo> --glob 'cli/tests/test_*_integration.py' --format markdown` | pass: 11 passed, 11 Jira scenarios listed, all six planned ones among them. `--root` had to be absolute; see the evidence | [integration.md](integration.md) |
| T7 | `cd cli && uv run python -m pytest -q -k "jira and (…)"`, then the twelve named tests by name | pass: 67 passed; all twelve names exist and pass (25 cases) | [unit.md](unit.md#t7) |
| T8 | `cd cli && uv run python -m pytest -q tests/test_migrations.py tests/test_config_schema_parity.py tests/test_jira_config.py` | pass: 108 passed | [unit.md](unit.md#t8) |
| T9 | `uv run pre-commit run --all-files --show-diff-on-failure` | pass: all six hooks; full suite 5950 passed | [regression.md](regression.md) |
| T10 | four bodies in `evidence/jira-bodies.md`; `pytest -k golden tests/test_jira_format.py` | pass: four bodies, each as ADF JSON and wiki. The eight blocks equal the golden fixtures byte for byte, and `test_golden_bodies` gives 4 passed | [jira-bodies.md](jira-bodies.md) |
| T11 | `evidence/jira/t11_run.py` against the Jira Cloud sandbox, project `KAN` | pass, replanned: webhook step dropped with the operator (polling covers delivery) | [manual-jira.md](manual-jira.md) |

## Deviations

- **No file substitutions were needed.** Every test file the plan names exists. Three
  more Jira test files that the plan does not name (`test_jira_linkage.py`,
  `test_jira_verbs.py`, `test_doctor_jira.py`) run in T9's full suite. The T7 names for
  abuse case 7 are in `test_jira_linkage.py`.
- **Trace names.** `test_migrate_is_idempotent` is `test_migrate_jira_stub_is_idempotent`.
  `test_github_refs_unchanged` is not a test of its own. It stands for the existing
  GitHub tests, which are unchanged. See [unit.md](unit.md#trace-names).
- **T6 `--root`.** The scenarios command, routed to the running daemon, resolved `.`
  against the daemon's working directory. An absolute `--root` fixes it. This is older
  than issue-475 and is noted, not fixed.

## T11: run on 2026-10-07, replanned

First pass (2026-10-06): not executed. The sandbox variables were unset, and the gap was
escalated on #475. The operator then set `JIRA_SANDBOX_SITE`, `JIRA_EMAIL`,
`JIRA_API_TOKEN` and `THE_LOOP_JIRA_WEBHOOK_SECRET` on the daemon host.

Second pass: three of the four facts the fakes cannot prove are now proven against live
Jira Cloud:

- ADF renders as intended;
- `/search/jql` accepts the poller's JQL;
- `myself` equals the author of the-loop's comments.

The fourth, live webhook signing, was dropped with the operator because polling covers
delivery. Signing remains proven by unit test only. The replan and its reasons are in
`testing-plan.md` under T11, and every step is in [manual-jira.md](manual-jira.md).
