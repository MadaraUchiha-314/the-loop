---
type: testing-plan
phase: test-planning
workItem: issue-157
status: approved              # draft | in-review | approved
approvedBy: []
overrides: {}
---

<!-- Written per the `the-loop:writing` skill. -->

# Testing plan: `the-loop install`/`upgrade` supports the Cursor plugin

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md).
> Authored at `test-planning`, completed at `verification`.
>
> **This file is executable content.** Review the commands like code. No credentials are
> involved — every command runs this repository's own test suite and linters, offline.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | every branch of `plan_cursor` and `_cursor_clone_steps` as *the argv/state a given (probe result, verb, scope, filesystem) produces*: harness-CLI route, clone, pull, `already`, the three skips, dry-run inertness, component resolution | `make test` |
| T2 | Integration (scenario) | yes | the two end-to-end command paths through `install_cmd`, with a Gherkin docstring each: a default no-argument run on a machine with `cursor-agent` present, and a `--format json` run whose records a setup script can act on | `make test` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API surface. `the-loop install` is a CLI verb; `docs/api-specs/openapi` is untouched. | | |
| T4 | End-to-end | n/a — a true e2e would need a real Cursor installation, which is precisely what this environment does not have (see `requirements.md` § open question 1). The command layer is covered at T2 and the plan/execute seam at T1; what is left unproven is Cursor's own acceptance of the clone, which the-loop cannot assert about a harness it does not ship. Stated rather than silently dropped. | | |
| T5 | UI / visual | n/a — no user-facing surface (`design.uiArtifacts` produces nothing for CLI work). | | |
| T6 | Snapshot | n/a — the report table already has assertions on its rows at T1/T2; freezing the rendered text would test the renderer #152 shipped, not this change. | | |
| T7 | Performance / load | n/a — two bounded `--help` probes and one `git` invocation per run, both already bounded by the existing timeouts. | | |
| T8 | Security / abuse case | yes | the four abuse cases in `requirements.md`: an invalid `--from` never reaches `git` or a URL; an occupied non-checkout path is left byte-identical; `--dry-run` touches nothing; a project-scoped request never becomes a user-level clone | `make test` |
| T9 | Accessibility | n/a — no UI. | | |
| T10 | Migration / upgrade | yes | nothing configured changes shape, and that is the claim worth proving: a CLI config and a harness config written before this change still validate, and a `the-loop install` invocation written against #152 still selects the same components on a machine without `cursor-agent` | `make validate`, `make test` |
| T11 | Manual exploratory | yes | read `the-loop install --help` and the rewritten docs as an operator who uses Cursor: is it obvious which route will run on *their* machine, and what to do when it skips? | manual |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R5.1 | `cursor-agent` reports a plugin surface → the same two harness-CLI steps Claude drives |
| T1 | R1.1, R4.1, R4.2 | no surface, no clone, install → `git clone -- https://github.com/<repo>.git <dir>` |
| T1 | R1.2, R4.1 | no surface, clone present, upgrade → `git -C <dir> pull --ff-only` |
| T1 | R1.3 | upgrade with no clone → `skipped`, naming the install command |
| T1 | R4.3 | install with the clone already present → `already`, nothing run |
| T1 | R4.4 | destination exists but has no `.git` → `skipped`, naming the path |
| T1 | R4.5 | `git` absent → `skipped`, naming the binary and the manual command |
| T1 | R2.1, R2.2 | `cursor-agent` on `PATH` → in the default set; absent → not in it |
| T1 | R2.3, R2.4 | `all` includes `cursor` when undetected; `cursor` named explicitly is accepted |
| T1 | R3.1 | a probed surface that takes `--scope` receives the requested scope |
| T1 | R4.6 | `--dry-run` reports the plan; `already` and `skipped` survive it unchanged |
| T1 | R5.2 | `plugin marketplace` without a working `plugin install` → fallback, not a failed install |
| T1 | R5.3 | a hanging/erroring `cursor-agent` → fallback, no propagated failure |
| T2 | R1.4, R2.1 | default run on a machine with both harnesses: every component reported, one component's skip does not stop another |
| T2 | R4.6 | `--format json` emits Cursor's steps as records with the same keys |
| T8 | abuse case 1 | invalid `--from` (including `--upload-pack=…`) refuses the plan; no `git` call, no URL |
| T8 | abuse case 2 | occupied non-checkout path is byte-identical after the run |
| T8 | abuse case 3 | `--dry-run` creates no directory and runs no `git` |
| T8 | abuse case 4 / R3.3 | `--scope project` never produces a clone step |
| T10 | non-functional | both shipped configs still validate; component resolution unchanged where `cursor-agent` is absent |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. Every test drives fakes — a fake `PATH`, a fake HOME
  under `tmp_path`, and a recording runner. **No test starts a real `git` or reaches the
  network.**
