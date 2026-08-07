# Decision 064: Cursor is installed by the same probe as Claude Code, and falls back to the documented local checkout

- **Status:** proposed
- **Date:** 2026-08-06
- **Deciders:** @MadaraUchiha-314 (issue #157)
- **Work item:** issue-157
- **Spec:** `docs/specs/issue-157/`
- **Amends:** [decision-057](decision-057.md) § *Cursor, parked* — the deferral is
  discharged; everything else in 057 (harness-owned installing, plan-then-execute,
  scope honoured-or-refused, one marketplace source) stands unchanged.
- **Extends:** [decision-015](decision-015.md) (the-loop ships as a Cursor plugin).

## Context

decision-057 shipped `the-loop install` / `upgrade` for the CLI and Claude Code, and
parked Cursor on the owner's call during PR #153: *"Let's park cursor for now. For now
let's only support claude."* The reason recorded was specific — the first cut **hard-coded
a local clone**, and as of Cursor 2.5 (Feb 2026) plugins were installed from the
marketplace site or `/add-plugin` in the editor, with `cursor-agent plugin marketplace add`
reported to exist but no documented CLI install and no project-local plugin directory. A
Cursor component would have been *"clone-and-hope with a permanently skipped project
scope"*.

Issue #157's own first step was to run `cursor-agent plugin --help` on a machine with
Cursor and design from the output. **That output is still unobtainable**: `cursor.com/docs`
and `forum.cursor.com` return HTTP 403 from the agent environment, and no `cursor-agent`
binary is reachable. Waiting for it has cost operators the Cursor half of the command for
six months, and would cost more.

The question this decision answers is therefore: *can a Cursor component be built that is
correct without knowing what that command prints?*

## Decision

**Yes — by making the answer a runtime question. `cursor` becomes a component whose route
is chosen by probing the binary, with the local checkout demoted from design to fallback.**

1. **`cursor` is a `BINARIES` entry (`cursor-agent`) plus a planner** — exactly the
   extension point decision-057 named. It joins `COMPONENTS`, the default set (every
   harness found on `PATH`) and `all`. `plan()`'s hard-wired dispatch becomes a `PLANNERS`
   mapping.
2. **The surface is asked for, not assumed.** `plan_cursor` runs the *same* `probe()` as
   Claude Code (`plugin --help`, then `plugin install --help` — the command actually
   driven), and on a positive answer calls the *same* `_harness_cli_steps`: marketplace
   add/update, plugin install/update, with `--scope` passed through when the binary
   accepts it. The day Cursor ships a plugin CLI, the-loop drives it with no release of
   ours.
3. **One fallback, and it is one this repository already prints.** No usable surface →
   the local checkout at `~/.cursor/plugins/local/the-loop` documented in
   `docs/guide/installation.md`: `git clone` at install, `git -C … pull --ff-only` at
   upgrade, `already` when the checkout is present, and a **reported skip** when `git` is
   absent, when an upgrade finds nothing to upgrade (an upgrade never becomes an install),
   or when the path exists without a `.git` — which is left byte-for-byte as found.
4. **Project scope is still skipped, and no longer permanently.** Cursor documents no
   project-local plugin mechanism, so `--scope project` reports `skipped` with the manual
   instruction. The moment `cursor-agent` reports a `--scope` flag, point 2 passes the
   operator's scope straight through. A scope that cannot be expressed is never widened.
5. **Nothing else changes.** No new flag, no new command, no new dependency, no change to
   the report shape, the JSON records or the exit codes.

## Consequences

**Easier.** One command sets up a machine that has both harnesses, and the default
(`the-loop install`) does the obvious thing on it. Cursor's terminal installation stops
being a docs page an operator has to find. The marketplace source is validated, printed
and shared with the daemon for Cursor exactly as for Claude Code.

**Harder / accepted costs.**

- **The clone route assumes the marketplace repository *is* the-loop.** Cursor loads a
  local checkout as a plugin from its root manifest, so `--from acme/fork` works when the
  fork is a fork of the-loop — the only shape that key is meant to take — and not for an
  arbitrary marketplace repository holding many plugins. The resolved repository is
  printed in the plan header before anything is fetched.
- **The command now runs `git`.** A binary the operator already has, invoked as an argv
  list with no shell, against one URL built from an already-validated `owner/repo`, into
  one path under their home directory. It never deletes, never overwrites, and never
  writes into a directory it did not create as a checkout.
- **Cursor's side is still unverified.** Whether a cloned plugin loads in Cursor **CLI**
  mode is a property of Cursor, not of this command; it is recorded as an open question on
  the ticket and in `requirements.md`. The design does not depend on the answer, and the
  end-to-end row of the testing plan says so rather than claiming coverage it does not
  have.
- **A second `--ff-only` failure mode.** A developer's local checkout with commits on top
  reports `failed` carrying git's own message. That is deliberate: the alternative is a
  merge commit the-loop invented in someone's working tree.

## Alternatives considered

- **Keep waiting for `cursor-agent plugin --help`.** The status quo, and the reason the
  ticket has been open since February. A probe-first design is what the probe was *built*
  for; the confirmation is still wanted, but as a docs input, not a gate.
- **Write Cursor's plugin configuration file directly**, mirroring the decision-054
  Claude fallback. Rejected: that file's format is not documented anywhere reachable, so
  writing it would be the invention decision-057 forbids — and a wrong guess about a file
  format fails silently, where a wrong guess about a command line fails loudly.
- **Ship `cursor` as a component that only ever skips, with instructions.** Honest, and
  strictly worse: the operator still does the work by hand, and the instruction printed
  would be the very command we declined to run.
- **`git clone --depth 1`.** Faster, and a divergence between the documented command and
  the executed one for a saving nobody would notice on a repository this size.
