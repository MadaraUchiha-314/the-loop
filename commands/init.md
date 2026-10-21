---
description: Initialize "the-loop" in this repository — harness config, collaborators, the docs trees (specs, capabilities, decisions, learnings) and the phase labels, established with the user via a guided, schema-driven onboarding. Sets up no daemon (that is /the-loop:init-cli). Idempotent, non-clobbering, with drift detection.
argument-hint: "[--dry-run] [--defaults]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: init

Initialize "the-loop" into the current project repository. **Idempotent and safe to
re-run:** it is driven entirely by the manifest, creates only what is missing, and
**never overwrites user-owned files**.

**This command sets up the repository, and only the repository** (issue-514). Every
repository that uses the-loop needs what it writes: the harness config the agent reads,
the collaborators file, the docs trees and the `loop:<phase>` labels. The daemon's
config and a gateway's config belong to one operator and one machine, and have commands
of their own (§ Not set up here).

**What a finished init owes the user:** a harness config they understand, the docs trees
the loop maintains, the labels its phases use, and a plain statement of what this command
did not set up and which command does.

The **authoritative** source of what to create — and which files are managed vs.
user-owned — is `${CLAUDE_PLUGIN_ROOT}/.the-loop/manifest.yaml` (each entry's
`managed: true|false`). Two kinds of file are **internal to the-loop** and are **never**
copied into the project — they ship with the plugin and are read from there:

- **Templates** — `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/`
  (`manifest.templatesDir`), read when a file needs scaffolding.
- **Config schemas** — `${CLAUDE_PLUGIN_ROOT}/.the-loop/*.schema.json`
  (`manifest.schemasDir`), read when a config needs validating or onboarding. They are
  the plugin's contract, not the operator's data, and a copy in the project only goes
  stale (issue-220). Each scaffolded config instead opens with a
  `# yaml-language-server: $schema=<published url>` line, so the operator's editor
  validates it with nothing local on disk.

