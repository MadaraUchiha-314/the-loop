# Decision 052: trust the spawn directory itself under every scope — `harnessTrust.scope` only widens

- **Status:** proposed
- **Date:** 2026-08-04
- **Deciders:** @MadaraUchiha-314 (issue #136)
- **Work item:** issue-136
- **Spec:** `docs/specs/issue-136/`
- **Revises:** [decision-037](decision-037.md) (the scoping half; everything else stands)

## Context

Issue #136: *"the-loop's CLI when it launches claude session on a cloned repo still asks
for 'Trusted Workspace' permission … there's some code in the-loop's CLI to add the newly
cloned repo to the trusted workspace, but there seems to be some race conditions or it's
not working."*

decision-037 shipped the pre-spawn trust write, and PR #92 made `workspace-root` the
default scope: one `hasTrustDialogAccepted` entry on the workspace root, relying on the
harness's ancestor walk to cover the checkouts beneath it. It also established, from the
shipped CLI, that `hasCompletedProjectOnboarding` is **not** ancestor-inherited and must
be written per directory.

That last observation was right and incomplete. `hasTrustDialogAccepted` has **two**
readers in Claude Code, and they scope it differently:

| reader | lookup | governs |
|---|---|---|
| base trust | `projects[cwd]`, then walks **up** | the untrusted-workspace state generally |
| grant gate | `projects[cwd]` **only** | whether the dialog is shown *anyway*, and whether the repo's `.claude/settings.json` `permissions.allow` / `additionalDirectories` load |

Under `scope: workspace-root` the base check passes via the root entry, and then the grant
gate — finding no exact-key entry for the brand-new checkout — asks whether the repository
ships project-scoped grants. If it does, the dialog is rendered. The harness names the
missing key itself:

```text
Ignoring 1 permissions.allow entry from .claude/settings.json: this workspace has not
been trusted. Run Claude Code interactively here once and accept the trust dialog, or
set projects["<the checkout>"].hasTrustDialogAccepted: true in <config>.
```

So the reporter's symptom is deterministic, not a race, and it hits precisely the common
case: any repo that carries a `.claude/settings.json` with allow-rules — the-loop's own
repository among them. `scope: directory` was never affected, which is why the feature
looked correct when it shipped. `--dangerously-skip-permissions` does not help: the grant
gate short-circuits only on sandbox mode, an in-session acceptance, a background session
kind, `cwd == $HOME`, or the exact-key trust — never on the permission mode.

## Decision

**Both keys are always written on the exact spawn directory, under every `scope`.**
`harnessTrust.scope` is redefined from *"where the trust entry goes"* to *"whether trust
**additionally** widens to an ancestor"*:

- `workspace-root` (unchanged default) writes a **second** `hasTrustDialogAccepted` entry
  on `routing.workspace.root`, so the walking check still covers checkouts the-loop never
  spawned into — the thing the owner asked for on PR #92, preserved exactly.
- `directory` keeps trust on the spawn directory alone. Byte-for-byte unchanged.

Every existing guard stays: a root that does not contain the spawn directory is dropped,
`/` and `$HOME` degrade to per-directory trust with a warning, an unparseable config is
reported and never overwritten, nothing is written when the value already holds, and a
failed write warns, emits `workspace.trust_failed` and lets the spawn proceed.
`workspace.trusted` now names **every** directory that was trusted, so the audit trail
reports the real scope rather than the widest entry.

Consequences:

- **The trust boundary becomes effective rather than merely declared.** Under
  `workspace-root` the operator had already declared the whole subtree trusted, and the
  ancestor walk already carried every checkout past base trust; this makes the second gate
  agree about a directory that was always meant to be inside the grant. The observable
  new capability is that a cloned repository's own `.claude/settings.json` allow-rules and
  `additionalDirectories` now load — exactly what answering the dialog by hand does, and
  what `scope: directory` already did. Because it is now effective, the schema, the config
  reference and the capability doc state it outright: pre-trusting a clone honours grants
  authored by whoever can push to that repository. `enabled: false` is the opt-out.
- **One more `projects` entry per work item** in the operator's config, alongside the
  `hasCompletedProjectOnboarding` entry that was already written there. Two booleans.
- **decision-037's "trust is recorded per directory, never a parent" bound is gone** —
  it was already gone when PR #92 made `workspace-root` the default; this decision makes
  the docs say what the code does.

## Alternatives considered

- **Keep root-only trust and tell operators to set `scope: directory`.** Rejected: the
  default is the broken configuration, the failure is silent (a modal in a detached tmux
  pane), and `directory` gives up the coverage the owner explicitly asked for on PR #92.
  A default nobody should use is not a default.
- **A third scope value (`root-only`) preserving today's behaviour.** Rejected on the
  minimalism ladder: nobody would choose a scope whose distinguishing property is that the
  dialog stays up.
- **Write `.claude/settings.local.json` into the checkout instead.** Same chicken-and-egg
  decision-037 already rejected: workspace settings are ignored until the workspace is
  trusted, and it dirties a git worktree.
- **Set `CLAUDE_CODE_SANDBOXED=1` for the spawned process.** It does short-circuit both
  gates, and it remains rejected for decision-037's reason: asserting a sandbox that does
  not exist is a lie to the harness with other behavioural effects.
- **Verify the key after writing (re-read, retry).** Rejected: the only thing that could
  remove it is another harness process rewriting its cached config wholesale, and
  defending against that means racing another process's save. Out of scope in
  `bugfix.md`, and unrelated to this deterministic failure.
