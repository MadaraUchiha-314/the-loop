---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#433"
status: approved
approvedBy: ["the-loop"]     # locked with bugfix.md; tier 2
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: two bugs in the `hooks[]` declaration loader

> Derived from [`bugfix.md`](bugfix.md). Planned at `test-planning`, results recorded at
> `verification` — see [`evidence/verification.md`](evidence/verification.md).

## What "proved" means here

Both defects are in one pure function with no I/O, so unit tests over the loaded mapping
are the proof, plus one test through the real YAML loader and the `the-loop hooks`
command, because the ticket's reproduction is that path and because the YAML 1.1 premise
is the thing most likely to move under us. A negative control on the unfixed tree shows
the new tests are evidence of a fix, not of a suite that never had the bug.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (loader, bug 1) | yes | the documented example, through `yaml.safe_load`, loads with `Entry.on` naming the points; the test first asserts the key arrived as `True` (R1.1, R1.4) | `tests/test_lifecycle_declaration.py` |
| T2 | Unit (loader, both spellings) | yes | a quoted `"on"` still loads; both spellings on one entry are refused naming the entry (R1.2, R1.3) | same |
| T3 | Unit (loader, bug 2) | yes | an unknown key of type `int`, `NoneType`, `bool` raises `HooksConfigError` naming the entry and the key; mixed-type unknown keys are all named (R2.1, R2.2) | same |
| T4 | Command (the ticket's reproduction) | yes | a config file with the documented bare `on:`, read by the real loader, is reported by `the-loop hooks --format json` with exit 0 and no `error` (R1.5) | `tests/test_hooks_cmd.py` |
| T5 | Negative control | yes | T1–T4 fail on the unfixed loader with the ticket's exact `TypeError` texts (R2.3) | `git stash` of `declaration.py` + T1–T4 |
| T6 | Regression (module) | yes | every existing declaration and command test still passes, in particular the unknown-key test whose message wording changed | the two modules |
| T7 | Regression (full suite) | yes | nothing else reads the changed message or the key normalisation | `cd cli && uv run python -m pytest -q` |
| T8 | Static | yes | `ruff check`, `ruff format --check`, `pyright cli`, `markdownlint` on the docs touched | `make lint`, `make format-check`, `make typecheck` |
| T9 | Contract (OpenAPI) | n/a — no route, parameter or response changed | | |
| T10 | End-to-end (live) | n/a — no daemon, network or GitHub behaviour changed; T4 covers the command | | |
| T11 | Security / abuse case | yes | the normalisation maps exactly one key and widens nothing; `_read_on` still refuses a non-catalog point; the refusal path is total over any key type | review + T2, T3 |
| T12 | Migration / upgrade | n/a — a config that loaded before still loads to the same `Declaration`; a config that was refused for this reason now loads, which is the fix | | |
| T13 | UI / visual, accessibility, performance, snapshot | n/a | | |
| T14 | Manual exploratory | no — the ticket's three reproductions are automated as T1, T3 and T4 | | |

## Scenarios & requirement trace

| Row | Acceptance criterion | Scenario / case |
|-----|----------------------|-----------------|
| T1 | R1.1, R1.4 | `DOCUMENTED_ENTRY` (the options page's first entry, verbatim) → `True in loaded`, `Entry.on == ("work_item_start", "session_spawn")`, `required is True` |
| T2 | R1.2, R1.3 | `"on": [...]` loads; `{"on": [...], True: [...]}` → `HooksConfigError` containing `entry 'a'` and `twice` |
| T3 | R2.1, R2.2 | keys `1`, `None`, `False` → `HooksConfigError` containing `entry 'acme'`, `repr(key)` and the valid keys; `{"bogus": 1, 2: 3}` names both |
| T4 | R1.5 | file text `on: [work_item_start]` → exit 0, `report["hooks"][0]["on"] == ["work_item_start"]` |
| T5 | R2.3 | the same tests on the stashed loader: `TypeError: sequence item 0: expected str instance, bool found` and `'<' not supported between instances of 'int' and 'str'` |
| T11 | Security considerations | `on: [session.spawned]` is still refused after normalisation (existing `test_on_may_name_only_catalog_points`) |

## Verification environment

- Python 3.11, `uv` 0.12.17 (the version `.github/workflows/ci.yml` pins), `uv sync --locked`.
- PyYAML from `uv.lock`; the premise assertion in T1 records whether it still resolves
  the bare `on` to a boolean.
- Run from `cli/`, the working directory the pre-commit hook and `make test` use
  (issue-412).
