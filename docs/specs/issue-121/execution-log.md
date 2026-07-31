---
type: execution-log
workItem: issue-121
phase: needs-review       # not-started | brainstorming | requirements-definition | design | tasks-breakdown | implementation | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: why the CLI reads `harness-config.yaml`, and the rule that says when it may

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-30 | pending (PR) | A question ticket; the investigation *is* the requirements phase, so `requirements.md` carries an Analysis section answering all three questions |
| design | 2026-07-30 | pending (PR) | Three reinforcing changes: one reader module, one decision record, corrected docs |
| tasks-breakdown | 2026-07-30 | pending (PR) | 7-task DAG |
| implementation | 2026-07-30 | pending (PR) | T1–T7 |
| needs-review | 2026-07-30 | pending | Tier 3 ⇒ `human-approves-pr`; completes when the PR merges |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#122](https://github.com/MadaraUchiha-314/the-loop/pull/122) | spec + T1–T7 | open |

## Progress entries

### 2026-07-30 — the investigation, and what it turned up

- **Phase:** not-started → requirements-definition
- **Did:** Traced every harness-config read in the CLI. Three readers, five keys:
  `graph/bootstrap.py` (`workflow.phaseLabelPrefix`, `workflow.specDir`,
  `notifications`), `critics.py` (`reviews.critics[]`), `commands/scenarios.py`
  (`testing.integrationTestGlobs`). All five are per-repository policy the skill reads
  too, so the answer to question 1 is that the CLI executes the repository's own policy
  on its behalf; the answer to 2 is yes; the answer to 3 is no, for the four reasons in
  `requirements.md` § Analysis.

  Two things the trace turned up that the ticket did not ask about but that are the
  *reason* it was asked:

  1. **The documented rule is false.** `graphlink.py` is constructed by
     `webhook/dispatcher.py` — shared by both ingresses — and `GraphLinkConfig.enabled`
     defaults to true, so the **daemon** reads a work item's checkout on every spawn and
     every routed event with a spec dir. Four pages say it never does
     (`docs/config/index.md`, `docs/cli/concepts.md`, `docs/cli/commands/index.md`,
     `docs/cli/index.md`). That has been wrong since issue-113 shipped.
  2. **Three copies of one fallback.** Each reader carried its own
     `harness-config.yaml` → `config.yaml` candidate list, with three different
     behaviours for an unparseable file. With no single reader there was nowhere for the
     rule to live and nothing for a test to pin — which is why the rule was never
     written down.
- **Checkpoint/tests:** none yet — no code written.
- **Next:** design, then T1 (the pin, red first).
- **Blockers:** none.

### 2026-07-30 — implementation complete (T1–T7)

- **Phase:** design → needs-review
- **Did:**
  - **T1/T2/T3** — `cli/tests/test_harness_config.py` first (red: no module), then
    `cli/the_loop/harness_config.py` (the mirror of `cli_config.py`: `FILENAMES`,
    `config_path`, `load`, `load_strict`, `HarnessConfigRead`, `READS`), then the three
    call sites collapsed onto it, keeping `bootstrap.load_harness_config` and
    `critics.config_path` as the same public names. Two load functions rather than a
    `strict=` flag because the callers have genuinely different contracts —
    `check`/`graph`/`scenarios` must degrade so a CI gate still reports what it can
    compute, `critic` must not, because "no critics configured" and "the file naming them
    does not parse" would otherwise look identical and the second is a false green.
  - **T4** — decision-044, stating the rule as a **direction** rather than a per-process
    partition, refining decision-032 rather than reversing it (its real content was
    always the ⟵ direction, which is untouched).
  - **T5/T6** — the four false claims corrected, `docs/config/harness-config.md` gained
    the "What the CLI reads from it" table the test asserts against, `docs/cli/index.md`'s
    Mermaid now shows the daemon → work item's checkout edge, `docs/cli/extending.md`
    tells a new command's author how to decide, and `docs/capabilities/cli.md` carries
    the invariant plus a history row.
