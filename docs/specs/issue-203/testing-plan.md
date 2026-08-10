---
type: testing-plan
phase: test-planning
workItem: issue-203
status: approved
approvedBy: []
overrides: {}
---

# Testing plan: an inline `url` for the Slack integration

> Derived from the approved [`requirements.md`](requirements.md) and
> [`design.md`](design.md). Authored at `test-planning`, completed at `verification`.
>
> **This file is executable content** — it names commands an agent runs. Credentials
> appear by reference only; the URLs below are `https://hooks.slack.example/…` fakes that
> reach nothing.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | precedence in `_SlackBase._url()` through `resolve()`: inline only, inline over env, env only, neither; and both transports resolving through the same method | `uv run --project cli python -m pytest -q cli/tests/test_graph_integrations.py` |
| T2 | Integration (scenario) | yes | the URL an operator wrote in the config is the URL `notify` posts to, end to end through `resolve()` and the hook | `uv run --project cli python -m pytest -q cli/tests/test_graph_slack_url_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — the control-plane API is untouched; this work item adds no endpoint and changes no response shape | | |
| T4 | End-to-end | n/a — an end-to-end row would mean posting to a real Slack workspace. the-loop does not test Slack; the HTTP boundary is the contract, and T2 verifies our side of it | | |
| T5 | UI / visual | n/a — no user-facing surface (CLI/daemon only) | | |
| T6 | Snapshot | n/a — no rendered output or serialized artifact changes | | |
| T7 | Performance / load | n/a — one dictionary lookup replaces one environment lookup on a path that already makes an HTTP call | | |
| T8 | Security / abuse case | yes | the three abuse cases of `design.md` § Security design: a non-string `url` refused by the schema, an empty `url` falling back rather than disabling, and the failure message naming sources but never the URL | `uv run --project cli python -m pytest -q cli/tests/test_graph_integrations.py -k "abuse or refused or empty or remedies"` |
| T9 | Accessibility | n/a — no user interface | | |
| T10 | Migration / upgrade | yes (as a **non**-migration) | a CLI config written before this change validates and behaves identically, and the schema `version` is unchanged — the claim that no `migrate-config` step is needed | `uv run python scripts/validate_config.py` + `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py cli/tests/test_migrations.py` |
| T11 | Manual exploratory | n/a — every behaviour is reachable from a unit or integration test; a manual pass would only re-run them by hand | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.2, R1.3 | inline-only resolves to the inline URL; inline + env resolves to the inline URL; env-only resolves to the env URL |
| T1 | R3.3 | `sdk` and `webhook` resolve through the same `_url()` — asserted over both transports |
| T1 | R3.1 | the pre-existing positional constructor (`SlackWebhook("X")`) still builds a working provider |
| T2 | R1.1, R1.2 | `Scenario: a notification is delivered to the URL configured inline` |
| T2 | R1.3 | `Scenario: a configuration with no inline url still reads the environment` |
| T8 | R1.4 / abuse 1 | a non-string `url` fails schema validation |
| T8 | abuse 2 | an empty `url` falls back to the environment |
| T8 | R2.1 / abuse 3 | the failure names the config key and the env var, and contains neither URL |
| T10 | R3.2 | the schema `version` is unchanged; a pre-change config validates |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. Every row runs offline — the Slack HTTP boundary is
  faked in-process, and no row makes a network call.
- **Fixtures & data:** in-test config mappings and fake webhook URLs on the reserved
  `hooks.slack.example` host. No fixture files are added.
- **Credentials:** none. `THE_LOOP_SLACK_WEBHOOK_URL` is set and deleted **by name**
  through `monkeypatch` within tests; no real webhook exists in this repository.
- **Bring-up:** `make install-dev` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent rows
  unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T8 | unit + abuse-case run output, with counts | `unit.md` |
| T2 | the Gherkin scenario table and the run output | `integration.md` |
| T10 | `validate_config.py` output and the unchanged-`version` check | `unit.md` |
| all | the whole-suite and repository gates (`make test`, `make lint format-check typecheck validate`) | `gates.md` |

Redaction: nothing captured contains a credential — the only URLs in the output are the
`hooks.slack.example` fakes — so the evidence is committed as captured.

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_graph_integrations.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_graph_slack_url_integration.py`
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests/test_graph_integrations.py -k "refused or empty or remedies"`
- [x] T10 — `uv run python scripts/validate_config.py` and `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py`
- [x] Whole suite — `make test`
- [x] Repository gates — `make lint format-check typecheck validate`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `pytest -q cli/tests/test_graph_integrations.py` | pass — 23 passed; 6 of them red before the source change | [`evidence/unit.md`](evidence/unit.md) |
| T2 | `pytest -q cli/tests/test_graph_slack_url_integration.py` | pass — 3 passed; 2 of the 3 verified red against the pre-change resolver (the third is the R3 regression guard, green on both sides) | [`evidence/integration.md`](evidence/integration.md) |
| T8 | `pytest -q cli/tests/test_graph_integrations.py -k "refused or empty or remedies"` | pass — 9 passed, 14 deselected (the selector also picks up the pre-existing transport-refusal tests) | [`evidence/unit.md`](evidence/unit.md) |
| T10 | `uv run python scripts/validate_config.py`; `pytest -q cli/tests/test_docs_parity.py` | pass — 7 configs VALID; 5 parity assertions pass; `CURRENT_CONFIG_VERSION` unchanged at `0.4.0` and no `version` line in the schema diff | [`evidence/unit.md`](evidence/unit.md) |
| Whole suite | `make test` | pass — 1796 passed, 1 skipped (1782 before this work item) | [`evidence/gates.md`](evidence/gates.md) |
| Gates | `make lint format-check typecheck validate` | pass — ruff clean, 0 markdown errors, pyright 0 errors, 7 configs VALID | [`evidence/gates.md`](evidence/gates.md) |

**Not executed:** none. Every row marked `yes` ran; the `n/a` rows carry their reason in
the matrix.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
