# Decision 054: the CLI enables the-loop's own plugin in the harness's **user settings** before a spawn

- **Status:** proposed
- **Date:** 2026-08-04
- **Deciders:** @MadaraUchiha-314 (issue #143)
- **Work item:** issue-143
- **Spec:** `docs/specs/issue-143/`
- **Extends:** [decision-036](decision-036.md) / [decision-052](decision-052.md) (the
  pre-spawn preparation step this joins)

## Context

Issue #143: *"the-loop's CLI should add itself as enabled plugins before it starts the work
on a repo"*, with the target settings shape spelled out (`extraKnownMarketplaces["the-loop"]`
plus `enabledPlugins["the-loop@the-loop"]`).

The daemon clones a repository per work item and spawns a harness session in that fresh
checkout. Everything that session knows about the loop — the `the-loop` skill, the
`/the-loop:*` commands, the SessionStart hook that states the operating rules — arrives
through **the plugin**. decision-036 made the session *start* (workspace trust,
bypass disclaimer) and decision-052 made that trust effective; neither installs the plugin.
On a machine where the operator never ran `/plugin marketplace add` by hand, the-loop hands
a session a work-on prompt for machinery it does not have, and it works the ticket as a
plain agent: no phase labels, no spec chain, no gates. This is the same gap `CLAUDE.md`
records for cloud/web sessions in this repository, one layer down.

The harness reads plugin state from a settings file, and Claude Code merges settings from
several scopes. So the question is not *whether* to write it, but **where**.

## Decision

**Write the marketplace + enablement into the harness's own USER settings file**
(`<config dir>/settings.json`, honouring `CLAUDE_CONFIG_DIR`) as part of the existing
pre-spawn preparation, governed by a new `routing.harnessPlugins` block
(`enabled: true`, `marketplaceRepo: MadaraUchiha-314/the-loop`).

It reuses `harnessTrust`'s writer and its guarantees — those two keys only, merged into
what is already there, temp file + atomic replace, nothing written once both hold a value,
an unparseable file reported rather than overwritten — and adds two rules of its own:

- **An existing value is never changed.** A `the-loop` marketplace that already points at a
  fork or a local checkout keeps pointing there; an `enabledPlugins` entry already set to
  `false` stays `false`. This write is a convenience, never an override.
- **Only `owner/repo` is written.** `marketplaceRepo` is validated before it lands in the
  file, and it is read only from the operator's own config — never from an event payload or
  a cloned repository, so a work item cannot redirect a session at a marketplace of its
  choosing.

The step is **independent** of `harnessTrust`: either switch may be off without the other.
Failures are best-effort (warning + `workspace.trust_failed`, the spawn proceeds), and
`cursor-agent`, which has no such surface, stays a silent no-op.

Consequences:

- **The write is user-global.** `enabledPlugins` in the user settings file is not scoped to
  the-loop's checkouts, so the plugin — skill, commands, and its SessionStart hook — also
  loads in the Claude Code sessions the operator starts by hand. This is the same asymmetry
  `harnessTrust.acceptBypassPermissions` carries, it is what installing a plugin means, and
  it is stated in the schema, the config reference and the capability doc rather than left
  to be discovered. `harnessPlugins.enabled: false` is the opt-out.
- **Pointing `marketplaceRepo` at a fork is a decision to run that fork's code** in every
  session on the machine. Said out loud in the same places.
- **`workspace.trusted` now covers plugin enablement too** — one pre-spawn step keeps one
  audit trail; its `applied` list names the settings file.
- This repository's own `.claude/settings.json` carries the same two entries, so a
  cloud/web session here loads the plugin without the daemon being involved.

## Alternatives considered

- **Write the checkout's `.claude/settings.json`.** Rejected: it is a *tracked* file in the
  work item's clone, so the daemon's convenience write would appear as a modified file in
  every PR the loop produces.
- **Write the checkout's `.claude/settings.local.json`.** Rejected: untracked only *by
  convention* (the harness adds it to `.gitignore` when it creates it). In a repository that
  neither ignores nor expects it, the daemon would leave a file it authored in the path of an
  agent about to `git add`. the-loop's workspace machinery otherwise never writes into a
  checkout, and this is not worth being the exception.
- **A generic "install these plugins" list.** Rejected on the minimalism ladder: the issue
  asks the-loop to add *itself*, and `marketplaceRepo` already covers the real variant
  (running a fork). A general plugin installer is a different feature, addable later without
  breaking this one.
- **Shell out to `claude plugin install`.** Rejected: it is an interactive-leaning command
  with its own prompts and exit semantics, on a path that must never block a spawn — and
  the-loop already owns a safe writer for the exact file it would edit.
- **Do nothing and document `/plugin install` as a prerequisite.** Rejected: the failure is
  silent. A session without the plugin does not error; it quietly stops running the loop,
  which is precisely the class of gap issue #73 and `CLAUDE.md` already record.
