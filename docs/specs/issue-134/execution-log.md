---
type: execution-log
workItem: "issue-134"
phase: needs-review
status: in-progress
---

# Execution Log: say where a spawned session takes its answers from — CLI or the work item

> Append-only log of progress for the user's visibility. The-loop keeps the work item's
> phase label in sync with the `phase` front-matter above, and self-checks (runs tests at
> logical checkpoints) recording the outcome here.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-04 | — | Scope taken straight from the issue: a cli-config knob, the prompt carrying it, and the artifact-iteration rule. |
| design | 2026-08-04 | — | Two-value enum (no `auto`), directive as a constant in code, invariant artifact rule — [decision-051](../../decisions/decision-051.md). |
| tasks-breakdown | 2026-08-04 | — | 11 tasks; the fail-safe (task 2) and the templates (task 5) carry the security-relevant behaviour. |
| implementation | 2026-08-04 | — | All 11 ticked. |
| needs-review | 2026-08-04 | — | Awaiting human approval on the PR **and** a named security sign-off (effective tier 4 — see § Security review). |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#139](https://github.com/MadaraUchiha-314/the-loop/pull/139) | All tasks 1–11 | open |

## Progress entries

### 2026-08-04 — Spec written; the two judgement calls settled before any code

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** Wrote requirements/design/tasks. Two calls were worth settling up front because
  they shape the whole change: (1) **no `auto` mode** — deriving from `routing.runner`
  would be a static alias, since `runner` is receiver-global; (2) **the artifact rule is an
  invariant, not a third setting** — the issue states it absolutely, and a configuration in
  which generated artifacts are reviewed nowhere durable is not one worth offering. Both
  recorded in decision-051 and flagged as review items rather than resolved silently.
- **Checkpoint/tests:** n/a (spec phase). Baseline suite green (969 passed, 2 skipped).
- **Next:** implementation, test-first for the wiring.

### 2026-08-04 — Implementation, red→green

- **Phase:** implementation
- **Did:** `cli/the_loop/interaction.py` (resolution + the two directive constants +
  `apply_directive`), the `routing.interaction` schema block, the dispatcher wiring at its
  single `_render_prompt` choke point, `$interaction_directive` in both prompt templates
  and both built-in fallbacks, the resolved mode on both `session.spawned` emits, both
  config files, the skill rules, the operator docs, the capability doc and decision-051.
- **Checkpoint/tests:**
  - Red first (tests written before the wiring):
    `pytest cli/tests/test_interaction*.py` → **12 failed, 25 passed**, including
    `TypeError: RoutingConfig.__init__() got an unexpected keyword argument 'interaction'`.
  - Green after the dispatcher wiring and the template edits: **37 passed**.
  - Red again for the docs contract, as designed:
    `test_p4_every_schema_leaf_is_documented` →
    `in the schema but undocumented … webhooks.ghWebhook.routing.interaction.mode`;
    green after the routing-options page.
  - Honest note on TDD order: `interaction.py` itself (task 1) was written **before** its
    unit tests, so only tasks 2/4/9 have a genuine recorded red→green. The module is pure
    functions with no I/O, and every one of its behaviours is now pinned.
  - Full suite: **1011 passed, 2 skipped**.
- **Next:** self-review rounds.

### 2026-08-04 — Rebased onto main; decision renumbered 050 → 051

- **Phase:** needs-review
- **Did:** Rebased onto `origin/main` at the reviewer's request. Main had moved four
  commits (issue-135's short control keywords, issue-137's `reset`, two version bumps),
  producing five conflicts. Resolutions:
  - **`decision-050` collided.** issue-137 claimed 050 on main while this branch was open,
    so this work item's decision became **051** — file, heading, index row and all 13
    references. Main's 050 is byte-identical to its merged form, and the four issue-137
    files a careless rename would have corrupted (`sessions_cmd.py`,
    `capabilities/cli.md`, `capabilities/interactive-sessions.md`,
    `cli/commands/sessions.md`) were restored from main and verified untouched.
  - **Control keywords** (both `cli-config.yaml` files): took main's new short form
    (`the-loop start`), kept the `interaction` block after it. Nothing in this work item
    referenced the old `the-loop:<verb>-execution` shape — checked, not assumed.
  - **Capability history table:** kept *both* rows (issue-134 and issue-135), newest first.
  - **`uv.lock`:** the second commit had in fact carried the 136-line `uv run` reformat
    despite an earlier claim that it was reverted. The rebase surfaced it; it is now
    dropped entirely and `uv.lock` is byte-identical to main.
