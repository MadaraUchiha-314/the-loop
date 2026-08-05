---
type: execution-log
workItem: "issue-154"
phase: needs-review
status: in-progress
---

# Execution Log: the tmux session name posted on the ticket is not the one tmux gave the session

> Append-only log of progress for the user's visibility. Checked in alongside the
> spec at `docs/specs/issue-154/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-05 |  | Issue #154: tmux rewrites `.` in a session name, so the attach command the-loop posts names a session that does not exist. Confirmed against tmux 3.4, and found to break the whole tmux lifecycle for such a work item, not just the comment. |
| design | 2026-08-05 |  | One pure `tmux_session_name()` mirroring tmux's `session_check_name()`, applied where a name is **minted** (`target_for`) and where one is **admitted** (`Session.__post_init__`); `_LOOP_TARGET_RE` tightened to reject the target-grammar shape. |
| tasks-breakdown | 2026-08-05 |  | 11-task DAG, TDD per task. |
| implementation | 2026-08-05 |  | Implemented on `claude/github-issue-154-wn98db` |
| needs-review | 2026-08-05 |  |  |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| #155 | T1–T11: the whole fix, tests, capability doc | open |

## Progress entries

### 2026-08-05 — root cause confirmed against real tmux, spec drafted

- **Phase:** requirements → design → tasks
- **Did:** Traced the name from `WorkItemRef.slug` (which deliberately keeps `.`
  — it is also the registry file name, issue-130) through
  `TmuxRunner.target_for` into every consumer, then **ran tmux 3.4** to check
  what it does with such a name rather than assuming:

  ```console
  $ tmux new-session -d -s 'loop-a.b-15' && tmux ls -F '#{session_name}'
  loop-a_b-15
  $ tmux has-session -t 'loop-a.b-15'; echo "exit=$?"
  can't find pane: b-15
  exit=1
  $ tmux new-session -d -s 'loop-a.b-15'
  duplicate session: loop-a_b-15
  ```

- **Found:** worse than the reported cosmetic defect. `.` is tmux's *target
  grammar*, so the dotted name is not merely "not found" — it is re-parsed as
  `session.window`. For any work item whose slug has a dot (a repo like
  `octo/foo.js`, or **every** work item on a GitHub Enterprise host) the
  liveness probe reads the live session as absent, every delivery reports
  `session_missing`, and the respawn lands on the issue-146 collision —
  deterministically, not just under load. issue-146's handling contains the
  damage, which is why this surfaced as a wrong comment rather than a crash loop.
- **Decided:** mirror tmux's own rule rather than invent an escaping scheme, and
  normalise on **load** rather than ship a migration — a session created under a
  dotted spelling was always named with underscores *by tmux*, so nothing needs
  renaming; the record is what is wrong. Recorded the residual `.`/`_` aliasing
  as known-and-bounded instead of engineering around it (`bugfix.md` § Out of
  scope, § Security considerations).
- **Next:** T1–T11, TDD per task.

### 2026-08-05 — implemented, self-reviewed, docs updated

- **Phase:** implementation → needs-review
- **Did:** T1–T10. `sessions/registry.py`: `tmux_session_name()` (exported from
  `the_loop.sessions`) and `Session.__post_init__` normalising `tmux_target`.
  `runner.py`: `target_for` applies it, `_LOOP_TARGET_RE` drops `.` from its
  charset, and `_clear_target`'s docstring now states the alias exception instead
  of asserting an invariant that is not quite total. No other production file
  changed: every consumer already reads `target_for()` or
  `session.tmux_target`, which is why one chokepoint each was enough.
- **Deviations from the plan, and why:**
  - **T4** — as predicted, `announce.py` needed no code change; the test is the
    deliverable, because the announced attach command is the surface the issue is
    actually about.
  - **T8, widened during the task** — teaching the stub the creation-time rename
    alone was not enough: it would still have resolved `-t loop-a.b-15` happily,
    i.e. still been unable to express the defect, where real tmux answers `can't
    find pane: b-15`. The stub therefore also rejects any *target* carrying
    `.`/`:`. All 21 pre-existing integration scenarios stayed green with the
    stricter stub.
  - **Self-review finding (cycle 3), fixed:** three test names and one `-k`
    selector in `design.md`/`tasks.md` did not resolve to a real test —
    `-k tmux_session_name` selected **0 of 106** (the class is
    `TestTmuxSessionName`), and the AC3/AC4/AC6 rows named tests that had been
    written under different names. Every selector in both artifacts was then run
    and its selection count checked, not eyeballed.
- **Evidence:** see § Final validation evidence.
- **Known limit (recorded, not hidden):** the `.`/`_` alias. Two work items whose
  slugs differ only there share a tmux name; tmux cannot host both either. Pinned
  by `test_target_for_aliases_dot_and_underscore` so a future change that makes
  the alias destructive fails a test.
- **Next:** T11 — PR + reviewer briefing, then human approval (tier 3).

## Review cycles

> Outcome is one of: new findings · zero (converged) · escalated · **unavailable**
> (the configured critic could not run — it does NOT count toward
> `reviews.criticReviewCount`).

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self (correctness — every reader of a tmux name re-read end to end: `announce`, `sessions_cmd`, `deliver`/`kill`/`terminate_harness`, both dispatcher spawn paths, the event log) | agent | new finding: the stub tmux modelled the creation-time rename but still resolved dotted *targets*, so the integration test could pass for the wrong reason — fixed | PR #155 |
| 2 | self (blast radius — what a tightened `_LOOP_TARGET_RE`, a normalising `__post_init__` and a stricter stub could break; grepped for every construction/comparison of a target) | agent | zero (converged): full suite green, no other site mints or compares a tmux name | PR #155 |
| 3 | self (docs/spec ↔ code parity: every test name and `-k` selector in the artifacts actually run) | agent | new findings: 3 wrong test names + 1 `-k` selector matching nothing — fixed | PR #155 |
| — | critic | n/a | **unavailable** — `reviews.critics` is empty in `.the-loop/harness-config.yaml`, so no second harness/model is configured in this repo; does not count toward `reviews.criticReviewCount` | — |
| 4 | security (see gate below) | agent | zero (converged) | PR #155 |

## Capability docs

[`docs/capabilities/interactive-sessions.md`](../../capabilities/interactive-sessions.md)
— added the session-naming behaviour (tmux's rewrite, normalisation on load, the
unchanged-for-plain-slugs guarantee and the recorded aliasing), qualified the
issue-146 "an occupant is always this work item's own agent" line accordingly, and
added the issue-154 history row. No other capability's current behaviour changes.

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto` → checklist)
- **Outcome:** pass. The change **removes** an injection *shape* and adds none:
  `.` and `:` are tmux's target grammar, so a name carrying them is re-parsed by
  tmux into a target the-loop did not mean (demonstrated above). Both are now
  stripped at the only two points a name enters the process, and
  `_LOOP_TARGET_RE` — the guard on the one path that reaches OS processes
  (`terminate_harness` → `os.kill`) — rejects them outright, with a negative test
  per rejected shape. No new trust boundary, ingress, secret, file, network call,
  config key or dependency; the normalisation is a pure string substitution with
  no failure mode. The one abuse case (colliding on another work item's session
  via the `.`/`_` alias) is bounded by issue-146's rule that a live occupant is
  never killed or spawned over, and is pinned by a test.
