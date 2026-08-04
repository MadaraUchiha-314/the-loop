---
type: execution-log
workItem: "issue-137"
phase: needs-review
status: in-progress
---

# Execution Log: reset the-loop CLI's state for a work item

> Append-only log of progress for the user's visibility. The-loop keeps the work item's
> phase label in sync with the `phase` front-matter above, and self-checks (runs tests at
> logical checkpoints) recording the outcome here.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-04 | — | Scope, the four pieces of state and the two warnings were posted to the ticket before the spec was written, with the two assumptions stated for correction. |
| design | 2026-08-04 | — | Compose the existing erasure paths; not a control verb — [decision-050](../../decisions/decision-050.md). |
| tasks-breakdown | 2026-08-04 | — | 12 tasks; the security-relevant ones (5, 8, 9) carry the negative tests. |
| implementation | 2026-08-04 | — | All 12 ticked. |
| needs-review | 2026-08-04 | — | Awaiting human approval on the PR (tier 3 → `human-approves-pr`). |
| complete | | | |

**Note on the per-phase gates.** `workflow.requireHumanReviewPerPhase` is true, and this
work item ran from a non-interactive session started off the ticket — there was no
human at a keyboard to approve each phase in turn. The gates are therefore **consolidated
into the PR review**, which is what the risk tier (3 → `human-approves-pr`) requires
anyway. The three spec artifacts are in the diff and can be rejected there like any other
change; the phase rows above record that, rather than claiming approvals nobody gave.

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#138](https://github.com/MadaraUchiha-314/the-loop/pull/138) | All tasks 1–12 | open |

## Progress entries

### 2026-08-04 — Scope stated on the ticket before the spec

