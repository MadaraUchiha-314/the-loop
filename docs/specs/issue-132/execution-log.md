---
type: execution-log
workItem: "issue-132"
phase: needs-review
status: in-progress
---

# Execution Log: verifiable custom instructions — make `customInstructions` findable and checkable

> Append-only log of progress for the user's visibility. The-loop keeps the work item's
> phase label in sync with the `phase` front-matter above, and self-checks (runs tests at
> logical checkpoints) recording the outcome here.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-03 | @MadaraUchiha-314 | Scope agreed before phase 1: the capability already exists (issue-59), so the deliverable is discoverability + verification, not the config shape. |
| design | 2026-08-03 | @MadaraUchiha-314 | Command over graph hook — [decision-049](../../decisions/decision-049.md). |
| tasks-breakdown | 2026-08-03 | @MadaraUchiha-314 | 10 tasks; security-relevant tasks 2 and 4 carry the negative tests. |
| implementation | 2026-08-03 | — | All 10 ticked. |
| needs-review | 2026-08-03 | — | Awaiting human approval on the PR (tier 3 → `human-approves-pr`). |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#133](https://github.com/MadaraUchiha-314/the-loop/pull/133) | All tasks 1–10 | open |

## Progress entries

### 2026-08-03 — Answered the question, then scoped what was actually missing

- **Phase:** requirements-definition
- **Did:** Established that `customInstructions` already ships (issue-59, decision-029)
  and answered #132 on the ticket with the config, the read order and the precedence
  rules. Confirmed scope with the requester rather than assuming: answer + close the
  discoverability gap + add the mechanical check, **without** extending the config shape.
- **Checkpoint/tests:** n/a (spec phase).
- **Next:** design.

### 2026-08-03 — Design locked: a command, not a graph hook

- **Phase:** design
- **Did:** Chose `the-loop instructions` in the shape of `the-loop scenarios` over a
  `pdlc.yaml` hook. Two disqualifiers for the hook, recorded in
  [decision-049](../../decisions/decision-049.md): the obligation is per-work-item rather
  than per-node, and `Runtime.evaluate` runs **exit** chains only — so the semantically
  correct entry-chain hook would never be reported by `the-loop check`, relocating the
  silence instead of removing it.
- **Checkpoint/tests:** n/a (spec phase). Corrected one requirements↔design mismatch found
  while writing the ladder: a directory resolves to `unreadable` (something is there, but
  it is not a doc), a broken symlink to `missing` (nothing resolves at all).
- **Next:** tasks breakdown, then implementation on a fresh window.

### 2026-08-03 — Implementation complete, red→green per task

- **Phase:** implementation
- **Did:** Tasks 1–10. `cli/the_loop/instructions.py` (resolution) +
  `cli/the_loop/commands/instructions_cmd.py` (surface, rendering, exit codes), the sixth
  `harness_config.READS` entry, unit + integration tests, command page and nav, the
  README/skill/reference/capability-doc updates, decision-049.
- **Checkpoint/tests:**
  - Red first: `pytest cli/tests/test_instructions.py` →
    `ModuleNotFoundError: No module named 'the_loop.commands.instructions_cmd'`.
  - Green after task 3: `33 passed, 1 skipped` (the skip is the unpermitted-file abuse
    case, which cannot fail as root).
  - Red for the docs contract: `test_p1_every_registered_command_has_a_page` →
    `registered but undocumented … instructions`; green after task 7.
  - Full suite: `uv run --project cli python -m pytest -q cli` → **969 passed, 2 skipped**.
  - Gates: `ruff check`, `ruff format --check`, `pyright`, `markdownlint`,
    `scripts/validate_config.py` — see § Final validation evidence.
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

1. Requirements and design disagreed on how a **directory** resolves (`unreadable` vs
   `missing`). Fixed in the spec before implementation: `missing` means nothing resolves
   at the path, `unreadable` means something does but is not a readable doc. Collapsing
   them would have sent half the operators to the wrong place.
2. An unrecognised `onMissing` value would have fallen through to a permissive branch.
   Fixed: `on_missing` falls back to `warn`, never `ignore` — a typo in the policy must
   not disable the check that catches typos. Pinned by
   `test_on_missing_falls_back_to_warn_for_an_unknown_value`.

**Round 2 findings (fixed).**

1. A malformed entry (`{notes: …}` with no `path`) was initially going to be skipped.
   That restores the exact silence #132 is about — the operator believes a doc is
   registered and nothing says otherwise. Fixed: `invalid` is a reported state and counts
   toward `onMissing`.
