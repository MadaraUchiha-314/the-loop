---
description: Initialize "the-loop" in the current repository — scaffold .the-loop/, the docs trees (specs, capabilities, decisions, learnings) and validated configs, establishing them with the user via a guided, schema-driven onboarding that covers the automation, Slack and the credentials they need. Idempotent, non-clobbering, with drift detection.
argument-hint: "[--dry-run] [--defaults]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: init

Initialize "the-loop" into the current project repository. **Idempotent and safe to
re-run:** it is driven entirely by the manifest, creates only what is missing, and
**never overwrites user-owned files**.

**What a finished init owes the user:** two configs they understand, an honest answer to
"what will this do while I am not looking", and a list of every credential still missing.
An init that writes a valid config and leaves the user with nothing running — and no
signal that nothing is running — has failed, whatever the report says.

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
  and without interacting. Use it to preview an init or an upgrade safely. It writes no
  config and no `.gitignore` line.
- **`--defaults`** — non-interactive: skip every guided step (2, 3, 4, 5), apply
  sensible defaults everywhere (existing answer → detected signal → schema default), and
  list every gap that genuinely needs the user under **needs-user** in the final report.
  With no autonomy profile chosen, the shipped defaults apply, which means **no
  automation is enabled** — say so in the report rather than leaving it implied.

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
   - the **repository ref** (`owner/repo` from the `origin` remote) for the CLI config's
     `repositories`.
   - the **deployment shape**, where it is unambiguous — a container, a cloud shell, a
     CI runner. Where it is not, step 3 asks. Never act on an inferred shape silently:
     show it and let the user correct it.
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

3. **Establish the posture: where this runs, and how much of it runs unattended.** Two
   questions, before any automation key is proposed, both from `reference/onboarding.md`
   (§ The deployment shape, § The autonomy ladder). They have no defaults worth guessing,
   which is why they come first and why they are the CLI config's `always` group.

   - **The deployment shape** — a personal machine you close, an always-on host with an
     inbound route, or nowhere yet. This is the fact that decides the ingress: GitHub
     cannot reach a webhook receiver behind NAT, so a laptop polls and a reachable host
     receives. The answer is used and not stored.
   - **The autonomy profile** — read `x-onboarding.profiles` from the plugin's
     `cli-config.schema.json` and present the whole ladder: every rung with its
     `summary` **and** its `stillHuman` line, with `profiles.recommended` marked. Take
     the answer as the **proposal** for the keys it covers, never as a write; the
     resolved values are shown in step 4 and the user may still adjust them.

   **Say the invariant out loud when you present the top rung:** no profile removes a
   human gate. The phase-selection checklist, the `requirements.md` and `design.md`
   approvals, the pull-request approval and the risk tiers are fixed rules of the skill
   and the process graph, not settings. A profile decides who **starts** work and how
   events arrive; never who **approves** it.

   Record the chosen rung as a comment in the config written in step 6
   (`# onboarding profile: <id>`) and name it in the final report. Under `--defaults` or
   `--dry-run`, ask neither question and report both under **needs-user**.

