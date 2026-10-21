---
description: Initialize the-loop's CLI daemon config (cli-config.yaml) for the operator — where the daemon runs, how much runs unattended, its ingress, Slack, Jira, the arming labels and the credentials they need — via the same guided, schema-driven onboarding. Run once, in the operator repository or for ~/.the-loop/. Idempotent, non-clobbering.
argument-hint: "[--dry-run] [--defaults]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: init-cli

Initialize the **CLI config** — the operator's file that the-loop's daemon reads
(`start`/`stop`/`status`, the webhook receiver, the poller, `sessions`, `channels`). It is
separate from, and independent of, any repository's `.the-loop/harness-config.yaml`
(decision-032), and it is resolved via `--config`/`$THE_LOOP_CLI_CONFIG`/
`./.the-loop/cli-config.yaml`/`~/.the-loop/cli-config.yaml` (see `cli/README.md`).
**Idempotent and safe to re-run:** it creates only what is missing and never overwrites a
user-owned file.

**Who runs this, and when** (issue-514): the operator, once — in the **operator
repository** (the one whose checkout keeps the daemon's config) or for
`~/.the-loop/`. A repository that only *uses* the-loop runs `/the-loop:init` and never
this. This command needs no `.the-loop/harness-config.yaml` and writes none: it creates
nothing but the CLI config, the Slack app manifest beside it, and the arming labels on the
repositories the config routes.

**What a finished init-cli owes the user:** a CLI config they understand, an honest answer
to "what will this do while I am not looking", and a list of every credential still
missing. An init-cli that writes a valid config and leaves the user with nothing running —
and no signal that nothing is running — has failed, whatever the report says.

Templates (`${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/`, `manifest.templatesDir`)
and config schemas (`${CLAUDE_PLUGIN_ROOT}/.the-loop/*.schema.json`,
`manifest.schemasDir`) are internal to the-loop and are **never** copied anywhere — read
them from the plugin (issue-220). The scaffolded config opens with a
`# yaml-language-server: $schema=<published url>` line so the operator's editor validates
it with nothing local on disk. (`${CLAUDE_PLUGIN_ROOT}` is the installed plugin's root
directory; in Cursor, resolve it to the plugin's install directory.)

## Modes

- **`--dry-run`** — compute and print the report (below) **without writing anything**
  and without interacting. It writes no config, no Slack manifest, no label and no
  `.gitignore` line.
- **`--defaults`** — non-interactive: ask nothing, scaffold nothing (the home-directory
  default applies with zero setup), and list every gap under **needs-user** — the
  deployment shape, the autonomy profile, the config's location, every unset credential.
  With no autonomy profile chosen, the shipped defaults apply, which means **no
  automation is enabled** — say so in the report rather than leaving it implied.

## Steps

1. **Detect** what the walkthrough can propose rather than ask:
   - the **repository ref** (`owner/repo` from the `origin` remote of the current
     checkout, when there is one) for the config's `repositories` and `polling.sources`.
   - the **deployment shape**, where it is unambiguous — a container, a cloud shell, a
     CI runner. Where it is not, step 2 asks. Never act on an inferred shape silently:
     show it and let the user correct it.

2. **Establish the posture: where this runs, and how much of it runs unattended.** Two
   questions, before any automation key is proposed, both from the skill's
   `reference/onboarding.md` (§ The deployment shape, § The autonomy ladder). They have
   no defaults worth guessing, which is why they come first and why they are the CLI
   config's `always` group.

   - **The deployment shape** — a personal machine you close, an always-on host with an
     inbound route, or nowhere yet. This is the fact that decides the ingress: GitHub
     cannot reach a webhook receiver behind NAT, so a laptop polls and a reachable host
     receives. The answer is used and not stored.
   - **The autonomy profile** — read `x-onboarding.profiles` from the plugin's
     `cli-config.schema.json` and present the whole ladder: every rung with its
     `summary` **and** its `stillHuman` line, with `profiles.recommended` marked. Take
     the answer as the **proposal** for the keys it covers, never as a write; the
     resolved values are shown in step 3 and the user may still adjust them.

   **Say the invariant out loud when you present the top rung:** no profile removes a
   human gate. The phase-selection checklist, the `requirements.md` and `design.md`
   approvals, the pull-request approval and the risk tiers are fixed rules of the skill
   and the process graph, not settings. A profile decides who **starts** work and how
   events arrive; never who **approves** it.

   Record the chosen rung as a comment in the config written in step 5
   (`# onboarding profile: <id>`) and name it in the final report.

3. **Onboard the CLI config with the user (guided, grouped, schema-driven).**

   **First, where it lives** (one plain question — decision-032): *"Do you want the CLI
   daemon's config tracked and versioned in this repo (`.the-loop/cli-config.yaml`,
   picked up automatically when you run `the-loop` from here), or in your home directory
   (`~/.the-loop/cli-config.yaml`)?"* Never assume either answer.

   **Then walk it** from `x-onboarding.groups` in the plugin's `cli-config.schema.json`,
   following `reference/onboarding.md` exactly — the same procedure `/the-loop:init`
   uses for the harness config. Walk it **whichever answer they gave**: where the file
   lives is a storage question; what it turns on is the reason they ran this command.
   The groups are `deployment`, `ingress`, `execution`, `channels` (step 4), then the
   `advanced` pair `review` and `operations`. For each key the autonomy profile covers,
   show its value with the provenance *"from the profile you picked"*. On a re-run,
   only raise gaps — never re-ask what is already established.

   Three keys deserve a sentence of their own even when the profile has proposed the rest,
   because a deployment is broken without them and nothing else will tell the user:
   - `routing.authorizedUsers` — **empty by default**, and until someone is named here
     nobody can start, stop or approve anything from a comment. No profile fills it: who
     may drive the loop is established by name.
   - `routing.workspace.root` — **empty by default**; the daemon runs independent of any
     repository, so without it a spawned session has nowhere to check the code out.
   - `routing.autoExecuteLabels` — the labels that arm a work item, **all of which** must
     be present before anything spawns. Apply the whole list when you arm an item.

   **Then ask about a gateway** (issue-496), one plain question: *"Will this instance
   read its events from a the-loop gateway — one process that owns the webhooks and the
   Slack connection for several instances — or run its own receiver, poller and Slack
   listener?"* With a gateway, the `ingress` group's answer is a `gateway` block
   (`url`, and the `actors` this instance works for: the GitHub logins, Slack user ids
   and Jira account ids of its users); the receiver and the poller are still asked for
   and run as answered (the gateway's own pollers are opt-in), and only the Slack
   listener is left off, since the gateway holds the app's connection; without one,
   nothing changes. If the user says **they run the gateway on this machine**, do not
   walk the gateway's own config here: name `/the-loop:init-gateway` under
   **needs-user** in the report — it establishes `gateway-config.yaml`. Never assume
   either answer.

4. **Set up Slack, or skip it cleanly.** Slack is the `channels` group, and it gets its
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
   1. **The app, from one click** (issue-464). Each operator creates their own app,
      because its tokens are what their daemon runs on. So first **ask the app's name**,
      proposing `the-loop` and saying that a workspace other operators share needs a
      distinct one (e.g. `the-loop-dana`). It is at most 35 characters, and the bot's
      `@handle` is derived from it. Then write the manifest beside the CLI config, in
      the directory step 3 chose:

      ```bash
      the-loop channels manifest --name "<name>" --write <cli-config dir>/slack-app-manifest.json
      ```

      It prints the path and a **link**
      (`https://api.slack.com/apps?new_app=1&manifest_json=…`). Give the user the link:
      they click it, pick the workspace, confirm *Create*, then *Install to Workspace*.
      No token is needed to build it. The kept `slack-app-manifest.json` is what
      `/the-loop:upgrade-the-loop` regenerates when a release changes the app's scopes.
      An app that already exists is upgraded by pasting that file over its *App
      Manifest* and reinstalling, not by clicking the link again (a second click
      creates a second app). Under `--dry-run`, print the command and write nothing.
   2. **The bot token** (`xoxb-…`) — *OAuth & Permissions*, shown once the app is
      installed. The user puts it in their environment, or in the `env.file` when one is
      configured, under the name `channels.slack.botTokenEnv` (default
      `THE_LOOP_SLACK_BOT_TOKEN`). **Never ask them to paste a token into this
      conversation**: step 8 reports only whether it is set.
   3. **The app-level token** (`xapp-…`, scope `connections:write`) — *Basic Information →
      App-Level Tokens*. A manifest cannot mint it. It goes in the same place as the bot
      token, under `channels.slack.appTokenEnv` (default `THE_LOOP_SLACK_APP_TOKEN`).
      This is what Socket Mode connects with, and Socket Mode is what makes the buttons
      and `/the-loop` work.
   4. **The conversation** — invite the bot to the channel and take that conversation's
      **id** from its details pane for `channels.slack.channel`.

   Propose `subscribe` from the schema; propose `publish` at the schema default and
   **never widen it unasked** — each grant is authority the channel did not have.
   Verification happens in step 8.

   **Then offer Jira, the same way** — only when work items (or mirror rooms) live on
   Jira; **if the user declines, write no `integrations.jira` block**. Walk
   `reference/onboarding.md` § Jira onboarding: the site; the deployment kind (`cloud`,
   `cloud-scoped`, `data-center`); the **names** of the variables holding the email and
   token, plus the `cloudId` when scoped; a dedicated service account with least
   privilege (`read:jira-work`, `write:jira-work`, `read:jira-user` for a scoped token);
   the projects and the repository each maps to (none = mirror-only), with a
   `polling.sources` entry for those polled; and the webhook secret's variable. Print
   the Jira-safe label table. Never take a credential's value.

5. **Write the config (idempotent, non-clobbering).** At the path step 3 established,
   from `templates/cli-config.yaml` with steps 2–4's answers applied, carrying the
   `# onboarding profile: <id>` provenance comment and keeping the template's
   `# yaml-language-server: $schema=…` **first line** intact. A config already there is
   user-owned: never overwrite it — raise only its gaps, and diff and *suggest* any
   drift from the current template. Never scaffolded under `--defaults` or `--dry-run`.

6. **Create the arming labels.** Where routing was enabled, create each
   `routing.autoExecuteLabels` entry that is missing in every GitHub repository the
   config routes (`repositories`, and the `github` entries of `polling.sources`) — an
   arming label that does not exist cannot be applied. On Jira create **nothing**: Jira
   creates a label the first time an issue carries it, in the Jira-safe form step 4
   printed. Skip any that already exist. The `loop:<phase>` labels are not this
   command's: each repository gets those from `/the-loop:init`.

7. **Validate** the config against the plugin's `cli-config.schema.json`, read from
   `${CLAUDE_PLUGIN_ROOT}/.the-loop/` (`manifest.schemasDir`) on disk — never fetched over
   the network, never copied into the project. **If the schema cannot be read, stop
   before writing the config** and report the missing path under **needs-user** — never
   write an unvalidated file.

8. **Preflight the credentials, then verify what you can.** Follow
   `reference/onboarding.md` § The credential preflight exactly — it is the step that
   stands next to the secrets, and its rules are not negotiable.

   Collect the environment-variable **names** the config just written declares —
   `channels.slack.botTokenEnv`, `channels.slack.appTokenEnv`,
   `webhooks.ghWebhook.secretEnv`, `integrations.github.api.tokenEnv`, and with Jira
   `integrations.jira.api.emailEnv`, `integrations.jira.api.tokenEnv` and
   `integrations.jira.webhook.secretEnv` — from the file itself, not from a
   hardcoded list, and report **presence only** for each one that
   this configuration actually needs.

   **Report whether it is set. Never the value, a prefix of it, its length, or a hash of
   it. Never write a credential into any file.** This is the contract
   `the-loop channels status` already keeps, and init-cli keeps the same one.

   An unset variable is a **needs-user** line naming the variable, what it gates, where
   to obtain it and — when an `env.file` is configured — which file to put it in. When
   you propose an `env.file`, say it will hold secrets and check `.gitignore` covers it,
   offering to add the line when it does not. A variable that only the daemon's
   environment would carry is reported as *unverified*, which is not the same as *unset*.

   Then verify: `the-loop channels status` (and `--probe` where a token is present) for
   a configured Slack channel, `the-loop doctor slack` for the deployment-wide view,
   and `the-loop doctor jira` for a configured Jira (offline: it sends nothing).
   Where the CLI is not on this machine, print the commands for the user to run and
   report the channel as **unverified** — never as working. A failed probe is a finding
   for the report, not an init failure.

9. **Report.** End with a short summary grouped as **created / skipped (up to date) /
   drifted (suggested) / needs-user** (config gaps or credentials the user must fill),
   then the immediate next action (`the-loop start`, or `/the-loop:init-gateway` when
   this machine hosts the gateway). Name the **autonomy profile that was applied**, by
   id, and — when none was — say plainly that no automation is enabled and that
   re-running `/the-loop:init-cli` is how to change that. Under `--dry-run`, print
   exactly this report and write nothing.

Respect existing files. This command is idempotent, non-clobbering, and safe to re-run.
