---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#460"
status: in-review
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: an orphan tag blocks every release

> Derived from [`bugfix.md`](bugfix.md). The results are in
> [`evidence/verification.md`](evidence/verification.md).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (workflow contract) | yes | `release.yml` checks out `ref: main`, and every `git push` in the release job is `--atomic`. Red before the fix | `uv run pytest -c cli/pyproject.toml cli/tests/test_release_workflow.py` |
| T2 | Integration (lockstep guard) | yes | every `version_files` target and `uv.lock` carry 19.22.0 | `cli/tests/test_version_lockstep.py` |
| T3 | Replay: the race, before | yes | a non-atomic push after `main` moved leaves the tag on the remote (the bug) | scratch bare remote, `cz bump` from uv 0.12.17 |
| T4 | Replay: the race, after | yes | the same push with `--atomic` leaves neither ref on the remote | with T3 |
| T5 | Replay: recovery | yes | on `main` + this PR with the orphan `v19.22.0` present, `cz bump` yields 19.22.1 (not "tag exists"), and the changelog lists only the unreleased commits | with T3 |
| T6 | Replay: no-op from the tip | yes | a second run on a tip that is a fresh bump commit exits 21 or 3, which the job treats as "no release" | with T3 |
| T7 | Regression (full suite) | yes | pre-commit across the repository stays green | `uv run pre-commit run --all-files` |
| T8 | Security | yes (review) | no permission, secret or trust-boundary change | `evidence/security-review.md` |
| T9 | UI / accessibility / snapshot / migration | n/a | | |

## Requirement trace

| Requirement | Tests |
|-------------|-------|
| R1 | T1, T3, T4 |
| R2 | T1, T6 |
| R3 | T2, T5 |
| R4 | T1 (red first) |

## Not covered by an automated test

The runner's own queueing (`concurrency`, `cancel-in-progress: false`) is GitHub
behaviour. T3–T6 replay the job's git and commitizen steps verbatim. The first real
release after merge (expected: 19.22.1 on PyPI) is the live check.