- **Human sign-off:** n/a (risk tier 3, below `security.review.humanSignOffMinTier: 4`)

## Final validation evidence

**Red → green, per acceptance criterion.** With the two production hunks
neutered (`target_for` returning the raw slug, `__post_init__` not normalising,
`_LOOP_TARGET_RE` back to its old charset) and the tests unchanged:

```text
FAILED cli/tests/test_tmux_runner.py::TestSessionRunnerFields::test_normalises_a_legacy_tmux_target        (AC3)
FAILED cli/tests/test_tmux_runner.py::TestTmuxRunner::test_target_for_strips_tmux_target_syntax            (AC1)
FAILED cli/tests/test_tmux_runner.py::TestTmuxRunner::test_target_for_aliases_dot_and_underscore           (abuse case)
FAILED cli/tests/test_tmux_runner.py::TestTmuxRunner::test_deliver_and_kill_address_the_normalised_target  (AC5)
FAILED cli/tests/test_tmux_runner.py::TestTerminateHarness::…[loop-other.session]                          (AC6)
FAILED cli/tests/test_announce.py::test_body_names_the_real_tmux_session                                   (AC4)
FAILED cli/tests/test_tmux_runner_integration.py::test_a_dotted_repo_name_gets_a_session_it_can_attach_to   (AC7, AC8)
```

The integration failure is the reporter's own scenario, and its log line is the
bug in one sentence:

```text
WARNING the-loop.runner: could not set remain-on-exit on loop-github-octo-foo.js-15
        (tmux set-option exited 1: can't find pane: js-15)
```

With the fix in place, all seven pass and `test_target_for_unchanged_for_plain_slugs`
holds AC2 (no existing session, record or already-posted attach command is
invalidated).

**Full gate — the same commands the pre-commit hooks and CI run:**

- `uv run pytest -q` → **1177 passed, 2 skipped** (was 1170 before this work)
- `uv run ruff check cli hooks` → All checks passed
- `uv run ruff format --check cli hooks` → 128 files already formatted
- `uv run pyright cli` → 0 errors, 0 warnings, 0 informations
- `npx markdownlint-cli2 "**/*.md"` → 0 errors (374 files)
- `uv run python scripts/validate_config.py` → VALID (6 files)
- `uv run the-loop check issue-154 --recompute --fail-on block` → exit 0
