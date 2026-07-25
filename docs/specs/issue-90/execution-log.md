---
type: execution-log
workItem: "issue-90"
phase: needs-review
status: in-progress
---

# Execution Log: pre-trust the workspace before spawning a harness session

> Append-only log of progress for the user's visibility. Checked in alongside
> the spec at `docs/specs/issue-90/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-25 |  | Issue #90: claude still asks to trust the workspace even under `--dangerously-skip-permissions`; the-loop should write the required config before spawning. |
| design | 2026-07-25 |  | Three seams: new `trust.py` (config layout + safe read-merge-write), a `prepare_environment()` hook on the adapter contract, and dispatcher calls on both spawn paths. |
| tasks-breakdown | 2026-07-25 |  | 12-task DAG |
| implementation | 2026-07-25 |  | Implemented on `claude/github-issue-90-y6uqhg` |
| needs-review | 2026-07-25 |  | PR #92 opened; rebased onto #91 (issue-89); awaiting human review + the tier-4 named security sign-off |
| complete |  |  |  |

## Progress entries

### 2026-07-25 — spec drafted

- **Phase:** requirements → design → tasks
- **Did:** Established the actual mechanism before designing anything, by reading
  it off the shipped Claude Code CLI rather than guessing: workspace trust lives
  in `projects[<path>].hasTrustDialogAccepted` in the user config file (with the
  lookup walking **up** from the cwd), onboarding in
  `hasCompletedProjectOnboarding` beside it, and the bypass-permissions
  disclaimer in `skipDangerousModePermissionPrompt` in the user settings file
  (current builds migrate the legacy top-level `bypassPermissionsModeAccepted`
  into it). That also explains the issue's core observation: none of these is a
  permission *rule*, so `--dangerously-skip-permissions` cannot silence them.
  Two findings shaped the design:
  - ancestor entries grant trust, which makes "trust the workspace root once"
    tempting and wrong — it would silently trust every future checkout under the
    root, so the design writes the exact spawn directory only, with a dedicated
    regression test;
  - `CLAUDE_CODE_SANDBOXED=1` short-circuits the trust check entirely, i.e. there
    is a one-line "fix" available — rejected in design §8 because asserting a
    sandbox that does not exist is a lie to the harness.
- **Risk tier:** raised to **4**. This writes to the operator's own global
  harness config and can pre-accept a safety disclaimer on their behalf, which is
  a wider blast radius than the usual CLI change; `security.humanSignOffMinTier: 4`
  therefore applies and the PR briefing requests a named security sign-off.
- **Next:** implement T1–T12.
- **Blockers:** none.

### 2026-07-25 — implemented (T1–T12)

- **Phase:** implementation
- **Did:**
  - **T1/T2** — new `cli/the_loop/trust.py`: `TrustConfig` /`TrustResult`, the
    `_update_json` read-merge-write (no-write-when-unchanged, temp file +
    `os.replace`, `0600` on creation, per-path lock, refuse-on-unparseable) and
    `ClaudeTrustStore` (config-dir/config-file/settings-file resolution honouring
    `CLAUDE_CONFIG_DIR` and the `.config.json` preference; exact-directory
    project keys; `trust()`; `accept_bypass_permissions()`).
  - **T3** — `HarnessAdapter.prepare_environment(cwd)` (base no-op, so
    cursor-agent needs nothing), `ClaudeCodeAdapter` implementation with
    `auto | always | never` bypass gating, `build_adapters(..., trust)`.
  - **T4** — `RoutingConfig.harness_trust`, threaded through both CLI entry
    points and `reload()`, plus `Dispatcher._prepare_environment` called from
    `_spawn_for` (before either runner) and `_respawn_tmux`. Never raises, never
    changes the dispatch outcome.
  - **T5** — `workspace.trusted` / `workspace.trust_failed` event types.
  - **T6/T7** — 30 unit tests + 5 Gherkin integration scenarios. The integration
    tests assert **ordering** (the trust key was already on disk at the moment
    the harness was started), not merely the end state — that is what proves the
    dialog cannot appear.
  - **T8/T9/T10** — schema + both `cli-config.yaml`s, `cli/README.md`, the
    observability and automation references, both affected capability docs with
    history rows, and `decision-037`.
- **Evidence:** `ruff check` + `ruff format --check` clean, `pyright` 0 errors,
  `markdownlint` 0 errors, `validate_config.py` all VALID, `pytest` **352
  passed** (37 of them new).
- **Next:** self/critic review, then open the PR with the briefing.
- **Blockers:** none.

### 2026-07-25 — rebased onto main (issue-89 landed in between)

- **Phase:** needs-review
- **Did:** Owner asked for a rebase on PR #92. `main` had gained #91 (issue-89:
  resume the harness conversation when a dead tmux session is respawned), which
  rewrote the exact function this work item also touches. Two conflicts:
  - `cli/README.md` — a heading #91 reworded, adjacent to the new
    `harnessTrust` section. Textual; took both.
  - `webhook/dispatcher.py::_respawn_tmux` — the substantive one. issue-89
    split the respawn into a **conversation-resume attempt** followed by a
    fresh-conversation fallback, and `_try_resume()` starts a harness process
    of its own. Resolving the conflict "where the lines used to be" would have
    put the trust write *between* the two starts, leaving the resume path — the
    common case — still stalling on the dialog. Moved the
    `_prepare_environment` call **above** `_try_resume` so it precedes every
    harness start.
- **Test follow-through:** `TmuxRunner.spawn` gained a `resume` kwarg, so the
  `DeadTmux` double needed it; and the respawn now calls `spawn` twice, which
  broke an assertion that assumed exactly one call. Rather than relax it,
  strengthened it: the test now asserts the directory was trusted at **every**
  recorded harness start, which is the property that actually matters and would
  have caught the naive conflict resolution.
- **Evidence:** `ruff` + `pyright` + `markdownlint` clean, config validation all
  VALID, `pytest` **367 passed**.
- **Next:** awaiting the owner's review and the tier-4 security sign-off.
- **Blockers:** none.
