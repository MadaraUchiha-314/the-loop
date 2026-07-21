# Decision 022 — Auto-upgrade the installed plugin from the SessionStart hook

- **Status:** accepted
- **Date:** 2026-07-21
- **Work item:** issue #38

## Context

the-loop is installed as a Claude Code / Cursor plugin from this GitHub repo
(decision-001, decision-015). Once installed, the plugin's files are a static git
checkout under the harness's plugin directory; they only change when the user runs
`/plugin update` (or reinstalls) by hand. In practice that rarely happens, so sessions
drift onto stale versions of the-loop's skill, commands, templates and rules — the exact
opposite of "always run the latest loop." Issue #38 asks for the plugin to keep itself
current so a new session is always up to date.

Note the distinct, pre-existing `/the-loop:upgrade-the-loop` command: that reconciles a
**project's** `.the-loop/` files with the installed plugin version. This decision is
about keeping the **installed plugin itself** current — the input that command
reconciles against.

## Decision

The Claude Code `SessionStart` hook (`hooks/hooks.json`) runs a new
`hooks/session-start.sh` that, before emitting the config reminder, fast-forwards the
installed plugin's git checkout to `origin`:

- **Fast-forward only, on the checked-out branch.** `git -C "$CLAUDE_PLUGIN_ROOT" pull
  --ff-only origin <branch>`, where `<branch>` is the checkout's current
  `symbolic-ref`. A detached/pinned checkout has no branch and is skipped.
- **Best-effort and non-blocking.** Fully quiet, time-boxed (`timeout`, default 15s, when
  available), and it always `exit 0`. Offline, no network, no `git`, no
  `CLAUDE_PLUGIN_ROOT`, non-git directory — every failure mode is a silent skip. A
  session must start regardless.
- **Never touches a dirty checkout.** If `git status --porcelain` is non-empty the
  upgrade is skipped, so a developer hacking on the-loop itself (or a local dev install)
  is never disrupted, and an unrelated fast-forward is never attempted over local edits.
- **Announces only real updates.** It compares `HEAD` before/after and prints a one-line
  notice into session context only when the SHA actually moved.
- **Opt-out and tuning via env.** `THE_LOOP_AUTO_UPGRADE=0` disables it entirely;
  `THE_LOOP_UPGRADE_TIMEOUT` overrides the network time-box.

Updated files take effect for the next session (and for anything the harness loads after
the hook runs), which is the "up to date when a new session starts" guarantee.

## Rationale

- **git fast-forward is the mechanism the install already provides.** The marketplace
  install is a git checkout; pulling it is the smallest possible "upgrade" and needs no
  new distribution channel. `--ff-only` guarantees we never create merge commits or
  rewrite history, so we can't corrupt the checkout.
- **A hook is the only always-on entry point.** `SessionStart` fires on every
  `startup|resume` without user action — the requirement is precisely "on every new
  session." Slash commands (`/plugin update`) require the user to remember.
- **Safety over freshness.** Every ambiguous state (dirty tree, detached HEAD, offline,
  missing tools) skips rather than guesses. The worst case is "stayed on the current
  version," never "broke the session" or "clobbered local work."
- **Claude-Code-only, by construction.** Cursor has no `SessionStart` event, so the
  Cursor reminder stays in `rules/the-loop.mdc`. Cursor also resolves the plugin from
  the repo directly rather than from a managed checkout, so it does not need a hook to
  self-upgrade. This is noted in `hooks/hooks.json` and the README.

## Consequences

- New file `hooks/session-start.sh` (executable); `hooks/hooks.json` now invokes it via
  `sh "${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh"` instead of an inline command.
- New env vars: `THE_LOOP_AUTO_UPGRADE` (opt-out) and `THE_LOOP_UPGRADE_TIMEOUT`.
- Behaviour is covered by `cli/tests/test_session_start_hook.py` (fast-forward,
  up-to-date no-op, opt-out, dirty-skip, config reminder, and never-fail paths).
- **Re-evaluation trigger:** if a harness ships a first-class "keep plugins updated"
  setting, or marks its plugin checkout as managed-only (so a manual `git pull` conflicts
  with its own version tracking), prefer that mechanism and retire the git pull.
