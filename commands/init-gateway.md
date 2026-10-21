---
description: Initialize a the-loop gateway's config (gateway-config.yaml) on the machine that runs it — the listener, the store, the GitHub, Jira and Slack transports with every secret as a variable name, and the repositories it may start work in — via a guided, schema-driven walk. Idempotent, non-clobbering.
argument-hint: "[--dry-run] [--defaults]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: init-gateway

Initialize `gateway-config.yaml` — the config of a the-loop **gateway**: one process that
owns the inbound transports (the GitHub and Jira webhooks, one Slack Socket Mode
connection per app, optional pollers) for several instances, each of which polls its own
queue from it (issue-496). **Idempotent and safe to re-run:** it creates only what is
missing and never overwrites a user-owned file.

**Who runs this** (issue-514): only the person who runs a gateway, on the machine that
runs it. An instance that merely *reads from* a gateway needs nothing from this command:
its `gateway` block is part of its CLI config, established by `/the-loop:init-cli`. A
repository that only uses the-loop runs `/the-loop:init` and never this. This command
writes nothing but `gateway-config.yaml`: no harness config, no CLI config, no docs tree,
no label.

The template (`${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/gateway-config.yaml`) and
the schema (`${CLAUDE_PLUGIN_ROOT}/.the-loop/gateway-config.schema.json`,
`manifest.schemasDir`) are internal to the-loop and are read from the plugin, never copied
(issue-220). (`${CLAUDE_PLUGIN_ROOT}` is the installed plugin's root directory; in
Cursor, resolve it to the plugin's install directory.)

## Modes

- **`--dry-run`** — compute and print the report (below) **without writing anything**
  and without interacting.
- **`--defaults`** — non-interactive: ask nothing, write nothing, and list every gap under
  **needs-user** — the file's location, the repositories, every secret variable that is
  unset. A gateway with no repositories and no transports does nothing, so there is no
  default worth scaffolding.

## Steps

1. **Where it lives** (one plain question): *"Keep the gateway's config in this
   repository (`.the-loop/gateway-config.yaml`, beside a CLI config kept here) or in your
   home directory (`~/.the-loop/gateway-config.yaml`)?"* Never assume either answer.
   When a CLI config already exists, propose its directory: the two files are usually
   kept together.

2. **Walk the config with the user (guided, schema-driven).** Follow the skill's
   `reference/onboarding.md` procedure — the same precedence, explanations and
   presentation `/the-loop:init` and `/the-loop:init-cli` use — over the top-level blocks
   of the plugin's `gateway-config.schema.json`, in this order:
   - `listen` — where it listens (`127.0.0.1:8790` by default). Say plainly that a
     non-loopback `listen.host` needs `listen.exposed: true`, and that there is no
     instance authentication in this release, so the network is the boundary
     (decision-146).
   - `store` and `state` — where the queues and the gateway's own state live.
   - `repositories` — the repositories it may start work items in.
   - `github`, `jira`, `slack` — each transport, offered and skippable. Every secret is an
     environment-variable **name** (`*Env`), never a value. The gateway's own GitHub and
     Jira pollers are **off** unless the user turns them on: instances keep polling as
     they do today.
   - `consume`, `instances`, `observability`, `env` — `advanced`: default silently and
     summarize, with an offer to tour them.
   For every block: explain what it does and why it matters; for enum keys show ALL the
   possibilities; for free-form keys show the schema's `examples`. Pull explanations,
   defaults, enums and examples from the schema — never from memory. On a re-run, only
   raise gaps — never re-ask what is already established.

3. **Write the file (idempotent, non-clobbering).** At the path step 1 established, from
   `templates/gateway-config.yaml` with the answers applied, keeping the template's
   `# yaml-language-server: $schema=…` **first line** intact. A file already there is
   user-owned: never overwrite it — raise only its gaps, and diff and *suggest* any drift.
   Never written under `--defaults` or `--dry-run`.

4. **Validate** it against the plugin's `gateway-config.schema.json`, read from disk under
   `manifest.schemasDir` — never fetched over the network. **If the schema cannot be
   read, stop before writing the file** and report the missing path under **needs-user**.

5. **Preflight its credentials.** Follow `reference/onboarding.md` § The credential
   preflight exactly. Collect every `*Env` name the file declares — from the file
   itself, not from a hardcoded list — and report **presence only** for each one this
   configuration needs. **Never the value, a prefix of it, its length, or a hash of it.
   Never write a credential into any file.** An unset variable is a **needs-user** line
   naming the variable, what it gates and where to obtain it; when an `env.file` is
   configured, check `.gitignore` covers it.

6. **Report.** End with **created / skipped (up to date) / drifted (suggested) /
   needs-user**, then the next actions: `the-loop gateway start`, and — for **each**
   instance that will read from this gateway — a `gateway` block in its CLI config
   (`/the-loop:init-cli` establishes it), plus `channels.slack.read.mode: gateway` when
   that instance's Slack channel is enabled (issue-503). Under `--dry-run`, print exactly
   this report and write nothing.

Respect existing files. This command is idempotent, non-clobbering, and safe to re-run.
