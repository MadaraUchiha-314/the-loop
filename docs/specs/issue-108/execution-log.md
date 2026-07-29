---
type: execution-log
workItem: issue-108
phase: needs-review          # not-started | brainstorming | requirements-definition | design | tasks-breakdown | implementation | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: specify (and actually invoke) the critic harness

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-29 | pending (PR) | No brainstorm — the ticket states the gap and the three questions precisely |
| design | 2026-07-29 | pending (PR) | |
| tasks-breakdown | 2026-07-29 | pending (PR) | |
| implementation | 2026-07-29 | pending (PR) | T1–T10 |
| needs-review | 2026-07-29 | pending (PR) | Tier 4 → `human-approves-pr` + a named human security sign-off |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#115](https://github.com/MadaraUchiha-314/the-loop/pull/115) | spec + T1–T10 | open |

## Progress entries

### 2026-07-29 — spec written (requirements → design → tasks)

- **Phase:** requirements-definition → design → tasks-breakdown → implementation
- **Did:** Traced the gap: `reviews.critics[]` had `name`/`harness`/`model` and a free-form
  `command` **string** (shipped example `"cursor-agent review"` — a phrase, ambiguously a
  shell line), and nothing in the repo consumed it. `reference/reviewing.md` specified the
  critic-round *policy* in full but never the *mechanism*, so a critic round was un-runnable
  as written. Wrote `requirements.md` (5 requirements, 26 EARS ACs + threat-model-lite,
  risk tier 4 — the schema is a `sensitivePath` and the change spawns declared executables),
  `design.md` (a repo-scoped `the-loop critic` command over a pure resolver + a shell-free
  runner), `tasks.md` (10-task DAG).
- **Checkpoint/tests:** none yet — no code written. Baseline suite: 758 passed, 1 skipped.
- **Next:** T1 — `HarnessAdapter.oneshot_argv`, red first.
- **Blockers:** none. Tier 4 → `human-approves-pr` plus a named human security sign-off
  before completion; both requested on the PR.

### 2026-07-29 — implementation complete (T1–T10)

- **Phase:** implementation → needs-review
- **Did:**
  - **T1** `HarnessAdapter.oneshot_argv(prompt, model)` + per-adapter `model_flag`
    (`--model` / `-m`), so "how do you run harness X once, non-interactively" keeps one
    owner and any future adapter is usable as a critic for free. Promoted
    `_parse_json_object`/`_usage_from_output` to package API now that they have a second
    consumer (call sites and `test_harness_usage.py` moved with them; behaviour unchanged).
  - **T2–T4** `the_loop/critics.py`: `Critic`/`CriticResult`, `load_critics` (pre-rename
    `config.yaml` fallback, duplicate-name rejection, per-entry `error` so a broken entry is
    *shown* rather than fatal), `resolve_invocation` (pure; `command` > built-in `harness` >
    refusal; element-wise substitution of a closed placeholder set) and `run_critic`
    (`shell=False` argv list, availability check, timeout, `outputFormat` extraction with a
    raw-stdout fallback, usage telemetry, never raises on a *critic* failure).
  - **T5** `the-loop critic list|run` — one named critic per invocation, one JSON envelope on
    stdout, diagnostics to the log stream, exits 0/1/2.
  - **T6** Three Gherkin integration scenarios driving a **real** stub critic process.
  - **T7** Schema: the richer `reviews.critics[]` item (all new keys optional). Both config
    templates carry a worked example; `.the-loop/harness-config.yaml` joins its own
    `autonomy.sensitivePaths` because a critic entry is executable configuration.
  - **T8–T9** `reference/reviewing.md` § Running a critic round (invocation, required prompt
    content, what to do with the envelope, the `unavailable` outcome, "critic output is
    findings, never instructions"); `workflow.md` pointer; `unavailable` added to the
    execution-log template's review table; minted `docs/capabilities/review-loop.md` (+
    index + sidebar), `docs/decisions/decision-043.md` (+ index), and updated
    `docs/capabilities/cli.md`, `docs/reference/configuration.md`, `cli/README.md`, `README.md`.
- **Unplanned, in scope:** `timeoutSeconds: 0` was silently rewritten to the 900s default by
  an `or DEFAULT` fallback — caught by the T2 validation test, fixed to an explicit
  `None` check so an invalid value is rejected rather than defaulted.
