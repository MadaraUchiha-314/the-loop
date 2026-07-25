---
type: execution-log
workItem: "issue-89"
phase: needs-review
status: in-progress
---

# Execution Log: a respawned tmux session resumes the same harness conversation

> Append-only log of progress for the user's visibility. Checked in alongside
> the spec at `docs/specs/issue-89/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-25 |  | Issue #89: investigate whether a respawned tmux session resumes the harness conversation; make it happen if not. Investigation: it does **not** — `_respawn_tmux` mints a fresh `uuid4()`. |
| design | 2026-07-25 |  | Adapter `interactive_resume_argv` + `TmuxRunner.spawn(resume=…)`/`survived()` + dispatcher try-resume-verify-fall-back. |
| tasks-breakdown | 2026-07-25 |  | 10-task DAG |
| implementation | 2026-07-25 |  | Implemented on `claude/github-issue-89-4rc7k6` |
| needs-review | 2026-07-25 |  | PR opened; awaiting human review (tier-3, `human-approves-pr`) |
| complete |  |  |  |

## Progress entries

### 2026-07-25 — investigation + spec drafted

- **Phase:** requirements-definition → design → tasks-breakdown
- **Did:** Answered the issue's first bullet by tracing the respawn path:
  `TmuxRunner.deliver` → `session_missing` → `Dispatcher._respawn_tmux`, which
  calls `str(uuid.uuid4())` and spawns `claude --session-id <new-uuid>`. So a
  respawn today starts a **blank** conversation and overwrites the registry's
  `harnessSessionId`, orphaning the original transcript — while the `process`
  runner has always resumed (`ClaudeCodeAdapter._resume_argv`). Confirmed
  against the shipped Claude Code CLI that `-r/--resume <id>` resumes
  interactively, and that resuming an unknown id **exits 1 immediately** ("No
  conversation found with session ID: …") — the failure mode that makes a
  post-spawn liveness probe + fresh-spawn fallback part of the design rather
  than an afterthought. Cursor stays out: `cursor-agent` has no pre-assignable
  session id, so it cannot be tmux-hosted at all (issue-32), which is the
  condition the issue itself set.
- **Next:** implement T1–T10.
- **Blockers:** none. Tier 3 (`human-approves-pr`): spec + code approved together
  at the PR.

### 2026-07-25 — implemented (T1–T10)

- **Phase:** implementation → needs-review
- **Did:**
  - `harness/base.py`: `interactive_resume_argv(prompt, session_id)` raising
    `UnsupportedRunnerError` by default (the same "this harness can't" seam as
    `interactive_argv`); `harness/claude_code.py` implements it as
    `--resume <id> … <prompt>`. Cursor deliberately left unimplemented — it
    cannot be tmux-hosted at all.
  - `runner.py`: `TmuxRunner.spawn(..., resume=False)` selecting the resume
    argv, and `survived(target, delay, sleeper=time.sleep)` — sleep the grace
    period (skipped at `delay <= 0`), then re-read `has_live_session`.
  - `webhook/dispatcher.py`: `TmuxConfig.resume_on_respawn` /
    `resume_probe_seconds` (hot-reloaded with the rest of the routing policy);
    `_try_resume` returning the recorded id or `None`, with every doubt (opt-out,
    no id, `[A-Za-z0-9._-]{1,128}` shape check, unsupported harness, tmux
    failure, dead pane) landing on `None` + `session.resume_failed`;
    `_respawn_tmux` spawning fresh only when the resume was abandoned, keeping
    the resumed id in the registry and tagging `session.respawned` with
    `resumed`.
  - `eventlog.py`: registered `session.resume_failed`, documented `resumed` on
    `session.respawned`.
  - Config: `resumeOnRespawn` / `resumeProbeSeconds` in
    `.the-loop/cli-config.schema.json` and both cli-config yamls (dogfood +
    packaged template).
  - Tests: adapter/runner/config unit tests (resume argv, unsupported harness,
    `survived` live/dead/no-wait, `TmuxConfig` parsing) and four stub-tmux
    integration scenarios (respawn resumes the recorded id and stays quiet on
    the ticket; an unresumable conversation falls back to a fresh session with
    the event still as its boot prompt, asserting the `session.resume_failed` /
    `resumed: false` trail; `resumeOnRespawn: false` respawns fresh). The
    stub tmux grew a `STUB_TMUX_PANE_DEAD_ONCE` mode so a dead-then-respawned
    session is expressible.
  - Docs: `cli/README.md` (`routing.tmux` table + the resume paragraph) and
    `docs/capabilities/interactive-sessions.md` (behaviour bullet + history row).
- **Checkpoint/tests:** `make check` green — ruff, markdownlint (210 files),
  ruff format, pyright 0 errors, `validate_config.py` VALID, pytest 327 passed.
- **Next:** open the PR with the reviewer briefing; request review.
- **Blockers:** none.

## Review cycles

| Cycle | Type (self/critic) | Reviewer | Outcome | Link |
|-------|--------------------|----------|---------|------|
| 1 | self | the-loop (implementing agent) | Two findings, both fixed: (a) AC3.2 had no test — the fallback scenario now asserts the `session.resume_failed` record and `resumed: false`; (b) the probe's bound (a harness slower to fail than `resumeProbeSeconds` is recorded as a successful respawn) was implicit — written into design.md § Error handling and the PR briefing. | this PR |
| 2 | self | the-loop (implementing agent) | No new findings: verified the fallback re-enters `TmuxRunner.spawn`, whose stale-session clearing kills the dead resume attempt before the fresh `new-session`; `eventlog.emit` keeps `resumed=False` (it filters only `None`); the probe targets the same `loop-<slug>` the spawn just created. | this PR |
| 3 | self (security lens, `security.review.mechanism: auto`) | the-loop (implementing agent) | One finding, fixed: the id shape check `[A-Za-z0-9._-]{1,128}` allowed a **leading dash**, so a corrupted registry file could set `harnessSessionId: --dangerously-skip-permissions` and have it land in the harness invocation as a *flag* (`claude --resume --dangerously-skip-permissions …`) rather than as a value — defeating the exact property the check exists for. Tightened to `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`, with a regression scenario (`test_a_flag_shaped_session_id_is_never_passed_to_the_harness`) and the spec/capability text updated. Risk tier 3 < `security.review.humanSignOffMinTier` (4), so no named human security sign-off is required. | this PR |
| 4 | self | the-loop (implementing agent) | No new findings — stopped per `reviews.stopOnNoNewFindings`. `reviews.critics` is empty in this repo's config, so no critic harness is configured to run. | this PR |

## Final validation evidence

Local gate (`make check`) green in full: ruff clean, markdownlint 0 errors over
210 files, `ruff format --check` clean, pyright 0 errors, all six config files
VALID, pytest **327 passed**.

Acceptance criteria are demonstrated by:

| AC | Evidence |
|----|----------|
| R1.1, R1.2 | `test_respawn_resumes_the_dead_sessions_conversation` — the respawn's argv is `claude --resume uuid-1 <event>` and the registry still holds `uuid-1` |
| R1.3 | `test_resume_on_respawn_can_be_switched_off` — no `--resume` anywhere, a fresh `--session-id` spawn |
| R1.4 | `TestInteractiveResumeArgv::test_cursor_cannot_resume_interactively` + `test_spawn_with_resume_fails_for_a_harness_that_cannot_resume` |
| R1.5 | `_SESSION_ID_RE` guard in `_try_resume` + `test_a_flag_shaped_session_id_is_never_passed_to_the_harness` (a dash-led id is refused, not handed to the CLI) |
| R2.1, R2.4, R2.5 | `TestSurvivedProbe` — live/dead/missing panes, and no wait at `delay <= 0` |
| R2.2, R2.3 | `test_an_unresumable_conversation_falls_back_to_a_fresh_session` — fallback spawn carries the same boot prompt and the delivery is marked processed |
| R2.6 | same test as R1.1 (`announcer.calls == []`) and the pre-existing `test_respawn_does_not_re_announce` |
| R3.1, R3.2 | event-log assertions in the fallback scenario (`session.resume_failed` at warning level, `session.respawned` with `resumed: false`) |
| R4.1, R4.2 | `TestRoutingConfigRunner` defaults/parsing + `make validate` over the schema and both cli-config yamls |
