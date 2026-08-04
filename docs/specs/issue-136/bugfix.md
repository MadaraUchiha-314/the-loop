---
type: bugfix
phase: requirements-definition
workItem: issue-136
status: approved
approvedBy: []
severity: high
collaborators: [engineer]
overrides: {}
---

# Bugfix spec: a spawned session still opens on the workspace-trust dialog

> Phase 1 of 3 for a bug (bugfix → design → tasks). Human approval for this change
> happens at the PR (`autonomy.tiers."4": human-approves-pr` — the change touches
> `.the-loop/cli-config.schema.json`, an `autonomy.sensitivePaths` match).

## Summary

issue-90 added a pre-spawn step (`routing.harnessTrust`) that marks a freshly cloned
checkout trusted in Claude Code's own user config so an unattended session starts
working instead of stalling on the "Accessing workspace:" dialog. It does not work at
the default scope: the operator still gets the dialog on every spawn.

Reported as [issue #136](https://github.com/MadaraUchiha-314/the-loop/issues/136):

> There's some code in the-loop's CLI to add the newly cloned repo to the trusted
> workspace, but there seems to be some race conditions or it's not working. I still
> get the permissions dialogue in claude everytime.

It is not a race. `routing.harnessTrust.scope` defaults to `workspace-root`, which
writes **one** `hasTrustDialogAccepted` entry on the workspace root and relies on Claude
Code's ancestor walk to cover the checkouts beneath it. That walk is real, but it governs
only *one* of Claude Code's two trust checks. The second check reads the **exact** cwd
project key with **no** ancestor walk, and it is the one that decides whether the dialog
is shown for a repository that ships `.claude/settings.json` — which the-loop's own
repository does.

## Steps to reproduce

1. Configure the daemon with `routing.workspace.root` set (issue-76 checkouts) and
   `routing.harnessTrust` left at its defaults (`enabled: true`, `scope: workspace-root`).
2. Let the-loop clone a repository that ships a `.claude/settings.json` containing
   `permissions.allow` entries (or `permissions.additionalDirectories`) — the-loop's own
   repository is such a repo.
3. Trigger a spawn (`the-loop gh-webhook start` / `poll start`, auto-execute label).
4. Attach to the spawned tmux session.

**Observed:** the TUI is sitting on `Accessing workspace: <checkout> … Yes, I trust this
folder`, with the event prompt pasted behind it. The work item never moves.
**Expected:** the session starts working; no dialog.

Reproduced headlessly (`claude -p` prints the same gate's diagnostic instead of
rendering the dialog):

```console
$ cat ws/repo/.claude/settings.json
{"permissions":{"allow":["Bash(ls:*)"]}}
$ cat home/.claude.json                     # exactly what scope: workspace-root writes
{"projects":{"…/ws":{"hasTrustDialogAccepted":true},
             "…/ws/repo":{"hasCompletedProjectOnboarding":true}}}
$ cd ws/repo && claude -p "hi"
Ignoring 1 permissions.allow entry from .claude/settings.json: this workspace has not
been trusted. Run Claude Code interactively here once and accept the trust dialog, or
set projects["…/ws/repo"].hasTrustDialogAccepted: true in …/home/.claude.json.
```

Claude Code names the missing key itself: the **checkout's own** project key, not the
root's.

## Expected vs actual

- **Expected:** WHEN the daemon has pre-trusted a checkout, THEN the harness spawned in
  it starts working — no trust dialog, and the repository's project-scoped permission
  grants are honoured rather than dropped.
- **Actual:** at the default `scope: workspace-root` the dialog is shown on every spawn
  into a fresh checkout of a repository that carries project-scoped grants, and those
  grants are silently discarded even if the operator dismisses the dialog.

## Root cause (confirmed)

Claude Code answers "is this workspace trusted?" in **two** places, and they scope the
same key differently. Read off the shipped CLI:

| check | how it reads `hasTrustDialogAccepted` | what it gates |
|-------|----------------------------------------|---------------|
| base trust | `projects[cwd]`, then **walks up** the ancestors | the untrusted-workspace state generally |
| grant gate | `projects[cwd]` **only** — no ancestor walk | whether the trust dialog is shown anyway, and whether `.claude/settings.json` grants load |

The grant gate short-circuits to "no dialog" on an exact-key match, and otherwise asks
whether the repo's `.claude/settings.json` / `.claude/settings.local.json` carry
`permissions.allow` rules or `permissions.additionalDirectories`. If they do, the dialog
is rendered **even though base trust already passed via the ancestor walk**. The same
exact-key check guards rule loading, so the project's allow-rules and additional
directories are dropped with an `Ignoring N permissions.allow entries …` diagnostic.

`ClaudeTrustStore.trust()` (`cli/the_loop/trust.py`) writes `hasTrustDialogAccepted` on
the root **instead of** the cwd when a root is supplied:

```python
if root and str(root).strip() and is_within(root, cwd):
    trust_keys = self.project_keys(str(root))
else:
    trust_keys = onboarding_keys
```

So under the default scope the exact cwd key never gets the flag, and the grant gate
never sees it. Under `scope: directory` the same line writes the cwd key and the bug does
not occur — which is why the feature looked correct when it shipped.

The module already knew one key has no ancestor walk (`hasCompletedProjectOnboarding`,
written per spawn directory under both scopes). This is the same discovery for the trust
key's *second* reader: root trust silences the base check and leaves the grant gate
behind it, exactly as root trust alone would have left the onboarding screen behind it.

`--dangerously-skip-permissions` does not help: the grant gate short-circuits only on
sandbox mode, an in-memory same-session acceptance, a background session kind,
`cwd == $HOME`, or the exact-key trust — never on the permission mode.

## Requirements

### Requirement 1 — a pre-trusted checkout starts without a dialog

As an operator running the-loop unattended, I want a spawned session to start working in
a freshly cloned checkout, so that a work item is not parked on a modal nobody is there
to answer.

#### Acceptance criteria (EARS)

1. WHEN the daemon prepares a spawn directory with `harnessTrust.enabled: true` THEN the
   system SHALL record `hasTrustDialogAccepted` on the **exact spawn directory's** project
   key (and its realpath when a symlink makes it differ), under **every** value of
   `harnessTrust.scope`. (AC1)
2. WHEN `harnessTrust.scope` is `workspace-root` and a usable root is supplied THEN the
   system SHALL record `hasTrustDialogAccepted` on the **root's** project key **in
   addition to** the spawn directory's, so that checkouts the-loop never spawned into
   stay covered by the harness's ancestor walk. (AC2)
3. WHEN the supplied root does not contain the spawn directory, or no root is supplied
   THEN the system SHALL record trust on the spawn directory alone — unchanged from
   today's fallback. (AC3)
4. WHEN every key this step would write already holds the desired value THEN the system
   SHALL write nothing, and the spawn SHALL proceed. (AC4)
5. WHEN trust is applied THEN the emitted `workspace.trusted` event SHALL name every
   project key that was written, so the audit trail shows the real scope. (AC5)

### Requirement 2 — the fix is proven and stays proven

#### Acceptance criteria (EARS)

1. The fix SHALL include a regression test that fails before it and passes after,
   asserting the spawn directory carries `hasTrustDialogAccepted` under
   `scope: workspace-root`. (AC6)
2. The fix SHALL include an integration test that drives the dispatcher's pre-spawn
   pre-flight end to end against a fake HOME and asserts the same. (AC7)
3. The documented behaviour (`.the-loop/cli-config.schema.json` `harnessTrust`
   description, `docs/config/`, `docs/capabilities/interactive-sessions.md`) SHALL
   describe what the code now does, including *why* the exact-directory entry is
   mandatory. (AC8)

## Security considerations

**No new attack surface; the widening is bounded by an option the operator already has.**

- **What changes.** Under `scope: workspace-root` one extra project key is marked
  trusted: the spawn directory the daemon just created and is about to run the harness
  in. That directory is already inside the trusted root — the operator's existing
  `workspace-root` grant *already* covers it through the ancestor walk. The change makes
  the two Claude Code checks agree about a directory that was meant to be trusted, rather
  than granting trust to anything new. Under `scope: directory` behaviour is byte-for-byte
  unchanged.
- **Trust boundary.** Workspace trust decides whether a repository's **own**
  `.claude/settings.json` may pre-approve tool permissions and add directories to the
  workspace. Pre-trusting a checkout therefore honours grants written by whoever can push
  to that repository. That boundary is not moved by this change — it is exactly what
  `harnessTrust.enabled: true` already means, and what `scope: directory` already does —
  but it is now *effective*, so it must be stated plainly in the schema and capability
  docs rather than implied (AC8). `harnessTrust.enabled: false` remains the way to opt
  out entirely.
- **Fail-closed.** Every existing guard stays: a root that does not contain the spawn
  directory is ignored, a root as broad as `/` or `$HOME` degrades to per-directory trust
  with a warning, a config file that does not parse is reported and never overwritten,
  and a failed write warns, emits `workspace.trust_failed` and still spawns (degrading to
  the pre-issue-90 dialog rather than to a wider grant).
- **No new inputs.** The spawn directory is derived by the-loop's own workspace machinery
  from the event's repository, never taken verbatim from payload text; nothing new is
  parsed, interpolated, or executed. Writes remain narrow (two boolean keys), merged,
  atomic, owner-only on create, and skipped when already correct.
- **Not a secret surface.** The keys written are booleans in the operator's own harness
  config; no credential is read or written.

## Out of scope

- **The bypass-permissions disclaimer** (`acceptBypassPermissions`). It is a separate,
  user-global setting and works as documented.
- **`hasCompletedProjectOnboarding`.** Already written per spawn directory; unchanged.
- **A concurrently running harness clobbering the config file.** Claude Code caches its
  user config in memory and rewrites it wholesale, so a long-lived session started before
  a trust write can drop it on its own next save. That is a real (if narrow) hazard, but
  it is not what produces the reported "every time" symptom — the deterministic
  exact-key gap is — and defending against it would mean racing another process's
  save rather than fixing our own write. Tracked separately if it is ever observed.
- **Other harnesses.** `cursor-agent` exposes no such config surface and stays a no-op.

## Open questions

None. The reporter's symptom, the shipped CLI's own diagnostic, and the reproduction all
name the same missing key.
