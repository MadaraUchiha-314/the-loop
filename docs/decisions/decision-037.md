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

- **Trust scope is configurable, defaulting to the workspace root** (`harnessTrust.scope`,
  owner decision on PR #92 — see "Scope: the owner's call" below). `workspace-root` writes
  one `hasTrustDialogAccepted` entry on `routing.workspace.root`, which the harness's
  upward lookup extends to every directory beneath it; `directory` keeps it on the exact
  spawn directory. Widening never happens implicitly — it takes an explicit root, that
  root must actually contain the spawn directory, and a root as broad as `/` or `$HOME`
  degrades to per-directory trust with a warning.
- **`hasCompletedProjectOnboarding` is always per-directory**, under both scopes, because
  the harness reads it from the exact project key with **no** ancestor walk (verified in
  the shipped CLI: `xd()` → `projects[<canonical cwd>]`). Root trust alone would silence
  the trust dialog and leave the onboarding screen behind it in every fresh checkout —
  which is why the per-directory machinery stays regardless of scope.
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
- **The two writes have different blast radii, and the asymmetry is forced.** Trust is
  recorded **per directory**, so it reaches exactly the checkout the work item runs in.
  The bypass acceptance is a **user-global** setting — the only form the harness offers —
  so accepting it removes the bypass-mode confirmation from every Claude Code session on
  that account, interactive ones included. That is why it is gated on the operator having
  already asked for bypass mode rather than bundled into the trust write, and why the
  schema, the README and the reviewer briefing all state it outright instead of leaving
  the operator to discover it. `never` plus a narrower `--permission-mode acceptEdits`
  avoids the acceptance entirely.
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

## Scope: the owner's call (PR #92 review)

This PR originally shipped **exact-directory trust only**, argued from least privilege:
an ancestor entry grants trust to every future checkout under the root, including repos
the operator has not started watching. The owner overrode that:

> this should be configurable. and default should be trust all folders within the
> workspace root. if claude needs additional permissions per repo, then what we are doing
> in this PR should still be kept.

Recorded because it is a deliberate reversal, and the reasoning is sound: the workspace
root is a directory the operator **created for the-loop to work in**. Every path under it
is by construction a checkout the daemon made, so "trust the workspace" is a truer
statement of intent than "trust each of the N directories the daemon happens to have
created so far" — and it covers the cases per-directory trust misses entirely: a repo the
operator clones into the workspace by hand, a nested repo the agent walks into, a
directory a session `cd`s to. Least privilege remains one config line away
(`scope: directory`) for an operator whose workspace root holds more than the-loop's own
checkouts.

The "should still be kept" half is load-bearing rather than a courtesy: per-directory
writing is not merely retained as an option, it is **required under both scopes** for the
onboarding key, which is not ancestor-inherited.

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
- **Trust the workspace *root* once instead of each checkout** — originally rejected here
  on least-privilege grounds. **Superseded by the owner's decision on PR #92**: this is
  now the default (`scope: workspace-root`), with exact-directory trust kept as
  `scope: directory`. See "Scope: the owner's call" above. The one technical objection
  that survives — that root trust does not cover `spawnWorkdir`-only setups, which have
  no root — is handled by falling back to per-directory trust when no root is configured,
  so the two scopes behave identically there.
- **Trusting the root *instead of* writing anything per directory** — rejected on the
  facts, not on taste: `hasCompletedProjectOnboarding` is not ancestor-inherited, so a
  root-only write leaves the onboarding screen in front of every fresh checkout.
- **A generic "merge this JSON blob into the harness config" config block** — maximally
  flexible, and an open-ended footgun pointed at the operator's own configuration.
  Rejected on the minimalism ladder: two well-understood keys, named in the schema, beat
  an arbitrary write primitive.
- **Put the logic in the dispatcher rather than the adapter** — rejected: the dispatcher
  is deliberately harness-agnostic (`_spawn_argv`, `interactive_argv`,
  `UnsupportedRunnerError` all live on adapters). "What does this harness need on disk to
  start unattended" is the same kind of knowledge, and hanging it off the adapter leaves
  the seam for a cursor-agent equivalent instead of hard-coding Claude Code into routing.
