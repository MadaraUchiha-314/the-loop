# Verification evidence: issue-217

Executed 2026-08-12 by the implementing session, per
[`../testing-plan.md`](../testing-plan.md). One section per activity; raw
output in fenced blocks.

## T1 + T2 + T8 — the e2e suite (scenarios, meta-tests, abuse-case negatives)

```console
$ uv run --project cli python -m pytest -q cli/tests/test_pdlc_e2e_integration.py
..............                                                           [100%]
14 passed in 0.47s
```

Seven scenarios (happy-path, trivial-tier, ask-reply, gate-rejection,
review-rejection, gh-unreachable, loop-prevention) plus seven harness
meta-tests (directory↔test lockstep, manifest well-formedness, no-manifest /
unknown-step / missing-fixture refusals, first-divergence event matcher, the
fake transport's unknown-operation tripwire).

## T3 — scenario discovery (`the-loop scenarios`)

```console
$ uv run --project cli python -m the_loop scenarios --format table | grep "PDLC process conformance" | head -3
157  PDLC process conformance, end to end   a tier-3 work item flows ticket → complete with no interventions      docs/specs/issue-217/requirements.md#R1, #R2.3   cli/tests/test_pdlc_e2e_integration.py:6x
158  PDLC process conformance, end to end   a trivial-tier item completes with declared skips recorded as skips   docs/specs/issue-217/requirements.md#R2.3        cli/tests/test_pdlc_e2e_integration.py:8x
159  PDLC process conformance, end to end   the agent escalates via the ask seam and the operator's reply …       docs/specs/issue-217/requirements.md#R2.3        cli/tests/test_pdlc_e2e_integration.py:9x
```

All 14 tests are listed with their `Requirement:` links attributed to the
right scenario (a first pass had the module-level `Requirement:` shifting
attribution by one row; moving each `Requirement:` above its `Scenario:`
fixed it — recorded as self-review finding 1).

## T7 — suite runtime

The 14-test e2e module runs in **0.47s**; the whole suite went from ~84s
(1872 passed + 1 skipped baseline) to 85.49s (1886 passed + 1 skipped) —
within the "a few seconds" budget (NFR3).

## T12 — docs parity

```console
$ uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py
(runs inside the full suite below — passed)
```

## T14 — lint / format / types / markdown

```console
$ uv run ruff check cli hooks
All checks passed!
$ uv run ruff format --check cli hooks
197 files already formatted
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
$ npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Summary: 0 error(s)
$ uv run python scripts/validate_config.py
(all listed configs VALID)
```

## T15 — whole-suite regression

```console
$ uv run --project cli python -m pytest -q cli
1886 passed, 1 skipped in 85.49s (0:01:25)
```

Baseline before this work item: 1873 collected (1872 passed + 1 skipped);
after: +14, no failures, no new skips.