4. **Onboard the CLI config with the user (the same walkthrough, the other schema).**
   The-loop's CLI (`start`/`stop`/`status`, the webhook receiver, the poller, `sessions`,
   `channels`) reads a separate, independent `cli-config.yaml` — not this repo's
   `.the-loop/harness-config.yaml` — resolved via `--config`/`$THE_LOOP_CLI_CONFIG`/
   `./.the-loop/cli-config.yaml`/`~/.the-loop/cli-config.yaml` (see `cli/README.md`).

   **First, where it lives** (one plain question — decision-032): *"Do you want the CLI
   daemon's config tracked and versioned in this repo (`.the-loop/cli-config.yaml`,
   picked up automatically when you run `the-loop` from here), or in your home directory
   (`~/.the-loop/cli-config.yaml`)?"* Never assume either answer.

   **Then walk it**, exactly as step 2 walks the harness config, from
   `x-onboarding.groups` in the plugin's `cli-config.schema.json`. Walk it **whichever
   answer they gave**: where the file lives is a storage question; what it turns on is
   the reason they ran init. The groups are `deployment`, `ingress`, `execution`,
   `channels` (step 5), then the `advanced` pair `review` and `operations`. For each key
   the autonomy profile covers, show its value with the provenance *"from the profile you
   picked"*.

   Three keys deserve a sentence of their own even when the profile has proposed the rest,
   because a deployment is broken without them and nothing else will tell the user:
   - `routing.authorizedUsers` — **empty by default**, and until someone is named here
     nobody can start, stop or approve anything from a comment. No profile fills it: who
     may drive the loop is established by name.
   - `routing.workspace.root` — **empty by default**; the daemon runs independent of any
     repository, so without it a spawned session has nowhere to check the code out.
   - `routing.autoExecuteLabels` — the labels that arm a work item, **all of which** must
     be present before anything spawns. Apply the whole list when you arm an item.

   Under `--defaults` or `--dry-run`, scaffold nothing here (the home-directory default
   applies with zero setup) and report the gaps.

