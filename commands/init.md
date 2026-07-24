---
description: Initialize "the-loop" in the current repository — scaffold .the-loop/, docs/, learnings/ and a validated config, establishing the config with the user via a guided, schema-driven onboarding. Idempotent, non-clobbering, with drift detection.
argument-hint: "[--dry-run] [--defaults] [--monorepo-tool nx|pnpm|yarn|bun|none] [--ticketing github|jira]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: init

Initialize "the-loop" into the current project repository. **Idempotent and safe to
re-run:** it is driven entirely by the manifest, creates only what is missing, and
**never overwrites user-owned files**.

The **authoritative** source of what to create — and which files are managed vs.
user-owned — is `${CLAUDE_PLUGIN_ROOT}/.the-loop/manifest.yaml` (each entry's
`managed: true|false`). Templates are **internal to the-loop** and are **not** copied
into the project; they live with the plugin's skill under
`${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/` (`manifest.templatesDir`) and are read
from there when a file needs scaffolding. (`${CLAUDE_PLUGIN_ROOT}` is the installed
plugin's root directory; in Cursor, resolve it to the plugin's install directory.)

## Modes

- **`--dry-run`** — compute and print the report (below) **without writing anything**
  and without interacting. Use it to preview an init or an upgrade safely.
- **`--defaults`** — non-interactive: skip the guided onboarding (step 2), apply
  sensible defaults everywhere (existing answer → detected signal → schema default),
  and list every gap that genuinely needs the user under **needs-user** in the final
  report.

## Steps

1. **Detect the project.** Inspect the repo to infer sensible defaults — never stamp
   the plugin's hardcoded tooling defaults onto an existing project unread:
   - languages present (python / js / ts / go) — from file extensions and manifests
     (`package.json`, `pyproject.toml`/`setup.cfg`/`requirements.txt`, `go.mod`).
   - whether it looks like a monorepo (nx.json, pnpm-workspace.yaml, workspaces) and
     which tool — default Nx; support non-monorepo (`monorepo: false`).
   - existing package manager / test runner / linter / type-checker per language, by
     reading lock files, manifest fields, and dependency lists, per the exact signal
     table in the `the-loop` skill's `reference/tooling.md` → "Tooling detection"
     (e.g. `package-lock.json`→npm, `yarn.lock`→yarn, `bun.lockb`→bun,
     `pnpm-lock.yaml`→pnpm; devDependencies for `jest`/`vitest`/`mocha`,
     `eslint`/`oxlint`/`biome`, etc.; the Python and Go equivalents).
   - cross-check inferred tooling against `.github/workflows/` (or other CI config) —
     the commands CI actually runs are a strong signal.
   - the git remote / owner / repo for ticketing.
   - candidate **custom instruction docs** for `customInstructions.docs` — existing
     convention files the team already maintains (`CONTRIBUTING.md`, style/convention
     guides under `docs/`). Propose them in the onboarding (never auto-register); the
     user confirms, adjusts, or adds paths — including absolute per-machine paths
     detection can never see (see the skill's `reference/instructions.md`).
   Where detection is unambiguous, write the detected tool into `tooling.<concern>.<lang>`.
   Where it's ambiguous or no signal exists, fall back to the plugin default but mark
   that line with a trailing `# TODO: verify — no signal found, defaulted` comment, and
   surface it in the guided onboarding (step 2) — or, when running non-interactively,
   in the **needs-user** section of the final report (step 8) — so the user confirms it
   before the agent invokes it.

2. **Onboard the config with the user (guided, grouped, schema-driven).** Do not dump
   a config file and walk away — establish it together, following the skill's
   `reference/onboarding.md` procedure exactly. The schema's `x-onboarding.groups`
   (in `harness-config.schema.json`) defines the ordered config groups (related keys that
   interact, clubbed together) and each group's `ask` level:
   - `always` groups (e.g. **Project & ticketing**, **People & communication**) have
     no sensible default — establish them with the user.
   - `confirm` groups (tooling, custom instructions, workflow, quality gates,
     reviews & autonomy) —
     present the proposal from step 1's detection (falling back to schema defaults)
     and confirm/adjust the whole group in ONE interaction.
   - `advanced` groups (API contracts, observability, self-improvement & context
     management) — default silently; offer a full tour only if the user wants it.
   For every group: explain what it does and why it matters (educating the user is
   mandatory); for enum keys show ALL the possibilities with a one-line meaning each;
   for free-form keys show the schema's `examples` so the user never guesses. Pull
   explanations, defaults, enums and examples from the schema — never from memory.
   Under `--defaults` (or `--dry-run`) skip all interaction and route un-defaultable
   gaps to the **needs-user** section of the final report. On a re-run, only raise
   gaps (empty required keys, `# TODO: verify` lines, keys added by an upgrade) —
   never re-ask what is already established.

   **Also ask about the CLI daemon config (one plain question, not a grouped
   onboarding — decision-032).** The-loop's CLI (`gh-webhook`/`poll`/`sessions`/
   `events`) reads a separate, independent `cli-config.yaml` — not this repo's
   `.the-loop/harness-config.yaml` — resolved via `--config`/`$THE_LOOP_CLI_CONFIG`/
   `./.the-loop/cli-config.yaml`/`~/.the-loop/cli-config.yaml` (see `cli/README.md`).
   Ask: *"Do you want the CLI daemon's config tracked and versioned in this repo
   (scaffolds `.the-loop/cli-config.yaml`, picked up automatically when you run
   `the-loop` from here), or should it default to your home directory
   (`~/.the-loop/cli-config.yaml`, nothing scaffolded here)?"* Under `--defaults` skip
   this question and scaffold nothing (home-directory default applies with zero setup).
   Never assume either answer.