2. The unpermitted-file abuse case passes vacuously as root. Fixed: skipped explicitly
   with a stated reason rather than left as a green that proves nothing.

**Round 3:** no new findings — converged, per `reviews.stopOnNoNewFindings`.

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`, no security-review
  skill invoked for a change of this shape).
- **Outcome:** **pass.** The command adds filesystem reads only — no network, no
  subprocess, no mutation, no new dependency, no schema change, no new credential or
  privilege. Each abuse case from `requirements.md` § Security considerations has a
  mechanism and a negative test:

  | Abuse case | Mechanism | Test |
  |---|---|---|
  | 1 — doc outside the repository | contents never rendered; path/state/size only | `test_doc_contents_never_reach_the_report`, `test_a_hostile_doc_body_never_reaches_the_report` |
  | 2 — directory / broken symlink / binary / unpermitted file | `exists()` → `is_file()` → caught `OSError`/`UnicodeDecodeError` | `test_a_directory_is_unreadable_not_a_crash`, `test_a_broken_symlink_is_missing`, `test_a_binary_file_is_unreadable`, `test_an_unpermitted_file_is_unreadable` |
  | 3 — metacharacters in `notes`/`path` | `json.dumps` encoding; `\|` escaped in markdown | `test_markdown_escapes_pipes_in_notes`, `test_json_encodes_control_characters_inertly` |
  | 4 — malformed harness config | `harness_config.load` degrades to `{}` → zero docs, exit 0 | `test_unparseable_config_reports_nothing_and_succeeds` |

  Note on **path traversal**: deliberately not treated as a boundary. Absolute and
  out-of-repo paths are the feature (decision-029, per-machine docs), so the enforced
  boundary is **output** — a doc's body has no channel into the report. That is why the
  byte count is reported rather than a preview.
- **Human sign-off:** n/a — effective risk tier 3, below
  `security.review.humanSignOffMinTier` (4). No sensitive path is touched: the harness
  **schema** is unchanged, and `.the-loop/harness-config.yaml` is not modified.

## Capability docs

- [`docs/capabilities/spec-workflow.md`](../../capabilities/spec-workflow.md) — the
  verifiability behaviour added to the custom-instructions statement; history row for
  issue-132.
- [`docs/capabilities/cli.md`](../../capabilities/cli.md) — `the-loop instructions`
  behaviour and the sixth harness-config read; history row for issue-132.

## Final validation evidence

Every command run from the project root, as CI runs them (`make check`).

| Gate | Command | Result |
|------|---------|--------|
| Unit + integration | `uv run --project cli python -m pytest -q cli` | **969 passed, 2 skipped** |
| Lint (Python) | `uv run ruff check cli hooks` | All checks passed |
| Format | `uv run ruff format --check cli hooks` | clean |
| Types | `uv run pyright cli` | 0 errors |
| Lint (markdown) | `markdownlint-cli2 "**/*.md"` | clean |
| Config validation | `uv run python scripts/validate_config.py` | valid against the schema |

Acceptance criteria, demonstrated:

- **R1** (query) — `test_registered_docs_are_reported_with_their_state` reports both docs
  in configured order with notes, resolved paths and states; `--format json|markdown|table`
  covered by the rendering tests.
- **R1.5** (absolute paths) — `test_an_absolute_per_machine_doc_resolves`.
- **R1.6** (nothing registered) — `test_a_repo_that_registers_nothing_succeeds`, and
  this repository itself, which registers `docs: []`.
- **R2** (`onMissing` as policy) — `test_on_missing_error_fails_the_build` (exit 1),
  `test_exit_is_zero_under_warn_and_ignore`,
  `test_warn_names_the_unresolved_doc_and_ignore_stays_quiet`,
  `test_exit_code_does_not_depend_on_the_output_format`,
  `test_unparseable_config_reports_nothing_and_succeeds`.
- **R3** (declared read) — `test_harness_config.py` H1–H4 and `test_docs_parity.py` P1/P2
  all green with the new entry and the new page.
- **R4** (discoverability) — README now names the capability, links the reference, lists
  the command, and enumerates the reference docs completely;
  `reference/instructions.md` gained § Verifying a registration.

Run against this repository (which registers no docs — R1.6):

```console
$ the-loop instructions
#  State  Path  Resolved  Notes
-  -----  ----  --------  -----
$ echo $?
0
```
