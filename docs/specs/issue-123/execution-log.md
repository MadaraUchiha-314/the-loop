---
type: execution-log
workItem: issue-123
phase: needs-review       # not-started | brainstorming | requirements-definition | design | tasks-breakdown | implementation | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: the daemon takes `specDir` from the operator's machine

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-31 | pending (PR) | Bugfix spec; the ticket already carried the trace, so the phase confirmed it against the tree and added the trust-direction analysis |
| design | 2026-07-31 | pending (PR) | Default change + reordering, not a new mechanism |
| tasks-breakdown | 2026-07-31 | pending (PR) | 8-task DAG |
| implementation | 2026-07-31 | pending (PR) | T1–T8 |
| needs-review | 2026-07-31 | pending | Tier 3 ⇒ `human-approves-pr`; completes when the PR merges |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#126](https://github.com/MadaraUchiha-314/the-loop/pull/126) | spec + T1–T8 | open |

## Progress entries

### 2026-07-31 — spec locked

- **Phase:** not-started → requirements-definition → design → tasks-breakdown
- **Did:** Confirmed the ticket's trace against the tree: `GraphLinkConfig.from_mapping`
  always sets `spec_dir`, `_build_runtime` passes it as `spec_root`, and `build_runtime`
  treats an explicit `spec_root` as an override — so `build_runtime`'s own fall-through to
  `workflow.specDir` is unreachable on the daemon path. Wrote the bugfix spec.

  Two things the requirements phase added that the ticket did not have:

  1. **An ordering requirement (R4.1).** Resolving `specDir` from the checkout means
     *reading the checkout's harness config*, and `_guarded` ran that gate **before**
     `_checkout_belongs_to`. Landing the fix as sketched would read a foreign checkout's
     config — breaking the invariant `harness_config.py`'s docstring states and
     decision-044 records. The reorder is the mitigation, not a tidy-up.
  2. **A containment requirement (R4.3).** Once the value comes from a repository, an
     absolute or `../`-escaping `specDir` would direct `graph-state.json` outside the
     checkout. Refused on the daemon path only — `check`/`graph` run inside the repository
     at the user's own invocation.
- **Checkpoint/tests:** none yet — no code written.
- **Next:** T1 (the failing tests, red first).
- **Blockers:** none.

### 2026-07-31 — implementation complete (T1–T8)

- **Phase:** design → needs-review
- **Did:**
  - **T1 (red first)** — 18 new cases across `test_graphlink.py` and
    `test_graphlink_integration.py`. Red before any production change: 20 failures, of
    which the substantive ones were "the repository's `specDir` is never honoured" — the
    defect itself, observed.
  - **T2** — `harness_config.DEFAULT_SPEC_DIR` + `spec_dir(harness)`, taking an
    already-loaded mapping so `build_runtime` does not read the file twice.
    `build_runtime`'s docstring now explains `spec_root` and `authorized_users`
    *separately*: one reason covering two parameters of different provenance is what let
    the defect in.
  - **T3** — `GraphLinkConfig.spec_dir` defaults to `""`; `from_mapping` uses
    `str(data.get("specDir") or "")` so `specDir: null` reads as unset rather than as the
    string `"None"`; `GraphLink._spec_dir` resolves once and `_guarded` threads the same
    value into the gate and `_build_runtime(cwd, spec_dir)`.
  - **T4** — `_checkout_belongs_to` moved ahead of the spec-directory gate. The set of
    skipped work items is unchanged (both gates are pure predicates over disjoint inputs);
    only the reported reason changes when both would fire, and the foreign-checkout reason
    is the more important one.
  - **T5** — `graph.skipped` in `EVENT_TYPES`, emitted at `info` from the two
    spec-directory refusals with `work_item`, `action`, `reason`, `spec_dir`.
  - **T6/T7** — the CLI schema default and description, the template's `graph` block, the
    `routing-options.md` entry rewritten as an override (with the upgrade warning), the
    `harness-config.md` note that `workflow.specDir` was the one declared key the daemon
    did not actually honour, and both capability docs with issue-123 history rows.