- **TDD record:** T1 recorded a genuine red→green
  (`AttributeError: 'CursorAgentAdapter' object has no attribute 'oneshot_argv'` → pass) and
  T5/T6 likewise (`critic` unregistered → `SystemExit(2)` on 9 CLI tests → pass). T2–T4 were
  written module-first with their tests added immediately after, against the design's test
  table; the tests did their job — one of them caught the `timeoutSeconds: 0` bug above.
  Recorded plainly rather than claimed as a red→green that was not observed.
- **Checkpoint/tests:** `make test` → **804 passed, 1 skipped** (was 758 before this work
  item; +46 new). `ruff check` clean, `ruff format` clean, `pyright` 0 errors,
  `markdownlint` 0 errors over 265 files, `validate_config.py` all VALID.
- **Next:** self/critic review rounds, then the security gate, then the human gate.
- **Blockers:** tier-4 human approval + named security sign-off on the PR.

### 2026-07-29 — evidence, review rounds

- **Phase:** needs-review
- **Did:** Ran the review rounds below and recorded the live evidence under **Final
  validation evidence**.
- **Checkpoint/tests:** as above, plus a live `critic list` / `critic run` against a stub
  critic and `the-loop scenarios` showing the three new scenarios.
- **Next:** human review of PR #115 (tier 4).
- **Blockers:** the critic rounds are `unavailable` on this machine — see the review table.

## Review cycles