5. **Set up Slack, or skip it cleanly.** Slack is the `channels` group, and it gets its
   own step because it is the only part of onboarding that reaches outside the machine.

   **Explain it in four sentences, not eight hundred lines.** Slack is a channel: one
   thread per work item, so an authorized member can drive the loop from their phone.
   `subscribe` is what the channel **hears**. `publish` is what a message there **may
   become** — it is the channel's authority, so everything is off except
   `work-item.reply` until the user says otherwise. GitHub stays the ledger: whatever
   starts in Slack is recorded on the work item first. Then link
   [the Slack guide](https://madarauchiha-314.github.io/the-loop/guide/slack) and stop explaining.

   **If the user declines, set `channels.slack.enabled: false` and ask nothing more.**

   If they want it, walk the four steps and wait at each:
   1. **The app** — `the-loop channels manifest` prints the app definition; at
      [api.slack.com/apps](https://api.slack.com/apps) choose *Create New App → From a
      manifest* and paste it. An app that already exists is upgraded by replacing its
      manifest and reinstalling.
   2. **The bot token** (`xoxb-…`) — *OAuth & Permissions → Install*. Export it under the
      name `channels.slack.botTokenEnv` (default `THE_LOOP_SLACK_BOT_TOKEN`).
   3. **The app-level token** (`xapp-…`, scope `connections:write`) — *Basic Information →
      App-Level Tokens*. Export it under `channels.slack.appTokenEnv` (default
      `THE_LOOP_SLACK_APP_TOKEN`). This is what Socket Mode connects with, and Socket Mode
      is what makes the buttons and `/the-loop` work.
   4. **The conversation** — invite the bot to the channel and take that conversation's
      **id** from its details pane for `channels.slack.channel`.

   Propose `subscribe` from the schema; propose `publish` at the schema default and
   **never widen it unasked** — each grant is authority the channel did not have.
   Verification happens in step 10.

6. **Reconcile against the manifest (idempotent, non-clobbering).** For every managed
   path, classify it and act:
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
   - **The CLI config, at the path step 4 established** — from `templates/cli-config.yaml`
     with steps 3–5's answers applied, and carrying the `# onboarding profile: <id>`
     provenance comment. Never scaffolded under `--defaults` or `--dry-run`.
   - `docs/architecture/architecture.md`, `docs/decisions/decisions.md`,
     `docs/specs/` (per-work-item Kiro specs + gate records), `docs/capabilities/`.
   - `docs/learnings/learnings.md` — the learnings index. The doc trees are the loop's
     convention, not a setting (issue-352).

7. **Create phase labels/tags** in the ticketing system for the process graph's phases
   — one per phase the shipped work-item loop declares, named `loop:<phase>` (the fixed
   vocabulary, issue-352): `loop:not-started`, `loop:phase-selection`,
   `loop:brainstorming`, `loop:requirements-definition`, `loop:design`,
   `loop:test-planning`, `loop:tasks-breakdown`, `loop:implementation`,
   `loop:verification`, `loop:needs-review`, `loop:complete`, `loop:cleanup`. The graph
   is the source (`the-loop graph show --format json` lists each node's `phase`); the
   config declares no phase list. On GitHub create issue labels; on Jira create the
   equivalent statuses/labels. Skip any that already exist. Create the
   `routing.autoExecuteLabels` entries too where routing was enabled — an arming label
   that does not exist cannot be applied. **No skip labels are needed** (issue-177):
   which phases a work item walks is chosen on the ticket itself, at the loop's
   `phase-selection` phase, by an authorized user replying to the-loop's checklist —
   nothing to create per repository.

8. **Validate** every config that was written, against the **plugin's** schemas under
   `${CLAUDE_PLUGIN_ROOT}/.the-loop/` (`manifest.schemasDir`) — read them from there and
   validate locally; never fetch a schema over the network, and never write one into the
   project to validate against:
   - `.the-loop/harness-config.yaml` ↔ `harness-config.schema.json`
   - `.the-loop/collaborators.yaml` ↔ `collaborators.schema.json`
   - the CLI config, wherever step 4 put it ↔ `cli-config.schema.json`

   The absence of a project-local schema copy never weakens or skips this step. Report
   any gaps the user must fill (e.g. empty `collaborators`).

   **Confirm collaborators.** If `.the-loop/collaborators.yaml` is still empty after
   the onboarding, ask the user (via a ticket comment if a ticket exists, otherwise
   interactively) to define at least one collaborator holding the approver role —
   collaborators.yaml is the single source for people and the roles they hold
   (issue-82, decision-035; it declares no delivery of its own — issue-304). RULE: every
   decision needs a paper trail.

9. **Wire local hooks & CI parity.** When the project has no hook manager of its own,
   set up pre-commit / pre-push hooks that run lint, typecheck and unit tests with the
   detected tooling, and ensure CI invokes the SAME root commands (see
   `reference/tooling.md` → "CI/CD must use exactly the same tooling as local"). Only
   scaffold what the project doesn't already have — a repository's existing hooks are
   what the loop runs.

10. **Preflight the credentials, then verify what you can.** Follow
    `reference/onboarding.md` § The credential preflight exactly — it is the step that
    stands next to the secrets, and its rules are not negotiable.

    Collect the environment-variable **names** the configs just written declare —
    `channels.slack.botTokenEnv`, `channels.slack.appTokenEnv`,
    `webhooks.ghWebhook.secretEnv`, `integrations.github.api.tokenEnv` — from the files
    themselves, not from a hardcoded list, and report **presence only** for each one that
    this configuration actually needs.

    **Report whether it is set. Never the value, a prefix of it, its length, or a hash of
    it. Never write a credential into any file.** This is the contract
    `the-loop channels status` already keeps, and init keeps the same one.

    An unset variable is a **needs-user** line naming the variable, what it gates, where
    to obtain it and — when an `env.file` is configured — which file to put it in. When
    you propose an `env.file`, say it will hold secrets and check `.gitignore` covers it,
    offering to add the line when it does not. A variable that only the daemon's
    environment would carry is reported as *unverified*, which is not the same as *unset*.

    Then verify: `the-loop channels status` (and `--probe` where a token is present) for
    a configured Slack channel, and `the-loop doctor slack` for the deployment-wide view.
    Where the CLI is not on this machine, print the commands for the user to run and
    report the channel as **unverified** — never as working. A failed probe is a finding
    for the report, not an init failure.

11. **Report.** End with a short summary grouped as **created / skipped (up to date) /
    drifted (suggested) / needs-user** (files, config gaps or credentials the user must
    fill), then the immediate next action (`/the-loop:work-on <ticket>` or
    `/the-loop:new-requirement`). Name the **autonomy profile that was applied**, by id,
    and — when none was — say plainly that no automation is enabled and that re-running
    init is how to change that. Under `--dry-run`, print exactly this report and write
    nothing.

Respect existing files. This command is idempotent, non-clobbering, and safe to re-run —
which is what makes it trustworthy to run on someone's repository.
