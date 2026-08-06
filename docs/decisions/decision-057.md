# Decision 057: `the-loop install`/`upgrade` drives the harness's own installer (Claude Code first), and falls back only to a documented route

- **Status:** proposed
- **Date:** 2026-08-05
- **Deciders:** @MadaraUchiha-314 (issue #152)
- **Work item:** issue-152
- **Spec:** `docs/specs/issue-152/`
- **Extends:** [decision-054](decision-054.md) (the settings keys the daemon writes before
  a spawn, reused here as the Claude fallback) · [decision-019](decision-019.md) (the
  `the-loopy-one` distribution name)
- **Deferred:** Cursor installation — issue-157 (owner decision on PR #153).
  **Discharged** by [decision-064](decision-064.md): `cursor` is now a component, probed
  the same way, with the local checkout as its documented fallback. Point 0 below is
  historical; everything else in this decision stands.

## Context

Issue #152: *"the-loop's CLI should provide a command to install and upgrade the CLI as
well as the claude/cursor plugin … it should also allow for installation at project or
user level."*

the-loop ships two artifacts — this CLI and the plugin — and had no command for either.
Installing meant knowing each harness's marketplace incantation and typing it *inside* an
interactive session; upgrading meant remembering which installer owned the copy you were
running (exactly the failure in issue-78); and scope could not be expressed at all,
although both harnesses distinguish user- from project-level installs. decision-054
already had to solve one corner of this for the daemon, because a spawned session without
the plugin has no loop at all.

The design question is not *whether* to install, but **who does the installing**. Two
credible answers: the-loop writes the harness's configuration files itself (it already
knows how — decision-054), or the-loop drives the harness's own plugin CLI.

## Decision

**Add `the-loop install` and `the-loop upgrade` — one implementation, two verbs — that
build a plan of steps and drive the harness's own installer, falling back only to a route
this repository already documents.**

0. **Claude Code only, for now.** *(Superseded by [decision-064](decision-064.md) —
   `cursor` is a component as of issue-157.)* `cli` and `claude` are the components;
   `cursor` is rejected as unknown rather than half-supported. the-loop *is* a Cursor
   plugin (decision-015), but installing one from a terminal is a different problem — see
   *Cursor, parked* below — and it is tracked as issue-157. The module is harness-shaped,
   so adding it later is a `BINARIES` entry plus a planner, not a new command.
1. **The harness owns installing.** Where `claude` exposes a plugin surface, the-loop
   shells out to it (`plugin marketplace add|update`, `plugin install|update`, `--scope`)
   and lets the harness own fetching, versioning and scope. The surface is **asked for**
   (`<binary> plugin --help`, **and** a working `plugin install --help` — the command
   actually driven), never inferred from a version number.
2. **One fallback, already documented.** No usable plugin surface → the decision-054
   settings keys (user file, or the project's `.claude/settings.json` at project scope,
   through the same single non-destructive writer). Where a requested scope cannot be
   expressed, the component is **skipped with instructions**, never invented.
3. **A plan, then its execution.** Every run is an ordered list of steps carrying the
   exact argv (or file) and one outcome each (`applied` · `already` · `skipped` ·
   `failed`, plus `planned` under `--dry-run`). `--dry-run` is the same plan with the
   execution left out, so preview and reality cannot drift.
4. **Scope is honored or refused.** A scope that cannot be expressed is skipped, never
   widened to the user account.
5. **The CLI's installer is detected, not declared** — `uv tool` / `pipx` / `pip` from
   where the running package lives, and a source checkout is skipped rather than installed
   over. Project scope installs into the project's `.venv`, deliberately not `uv add`:
   installing a tool must not rewrite the operator's dependency manifest.
6. **One marketplace source.** `--from` → `routing.harnessPlugins.marketplaceRepo` → the
   shipped default, validated as `owner/repo` before it can reach an argv, a URL or a
   settings file, and printed in the plan before anything is trusted.

## Consequences

**Easier.** A machine (or a CI job, or a Dockerfile) gets the-loop with one
non-interactive command, at a scope it chooses; upgrading no longer depends on
remembering how the thing was installed; the daemon and a human install now agree on one
marketplace source; and every step is auditable before it runs.

**Harder / accepted costs.**

- **Coupled to an external CLI.** Mitigated by probing rather than assuming, and by a
  fallback that keeps working when the surface is absent — but a harness that renames its
  subcommands still needs a change here. The probe is where that shows up, and it fails
  to a documented route rather than to nonsense.
- **A shipped command that executes package managers.** Bounded deliberately: argv lists
  with no shell, a validated marketplace source, no privilege elevation, and writes
  confined to the harness's own config files or the named project.
- **Cursor, parked (issue-157 — since discharged, decision-064).** The first cut supported it through a local clone under
  `~/.cursor/plugins/local/`. Review parked that: as of Cursor 2.5 (Feb 2026) plugins are
  installed from the marketplace site or with `/add-plugin` in the editor;
  `cursor-agent plugin marketplace add` is reported to exist, but no CLI install command
  is documented, and there is no documented project-local plugin directory — so a Cursor
  component would have been a clone-and-hope with a permanently skipped project scope.
  Better one harness done properly than two half-done, with the gap tracked in the open.
  The research left one lasting improvement: the probe now requires a working
  `plugin install`, not merely a `marketplace` command, so any harness that splits those
  two takes the fallback instead of running something that cannot work.
- **Two "upgrade" verbs now exist** (`the-loop upgrade` for the software,
  `/the-loop:upgrade-the-loop` for a project's files). They are documented next to each
  other for exactly that reason.

## Alternatives considered

- **Always write the harness's config files** (extend decision-054's writer to a
  user-facing command). Simplest, and it already exists — but it *registers* the plugin
  without fetching it, and it pins the-loop to today's file format. Kept as the fallback.
- **A `curl … | sh` bootstrap installer.** A second distribution channel to keep correct,
  and useless for the upgrade case that motivated the issue — the CLI is already there.
- **Wrap the harness's interactive flow** (drive `/plugin` inside a session). Not
  scriptable, not CI-able, and it is the very thing the issue asks to be freed from.
- **`uv add the-loopy-one` for project scope.** Rewrites the operator's `pyproject.toml`;
  installing into the project's existing virtualenv reaches the same result without
  editing their manifest.