- **Unplanned, in scope:** none.
- **Checkpoint/tests:** `make check` green — `ruff check`, `ruff format --check`,
  `pyright` 0 errors, `markdownlint` 0 errors (305 files), `validate_config.py` VALID,
  pytest **857 passed, 1 skipped** (839 before; +18 new).
- **Next:** human review of the PR (the tier-3 gate).
- **Blockers:** none.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self (does the fix reach the defect?) | the-loop session | Confirmed the fix is a *default* change, not a new mechanism: `build_runtime`'s `spec_root or workflow.get(...)` was already correct and merely unreachable. Also confirmed the sketch as filed would have read a **foreign** checkout's harness config, because the spec-dir gate ran before the ownership proof — promoted to R4.1 and T4 | `requirements.md` R4, `design.md` C5 |
| 2 | self (observability field correctness) | the-loop session | **Finding, fixed.** The `spec-dir-outside-checkout` record passed `str(root)` as its `spec_dir` field — the checkout path, not the refused value, and an absolute path the design had promised not to log. `_spec_dir` now returns the declared value whether or not it is usable, containment is a separate gate in `_guarded`, and the record names the value the operator has to change. Pinned by an assertion in `test_a_spec_dir_that_escapes_the_checkout_is_refused` | `graphlink.py::_spec_dir` |
| 3 | self (what did the reorder cost?) | the-loop session | `_checkout_belongs_to` spawns `git config --get remote.origin.url`, and now runs for a work item whose spec directory is absent, where `is_dir()` used to short-circuit it. Accepted and written down: one subprocess per delivery, already behind `_awaiting_start`, on a path about to spawn or resume a whole harness session — and the alternative is reading a checkout the daemon has not proved is the work item's | `design.md` C5 |
| 4 | human (PR approval) | @MadaraUchiha-314 | pending | PR #126 |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`)
- **Outcome:** pass. The change moves one value from the ⟵ direction (a machine-scoped
  default governing N repositories) into the ⟶ direction decision-044 declares allowed,
  and it *narrows* blast radius: `workflow.specDir` now governs the repository that
  declared it instead of one operator value governing all of them. The new abuse case — a
  hostile `workflow.specDir` — is met twice over. **Ordering:** the read happens only after
  `_checkout_belongs_to` has proved via the `origin` remote that the checkout is the work
  item's own repository, so the only actor who can set the value is one who can already
  commit to that repository (the same actor who can already set `reviews.critics[]` and
  `.the-loop/graph.yaml`); `test_a_foreign_checkouts_harness_config_is_never_read` pins
  that a foreign checkout's config is not opened at all. **Containment:** an absolute or
  `../`-escaping value is refused before it reaches `is_dir()` or the runtime
  (`_is_contained`, failing closed on `OSError`), covered by three parametrised cases. The
  ⟵ direction is untouched — `authorizedUsers` and `polling.sources[].repos` remain
  CLI-config-only with no fallback, and `test_trust.py`/`test_poller.py` are unmodified and
  green. Every failure path is a **skip**, so issue-113's asymmetry holds: no input can
  move a work item forward. The new `graph.skipped` record carries only the work-item ref,
  the action, a fixed reason string and a repo-relative directory the repository itself
  published — no comment text, no payload, no absolute paths (that last point is what
  self-review 2 caught and fixed).
- **Human sign-off:** not required — risk tier 3 < `security.review.humanSignOffMinTier: 4`.

## Final validation evidence

- **Test suite:** 857 passed, 1 skipped (839 before; +18 tests).
- **Red→green:** with the tests in place and no production change, 20 failures —
  `test_the_repositorys_spec_dir_is_honoured`,
  `test_the_gate_reads_the_same_directory_the_runtime_will`,
  `test_a_spec_dir_that_escapes_the_checkout_is_refused[…]`,
  `test_a_skipped_work_item_is_recorded_in_the_event_log`,
  `test_graph_skipped_is_in_the_event_catalog`,
  `test_the_graph_block_leaves_spec_dir_unset_by_default[…]`,
  `test_a_repository_that_moved_its_specs_still_advances`,
  `test_two_repositories_with_different_spec_dirs_are_both_driven` and the `_build_runtime`
  arity failures. All green after T3–T5.
