---
type: requirements
phase: requirements-definition
workItem: "issue-152"
status: approved            # locked; amended on PR #153 review (Cursor descoped) — see execution-log
approvedBy: []
collaborators: [engineer, approver]
riskTier: 3                  # runs installers on the operator's machine, but only when a human types the command
overrides: {}
---

# Requirements: `the-loop install` / `the-loop upgrade` — one command for the CLI and the plugin

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (<https://kiro.dev/docs/specs/>). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

[Issue #152](https://github.com/MadaraUchiha-314/the-loop/issues/152): the-loop ships as
**two** artifacts — a Python CLI (`the-loopy-one` on PyPI) and a plugin for Claude Code
and Cursor — and today there is no single way to put either of them on a machine, or to
move them forward when a release lands.

What an operator has to do instead, from the current docs:

| | Install | Upgrade |
|---|---|---|
| CLI | `pip install the-loopy-one` — or `uv tool install`, or `pipx`, depending on how they run it | remember which of those they used |
| Claude plugin | `/plugin marketplace add …` + `/plugin install …`, typed **inside a session** | `/plugin update`, again inside a session |
| Cursor plugin | `/add-plugin`, the marketplace UI, or a clone under `~/.cursor/plugins/local/` | `git pull` in that clone, if that is the route they took |

Three consequences, all of them observed in this repo's own history:

1. **The plugin is the operating model.** Everything a session knows about the loop — the
   `the-loop` skill, the `/the-loop:*` commands, the SessionStart hook — arrives through
   it. issue-143 already had to teach the *daemon* to install the plugin before a spawn,
   because on a machine where nobody ran `/plugin marketplace add` by hand the session
   worked its ticket as a plain agent. That fix is spawn-path-only: a human setting up
   the-loop, or a CI job, still has no non-interactive way in.
2. **Upgrading is invisible.** issue-78 is exactly this failure: a CLI installed with
   `uv tool install` kept reporting an old version because nothing tells the operator
   which installer owns the copy they are running.
3. **Scope is not expressible.** Both harnesses distinguish a user-level installation
   from a project-level one; the-loop's docs describe only the user-level route, so
   "the-loop for this repo only" cannot be asked for at all.

This work item adds one CLI verb for each half of that matrix — `the-loop install` and
`the-loop upgrade` — covering the CLI itself and the **Claude Code** plugin, at **user**
or **project** scope.

> **Amendment (PR #153 review, @MadaraUchiha-314):** *"Let's park cursor for now. For now
> let's only support claude. We will track the cursor installation as a separate issue."*
> Cursor was in the first cut of this spec (R1.2, and a local-clone fallback); it is now
> **out of scope** and tracked as
> [issue #157](https://github.com/MadaraUchiha-314/the-loop/issues/157). The requirements
> below are the amended set — R1.2 is retired, and R3/R6 speak of one harness. The
> reasoning is in [decision-057](../../decisions/decision-057.md) § Cursor, parked.

### Out of scope

- **Cursor plugin installation** — descoped on review, see the amendment above
  ([issue #157](https://github.com/MadaraUchiha-314/the-loop/issues/157)). the-loop keeps
  shipping as a Cursor plugin; only the *terminal installer* for it is deferred.

- Uninstalling. `claude plugin uninstall`, `pip uninstall` and deleting a clone are one
  command each and carry no ambiguity worth wrapping (YAGNI).
- Installing anything the-loop does not ship (`gh`, `tmux`, `ttyd`) — the CLI documents
  those as prerequisites and keeps doing so.
- Scaffolding a repository. That is `/the-loop:init`, and reconciling a project's files
  with a newer plugin is `/the-loop:upgrade-the-loop`; this command installs *software*,
  not project artifacts. The two are named next to each other in the docs so the
  difference is visible.

## Requirements

### Requirement 1 — install the plugin into a harness, from a terminal

**User story:** As an operator setting up the-loop, I want one command that installs the
plugin into the harness I use, so that I do not have to know each harness's marketplace
incantation or type it inside an interactive session.

#### Acceptance criteria (EARS)

1. WHEN `the-loop install claude` runs THEN the system SHALL register the-loop's
   marketplace and install the `the-loop@the-loop` plugin for Claude Code at the
   requested scope.
2. *(Retired on review — was Cursor; see the amendment above and issue #157.)* WHEN a
   component the system does not support is named THEN it SHALL reject it as unknown,
   naming the components it does support, rather than attempting a partial install.
3. WHEN no component is named THEN the system SHALL act on `cli` plus every harness whose
   CLI is detected on `PATH`, and SHALL report which harnesses it detected.
4. IF a named harness's CLI is absent AND no documented fallback applies THEN the system
   SHALL report that component as **skipped** with the reason, SHALL NOT fail the other
   components, and SHALL exit non-zero only per R5.4.

### Requirement 2 — upgrade what is already installed

**User story:** As an operator on an older release, I want one command that moves my CLI
and my plugin to the current version, so that upgrading is not a memory test about which
installer I used.

#### Acceptance criteria (EARS)

1. WHEN `the-loop upgrade` runs THEN the system SHALL, for each selected component, run
   the upgrade path of the installation method that component is actually installed with.
2. WHEN the CLI is upgraded THEN the system SHALL first determine how the running copy
   was installed (`uv tool`, `pipx`, `pip` in an environment, or a source checkout) and
   SHALL use that method's upgrade command.
3. IF the running CLI is a source checkout (an editable/development install) THEN the
   system SHALL report it as **skipped** naming the checkout, and SHALL NOT attempt a
   package-manager install over it.
4. WHEN a harness plugin is upgraded THEN the system SHALL refresh the marketplace before
   updating the plugin, so the update resolves against the current manifest.

### Requirement 3 — user scope or project scope

**User story:** As an operator, I want to choose whether an install affects my whole
machine or only this repository, so that trying the-loop out on one project does not
change how every other session on the machine behaves.

#### Acceptance criteria (EARS)

1. WHEN `--scope user` (the default) is in effect THEN the system SHALL install for the
   operator's user account.
2. WHEN `--scope project` is in effect THEN the system SHALL install for the project
   directory only (`--project-dir`, default the current directory).
3. WHERE a harness's own CLI expresses scope THEN the system SHALL pass the requested
   scope through to it rather than emulating it.
4. IF the requested scope cannot be expressed for a component THEN the system SHALL
   report that component as **skipped**, state why, and print the manual instruction —
   never silently install at a different scope than the one that was asked for.

### Requirement 4 — say what will be run, and let it be previewed

**User story:** As an operator, I want to see exactly which commands will touch my
machine before they run, so that a command that installs software is auditable rather
than magic.

#### Acceptance criteria (EARS)

1. WHEN either verb runs THEN the system SHALL print, for every step, the component, the
   outcome, and the exact argv (or the file path written) that produced it.
2. WHEN `--dry-run` is passed THEN the system SHALL print the same plan and SHALL NOT
   execute any step, write any file, or mutate any state.
3. WHEN `--format json` is passed THEN the system SHALL emit the same records as JSON, so
   a setup script can act on them.

### Requirement 5 — honest, idempotent outcomes

**User story:** As an operator (or a CI job) re-running the command, I want a re-run to be
a no-op with a clear verdict, so that it is safe to put in a bootstrap script.

#### Acceptance criteria (EARS)

1. WHEN the system can itself determine that a step's desired state already holds — a
   file it writes, a checkout it owns — THEN it SHALL report **already** and SHALL NOT
   write or run anything. WHERE only the harness can determine it (its own plugin CLI),
   the system SHALL delegate: it runs the command and reports the harness's verdict
   verbatim, which is what keeps a re-run safe without the-loop second-guessing a state
   it does not own.
2. WHEN a step changes something THEN the system SHALL report **applied** with what
   changed.
3. WHEN a step cannot run THEN the system SHALL report **skipped** (a precondition is
   missing) or **failed** (it ran and returned an error), and the two SHALL be
   distinguishable.
4. WHEN any step **failed** THEN the process SHALL exit non-zero; a run whose steps are
   only `applied`/`already`/`skipped` SHALL exit zero.

### Requirement 6 — never guess a harness's interface

**User story:** As the maintainer, I want the command to use each harness's documented
surface and to detect what it actually supports, so that a harness release does not turn
the-loop into a machine that writes plausible-looking nonsense into someone's config.

#### Acceptance criteria (EARS)

1. WHEN a harness CLI is present THEN the system SHALL determine whether it exposes a
   plugin-management surface (and whether that surface accepts a scope flag) by asking
   the binary itself, not by assuming a version.
2. IF a harness CLI is absent, or exposes no *usable* plugin surface — a `marketplace`
   command without a working `plugin install` counts as none, since `install` is what is
   driven — THEN the system SHALL fall back only to a route this repository already
   documents: the settings keys `/plugin marketplace add` + `/plugin install` write
   (`extraKnownMarketplaces` / `enabledPlugins`, as `routing.harnessPlugins` already
   does).
3. WHERE no documented route exists for a component-and-scope pair THEN the system SHALL
   skip it with instructions, per R3.4.

### Requirement 7 — one source of truth for where the plugin comes from

**User story:** As an operator running a fork, I want the install command to use the same
marketplace repository the daemon already uses, so that my machine does not end up with
two different the-loops.

#### Acceptance criteria (EARS)

1. WHEN no `--from` is given THEN the system SHALL resolve the marketplace repository from
   the CLI config's `routing.harnessPlugins.marketplaceRepo`, falling back to the shipped
   default `MadaraUchiha-314/the-loop`.
2. WHEN `--from <owner/repo>` is given THEN the system SHALL use it in preference to the
   config.
3. IF the resolved value is not of the form `owner/repo` THEN the system SHALL refuse the
   plugin steps with an error naming the offending value, and SHALL NOT pass it to a
   subprocess or write it to a settings file.

## Security considerations

> Threat-model-lite (`security.threatModel.required`). See `reference/security.md`.

**Untrusted actors.** None reach this command directly: it runs only when a human types
it in their own terminal (it is not reachable from a webhook payload, a ticket comment,
or any other event input). The relevant risk is therefore not "who calls it" but **what
it makes the operator's machine execute on their behalf**.

**Trust boundaries and abuse cases.**

1. **Installing is code execution.** Registering a marketplace and installing the plugin
   from it means running whatever that repository ships, in every subsequent session at
   that scope. `--from`/`marketplaceRepo` is therefore the sharpest input here: it SHALL
   be validated as `owner/repo` before it reaches a subprocess or a settings file (the
   same `^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$` rule `routing.harnessPlugins` already
   applies), and the resolved value SHALL be printed in the plan, so what is about to be
   trusted is visible before it is trusted.
2. **Subprocess construction.** Every command SHALL be executed as an argv list with no
   shell, so no configured or user-supplied value can become shell syntax. The binaries
   invoked are resolved from `PATH` by name (`claude`, `uv`, `pipx`, or `sys.executable`)
   and nothing else.
3. **Writing the operator's config.** The Claude fallback writes only the two keys
   `extraKnownMarketplaces["the-loop"]` and `enabledPlugins["the-loop@the-loop"]`, through
   the existing single non-destructive writer (`the_loop.trust.update_json`): merged into
   what is there, temp file + atomic replace, nothing written when the desired state
   already holds, and a file that does not parse is reported rather than overwritten. An
   existing value is never changed.
4. **Scope confusion.** Installing at a wider scope than the operator asked for is the
   abuse case that matters for `--scope`: a project-scoped request that cannot be honored
   SHALL be skipped, never silently widened to the user account (R3.4).
5. **Privilege.** The command SHALL NOT elevate privileges, invoke `sudo`, or write
   outside the operator's home directory / the named project directory.

**Fail-closed.** An unvalidated marketplace value, an unreadable settings file, or a
harness whose surface cannot be established stops *that component* with a reported reason
rather than falling through to a best guess.

**No secrets.** The command reads no tokens and writes none; the plugin is fetched from a
public repository by the harness itself.