- **Checkpoint/tests:** full suite **1067 passed, 2 skipped** on the rebased branch (up
  from 1011 — main brought issue-137's tests). ruff, pyright, markdownlint and config
  validation all clean.
- **Next:** human approval + the tier-4 security sign-off.

## Review cycles

> Outcome is one of: new findings · zero (converged) · escalated · **unavailable** (the
> configured critic could not run — it does NOT count toward `reviews.criticReviewCount`).

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (this session) | new findings — see below | this log |
| 2 | self | the-loop (this session) | new findings — see below | this log |
| 3 | self | the-loop (this session) | new findings — see below | this log |
| 4 | self | the-loop (this session) | zero (converged) | this log |
| — | critic | none configured | **unavailable** — `reviews.critics: []` in this repo, so no critic round could run; it does not count toward `criticReviewCount` | [harness-config.yaml](../../../.the-loop/harness-config.yaml) |
| 5 | security | the-loop checklist | pass, with a human sign-off **pending** — see § Security review | this log |

**Round 1 findings (fixed).**

1. `reload()`'s docstring enumerates what swaps live and did not mention the interaction
   mode. It *does* swap live (it is read from `self.config` at dispatch time), so the
   docstring was wrong rather than incomplete — and that docstring is the only place the
   live/restart split is written down.
2. A test asserted only that `RoutingConfig.from_mapping({"interaction": {"mode": "cli"}})`
   produced a truthy mode, which any string satisfies. Replaced with equality plus a check
   that the resolved config yields the `cli` directive.

**Round 2 findings (fixed).**

1. **The design left one combination silently broken:** `interaction.mode: cli` with
   `runner: process` is a headless one-shot session told to ask a human who has no terminal
   — precisely the defect this work item exists to remove, now reachable by configuration.
   Fixed by warning (not refusing, not overriding) from `InteractionConfig.from_mapping`,
   which every construction site already goes through, so the receiver, hot reload, the
   poller and `sessions` all get it from one place. Requirements gained R1.6; the schema,
   the operator docs, the capability doc and decision-051 all state it.
2. The `work-item` directive said "There is NO human at this session's terminal". Under
   the tmux runner — with the default mode — that is simply false, and an instruction the
   agent can observe to be false is one it may discount wholesale. Reworded to "Do NOT
   assume a human is watching this session's terminal", which is true in both runners and
   asks for the same behaviour.

**Round 3 findings (fixed).**

1. The reworded directive left three copies of the old, now-inaccurate claim in prose —
   `design.md`, the capability doc and `reference/collaboration.md`. Swept.
2. Prose assertions in both test files matched substrings that the rewrap had split across
   lines (`"never as an\ninteractive prompt"`). Rather than pin the line breaks, both
   suites now normalise whitespace before asserting: the tests are about words.
3. `uv run` had rewritten `uv.lock` into a newer marker format — 136 lines of churn
   unrelated to this change. Reverted, so the diff is only this work item's.

**Round 4:** no new findings — converged, per `reviews.stopOnNoNewFindings`.

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`).
- **Outcome:** **pass.** The change adds no network call, no subprocess, no filesystem
  access, no credential, no dependency, and touches neither the authorized-actor guard nor
  the loop-prevention marker. Each abuse case from `requirements.md` has a mechanism and a
  test:

  | Abuse case | Mechanism | Test |
  |---|---|---|
  | 1 — a comment argues the agent out of the configured channel | the directive is a constant selected by a closed enum, rendered **above** the excerpt the template already labels UNTRUSTED; no payload value reaches it | `test_a_hostile_comment_cannot_rewrite_the_directive`, `test_the_directive_precedes_the_untrusted_payload_block`, `test_the_directive_is_constant_and_interpolates_nothing` |
  | 2 — a hand-edited config carries an unknown mode | resolution falls back to `work-item` **with a warning**, never to `cli` | `test_an_undeclared_mode_falls_back_to_work_item_and_warns` |
  | 3 — a custom template omits the placeholder | `apply_directive` appends rather than dropping | `test_a_template_without_the_placeholder_gets_the_directive_appended`, `test_a_custom_template_without_the_placeholder_still_gets_the_directive` |

  **Residual risk, stated rather than implied:** a commenter can *write text that looks
  like* the directive inside their comment, and it will appear in the payload excerpt.
  That is the pre-existing property of embedding untrusted text at all, and the existing
  mitigation is unchanged and applies: the excerpt sits below an explicit UNTRUSTED banner,
  after every the-loop instruction. This change adds no new channel — it only adds trusted
  text above the banner.

- **Human sign-off: PENDING (required).** `.the-loop/cli-config.schema.json` matches
  `autonomy.sensitivePaths` (`**/*schema*`), so with `inferFromChange: true` the effective
  risk tier is **4**, which is `human-approves-pr` **and**
  `security.humanSignOffMinTier: 4` — a named human security sign-off. Requested on the
  PR. The schema change itself is purely additive (one optional object, one enum, no key
  removed or moved, no version bump, no migration).

## Capability docs

- [`docs/capabilities/webhook-triggers.md`](../../capabilities/webhook-triggers.md) — the
  interaction-directive behaviour under *Current behaviour*, plus a history row for
  issue-134.

## Final validation evidence

Every command run from the project root, as CI runs them (`make check`).

| Gate | Command | Result |
|------|---------|--------|
| Unit + integration | `uv run --project cli python -m pytest -q cli` | **1011 passed, 2 skipped** (was 969 + 2) |
| Lint (Python) | `uv run ruff check cli hooks` | All checks passed |
| Format | `uv run ruff format --check cli hooks` | 121 files already formatted |
| Types | `uv run pyright cli` | 0 errors, 0 warnings |
| Lint (markdown) | `markdownlint-cli2 "**/*.md"` | 0 errors (332 files) |
| Config validation | `uv run python scripts/validate_config.py` | all six configs valid against their schemas |

Acceptance criteria, demonstrated:

- **R1.1/R1.2** — `test_a_declared_mode_resolves_to_itself`,
  `test_nothing_declared_resolves_to_the_default_silently`,
  `test_the_routing_config_carries_the_resolved_mode` (both ingresses build their
  `RoutingConfig` through the same `from_mapping`, so one wiring covers receiver and
  poller).
- **R1.3** — `test_an_undeclared_mode_falls_back_to_work_item_and_warns`,
  `test_case_and_whitespace_are_normalised`.
- **R1.4** — `test_the_schema_declares_the_mode_enum` + `scripts/validate_config.py`.
- **R1.5** — the resolved mode on both `session.spawned` emits (process and tmux).
- **R1.6** — `test_cli_mode_under_the_headless_runner_warns`,
  `test_the_workable_combinations_are_quiet`,
  `test_the_routing_config_warns_for_cli_under_the_process_runner`.
- **R2.1–R2.3** — `test_the_work_item_directive_reaches_both_prompts`,
  `test_the_cli_directive_reaches_both_prompts` (each parameterised over the event and
  spawn templates).
- **R2.4** — `test_a_custom_template_without_the_placeholder_still_gets_the_directive`.
- **R2.5** — `test_the_bundled_templates_match_the_built_in_fallbacks` and
  `test_both_built_in_templates_declare_the_placeholder`. This turns the "Kept in sync
  with `skills/…`" comment that has ridden on those constants since issue-36 into a test.
- **R3.1/R3.4** — `test_every_mode_carries_the_artifact_rule`,
  `test_the_artifact_rule_travels_with_every_prompt`.
- **R3.2/R3.3** — `SKILL.md` operating principle + `reference/collaboration.md`
  § Where questions go (prose obligations; not mechanically testable, and deliberately
  placed in the skill so they bind human-started sessions too).
- **R4.1** — `test_p4_every_schema_leaf_is_documented` / `test_p5_…` green with the new
  `### interaction.mode` heading.
- **R4.2/R4.3** — capability doc behaviour + history row; decision-051.
