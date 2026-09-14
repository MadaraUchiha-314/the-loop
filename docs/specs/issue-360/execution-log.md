---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#360"
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: the cursor adapter passes the model as `-m`, an option `cursor-agent` does not have

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-14 | — | **Risk tier 2** (`autonomous-complete`): one string constant in an adapter, a rule written into a capability doc, and tests. No sensitive path is touched — nothing under `.the-loop/**`, no `*schema*`, no `.github/workflows/**`, no auth/secret/credential path — and no trust boundary moves (`evidence/security-review.md`). Tier 2 is below the tier-4 named-security-sign-off threshold. `brainstorming` skipped — the reporter measured the CLI and named the fix; `design-critic-review` not selected (`critics: []` in this repository, so a round would be `unavailable`). No authorized `the-loop execute` reaches this cloud session, so the selection is recorded here and every phase is walked by hand |
| requirements-definition | 2026-09-14 | pending — this branch's PR | [`bugfix.md`](bugfix.md) — two requirements, three abuse cases. Root cause confirmed by building the argv, not by reading the ticket |
| design | 2026-09-14 | pending — this branch's PR | [`design.md`](design.md) — one constant, four decisions, [`decision-125`](../../decisions/decision-125.md) |
| test-planning | 2026-09-14 | pending — this branch's PR | [`testing-plan.md`](testing-plan.md) — thirteen rows, five applicable; every `n/a` carries its reason |
| tasks-breakdown | 2026-09-14 | | [`tasks.md`](tasks.md) — six tasks, red root first |
| implementation | 2026-09-14 | | On `claude/github-issue-360-uav3nz`. TDD: [`evidence/red.md`](evidence/red.md) captured before the fix |
| verification | 2026-09-14 | | [`evidence/verification.md`](evidence/verification.md) — every applicable row plus `make check`; [`evidence/security-review.md`](evidence/security-review.md) — three abuse cases, no findings |
| needs-review | 2026-09-14 | | PR raised with the R10 briefing. Tier 2 permits autonomous completion after the review loop; the merge is still the owner's |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#361](https://github.com/MadaraUchiha-314/the-loop/pull/361) | tasks 1–6: the whole work item | open |

## Progress entries

### 2026-09-14 — the ticket's one-line fix, and the second surface it also breaks

- **Phase:** requirements-definition → design
- **Did:** confirmed the root cause by building the argv rather than by reading the
  adapter (`oneshot_argv('review this', model=…)` → `[…, '-m', 'gpt-5.6-sol']`), then
  traced every reader of `model_flag`.
- **Found, and it widened the spec without widening the diff:** the critic round is not
  the only victim. `the-loop models check` builds the same one-shot argv
  (`modelprobe.py:158`) and reads a **non-zero exit as `refused`** — the harness said no.
  `cursor-agent` exits non-zero on `-m` before it has an opinion about any name, so every
  declared model comes back `refused` on cursor, is cached, and is then **withheld from
  the phase-selection checklist**: a human cannot pick a cursor model at all. A parse
  error about the-loop's own flag was being recorded as the vendor refusing the
  operator's model.
- **Also checked, and it is not affected:** interactive dispatch. `cursor-agent` has no
  pre-assignable session id, so the adapter's `interactive_*` methods raise
  `UnsupportedRunnerError` and no cursor session is ever spawned. The blast radius is
  critics and the probe, and nothing else.
- **Why the repository did not catch it:** the two assertions that named the flag compared
  the adapter's own constant to itself (`("-m", …)` on both sides), and the one test that
  ran the whole critic argv had `-m` written into it. The suite agreed with the bug. The
  new test asserts the argv from `oneshot_argv`, which is what reaches the process.
- **Next:** the red root, then the constant.

### 2026-09-14 — red, one line, and a cache that heals itself

- **Phase:** tasks-breakdown → implementation → verification
- **Did:** tasks 1–6. Wrote the two new assertions and captured the failing run
  ([`evidence/red.md`](evidence/red.md)); changed `model_flag` to `--model` with the
  reason beside it; corrected the three assertions that had pinned `-m`; added the
  verdict-cache test; wrote the rule into `docs/capabilities/review-loop.md` and
  [`decision-125`](../../decisions/decision-125.md).
- **The migration that isn't:** every cursor model probed during the `-m` era is cached
  as `refused`, and a standing `refused` withholds a choice. Nothing has to clear it — a
  verdict records the digest of the argv it was taken against, and `VerdictCache.get`
  drops one whose digest no longer matches (`modelprobe.py:225`). Changing the flag
  changes the digest. That is asserted (T3) rather than assumed, in both directions: the
  cached refusal still withholds under the **old** digest, and no longer does under the
  new one.
- **Checkpoint/tests:** red first, then green. `make check`: 3605 passed, 1 skipped (3603
  before — the two added tests); ruff, ruff format, pyright, `validate_config` clean;
  markdownlint 0 errors over 1103 files.
- **Self-review, three passes.** Pass one found the new verdict-cache test asserting only
  that the choice *is* offerable after the fix — which a broken `offerable` would also
  satisfy — so it now asserts the converse first: still withheld under the old argv's
  digest. Pass two re-read the capability bullet, which ended "`claude` is `--model`;
  `cursor-agent` is `--model`" — two clauses saying one thing; now "Both shipped adapters
  are `--model`." Pass three checked the claim in `design.md` that the duplicated-flag
  warning starts working: it does, but it is `config_findings` over
  `harnesses[<name>].args` (session dispatch), **not** over the `critics[].args` the
  ticket's workaround uses. Corrected rather than dropped, because the distinction is the
  reason the workaround never warned.
