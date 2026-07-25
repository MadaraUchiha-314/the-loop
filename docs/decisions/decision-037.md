# Decision 037: pre-seed the harness's own config before spawning — trust the exact checkout, and accept the bypass disclaimer only when it was already requested

- **Status:** proposed
- **Date:** 2026-07-25
- **Deciders:** @MadaraUchiha-314 (issue #90)
- **Work item:** issue-90
- **Spec:** `docs/specs/issue-90/`

## Context

Issue #90: *"claude still asks to trust the workspace even when it's run using
dangerously-skip — before the-loop spawns a claude session, it should add all the
required configs in whatever place necessary so that claude doesn't ask for this trust
workspace permission."*

Two dialogs stand between an auto-executed work item and any actual work, and neither is
a permission *rule* — which is exactly why `--dangerously-skip-permissions` does not
silence them:

1. **Workspace trust** ("Do you trust the files in this folder?"), shown for any
   directory not marked trusted in the harness's user config. Since decision-034 gives
   every work item its **own** checkout (`<root>/.worktrees/…/<slug>` or
   `<root>/.work-items/<slug>/…`), *every single spawn* lands in a directory the harness
   has never seen. This is not an edge case; it is the default path.
2. **The bypass-permissions disclaimer**, the one-time acceptance that gates
   `--dangerously-skip-permissions` itself. Unaccepted, the harness either asks for it or
   downgrades the permission mode back to `default` — the flag configured in
   `routing.harnessArgs` silently does nothing.

The failure mode is worse than a visible error. With `runner: tmux` the-loop records
`session.spawned`, bracket-pastes the event prompt into a TUI that is showing a modal,
and the work item simply never moves — the daemon looks healthy and nothing happens.

## Decision

Add a **pre-spawn harness preparation step**, owned by a new `the_loop.trust` module,
hung off the adapter contract (`HarnessAdapter.prepare_environment(cwd)`) and called by
the dispatcher on **both** spawn paths (first spawn and the issue-80 respawn), before
either runner starts anything. Configured under
`webhooks.ghWebhook.routing.harnessTrust` (reused by the poller, like the rest of
`routing`).

For Claude Code it writes, into the harness's own user-level files (honouring
`CLAUDE_CONFIG_DIR`, and preferring `<config dir>/.config.json` when that file exists):

- `projects["<spawn dir>"].hasTrustDialogAccepted: true` and
  `hasCompletedProjectOnboarding: true` — removing the trust dialog must not merely
  reveal the onboarding screen behind it;
- `skipDangerousModePermissionPrompt: true` in the user settings file (plus the legacy
  top-level `bypassPermissionsModeAccepted` for older builds) — **only** when the
  operator's own `harnessArgs` already ask for bypass mode.

Four properties make this safe enough to default to **on**:

- **Exact-directory trust, never a parent.** The harness's own lookup walks *up* from the
  cwd, so an ancestor key would silently trust every sibling checkout under the workspace
  root. Only the spawn directory (and its realpath, for symlinked roots) is written, and
  a dedicated test asserts no ancestor key appears.
- **No unrequested permission widening.** `acceptBypassPermissions: auto` (the default)
  follows `harnessArgs`. the-loop refuses to accept a safety disclaimer for a session
  that was not already configured to run that way — the standing "the dispatcher never
  widens permissions itself" rule, applied to config as well as argv. `always`/`never`
  exist for operators who want to decide explicitly.
- **Non-destructive writes.** Only those keys, merged into whatever is already there, via
  a temp file + `os.replace`, `0600` on files we create, **skipped entirely** when the
  value is already correct, and never applied to a file that does not parse as JSON.
- **Audited and reversible.** Every applied change emits `workspace.trusted` (directory
  included) and every failure `workspace.trust_failed`, so
  `the-loop events --type 'workspace.trust*'` answers "what has this daemon trusted on my
  machine?". `harnessTrust.enabled: false` restores the previous behaviour exactly.

Preparation is **best-effort**: a write failure logs a warning, emits
`workspace.trust_failed`, and lets the spawn proceed. Failing the dispatch instead would
release the delivery for retry, and the retry would hit the same unwritable file forever
— burying the work item behind an error the operator has to fix anyway. The open failure
degrades to precisely the pre-issue-90 behaviour and is loud in two places.

A harness with no such surface (cursor-agent today) inherits the base no-op, so the seam
exists without inventing a config format for a harness that has none.

Consequences:

- **the-loop now writes outside its own state directory.** That is a real widening of
  what the daemon touches, and the reason this work item was raised a risk tier and
  carries a named human security sign-off. The bounds above (which keys, which
  directory, merge-not-replace, refuse-on-unparseable) are the whole of it.
- **Trusting a checkout means the repo's `.claude/` hooks and settings load** in the
  spawned session. That is already the operating assumption of auto-execute — the agent
  runs the repo's code, tests and scripts — and the actual gate against hostile repos is
  `routing.authorizedUsers` plus which repos the daemon watches, not a dialog no
  unattended daemon can answer. Stated explicitly in `docs/specs/issue-90/requirements.md`
  rather than left implied.
- **Residual concurrent-write risk.** An interactive harness process could write the same
  config file between our read and our replace and lose its change. The
  no-write-when-unchanged rule shrinks the window to the first spawn into a given
  directory; cross-process locking on a file we do not own is not worth the complexity
  (YAGNI). Recorded here rather than hidden.

## Alternatives considered

- **Set `CLAUDE_CODE_SANDBOXED=1` in the spawned environment** — the CLI does
  short-circuit its trust check on it, so this is a one-line "fix". Rejected: it is a
  sandbox-mode signal with other behavioural effects, and asserting a sandbox that does
  not exist is a lie to the harness that would break in unpredictable ways on any future
  build.
- **Write `.claude/settings.local.json` inside the checkout** — appealingly local, but
  workspace settings are *ignored until the workspace is trusted*, which is the very
  thing being configured (chicken-and-egg), and it dirties a git worktree the agent then
  has to remember not to commit. Rejected.
- **Tell operators to run `claude` once per workspace by hand** — there is no stable
  directory to pre-trust: decision-034 mints a new one per work item. That is the bug.
- **Trust the workspace *root* once instead of each checkout** — ancestor trust does
  work, and is one write instead of N. Rejected as least-privilege: it grants trust to
  every future checkout under the root, including repos the operator has not started
  watching yet, and it would not cover `spawnWorkdir` setups at all.
- **A generic "merge this JSON blob into the harness config" config block** — maximally
  flexible, and an open-ended footgun pointed at the operator's own configuration.
  Rejected on the minimalism ladder: two well-understood keys, named in the schema, beat
  an arbitrary write primitive.
- **Put the logic in the dispatcher rather than the adapter** — rejected: the dispatcher
  is deliberately harness-agnostic (`_spawn_argv`, `interactive_argv`,
  `UnsupportedRunnerError` all live on adapters). "What does this harness need on disk to
  start unattended" is the same kind of knowledge, and hanging it off the adapter leaves
  the seam for a cursor-agent equivalent instead of hard-coding Claude Code into routing.
