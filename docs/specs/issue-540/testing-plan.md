---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#540"
status: in-review            # design-approval was skipped at phase-selection; the PR approval is the human gate
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: prompts in Markdown files, application strings in one JSON catalog

> Derived from `requirements.md` and `design.md`. The existing suite does most of the
> proving: it already pins today's prompt and message text, so a green run after the move
> is the evidence that rendered output stayed byte-identical (R1.4, R2.5). New tests cover
> the loader, the lookup, the fallback, the sync between the skill templates and the
> packaged prompts, the guard, and packaging.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `prompts.load/render/names`, `strings.t/section/catalog`, fallback, missing file/key errors, name validation | `make test` (`cd cli && uv run python -m pytest -q`) |
| T2 | Regression (existing suite) | yes | every test that pins prompt or message text still passes unchanged, so output is byte-identical | `make test` |
| T3 | Contract (data files) | yes | `en.json` is a flat object of string values with valid keys; placeholders match call-site vars; every `t`/`section` key used in code exists; skill templates equal `prompts/webhook/*.md` | `make test` (`cli/tests/test_strings_catalog.py`, `test_prompts.py`) |
| T4 | Guard (static) | yes | R3.1: AST scan fails on a multi-line prompt-named module constant; a planted fixture proves it fires | `make test` (`cli/tests/test_prompts_guard.py`) |
| T5 | Packaging | yes | the built wheel contains `the_loop/prompts/**/*.md` and `the_loop/strings/en.json`; an installed wheel renders a prompt | `uv build --wheel cli` + `unzip -l` + a venv smoke run |
| T6 | Security / abuse case | yes | `$work_item` / `{name}` inside an untrusted payload come out literal; a prompt name with `..` is rejected; `t` with an unknown key raises | `make test` |
| T7 | Static checks | yes | lint, format, typecheck and config validation stay green | `make check` (ruff, markdownlint, pyright, validate, pytest) |
| T8 | Integration (scenario) | n/a | no new routing behaviour; the existing webhook→session scenarios run in T2 and render through the new loader | — |
| T9 | End-to-end | n/a | the daemon's behaviour does not change; T2 + T5 cover the render path end to end without a live GitHub | — |
| T10 | UI / visual | n/a | the UI is out of scope (requirements § Out of scope) | — |
| T11 | Performance | n/a | one cached file read per prompt per process; nothing measurable | — |
| T12 | Accessibility | n/a | no UI change | — |
| T13 | Migration / upgrade | n/a | no config, schema or state-file change; `promptTemplate`/`spawnTemplate` overrides keep working (covered by existing tests in T2) | — |
| T14 | i18n fallback | yes | a fixture locale with one translated key and one missing key: translated key returns the translation, missing key returns `en`, invalid locale file warns and falls back | `make test` |
| T15 | Manual exploratory | n/a | nothing user-visible changes | — |

## Scenarios & requirement trace

| Row | Requirement(s) | Case |
|-----|----------------|------|
| T1 | R1.2, R1.7, R2.2, R2.4 | loader reads a file; missing prompt raises naming the file; `t` formats vars; missing key raises naming the key |
| T2 | R1.1, R1.3, R1.4, R2.5 | existing dispatcher/interaction/standing/selfdiagnosis/sessions/assignment/slack/prnotice/attachments/bodies/digest tests unchanged and green |
| T3 | R1.6, R2.1, R2.6 | catalog shape; placeholder parity; used keys exist; skill templates identical to packaged prompts |
| T4 | R3.1 | guard passes on the tree; guard fails on a planted multi-line `FOO_PROMPT = """…"""` |
| T5 | R1.5 | wheel lists the data files; `python -c "from the_loop import prompts; prompts.load('webhook/event')"` from the installed wheel |
| T6 | Security abuse 1–2, fail-closed | payload `$work_item {name}` stays literal in the rendered spawn prompt; `prompts.load('../x')` raises `ValueError` |
| T7 | R3.2 (docs lint), NFR no new dependency | `make check` green; `cli/pyproject.toml` dependencies unchanged |
| T14 | R2.3 | fixture `xx.json` via `THE_LOOP_LOCALE=xx` |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none.
- **Fixtures & data:** temporary locale files written by the tests under `tmp_path`;
  the locale directory is injected, so the shipped package is not modified.
- **Credentials:** none.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1–T4, T6, T14 | pytest summary (counts) and the new tests' names | `verification.md` |
| T5 | `unzip -l` excerpt for the data files and the smoke-run output | `verification.md` |
| T7 | `make check` summary | `verification.md` |

## Verification activities

- [x] T1, T3, T4, T6, T14 — `cd cli && uv run python -m pytest -q tests/test_prompts.py tests/test_strings_catalog.py tests/test_prompts_guard.py`
- [x] T2 — `cd cli && uv run python -m pytest -q` (full suite)
- [x] T5 — `uv build --wheel cli -o <tmp>` then `unzip -l <wheel> | grep -E 'the_loop/(prompts|strings)/'` and a smoke import from a fresh venv
- [x] T7 — `make check`

## Verification results

Executed 2026-11-18 at `d0470779`. Raw output: [`evidence/verification.md`](evidence/verification.md).

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1, T3, T4, T6, T14 | `pytest tests/test_prompts.py tests/test_strings_catalog.py tests/test_prompts_guard.py` | 36 passed; guard reports the 6 inline prompts on `origin/main` | [V1](evidence/verification.md#v1--new-tests-t1-t3-t4-t6-t14) |
| T2 | full suite, daemon env vars unset as in CI | 6992 passed. Old-vs-new render hashes identical over 66,174 cases | [V2](evidence/verification.md#v2--full-suite-t2-existing-tests-pin-todays-text) |
| T5 | `uv build --wheel cli`; `unzip -l`; fresh-venv smoke import | 101 prompt files + `en.json` ship; installed wheel renders | [V3](evidence/verification.md#v3--packaging-t5) |
| T7 | ruff format/check, pyright, markdownlint, `validate_config.py` | all green; dependencies unchanged | [V4](evidence/verification.md#v4--static-checks-t7) |

## Review comments