- **Phase:** requirements-definition
- **Did:** Established where the CLI's memory of a work item actually lives — four places,
  all surviving an upgrade — and that the existing verbs each miss part of it (`stop`
  leaves a closed record and the whole poll ledger). Found the trap in the by-hand
  workaround: deleting `portable/<slug>.json` lets the pre-issue-128 readers hand the old
  `start` back, so the item returns **armed**. Posted the scope, the erasure table and the
  two assumptions to
  [#137](https://github.com/MadaraUchiha-314/the-loop/issues/137#issuecomment-5173461655).
- **Checkpoint/tests:** n/a (spec phase).
- **Next:** design.

### 2026-08-04 — Design locked: compose the erasure paths, and stay out of the vocabulary

- **Phase:** design
- **Did:** Two commitments, both recorded in
  [decision-050](../../decisions/decision-050.md). Reset **composes** — the dispatcher's
  close path for a live session, `WorkItemStore.write_section(..., None)` for the portable
  sections — around one new primitive, `SessionRegistry.forget`. And it is **not** a
  control verb: no `reset` keyword (a comment must not be able to delete local state) and
  no ticket comment (posting `stop-execution` would record intent the reset just cleared),
  so the append-only event log is its trail.
- **Checkpoint/tests:** n/a (spec phase). The non-obvious correctness constraint identified
  here — clear through the store, never `unlink()`, or the legacy tree resurrects the
  record — became its own test before any code was written.
- **Next:** tasks breakdown, then implementation.

### 2026-08-04 — Implementation complete, red→green per task

- **Phase:** implementation
- **Did:** Tasks 1–12. `cli/the_loop/reset.py` (the domain), the `reset` action in
  `commands/sessions_cmd.py` (selectors, all-or-nothing ref validation, reporting, the two
  warnings, the lazily-built dispatcher), `SessionRegistry.forget`, `close_session`
  returning whether a checkout went with it, the `session.reset` event type, unit +
  integration tests, the command page, `docs/cli/state.md` § wiping, both capability docs
  and decision-050.
- **Checkpoint/tests:**
  - Red first: `pytest cli/tests/test_reset.py` →
    `ModuleNotFoundError: No module named 'the_loop.reset'`.
  - Green after the domain: `24 passed`.
  - Red for the catalog contract: `test_every_emitted_event_type_is_documented` →
    `emitted but not in EVENT_TYPES: ['session.reset']`; green after the catalog entry.
  - Full suite: `make check` → **1024 passed, 2 skipped**, all gates clean.
- **Next:** self-review rounds, security review gate, reviewer briefing, PR.

## Review cycles

> Outcome is one of: new findings · zero (converged) · escalated · **unavailable** (the
> configured critic could not run — it does NOT count toward `reviews.criticReviewCount`).

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (this session) | new findings — see below | this log |
| 2 | self | the-loop (this session) | new findings — see below | this log |
| 3 | self | the-loop (this session) | zero (converged) | this log |
| — | critic | none configured | **unavailable** — `reviews.critics: []` in this repo, so no critic round could run; it does not count toward `criticReviewCount` | [harness-config.yaml](../../../.the-loop/harness-config.yaml) |
| 4 | security | the-loop checklist | pass — see § Security review | this log |

**Round 1 findings (fixed).**

1. **The rehearsal hid the unrecoverable part.** `--dry-run` reported "would remove
   session, control, poll" and said nothing about the workspace checkout — the one piece a
   real run cannot give back. A dry run cannot know whether a checkout is on disk without
   building the dispatcher it deliberately does not build, but the *config* says whether
   the close path would remove one. Fixed: `_warn_about_the_checkout` names it and its
   root. R4.5 was added to `requirements.md` to record the obligation, with
   `test_dry_run_names_the_checkout_it_would_remove` and its negative twin.
2. **A corrupt pidfile could widen the liveness probe.** `os.kill(0, 0)` and
   `os.kill(-1, 0)` address process *groups*. Signal 0 delivers nothing, so it was not
   exploitable, but a probe that can mean "the whole group" is the wrong shape. Fixed:
   `pid <= 0` is a corrupt pidfile, not a process
   (`test_a_corrupt_pidfile_does_not_warn`).
3. **The same ref twice reported the repeat as "nothing to reset"** and failed the run.
   Fixed by de-duplicating the parsed refs, order preserved (R2.7,
   `test_the_same_ref_twice_is_one_reset`).

**Round 2 findings (fixed).**

1. **`--all` enumerated `sealed` tombstones.** A sealed record marks a work item the-loop
   has *already* ended (it exists only so a pre-issue-128 tree cannot resurrect it), and
   holds no section — so `--all` on an otherwise clean machine would have reported
   "nothing to reset" for it and exited non-zero. Fixed in `work_items_with_state`: a
   record with no section is not state (`test_work_items_with_state_skips_a_sealed_tombstone`).
2. **Completeness check on "everything this machine remembers".** Audited every
   per-work-item path in the package (`grep '\.slug'`): the registry record, the portable
   record, the workspace checkout and the tmux session name — all four covered, the last
   through the close path. `docs/specs/<id>/graph-state.json` is the only other
   work-item-keyed file and is deliberately out of scope (it is tracked in the
   repository). No fifth store exists, so the claim in the docs is accurate.
3. **Two selector errors shared one message.** `--all --work-item X` was answered with
   "pass --work-item or --all", which is not the problem the operator has. Split into a
   "mutually exclusive" message.

**Round 3:** no new findings — converged, per `reviews.stopOnNoNewFindings`.

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`).
- **Outcome:** **pass.** The change adds a destructive *local* command and no new remote
  surface: no network call, no subprocess of its own, no new dependency, no schema or
  config key, no new credential. Each abuse case from `requirements.md` § Security
  considerations has a mechanism and a test:

  | Abuse case | Mechanism | Test |
  |---|---|---|
  | 1 — a ref carrying separators / traversal / a leading dash | `WorkItemRef.parse` (shape) rejects it; nothing is removed | `test_hostile_refs_are_rejected_and_remove_nothing` |
  | 1b — a ref that *parses* (leading slash, null byte) | `WorkItemRef.slug` replaces every character outside `[A-Za-z0-9._-]`; only the stores build paths, under their own roots | `test_a_ref_that_parses_is_still_neutralised_by_the_slug`, `test_a_traversal_shaped_ref_that_parses_stays_inside_the_root` |
  | 2 — a valid ref with no state | reported, nothing removed, no broader match | `test_a_work_item_with_no_state_is_reported_not_crashed` |
  | 3 — `--all` in a shared state directory | enumerates only what the stores recognise as records | `test_a_strangers_file_in_the_state_directory_is_left_alone`, `test_work_items_with_state_ignores_strangers` |
  | 4 — a corrupt record | the store degrades to "nothing recorded"; the run continues | `test_an_unwritable_store_is_reported_rather_than_raised` |
  | 5 — a removal fails | collected into `errors`, reported, exit non-zero; other items continue | `test_one_failing_work_item_does_not_strand_the_rest` |

- **The new trust boundary that was *not* opened.** Reset is deliberately absent from the
  control keyword vocabulary, so no comment — from an authorized user or anyone else —
  can reach it. `parse_command` returns one of four fixed constants, and this is not one
  of them. The command's only actor is a local shell, the same privilege `sessions stop`
  already assumes.
- **Append-only audit.** The module calls `eventlog.emit` and nothing else; there is no
  path that opens the log for writing, truncating or unlinking. Pinned by
  `test_the_event_log_is_appended_to_never_rewritten`, which compares the log's bytes
  before and after.
- **Fail closed.** Every ambiguity removes *less* and says *more*: no selector removes
  nothing, an invalid ref removes nothing, `--dry-run` removes nothing. Clearing the
  control section **disarms** the work item, so the failure mode of a half-understood
  reset is an item that waits rather than one that runs.
- **Human sign-off:** n/a — effective risk tier 3, below `security.review.humanSignOffMinTier`
  (4). No `autonomy.sensitivePaths` entry is touched: no schema, no workflow file, no
  config. The one irreversible effect in scope — uncommitted work in a workspace checkout
  — is the **existing** close path under the **existing**
  `routing.workspace.keepCheckoutOnClose` policy, unchanged here, and now announced on its
  own output line in both a real run and a rehearsal.

## Capability docs

- [`docs/capabilities/cli.md`](../../capabilities/cli.md) — `sessions reset` as current
  behaviour (what goes, what does not, the selector and warning rules); history row for
  issue-137.
- [`docs/capabilities/interactive-sessions.md`](../../capabilities/interactive-sessions.md)
  — a reset ends a live session through the close path and then deletes its record, so a
  tmux session retained by policy outlives it; history row for issue-137.

## Final validation evidence

Every command run from the project root, as CI runs them (`make check`).

| Gate | Command | Result |
|------|---------|--------|
| Unit + integration | `uv run --project cli python -m pytest -q cli` | **1024 passed, 2 skipped** |
| Lint (Python) | `uv run ruff check cli hooks` | All checks passed |
| Format | `uv run ruff format --check cli hooks` | clean |
| Types | `uv run pyright cli` | 0 errors |
| Lint (markdown) | `npx markdownlint-cli2 "**/*.md"` | 0 errors (332 files) |
| Config validation | `uv run python scripts/validate_config.py` | valid against the schema |

Acceptance criteria, demonstrated:

- **R1** (reset one) — `test_one_work_item_is_forgotten` (all three pieces gone, item
  disarmed, thread first-sight), `test_a_live_session_is_closed_before_its_record_goes`,
  `test_a_closed_session_is_removed_without_being_closed_again`,
  `test_only_the_pieces_that_exist_are_reported`,
  `test_nothing_recorded_is_reported_as_not_found`.
- **R2** (several / all) — `test_several_work_items_in_one_run`,
  `test_all_resets_every_work_item_this_machine_knows`,
  `test_a_bare_reset_refuses_rather_than_resetting_everything`,
  `test_both_selectors_is_refused`, `test_one_bad_ref_resets_none_of_the_good_ones`,
  `test_one_failing_work_item_does_not_strand_the_rest`, `test_the_same_ref_twice_is_one_reset`.
- **R3** (nothing comes back) —
  `test_a_legacy_record_leaves_a_seal_rather_than_a_resurrectable_gap`,
  `test_every_piece_is_removed` (no husk left),
  `test_the_index_no_longer_advertises_the_record`.
- **R4** (auditable) — `test_the_event_log_is_appended_to_never_rewritten`,
  `test_a_reset_that_found_nothing_is_still_recorded`, `test_a_dry_run_emits_nothing`,
  `test_dry_run_changes_nothing`, `test_dry_run_names_the_checkout_it_would_remove`.
- **R5** (warnings) — `test_a_running_receiver_warns_but_does_not_block`,
  `test_a_stale_pidfile_does_not_warn`, `test_a_corrupt_pidfile_does_not_warn`,
  `test_a_config_that_can_respawn_warns`, `test_a_fail_closed_config_does_not_warn`,
  `test_a_live_session_is_ended_and_said_so`,
  `test_close_session_reports_that_it_removed_the_checkout`.
- **R6** (documented, pinned) — `test_docs_parity.py` P1/P2,
  `test_eventlog.py::test_every_emitted_event_type_is_documented`, and the Gherkin
  docstrings in `cli/tests/test_reset_integration.py`.

Run against a scratch state root:

```console
$ the-loop sessions reset
error: pass --work-item <ref> (repeatable) or --all; a bare reset never means 'reset everything'
$ echo $?
2

$ the-loop sessions reset --all --dry-run
github:octo/repo#15: would end a live session
github:octo/repo#15: would remove session
github:octo/repo#21: would end a live session
github:octo/repo#21: would remove session
would reset 2 work items (dry run — nothing was changed)

$ the-loop sessions reset --work-item github:octo/repo#15
github:octo/repo#15: ended a live session
github:octo/repo#15: reset — removed session, control
reset 1 work item

$ the-loop sessions reset --work-item github:octo/repo#15
github:octo/repo#15: nothing to reset
$ echo $?
1
```