3. **Reconcile against the manifest (idempotent, non-clobbering).** For every managed
   path, classify it and act:
   - **missing** → create it (from the template/default);
   - **present & `managed: false`** (user-owned) → **never overwrite**; leave it, note it;
   - **present & `managed: true` but drifted** from the current template/schema → **do
     not clobber**: diff and *suggest* the change (or apply only with explicit consent);
   - **present & up to date** → skip.
   Create the following where missing (never overwrite user-owned files). Scaffold each
   from its template under `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/` — **do not**
   copy the templates directory itself into the project (templates are internal to the-loop):
   - `.the-loop/harness-config.yaml` — from the template, with the detected defaults and the
     answers established in step 2 applied.
   - `.the-loop/harness-config.schema.json` — copy of the schema.
   - `.the-loop/manifest.yaml` — the manifest.
   - `.the-loop/collaborators.yaml` — from templates (user-owned). External tools are
     declared inline in `config.externalTools`, not a separate file (issue-37).
   - **Only if step 2 answered "track it here":** `.the-loop/cli-config.yaml` — from
     `templates/cli-config.yaml`, and `.the-loop/cli-config.schema.json` (copy of the
     schema, alongside `harness-config.schema.json`). Never scaffolded on the home-directory
     answer or under `--defaults`.
   - `docs/architecture/architecture.md`, `docs/decisions/decisions.md`,
     `docs/specs/` (per-work-item Kiro specs + execution logs).
   - `learnings/learnings.md`.

4. **Create phase labels/tags** in the ticketing system for the workflow state
   machine — one per `workflow.phases`, named `<workflow.phaseLabelPrefix><phase>`
   (e.g. `loop:requirements-definition`, `loop:design`, … `loop:complete`). On GitHub
   create issue labels; on Jira create the equivalent statuses/labels. Skip any that
   already exist.

5. **Validate** the generated `.the-loop/harness-config.yaml` against
   `.the-loop/harness-config.schema.json` and `.the-loop/collaborators.yaml` against
   `.the-loop/collaborators.schema.json` (and, if scaffolded, `.the-loop/cli-config.yaml`
   against `.the-loop/cli-config.schema.json`). Report any gaps the user must fill
   (e.g. empty `collaborators`, `ticketing.github.owner`).

6. **Confirm collaborators.** If `.the-loop/collaborators.yaml` is still empty after
   the onboarding (step 2), ask the user (via a ticket comment if a ticket exists,
   otherwise interactively) to define at least one collaborator holding the approver
   role — collaborators.yaml is the single source for people and their notification
   channels (issue-82, decision-035). RULE: every decision needs a paper trail.

7. **Wire local hooks & CI parity.** Set up pre-commit / pre-push hooks that run the
   `hooks.preCommit` / `hooks.prePush` steps (lint, typecheck, unit-test) using the
   configured tooling, and ensure CI invokes the SAME root commands (see
   `reference/tooling.md` → "CI/CD must use exactly the same tooling as local"). Only
   scaffold what the project doesn't already have.

8. **Report.** End with a short summary grouped as **created / skipped (up to date) /
   drifted (suggested) / needs-user** (files or config gaps the user must fill), then the
   immediate next action (`/the-loop:work-on <ticket>` or `/the-loop:new-requirement`).
   Under `--dry-run`, print exactly this report and write nothing.

Respect existing files. This command is idempotent, non-clobbering, and safe to re-run —
which is what makes it trustworthy to run on someone's repository.
