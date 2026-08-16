# Evidence: final validation

Every activity in [`testing-plan.md`](../testing-plan.md) § Verification activities, as
run. The sweep that found the defects is in [`sweep.md`](sweep.md).

Redaction: pytest and tool output only — no tokens, hostnames or personal data.

## T9b — the whole suite under the lag (the regression test)

```console
$ uv run --project cli python -m pytest -q --dispatch-lag=0.5 cli
........................................................................ [ 97%]
................................................................         [100%]
2223 passed, 1 skipped in 563.02s (0:09:23)
```

Zero failures where the same command found two before the fix. This is the acceptance
criterion for R1.4 (no test in `cli/tests/` fails under `--dispatch-lag=0.5`) and the
proof for R1.3.

## T9c — the clean suite, and the cost of the default path

```console
$ uv run --project cli python -m pytest -q cli
2223 passed, 1 skipped in 117.67s (0:01:57)
```

Baseline before any change on this branch was `2223 passed, 1 skipped in 122.44s`. The
option is inert unless asked for (R2.2): same result, same band — the 5-second difference
is run-to-run noise, and there is one float comparison per test between them.

## T2 — the two fixed files, unlagged

```console
$ uv run --project cli python -m pytest -q \
    cli/tests/test_webhook_routing_integration.py cli/tests/test_poller_integration.py
42 passed in 12.80s
```

Both scenarios still prove what they always proved. The fixes changed *when* each test
looks, not what it claims: the delivery-count checks that used to be waits are still there
as assertions.

## T8 — the lag has no caller in production code

```console
$ rg -n "dispatch.lag" cli/the_loop
$ echo $?
1
```

No match. `--dispatch-lag` exists in `cli/tests/conftest.py` only: there is no environment
variable, config key or CLI flag that reaches it from the daemon, the service or the SDK,
and its patches unwind with the pytest fixture that made them.

## T13 — lint, format, typecheck, schema validation

```console
$ uv run ruff check cli hooks
All checks passed!

$ uv run ruff format --check cli hooks
229 files already formatted

$ uv run pyright cli
0 errors, 0 warnings, 0 informations

$ uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml

$ npx markdownlint-cli2 "**/*.md"
Linting: 746 files
Summary: 0 issues in 0 files
```

## Re-run after the rebase onto `main` (f869ac0)

The numbers above were measured on the pre-rebase base. `main` moved by two commits
(PR #255 and the 10.3.1 bump) and the branch was rebased at the maintainer's request, so
every claim was measured again rather than carried over. #255 adds two tests, hence 2225
where the earlier runs report 2223.

```console
$ cd cli && uv run python -m pytest -q                     # CI's own invocation
2225 passed, 1 skipped in 118.14s (0:01:58)

$ uv run --project cli python -m pytest -q --dispatch-lag=0.5 cli
2225 passed, 1 skipped in 562.87s (0:09:22)

$ uv run ruff check cli hooks && uv run ruff format --check cli hooks
All checks passed! · 229 files already formatted

$ uv run pyright cli
0 errors, 0 warnings, 0 informations

$ npx markdownlint-cli2 "**/*.md"
Linting: 756 files · Summary: 0 issues in 0 files

$ uv run the-loop check issue-251 --recompute --fail-on block   # the-loop's own gate
issue-251: UNMET (at phase-selection) — WAIT, exit 0
```

The gate's `WAIT` is the expected state of an open PR: the work item is parked at the
human phase-selection gate, which `--fail-on block` deliberately does not fail on.

## What is not claimed

- **The organic failure was not reproduced.** The ticket's own method — run the suite
  after something that burns wall-clock — is a coin toss by construction, and this
  container's timing is not the CI runner's. What is claimed instead is stronger and
  repeatable: with the dependent write delayed, each test fails on **every** run before
  the fix and on **none** after it.
- **`--dispatch-lag=0.5` is one value.** It is enough to separate the two events here by
  three orders of magnitude, not a proof that no ordering hazard exists at any lag. The
  suite passing at 0.5s says the shape this ticket is about is gone, not that the suite is
  provably free of every race.