- **Security review:** the built-in skill, scoped to this branch's own changes — its
  `origin/HEAD` diff resolved to the whole previous release on this fresh clone, which is
  another work item's paper trail. No findings; the three abuse cases are all "unchanged
  boundary", each mapped to an existing negative test that still passes
  ([`evidence/security-review.md`](evidence/security-review.md)).
- **Out of scope, noted for the owner:** two pieces of drift on `main`, reverted here
  rather than carried into this diff. `uv.lock` still records `the-loopy-one 15.0.0`
  while `cli/pyproject.toml` is at `16.0.0` after the release bump, so any `uv run`
  rewrites one line of the lockfile and every contributor gets a dirty tree; and
  `cli/tests/test_graph_drive_integration.py` writes a portable record into the
  checkout's own `.the-loop/` (`.the-loop/portable/github-octo-repo-15.json` changes
  whenever the suite runs) — the residue issue-339's log already flagged. Neither belongs
  in a bugfix about a flag.
- **Next:** the PR and its briefing.

## Verification results

> **Only when this work item declared `test-planning` away** (issue-179). This item kept
> the plan, so its results live in [`testing-plan.md`](testing-plan.md) §Verification
> results and this section stays as the template left it.

## Design critic review

> Not selected at `phase-selection` — this repository declares no critics
> (`critics: []`), so a round would be recorded `unavailable` and count for nothing. The
> section stays as the template left it.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop | new findings — the one-sided cache assertion, the duplicated capability clause, the `harnesses[].args` vs `critics[].args` mix-up; all three fixed | this log, entry 2 |
| 2 | self | the-loop | zero (converged) | this log, entry 2 |
| 3 | self | the-loop | zero (converged) | this log, entry 2 |
| 4 | critic | — | unavailable — no critic is configured in this repository (`critics: []`); does not count toward `reviews.criticReviewCount` | [`.the-loop/cli-config.yaml`](../../../.the-loop/cli-config.yaml) |
| 5 | security | built-in `security-review` skill | zero — no findings | [`evidence/security-review.md`](evidence/security-review.md) |

## Security review (gate)

- **Mechanism:** the harness's built-in `security-review` skill, scoped to this branch's
  own changes (see [`evidence/security-review.md`](evidence/security-review.md) for why
  the tool's own diff range was wider).
- **Outcome:** pass — no findings. The three abuse cases of
  [`bugfix.md`](bugfix.md) §Security considerations are all "unchanged boundary", each
  mapped to an existing negative test that still passes. The change restores a review
  control that was silently not running rather than relaxing one.
- **Human sign-off:** n/a — risk tier 2, below the tier-4 threshold.

## Final validation evidence

| Acceptance criterion | Proof |
|---|---|
| R1.1 — a resolved model is passed as `--model <name>` | `test_cursor_oneshot_argv_uses_the_long_model_flag`, `test_a_model_resolves_through_the_adapters_flag` (T1) |
| R1.2 — the full critic argv for `harness: cursor` + `model:` | `test_builtin_harness_derives_argv_from_the_adapter` (T2) |
| R1.3 — no model, no flag | `test_oneshot_argv_without_a_model_is_the_plain_one_shot_run`, untouched and passing (T1) |
| R1.4 — fails before, passes after | [`evidence/red.md`](evidence/red.md) → [`evidence/verification.md`](evidence/verification.md) |
| R2.1 — the `model_flag` rule in the capability doc | `docs/capabilities/review-loop.md` §Current behaviour |
| R2.2 — a History row tracing it to issue-360 | `docs/capabilities/review-loop.md` §History, first row |

`make check` green on the final tree: 3605 passed, 1 skipped; 0 type errors; 0 markdown
errors. Full transcript in [`evidence/verification.md`](evidence/verification.md).

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [review-loop.md](../../capabilities/review-loop.md) | §Current behaviour gains the rule that an adapter's `model_flag` is a spelling the harness's own `--help` lists — the long form where a CLI offers both — with the reason (the flag reaches a process the-loop does not parse for, so a wrong one is a dead run, not a degraded one) and the current value for both shipped adapters | `issue-360`, linking this spec and [decision-125](../../decisions/decision-125.md) |

No other capability doc changed. [cli.md](../../capabilities/cli.md) describes
`the-loop models check` as the verb that probes a declared choice, which is still exactly
what it does — the fix changes which flag the probe sends, not what the command promises.

## Documentation

| Document | What changed |
|----------|--------------|
| [decision-125](../../decisions/decision-125.md) | New. Where an adapter's flag spellings come from, why they are not derived from the binary at runtime, and the four alternatives rejected — including editing the locked issue-358 spec that records the wrong belief |
| [decisions.md](../../decisions/decisions.md) | The index row for decision-125 |

No user-facing page under `docs/cli/` or `docs/config/` changed, and the reason is that
none of them ever named a per-harness flag: `docs/config/cli/critics-options.md` says the
model is "passed via the harness's own model flag" and
`docs/config/cli/harnesses-options.md` says the name is passed to it "verbatim". Both
statements were true before this change and are true after it — the defect was that the
adapter's value did not match the CLI, which is a code fact, not a documented one.