- **Fixtures & data:** none beyond `tmp_path` directories the tests create.
- **Credentials:** none. No command here touches a secret.
- **Bring-up:** `make install-dev` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T8 | pytest output for the install tests — red first, then green — plus the full suite | `unit.md` |
| T2 | pytest output for the integration scenarios | `unit.md` |
| T10 | `make validate` output, and the-loop's own gate | `checks.md` |
| all | `make lint`, `make format-check`, `make typecheck` | `checks.md` |
| T11 | the real command's `--help` and four `--dry-run` runs on this machine | `operator-view.md` |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_install.py`
- [x] T8 — the same file, `-k "invalid or dry_run or project or occupied or exactly"`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_install_integration.py`
- [x] T1/T2/T8/T10 — `make test` (full suite: no regression from the dispatch change)
- [x] T10 — `make validate`
- [x] all — `make lint`, `make format-check`, `make typecheck`
- [x] T11 — run the real command (`--help`, and `--dry-run` for install, upgrade and
      project scope, plus an invalid `--from`) and read the rewritten docs as a Cursor
      operator; record whether the route and the recovery are obvious

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_install.py` | red first (22 failed, 40 passed — `cursor` rejected as unknown), then **64 passed** | [`evidence/unit.md`](evidence/unit.md) |
| T8 | the same file, `-k "invalid or dry_run or project or occupied or exactly"` | 21 passed, 43 deselected | [`evidence/unit.md`](evidence/unit.md) |
| T2 | `uv run --project cli python -m pytest -q cli/tests/test_install_integration.py` | 13 passed | [`evidence/unit.md`](evidence/unit.md) |
| T1/T2/T8/T10 | `make test` | 1366 passed, 1 skipped | [`evidence/unit.md`](evidence/unit.md) |
| T10 | `make validate` | all six configs/templates valid, unchanged | [`evidence/checks.md`](evidence/checks.md) |
| all | `make lint`, `make format-check`, `make typecheck` | ruff clean · markdownlint 0 errors over 432 files · 166 files formatted · pyright 0 errors | [`evidence/checks.md`](evidence/checks.md) |
| — | `the-loop check issue-157 --recompute` | `UNMET (at requirements-approval)` — the normal state of an open PR | [`evidence/checks.md`](evidence/checks.md) |
| T11 | ran the real command on this machine: `--help`, plus `--dry-run` for install, upgrade and project scope, plus an invalid `--from` | finding below | [`evidence/operator-view.md`](evidence/operator-view.md) |

**T11 finding, and the doc edit it caused.** Run as an operator would run it, the four
outcomes are self-explaining: each row's Detail column carries both the reason and the
recovery verbatim (*nothing to upgrade: no checkout at … ; run `the-loop install cursor`
first*), so recovering from a skip never requires opening the docs. The one question the
command *cannot* answer before you run it is **which of the two routes will run on your
machine** — the first draft of `docs/cli/commands/install.md` explained the probe in prose
and left the reader to infer it, so the Cursor section now leads with the decision table
(what `cursor-agent` reports → what runs). The `--from` refusal was confirmed to stop at
plan time with exit 2 and no `~/.cursor` created.

What remains genuinely unproven is on Cursor's side — whether a cloned plugin loads in
Cursor **CLI** mode, and what `cursor-agent plugin --help` prints. Neither is assertable
from here (see T4 and open questions 1–2); both are recorded rather than papered over.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.

*None yet.*
