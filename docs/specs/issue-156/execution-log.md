---
type: execution-log
workItem: "issue-156"
phase: needs-review
status: in-progress
---

# Execution Log: remove the process runner — tmux-only dispatch

> Append-only log of progress for the user's visibility. Checked in alongside
> the spec at `docs/specs/issue-156/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-05 |  | Issue #156: stale `runner: "process"` record silently downgrades tmux delivery. Owner's decision on the ticket: remove the process runner entirely; tmux only. |
| design | 2026-08-05 |  | Delete the two-runner switchyard: one dispatch plane (deliver into tmux, else the issue-80/89/146 respawn path). Legacy records heal lazily — no migration tool. |
| tasks-breakdown | 2026-08-05 |  | 15-task DAG; docs-parity (schema↔routing-options.md) pinned to one commit. |
| implementation | 2026-08-05 |  | On `claude/github-issue-156-w0x1bz`. |
| needs-review | 2026-08-05 |  | PR opened; tier-3 human approval happens there. |
| complete |  |  |  |

## Pull requests

| PR | Branch | Status |
|----|--------|--------|
| (opened at T15) | `claude/github-issue-156-w0x1bz` | |

## Progress entries

### 2026-08-05 — spec drafted

- **Phase:** requirements → design → tasks
- **Did:** read the full dispatch plane (`Dispatcher._dispatch_one`/`_spawn_for`
  → `HarnessAdapter.resume/spawn` vs `TmuxRunner.deliver/spawn` →
  `_respawn_tmux`/`_try_resume`), the registry (`Session.runner` default
  `"process"`), `check_dependencies`, the interaction-mode/runner coupling,
  and swept every non-source mention (configs, schema, docs, capability docs,
  skill references, tests). Confirmed the reported root cause: the per-record
  runner selector with a silent `"process"` default, consulted on every
  dispatch after the first spawn, with no reconciliation against config.
- **Decided:** per the owner's ticket comment, remove the runner rather than
  reconcile it. Critic one-shot invocation (`oneshot_argv`, issue-108) is
  explicitly retained — it is a review mechanism, not the process runner.
  Legacy records (no `tmuxTarget`) heal through the existing respawn path on
  their next event; no migration tool. Leftover `routing.runner` config warns
  and is ignored, never fatal.
- **Next:** implement T1–T14 (TDD per task).

### 2026-08-05 — implemented, tests re-hosted, docs swept

- **Phase:** implementation → needs-review
- **Did:** T1–T13. Source: `Session.runner` removed (legacy key ignored on
  read); `check_dependencies(web_enabled)` with tmux unconditional;
  `TmuxRunner.deliver` reports `session_missing` for an empty target (the
  lazy-healing seam); adapters lose `resume`/`spawn`/`_run`/`_resume_argv`/
  `DispatchResult` and `_spawn_argv` → `_oneshot_argv` (critic surface kept);
  `InteractionConfig` drops the runner coupling; the dispatcher is one plane
  (`_dispatch_one` tmux-only, `_spawn_for` → `_spawn_tmux`, leftover
  `routing.runner` warns); commands/announcer sweep. Tests: the dispatcher
  fleet re-hosted on a shared `FakeTmux`/`StubInteractiveAdapter` seam in
  `conftest.py` across 9 files; new pins for the leftover-key warning, the
  ignored legacy `runner` field, tmux-always-required, and the AC2.4
  healing scenario (a legacy record with no `tmuxTarget` respawns a tmux
  session **resuming the recorded conversation**). Docs: schema + both
  shipped configs, `routing-options.md` (docs-parity holds), state/concepts/
  install/commands docs, five capability docs (history rows added), three
  skill reference docs, `decision-056` (021's runner choice superseded).
- **Deviations from the plan, and why:**
  - The test re-host introduced shared doubles in `conftest.py` rather than
    per-file copies — nine files needed the identical `FakeTmux`, and a
    drifting copy per file is how the old stub let the process path linger.
  - `pyproject.toml` gained a `[tool.pyright]` executionEnvironments entry:
    test modules now import the shared doubles from their sibling
    `conftest.py`, which pytest resolves but pyright needed telling about.
  - `_log_usage` went with the headless path (tmux TUIs report no JSON
    usage; critic usage telemetry is separate and untouched).
- **Evidence:** see Final validation evidence below.
- **Next:** T15 — PR + reviewer briefing, then human approval (tier 3).

## Review cycles

- **Self-review 1 (residual-vocabulary sweep):** found and fixed stale
  process-runner prose in `announce.py`'s module docstring and the
  `session.registered` schema line in `eventlog.py`; confirmed no
  `session.runner` / `config.runner` / headless-dispatch references remain in
  `cli/the_loop` outside intentional issue-156 explanations.
- **Self-review 2 (behavioural edges):** traced the legacy-record path end to
  end (`deliver("")` → `session_missing` → `_respawn_tmux` → `_try_resume`
  with the recorded id) and found AC2.4 had no first-class integration pin —
  added `test_legacy_record_without_a_tmux_target_heals_via_respawn`
  (stub tmux, real `TmuxRunner`), which proves the respawn resumes the
  recorded conversation and back-fills `tmuxTarget`.
- **Self-review 3 (typing/format):** `FakeTmux`/`StubInteractiveAdapter` now
  subclass the real `TmuxRunner`/`HarnessAdapter` so pyright checks the
  doubles against the real contracts (caught a `terminate_harness` signature
  drift); ruff format drift on the new test fixed.

## Security review (gate)

- Checklist outcome: **pass**. This change only deletes an execution path.
  No new inputs, flags, or privileged operations. The untrusted-payload
  boundary is unchanged (payload → prompt only, never argv/path/target);
  `_SESSION_ID_RE` still gates recorded ids entering a resume argv;
  `_LOOP_TARGET_RE` still gates what `terminate_harness` may signal. The
  abuse case from `bugfix.md` (doctored record steering a silent headless
  resume) is closed structurally — the silent path no longer exists, and the
  surviving path is loud (named tmux session, events, announce comment).
  Fail-closed: no tmux → refused start / failed dispatch, never invisible
  execution. Risk tier 3 < `security.review.humanSignOffMinTier` (4), so no
  named human sign-off is required beyond the PR approval.

## Final validation evidence

Same commands the pre-commit hooks and CI run, all from the repo root:

- `uv run --project cli pytest cli/tests` — **1155 passed, 2 skipped**
- `uv run ruff check cli hooks` — All checks passed
- `uv run ruff format --check cli hooks` — 127 files already formatted
- `uv run pyright cli` — 0 errors, 0 warnings
- `npx --yes markdownlint-cli2@0.18.1 "**/*.md"` — 375 files, 0 errors
- `uv run python scripts/validate_config.py` — all six configs VALID
- `uv run the-loop check issue-156 --recompute --fail-on block` — exit 0
  (`WAIT requirements-approval` — the normal state of an open PR)