(`${CLAUDE_PLUGIN_ROOT}` is the installed plugin's root directory; in Cursor, resolve it
to the plugin's install directory.)

## Modes

- **`--dry-run`** — compute and print the report (below) **without writing anything**
  and without interacting. Use it to preview an init or an upgrade safely.
- **`--defaults`** — non-interactive: skip the guided step (2), apply sensible defaults
  everywhere (existing answer → detected signal → schema default), and list every gap
  that genuinely needs the user under **needs-user** in the final report.

## Steps

1. **Detect the project.** Inspect the repo to propose the few facts the config still
   carries — nothing about layout or tooling is written: the skill reads the languages,
   package managers, test runners, linters, type checkers, monorepo tool and git hooks
   off the repository itself at the start of every work item (`reference/tooling.md` →
   "Tooling detection (every session)"; issue-352), so a config cannot go stale on them.
   Detect, and propose in the onboarding:
   - candidate **custom instruction docs** for `customInstructions.docs` — existing
     convention files the team already maintains (`CONTRIBUTING.md`, style/convention
     guides under `docs/`). Propose them (never auto-register); the user confirms,
     adjusts, or adds paths — including absolute per-machine paths detection can never
     see (see the skill's `reference/instructions.md`).
   - the **integration-test globs** for `testing.integrationTestGlobs` — from the test
     directories and the naming the repository already uses.
   - existing **API contracts** (`openapi*.yaml`, `*.graphql`) for `apiSpecs`.
   Where no signal exists, keep the schema default and mark the line with a trailing
   `# TODO: verify — no signal found, defaulted` comment; surface it in the guided
   onboarding or, non-interactively, under **needs-user** in the final report.

2. **Onboard the harness config with the user (guided, grouped, schema-driven).** Do not
   dump a config file and walk away — establish it together, following the skill's
   `reference/onboarding.md` procedure exactly. The schema's `x-onboarding.groups`
   (in the plugin's `harness-config.schema.json` — `${CLAUDE_PLUGIN_ROOT}` /
   `manifest.schemasDir`, never a project copy) defines the ordered config groups
   (related keys that interact, clubbed together) and each group's `ask` level:
   - `always` groups (**People & interaction**: the collaborators file) have no
     sensible default — establish them with the user.
   - `confirm` groups (custom instructions, testing conventions) —
     present the proposal from step 1's detection (falling back to schema defaults)
     and confirm/adjust the whole group in ONE interaction.
   - `advanced` groups (API contracts & design artifacts) — default silently; offer a
     full tour only if the user wants it.
   For every group: explain what it does and why it matters (educating the user is
   mandatory); for enum keys show ALL the possibilities with a one-line meaning each;
   for free-form keys show the schema's `examples` so the user never guesses. Pull
   explanations, defaults, enums and examples from the schema — never from memory.
   Under `--defaults` (or `--dry-run`) skip all interaction and route un-defaultable
   gaps to the **needs-user** section of the final report. On a re-run, only raise
   gaps (empty required keys, `# TODO: verify` lines, keys added by an upgrade) —
   never re-ask what is already established.

3. **Reconcile against the manifest (idempotent, non-clobbering).** For every managed
   path this command owns, classify it and act:
   - **missing** → create it (from the template/default);
   - **present & `managed: false`** (user-owned) → **never overwrite**; leave it, note it;
   - **present & `managed: true` but drifted** from the current template/schema → **do
     not clobber**: diff and *suggest* the change (or apply only with explicit consent);
   - **present & up to date** → skip.
   Create the following where missing (never overwrite user-owned files). Scaffold each
   from its template under `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/` — **do not**
   copy the templates directory or any `*.schema.json` into the project (both are internal
   to the-loop):
   - `.the-loop/harness-config.yaml` — from the template, with the detected defaults and the
     answers established in step 2 applied. Keep the template's
     `# yaml-language-server: $schema=…` **first line** intact: the directive only works
     there, and it is the operator's editor validation (issue-220).
   - `.the-loop/manifest.yaml` — the manifest.
   - `.the-loop/collaborators.yaml` — from templates (user-owned). No tool registry is
     written: the harness discovers its own tools (issue-352).
   - `docs/architecture/architecture.md`, `docs/decisions/decisions.md`,
     `docs/specs/` (per-work-item Kiro specs + gate records), `docs/capabilities/`.
   - `docs/learnings/learnings.md` — the learnings index. The doc trees are the loop's
     convention, not a setting (issue-352).

   The manifest's optional daemon and gateway entries are **not** this command's: leave
   them as they are, present or absent, and list any that exist under *skipped* with the
   command that owns them (§ Not set up here).

4. **Create phase labels/tags** in the ticketing system for the process graph's phases
   — one per phase the shipped work-item loop declares, named `loop:<phase>` (the fixed
   vocabulary, issue-352): `loop:not-started`, `loop:phase-selection`,
   `loop:brainstorming`, `loop:requirements-definition`, `loop:design`,
   `loop:test-planning`, `loop:tasks-breakdown`, `loop:implementation`,
   `loop:verification`, `loop:needs-review`, `loop:complete`, `loop:cleanup`. The graph
   is the source (`the-loop graph show --format json` lists each node's `phase`); the
   config declares no phase list. On GitHub create issue labels; on Jira create
   **nothing** — Jira creates a label the first time an issue carries it. Skip any that
   already exist. These label this repository's own tickets, which is why they are this
   command's. **No skip labels are needed** (issue-177): which phases a work item walks
   is chosen on the ticket itself, at the loop's `phase-selection` phase, by an
   authorized user replying to the-loop's checklist — nothing to create per repository.

5. **Validate** every config that was written, against the **plugin's** schemas under
   `${CLAUDE_PLUGIN_ROOT}/.the-loop/` (`manifest.schemasDir`) — read them from there and
   validate locally; never fetch a schema over the network, and never write one into the
   project to validate against:
   - `.the-loop/harness-config.yaml` ↔ `harness-config.schema.json`
   - `.the-loop/collaborators.yaml` ↔ `collaborators.schema.json`

   The absence of a project-local schema copy never weakens or skips this step. **If a
   schema cannot be read from the plugin, stop before writing the config it validates**
   and report the missing path under **needs-user** — never write an unvalidated file.
   Report any gaps the user must fill (e.g. empty `collaborators`).

   **Confirm collaborators.** If `.the-loop/collaborators.yaml` is still empty after
   the onboarding, ask the user (via a ticket comment if a ticket exists, otherwise
   interactively) to define at least one collaborator holding the approver role —
   collaborators.yaml is the single source for people and the roles they hold
   (issue-82, decision-035; it declares no delivery of its own — issue-304). RULE: every
   decision needs a paper trail.

6. **Wire local hooks & CI parity.** When the project has no hook manager of its own,
   set up pre-commit / pre-push hooks that run lint, typecheck and unit tests with the
   detected tooling, and ensure CI invokes the SAME root commands (see
   `reference/tooling.md` → "CI/CD must use exactly the same tooling as local"). Only
   scaffold what the project doesn't already have — a repository's existing hooks are
   what the loop runs.

7. **Report.** End with a short summary grouped as **created / skipped (up to date) /
   drifted (suggested) / needs-user** (files and config gaps the user must fill), then
   the hand-off below, then the immediate next action (`/the-loop:work-on <ticket>` or
   `/the-loop:new-requirement`). Under `--dry-run`, print exactly this report and write
   nothing.

## Not set up here

This command checks no credential and writes nothing outside the repository. Two other
commands own the rest, and the report always ends by naming them, in these words or
close to them:

> No CLI or gateway setup was done. If this repository is your **operator** repository —
> the one whose checkout runs the-loop's daemon, or you keep its config in
> `~/.the-loop/` — run `/the-loop:init-cli` once to set up the daemon (`cli-config.yaml`:
> where it runs, how much runs unattended, Slack, Jira, the arming labels and their
> credentials). If this machine hosts a the-loop gateway, run `/the-loop:init-gateway`
> (`gateway-config.yaml`). A repository that only uses the-loop needs neither.

When `.the-loop/cli-config.yaml`, `.the-loop/slack-app-manifest.json` or a
`gateway-config.yaml` already sits in the repository, leave it untouched and list it under
*skipped*, naming `/the-loop:init-cli` (or `/the-loop:init-gateway`) as the command that
changes it.

Respect existing files. This command is idempotent, non-clobbering, and safe to re-run —
which is what makes it trustworthy to run on someone's repository.
