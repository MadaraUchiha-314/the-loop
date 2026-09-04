---
type: testing-plan
phase: test-planning
workItem: "issue-318"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: the env file the CLI config names

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `envfile.parse`: the grammar (comments, blanks, `export`, double/single/unquoted values, escapes, trailing comments, duplicates, invalid names, unterminated quotes, no interpolation); `envfile.load`: absent-only, missing, not a regular file, unreadable, mode warning, no values in any log line; `cli_config.resolve_env_file` / `load_env_file`: config-relative, `~`, absolute, wrong types, lenient config read; `cli.main`, `daemon_entry.main`, `api.serve.main` each call the loader first | `uv run --project cli python -m pytest -q cli/tests/test_envfile.py cli/tests/test_cli_config.py` |
| T2 | Integration (scenario) | yes | the Gherkin scenario: a config naming the Slack token variable and an env file carrying it; `the-loop` run through `cli.main`; the variable present afterwards, untouched when it was already exported | `uv run --project cli python -m pytest -q cli/tests/test_envfile_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API route changes; the schema the dashboard renders gains one block, covered by T10 | | |
| T4 | End-to-end | n/a — the entry points are exercised in-process with the daemon and service runs faked; a real daemon needs tmux and a listening port | | |
| T5 | UI / visual | n/a — the Settings tab renders the block from the schema, as every block | | |
| T6 | Snapshot | n/a — field assertions on two small dataclasses | | |
| T7 | Performance / load | n/a — one file read per process start | | |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A5 (`design.md` § Security design) | `uv run --project cli python -m pytest -q cli/tests -k "never_carries_a_value or readable_by_others or malformed_lines_are_skipped or environment_wins_over_the_file or parent_path_is_honoured"` |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | yes | a config without `env` behaves as before (`load_env_file` → `None`, nothing logged); a config with `env.file` validates against the authored schema and the packaged copy is byte-identical; `CURRENT_CONFIG_VERSION` unchanged; a stale-version config loads no env file and is still refused by the command | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_migrations.py cli/tests/test_envfile.py -k "parity or migrat or without_an_env or stale"` and `make validate` |
| T11 | Manual exploratory | n/a — the reviewer's walk-through is the PR briefing's "what to check" | | |
| T12 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T13 | Security review (gate) | yes | the-loop checklist against A1–A5, recorded as evidence; tier 3 needs no human sign-off (`humanSignOffMinTier: 4`) | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.4 | the grammar, line by line |
| T1 | R1.5 | a present name is left alone and reported as skipped |
| T1 | R1.3 | relative → the config's directory; `~` expanded; absolute honoured |
| T1 | R1.1, R2.6 | no `env` → nothing; a stale or unparseable config → nothing, no raise |
| T1 | R2.1, R2.2, R2.3, R2.4, R2.5 | missing, unreadable, malformed, readable-by-others; no value in any record |
| T1 | R1.2 | the three entry points call the loader before their own work |
| T2 | R1.2, R1.5, R1.6 | `Scenario: The Slack token comes from the env file the config names` |
| T8 | A1–A5 | one negative test each, named in `design.md` § Security design |
| T10 | R1.1, R3.1 | schema parity, docs parity, no migration |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. The poller's and the service's `run`/`main` are
  monkeypatched at the entry-point boundary; nothing binds a port.
- **Fixtures & data:** temp directories per test; env files written by the tests.
- **Credentials:** none. `THE_LOOP_SLACK_BOT_TOKEN` and friends are set to dummy values
  inside tests — by name, never a real token; `monkeypatch` restores the environment.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T10, T12 | command, counts, duration, raw tail of the output; red → green per task | `verification.md` |
| T13 | the abuse-case table with verdicts and the tests that close each | `security-review.md` |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_envfile.py cli/tests/test_cli_config.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_envfile_integration.py`
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests -k "never_carries_a_value or readable_by_others or malformed_lines_are_skipped or environment_wins_over_the_file or parent_path_is_honoured"`
- [x] T10 — `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_migrations.py cli/tests/test_envfile.py -k "parity or migrat or without_an_env or stale"` and `make validate`
- [x] T12 — `make check`
- [x] T13 — `evidence/security-review.md`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_envfile.py cli/tests/test_cli_config.py` | pass — 45 passed | [`evidence/verification.md`](evidence/verification.md) |
| T2 | `uv run --project cli python -m pytest -q cli/tests/test_envfile_integration.py` | pass — 2 passed (the two scenarios) | [`evidence/verification.md`](evidence/verification.md) |
| T8 | `uv run --project cli python -m pytest -q cli/tests -k "never_carries_a_value or readable_by_others or malformed_lines_are_skipped or environment_wins_over_the_file or parent_path_is_honoured"` | pass — 5 passed (A1–A5) | [`evidence/verification.md`](evidence/verification.md) |
| T10 | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_migrations.py cli/tests/test_envfile.py -k "parity or migrat or without_an_env or stale"` and `make validate` | pass — 53 passed; seven configs VALID | [`evidence/verification.md`](evidence/verification.md) |
| T12 | `make check` | pass — lint (ruff, markdownlint over 957 files), format, pyright, config validation, full suite: 3020 passed, 1 skipped | [`evidence/verification.md`](evidence/verification.md) |
| T13 | the-loop checklist over A1–A5 | pass; no human sign-off at tier 3 | [`evidence/security-review.md`](evidence/security-review.md) |

**Not executed:** none.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