- **Unplanned, in scope:** `uv.lock` still recorded `the-loopy-one 3.0.0` after the
  3.0.1 bump; `uv run` resynced the single line. Included rather than reverted — leaving
  a stale lock dirty for the next session is worse than a one-line unrelated hunk.
- **Checkpoint/tests:** `make check` green — `ruff check`, `ruff format --check`,
  `pyright` 0 errors, `markdownlint` 0 errors (300 files), `validate_config.py` VALID,
  pytest **839 passed, 1 skipped** (821 before; +18 new). Red→green recorded: H1–H4 and
  the loader tests failed on `ImportError: cannot import name 'harness_config'` before
  T2; after T2, H2 still red naming `bootstrap.py:32`, `critics.py:156`,
  `scenarios.py:39-40`, and H3 still red naming all five keys; T3 turned H2 green and T5
  turned H3/H4 green.
- **Next:** human review of the PR (the tier-3 gate).
- **Blockers:** none.

### 2026-07-31 — review question: what else should be logged?

- **Phase:** needs-review
- **Did:** @MadaraUchiha-314 asked on PR #122 whether the investigation turned up
  anything worth logging. Went back through the trace for defects the spec's own scope
  had set aside. Three outcomes:
  1. **A fifth stale claim, fixed here.** `docs/capabilities/webhook-triggers.md` also
     said the daemon *"never reads a repo's plugin config for anything"*. Same defect
     class as the four in R2.1, missed because R2.1 enumerated `docs/cli/` and
     `docs/config/` and this one lives under `docs/capabilities/`. In scope, one
     paragraph, corrected in this PR rather than deferred.
  2. **[#123](https://github.com/MadaraUchiha-314/the-loop/issues/123) — a live bug of
     exactly the class this work item is about.** `graphlink._build_runtime` passes
     `spec_root=self.config.spec_dir` (from `webhooks.ghWebhook.routing.graph.specDir`,
     **CLI config**), and `build_runtime` treats an explicit `spec_root` as an override
     of the repo's `workflow.specDir`. `GraphLinkConfig.from_mapping` always sets it, so
     the repository's value is *never* honoured on the daemon path. A repo with
     `workflow.specDir: specs` has its graph silently skipped at `logger.debug` while the
     delivery still counts. The documented workaround ("match `workflow.specDir` in the
     repository's harness config") is unfollowable: it is one flat value for N watched
     repos. Not fixed here — this PR is deliberately no-behavioural-change, and #123 is
     an ingress-path change that needs its own spec and tests.
  3. **[#124](https://github.com/MadaraUchiha-314/the-loop/issues/124) — the
     `bugfix.md` / `pdlc.yaml` mismatch** raised as a follow-up on PR #120 and never
     actually logged. Re-confirmed still present; filed with the two options and the
     missing parity test that is the real defect.
- **Checkpoint/tests:** `make check` green after the doc fix; 839 passed, 1 skipped.
- **Next:** unchanged — human review of PR #122.
- **Blockers:** none.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self (does the answer survive the code?) | the-loop session | Confirmed the daemon read on the `graphlink` path is real, default-on, and gated by `_checkout_belongs_to` — so the docs are wrong and the code is right, which inverted the shape of the fix | `requirements.md` § "The documentation is wrong, not the code" |
| 2 | self (behaviour delta) | the-loop session | None. Same keys, same paths, same defaults; the one behavioural risk — silently downgrading `critic`'s strict load to best-effort — is prevented by `load_strict` and covered by the untouched `test_critics.py` | 839 passed, no pre-existing test edited |
| 3 | self (is the pin worth its cost?) | the-loop session | H2 is a source scan, which is unusual; kept because the failure mode (a new command with no test yet) is visible only in the diff, and the filename-beside-`.the-loop` match does not trip the several docstrings that mention the file in prose | `test_harness_config.py` module docstring |
| 4 | human (PR approval) | @MadaraUchiha-314 | pending | PR #122 |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`)
- **Outcome:** pass. The work item *is* a trust-direction question, so the review is the
  substance rather than a formality. No trust boundary moves: no key is read that was not
  read before, none from a new path, and nothing crosses the boundary decision-032 drew.
  The ⟵ direction stays closed — `authorizedUsers` and `polling.sources[].repos` remain
  CLI-config-only with no fallback, and `test_trust.py` / `test_poller.py` are untouched
  and green. The ⟶ direction stays gated on the ingress path:
  `graphlink._checkout_belongs_to` still proves via the `origin` remote that the checkout
  is the work item's own repository, failing closed when it cannot tell, and this change
  adds no new caller of `harness_config.load` there. `reviews.critics[]` — the one
  executable key — keeps its strict load (`load_strict` exists precisely so consolidation
  could not quietly downgrade it), its fail-closed `_validate`, its by-name-only
  invocation and its `shell=False` spawn (decision-043). Parsing is still `yaml.safe_load`
  and now happens in one module instead of three. `READS` discloses nothing: every key is
  already in the published schema and the shipped template.
- **Human sign-off:** not required — risk tier 3 < `security.review.humanSignOffMinTier: 4`.

## Final validation evidence

- **Test suite:** 839 passed, 1 skipped (821 before; +18 tests). No pre-existing test
  modified — that is the evidence for R5.2.
- **AC coverage:**
  - R1.1–R1.3 — `docs/decisions/decision-044.md` (the invariant, both directions, the
    three readers and their keys, the four rejection reasons, `Refines: decision-032`),
    indexed in `docs/decisions/decisions.md`.
  - R2.1/R2.2 — `docs/config/index.md`, `docs/cli/concepts.md`,
    `docs/cli/commands/index.md`, `docs/cli/index.md`: no "never reads" claim remains;
    each states the direction rule and keeps the fail-closed `authorizedUsers` / `repos`
    warning.
  - R2.3 — `docs/config/harness-config.md` § "What the CLI reads from it".
  - R2.4 — `docs/cli/index.md`'s Mermaid, with the `D -->|phase label, specDir,
    notifications| HC` edge.
  - R3.1/R3.2 — `the_loop.harness_config` is the only reader (asserted by H2);
    `FILENAMES` is the one copy of the rename fallback, covered by
    `test_config_path_prefers_the_current_name` /
    `test_config_path_falls_back_to_the_pre_rename_name`.
  - R3.3 — `test_load_is_empty_for_an_unparseable_file`,
    `test_load_is_empty_for_a_non_mapping`,
    `test_load_strict_raises_for_an_unparseable_file`,
    `test_load_strict_raises_for_a_non_mapping`, plus the unmodified
    `test_critics.py` cases that still expect `CriticConfigError`.
  - R3.4 — `graph/bootstrap.py`'s `__all__` unchanged; `critics.config_path` re-exported;
    the whole pre-existing suite green.
  - R4.1–R4.5 — `test_reads_is_not_empty_and_is_self_describing` (R4.1),
    `test_h1_every_declared_key_resolves_in_the_harness_schema` (R4.2),
    `test_h2_only_the_shared_reader_opens_a_harness_config` (R4.3),
    `test_h3_every_declared_key_is_documented` /
    `test_h4_every_documented_key_is_still_read` (R4.4), the `needs_docs` skip (R4.5).
  - R5.1/R5.2 — 839 passed with zero pre-existing tests edited.
  - R5.3 — `docs/capabilities/cli.md`: two new behaviour bullets + the issue-121 history
    row.
- **Process gate:** `uv run the-loop check issue-121 --recompute --fail-on block` →
  **exit 0**, work item at `requirements-approval` in `WAIT` ("no authorized feedback
  yet") — the correct state for an open PR.
- **Regression check:** the readers' behaviour is bit-identical. `bootstrap.load_harness_config`
  is now an alias of `harness_config.load` with the same absent/unparseable/non-mapping
  contract; `scenarios._load_config_globs` loses only its private candidate list;
  `critics.load_critics` raises the same `CriticConfigError` with the same two messages,
  now constructed one layer down.

## Capability docs

- [`docs/capabilities/cli.md`](../../capabilities/cli.md) — the direction invariant and
  the single-reader requirement added to the behaviour section; issue-121 history row.