- **AC coverage:**
  - R1.1 — `test_the_repositorys_spec_dir_is_honoured`,
    `test_a_repository_that_moved_its_specs_still_advances` (integration).
  - R1.2 — `test_a_checkout_with_no_harness_config_uses_the_default`,
    `test_an_unparseable_harness_config_falls_back_to_the_default`.
  - R1.3 — `test_the_cli_key_overrides_the_repositorys_value`,
    `test_the_graph_block_leaves_spec_dir_unset_by_default` (3 shapes: absent block, empty
    block, explicit `null`).
  - R1.4 — `test_two_repositories_with_different_spec_dirs_are_both_driven`: one
    dispatcher, two checkouts, two layouts, both graphs at `brainstorming`.
  - R1.5 — the whole pre-existing suite green, and the default-path case asserts
    `built == [(cwd, "docs/specs")]`.
  - R2.1 — `test_the_gate_reads_the_same_directory_the_runtime_will`: a repository that
    declares `specs` while a stale `docs/specs` still exists is gated on the declared one;
    every resolution case additionally asserts the `(cwd, spec_dir)` handed to the runtime.
  - R2.2 — `test_a_repository_that_moved_its_specs_still_advances` asserts
    `specs/issue-113/graph-state.json` exists.
  - R3.1/R3.3 — `test_a_skipped_work_item_is_recorded_in_the_event_log` (one record, with
    `work_item`, `action`, `reason`, `spec_dir`, and `level != debug`),
    `test_the_skip_record_names_the_action_that_was_refused`,
    `test_the_quiet_skip_paths_stay_quiet` (disabled / awaiting-start / non-GitHub emit
    nothing).
  - R3.2 — `test_graph_skipped_is_in_the_event_catalog`, plus the pre-existing
    `test_every_emitted_event_type_is_documented`.
  - R4.1/R4.2 — `test_a_foreign_checkouts_harness_config_is_never_read` (a monkeypatched
    `harness_config.load` records zero calls), with the untouched issue-113 A6 cases
    (`test_a_checkout_of_another_repo_is_never_coupled`,
    `test_a_checkout_with_no_origin_is_skipped`,
    `test_a_directory_that_is_not_a_checkout_is_skipped`) still green.
  - R4.3 — `test_a_spec_dir_that_escapes_the_checkout_is_refused` over `../elsewhere`,
    `/etc` and `docs/../../escape`, each asserting the skip, the reason and that the record
    names the refused value.
  - R5.1/R5.2/R5.3 — `docs/config/cli/routing-options.md` (`graph.specDir` as an override,
    Type/Default retained for `test_docs_parity.py` P5, the upgrade warning),
    `.the-loop/cli-config.schema.json` (default `""`, rewritten description),
    `skills/the-loop/templates/cli-config.yaml` (the key commented out, with the reason).
  - R5.4 — `docs/capabilities/process-graph.md` and
    `docs/capabilities/webhook-triggers.md`, both with issue-123 history rows.
- **Process gate:** `uv run the-loop check issue-123 --recompute --fail-on block` →
  **exit 0**, work item at `requirements-approval` in `WAIT` ("no authorized feedback
  yet") — the correct state for an open PR.
- **Compatibility:** strictly widening. A repository using the default `docs/specs` — with
  or without a harness config — resolves to exactly the directory it did before. The only
  operators whose behaviour changes are those who set `routing.graph.specDir` (their value
  still wins) and those whose repositories declare a non-default `workflow.specDir` (whose
  graphs start working).

## Capability docs

- [`docs/capabilities/process-graph.md`](../../capabilities/process-graph.md) — where the
  daemon resolves the spec directory from, the one-resolution rule, the ownership-before-read
  ordering, the containment refusal, and the `graph.skipped` record; issue-123 history row.
- [`docs/capabilities/webhook-triggers.md`](../../capabilities/webhook-triggers.md) — the
  same from the ingress side, and `workflow.specDir` added to the keys the coupling reads
  from a work item's own checkout; issue-123 history row.
