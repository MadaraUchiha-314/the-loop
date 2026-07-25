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

### 2026-07-25 — trust scope made configurable, defaulting to the workspace root

- **Phase:** needs-review
- **Did:** Owner's call on PR #92 — *"this should be configurable. and default
  should be trust all folders within the workspace root. if claude needs
  additional permissions per repo, then what we are doing in this PR should
  still be kept."* This reverses the least-privilege default this PR shipped
  with; recorded as such in decision-037 ("Scope: the owner's call") rather than
  quietly restated, because the original position was argued in the spec.
- **The finding that shaped the implementation:** checked the shipped CLI before
  writing anything, and the two project keys are **not** read the same way.
  `hasTrustDialogAccepted` is resolved by walking *up* from the cwd (so one root
  entry does cover everything beneath it — the owner's ask works), but
  `hasCompletedProjectOnboarding` is read from the exact project key
  (`xd()` → `projects[<canonical cwd>]`) with **no** ancestor walk. A root-only
  write would therefore have removed the trust dialog and left the onboarding
  screen in front of every fresh checkout. So the two keys scope differently:
  trust on the root, onboarding always per spawn directory. That is also the
  concrete sense in which the owner's "what we are doing in this PR should still
  be kept" is load-bearing rather than a courtesy.
- **Guard rails** (kept narrow, so the wider default cannot mean more than
  intended): `project_keys()` still never widens on its own — it takes an
  explicit `root`; a root that does not contain the spawn directory is ignored
  (`is_within`, component-wise so `/ws` does not "contain" `/ws-other`); and a
  root as broad as `/` or `$HOME` degrades to per-directory trust with a warning
  (`is_too_broad`). With no workspace root configured, both scopes behave
  identically.
- **Evidence:** 10 new tests (root scope, sibling reuse, root-outside-cwd,
  `scope: directory`, too-broad root, `is_within`/`is_too_broad` units, config
  mapping); `ruff` + `pyright` + `markdownlint` clean, config validation VALID,
  `pytest` **377 passed**.
- **Next:** awaiting the owner's review and the tier-4 security sign-off.
- **Blockers:** none.

### 2026-07-25 — rebased onto main again; decision renumbered 036 → 037

- **Phase:** needs-review
- **Did:** `main` gained #95 (issue-93: route an event on a PR to its linked
  issue first), which **claimed `decision-036` too** — an add/add collision, two
  different decisions with the same number. Since #95 is merged and this PR is
  not, theirs keeps 036 and this work item's decision is renumbered to
  **037**, with every reference updated (spec, tasks, execution log,
  `trust.py`'s module docstring, the decisions index, both capability docs and
  `reference/automation.md`).
- **Also refreshed the decision's title**, which still read "trust the exact
  checkout" from before the owner's scope decision — it now says "trust the
  workspace root (configurable)", matching what actually shipped.
- **Conflicts** were all "both added a row/section" in shared docs (the
  decisions index, `automation.md`, both capability docs) — resolved by keeping
  both entries. The two later commits also patched `decision-036.md` by name, so
  their hunks were redirected into `decision-037.md` rather than resolved in
  place.
- **Evidence:** `ruff` + `pyright` + `markdownlint` clean, config validation
  VALID, `pytest` **394 passed** (the count rose because #95 brought its own
  tests along with the rebase).
- **Next:** awaiting the owner's review and the tier-4 security sign-off.
- **Blockers:** none.