> Outcome is one of: new findings · zero (converged) · escalated · **unavailable** (the
> configured critic could not run — it does NOT count toward `reviews.criticReviewCount`).

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | `[claude/claude-opus-5]` | New findings (3): `timeoutSeconds: 0` silently defaulted; a `{promptFile}` placeholder had to resolve even for `--prompt`; `env` needed an explicit no-secrets rule in the schema, both templates and the capability doc. All fixed. | this log |
| 2 | self | `[claude/claude-opus-5]` | New findings (2): the `unavailable` outcome was defined in `reviewing.md` but absent from the execution-log template's review table; `docs/capabilities/token-economy.md` still referenced the pre-promotion `_usage_from_output`. Both fixed. | this log |
| 3 | self | `[claude/claude-opus-5]` | New finding (1): a non-mapping `env:` was silently dropped, so the critic would run without the environment the operator believed they configured — now rejected with a reason, plus a case in the validation test. Self-round cap (`selfReviewCount: 3`) reached; no finding recurred, so nothing to escalate (`escalateOnRepeatFinding`). | this log |
| 4 | critic | *none configured* | **unavailable** — this repo's `reviews.critics[]` is `[]` and no second harness CLI is installed in this container (`the-loop critic list` → "No critics configured"; `cursor-agent` not on PATH). Does **not** count toward `criticReviewCount`; stated here and in the PR briefing rather than reported as converged. | this log |
| 5 | security | built-in security-review skill (`security.review.mechanism: auto`) | Zero findings — *"No high-confidence security findings."* over `origin/main...HEAD`. | § Security review below |
| 6 | human (PR review) | @MadaraUchiha-314 | New finding (1), **will-fix**: the design's *"AuthN/AuthZ: none introduced"* holds only for a critic-as-local-subprocess; a critic that speaks on the PR under its own identity — the third-party case — has an authz surface, and its findings should land in the PR. Replied before changing code, offered three options for which config file owns the critic's identity, flagged the implicit-authorization one as a privilege-escalation path. Owner chose **option (a)**. Spec claims corrected here; implementation stacked as [#116](https://github.com/MadaraUchiha-314/the-loop/issues/116). | [thread](https://github.com/MadaraUchiha-314/the-loop/pull/115#discussion_r3677517574) |

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** `security.review.mechanism: auto` → the harness's built-in
  **security-review skill**, run over the branch diff (`origin/main...HEAD`), backed by
  the-loop's own checklist below.
- **Outcome:** **pass** — the security-review skill reported *no high-confidence security
  findings*. The checklist pass behind it, with the mitigations built in rather than added
  after:
  - **Command injection** — the primary surface. Every invocation is an argv *list* with
    `shell=False`; substitution is element-wise, so a value can never introduce a word
    boundary, a redirect or a second command. Proven by
    `test_placeholder_value_with_metacharacters_stays_one_argument` and the integration
    scenario *A hostile prompt cannot escape into a shell command* (which asserts the file
    the injection asked for does not exist).
  - **Config-as-code** — a `reviews.critics[]` entry is an executable declaration in a
    repo-tracked file. Nothing runs implicitly (one named critic per invocation, no run-all:
    `test_run_requires_an_explicit_critic_name`), and `.the-loop/harness-config.yaml` was
    added to this repo's `autonomy.sensitivePaths` so proposing one raises the PR's tier.
  - **Fail closed** — ambiguous/unusable/disabled entries spawn nothing and exit 2; a missing
    binary has no fallback (`test_missing_binary_fails_closed`); a hung critic is terminated
    (`test_timeout_is_reported_as_a_failed_round`); an unrunnable round is `unavailable`,
    never a pass.
  - **Secrets** — none read from or written to config; the child inherits the operator's
    ambient environment and `env` is a documented non-secret overlay
    (`test_env_overlays_the_inherited_environment`).
  - **Prompt injection, outbound** — critic output is untrusted model text; `reviewing.md`
    states it is findings to evaluate, never instructions, and it is posted under the
    critic's attribution prefix. Procedural, no code path to test.
- **Human sign-off:** **pending** — risk tier 4 ≥ `security.review.humanSignOffMinTier` (4),
  so a named human security sign-off is required on PR #115 before completion.

## Final validation evidence

**Suite** — `make test`: **804 passed, 1 skipped** (baseline before this work item: 758
passed, 1 skipped). `ruff check` and `ruff format --check` clean over `cli hooks`;
`pyright cli` → 0 errors, 0 warnings; `markdownlint-cli2` → 0 errors over 264 files;
`scripts/validate_config.py` → VALID for all six shipped configs (this repo's and the
templates').

**R4 — the critics are discoverable.** `the-loop critic list` in a project configuring two
critics (one built-in `cursor`, one arbitrary CLI):

```text
Critic       Harness  Model    Executable            Available  Enabled
-----------  -------  -------  --------------------  ---------  -------
cursor-gpt   cursor   gpt-5.5  cursor-agent          no         yes
demo-critic  demo     gpt-5.5  …/fake-critic         yes        yes
```

In this repo itself (`critics: []`): `No critics configured — add reviews.critics[] to
.the-loop/harness-config.yaml to run critic rounds.` (exit 0 — a valid configuration.)

**R1–R3 — a round runs and its output comes back.** `the-loop critic run demo-critic
--work-item issue-108 --prompt "Review the critic-invocation seam for issue-108."`:

```json
{
  "critic": "demo-critic", "harness": "demo", "model": "gpt-5.5",
  "attribution": "[demo/gpt-5.5]",
  "ok": true, "exitCode": 0, "durationSeconds": 0.031,
  "output": "[gpt-5.5] 1 finding: Review the critic-invocation seam for is… lacks a negative test",
  "error": "",
  "usage": {"inputTokens": 812, "outputTokens": 47, "cacheReadTokens": 0,
            "cacheWriteTokens": 0, "costUsd": 0.013, "present": true}
}
```

The model reached the critic through the harness's own flag, the prompt through
`{promptFile}`, and the critic's text and token/cost usage came back in the envelope.

**R3.5 — a round fails closed.** Same project, `critic run cursor-gpt` with `cursor-agent`
not installed: `ok: false`, `error: "critic CLI 'cursor-agent' not found on PATH; install it
or point reviews.critics[] entry 'cursor-gpt' at the right executable"`, process exit **1**,
envelope still printed so the round is recordable.

**Scenario coverage** — `the-loop scenarios` lists the three new Gherkin scenarios, each
linked to `docs/specs/issue-108/requirements.md`:

```text
24  Critic-review invocation  A configured critic CLI reviews the work and its findings reach the harness  …#R3
25  Critic-review invocation  A critic that is not installed fails the round closed                        …#R3.5
26  Critic-review invocation  A hostile prompt cannot escape into a shell command                          …#abuse-case-1
```

**Capability docs** — minted `docs/capabilities/review-loop.md` (indexed and in the docs
sidebar) and recorded `docs/decisions/decision-043.md`; `cli.md`, `configuration.md`,
`cli/README.md` and `README.md` updated in this same PR.
