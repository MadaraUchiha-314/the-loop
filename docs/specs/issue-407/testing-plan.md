---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#407"
status: in-review            # draft | in-review | approved — tier 3: locked with design.md at the PR
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: re-lock into the bump commit, and make a stale lockfile loud

> Derived from [`bugfix.md`](bugfix.md) and [`design.md`](design.md). Planned at
> `test-planning`, results recorded at `verification` (below).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `check_uv_lock`: a member one version behind is reported with both versions and `uv lock`; a member in step passes while registry packages at their own versions are ignored; a lockfile with no editable member is reported | `cd cli && uv run pytest tests/test_version_lockstep.py` |
| T2 | Integration (the guard over the real repository) | yes | the shipped `scripts/check_version_lockstep.py` exits 0 against this repository's actual `.cz.toml` and `uv.lock` — the existing `test_version_files_are_in_lockstep`, now covering the lockfile too | `cd cli && uv run pytest tests/test_version_lockstep.py` |
| T3 | Replay (release job, scratch clone) | yes | the fold-in step on a **real** `cz bump`: `uv.lock` is in the bump commit, the tag names the amended commit, `uv lock --check` is clean afterwards | `docs/specs/issue-407/evidence/verification.md` (recorded transcript) |
| T4 | Replay (release job, no-op path) | yes | a second run of the step with the lockfile already in step leaves the commit SHA and the tag untouched | with T3 |
| T5 | Contract (CI guard) | yes | `uv sync --locked` fails on the pre-fix lockfile and passes on the fixed one — the check ci.yml now runs | with T3 |
| T6 | Contract (resolver window) | yes | `required-version` refuses a uv outside the window and admits one inside it | with T3 |
| T7 | Regression (full suite) | yes | every suite stays green; ruff, ruff format, pyright, markdownlint, `validate_config` | `uv run pre-commit run --all-files` |
| T8 | UI / visual | n/a | | |
| T9 | Snapshot | n/a — messages asserted directly (T1) | | |
| T10 | Security / abuse case | yes (review, not code) | the amend adds one named path; the forced tag is local and unpushed; no permission, secret or published tag changes — read against the job, recorded in the security review | `evidence/security-review.md` |
| T11 | Accessibility | n/a | | |
| T12 | Migration / upgrade | yes | a contributor on a uv below the window gets the refusal with the remedy, not a rewritten lockfile (T6); no state, schema or config migration | with T6 |
| T13 | Manual exploratory | no — the release job's only untestable surface is replayed in T3/T4 | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R2.2 | `check_uv_lock("19.9.1", <member at 19.9.0>)` → one problem naming `the-loopy-one`, `19.9.0`, `19.9.1` and `uv lock` |
| T1 | R2.2 | `check_uv_lock("19.9.1", <member at 19.9.1, fastapi at 0.110.0>)` → `[]` — a registry package's own version is not drift |
| T1 | R2.3 | `check_uv_lock("19.9.1", <no editable member>)` → one problem, *"no editable workspace member"* |
| T2 | R2.2, R2.4 | the script against this repository: red on the pre-fix `uv.lock` (`19.9.0`), green on the committed one |
| T3 | R1.1 | `git show --stat` on the bump commit lists `uv.lock` beside `.cz.toml`, `cli/pyproject.toml` and the four manifests |
| T3 | R1.2 | `git rev-parse v<next>` == `git rev-parse HEAD` after the amend |
| T3 | R1.1 | `uv lock --check` exits 0 on the resulting tree |
| T4 | R1.3 | the step re-run on an already-in-step lockfile prints *"nothing to fold in"*; `HEAD` and `v<next>` unchanged |
| T5 | R2.1 | `uv sync --locked` exits 1 with *"needs to be updated"* on the pre-fix lockfile, 0 on the fixed one |
| T6 | R3.1 | uv 0.8.17 → *"Required uv version `>=0.12, <0.13` does not match the running version"*; uv 0.12.17 → resolves |
| T6 | R3.2 | `ci.yml`, `release.yml`, `the-loop-gate.yml` each pin `version: "0.12.17"` |
| T7 | R1.4, all | `pre-commit run --all-files` green; the release job's no-op path is unchanged code (`if: steps.bump.outputs.released == 'true'`) |

## Requirements not covered by an automated test

- **R1.1–R1.4** (the release job) — no harness runs a GitHub Actions job locally. The
  replay in T3/T4 executes the step's script verbatim on a real `cz bump` in a scratch
  clone, which covers everything except the runner's own `if:` gating; that gate is
  the same expression the four surrounding steps already use.
- **R3.2** — the pin is a literal in three workflow files, read at review.

## Verification results

Recorded at the `verification` gate in
[`evidence/verification.md`](evidence/verification.md).
