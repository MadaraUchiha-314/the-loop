# Automation, distribution & roadmap reference

Captures the realization details and forward-looking pieces of issue #1 so they are not
lost. Items here that are not yet built are tracked as deferred work (see
`docs/decisions/decision-003.md`).

## Distribution

- the-loop ships as a **Claude plugin** (Cursor support planned — only Claude and Cursor
  are targeted). Personas across the PDLC (PM, design, architect, dev, QA) all use an
  agent harness, so the-loop meets them there.
- Hosted on GitHub and distributed via Claude's **marketplace** construct, installable
  **directly from GitHub** — no bespoke marketplace publishing.
  - _Open question:_ the Cursor equivalent of marketplace distribution — TODO.

## Footprint tracking

- Every file the-loop creates/maintains/tracks is listed in `.the-loop/manifest.yaml`.
- All meta files the-loop uses internally live under `.the-loop/`.

## CLI companion (`the-loop`, Python)

the-loop is primarily a plugin, but it ALSO ships a lightweight, extensible **Python
CLI** (`cli/`, package `the_loop`) for quality-of-life commands the plugin itself can
use. Python is deliberate — future self-learning/ML capabilities are mostly exposed as
Python SDKs. The core has **zero runtime dependencies** (stdlib only).

- Primary CLI: **`the-loop`**. Adding a command = subclass `Command`, `@register` it,
  drop the module under `the_loop/commands/`.
- First command — GitHub webhook receiver:
  - `the-loop gh-webhook start [--host --port --path --pidfile --secret-env]`
  - `the-loop gh-webhook stop [--pidfile]`
  - Verifies the GitHub `X-Hub-Signature-256` HMAC (secret from an env var), exposes
    `GET /health`, logs events, and is structured to route events to the harness.
  - Defaults come from `webhooks.ghWebhook` in `.the-loop/config.yaml`.

See `docs/decisions/decision-005.md`.

## Predictability & execution guarantees

The PDLC is largely fixed; the harness should not re-derive it each run. Make steps
predictable/guaranteed via:
- **Claude hooks** (`hooks/hooks.json`) — force steps to run at lifecycle points.
- **Custom code/scripts** where hooks are insufficient (the CLI is a natural home).
This is an open design question; record decisions as the approach firms up.

## Webhooks (receiver in CLI; harness routing deferred)

Auto-trigger the harness from external systems. The **receiver** is provided by the CLI
(`the-loop gh-webhook`); routing received events through to actually trigger the harness
is deferred:
- **GitHub PR review comments** → trigger the harness to respond.
- **GitHub Actions completion/failure** → trigger the harness to react/fix.

## The dream (deferred)

- An authorized user creates a work item (GH issue / Jira ticket) → an execution of
  the-loop is **automatically triggered in a remote workspace** (e.g. GitHub
  Codespaces) and delivers the work end-to-end. Humans are notified ONLY when a
  decision/opinion is required.
- Given a full project work-breakdown, the-loop orchestrates the whole **DAG** of work
  items to completion (see `workflow.md` → DAG orchestration).

## Self-improvement (learnings)

These loop systems are not perfect from the start. Capture learnings in the repo:
- `learnings/learnings.md` (index) + `learnings/learning-<nnn>.md` (detail).
- Sources: **user feedback** (during requirements/design/tasks iteration, PR reviews)
  and **system feedback** (repeated failures or insights the harness discovers).
- Checked in so the user can review and give feedback.

## Meta

- Feedback about the-loop itself is filed as GitHub issues on the the-loop repository.
- the-loop uses the-loop to develop and improve itself.

## Open TODOs carried from issue #1

- Validate "all scripts from root" scales for large monorepos.
- Confirm browser-logging via chrome-devtools MCP and document setup.
- Decide predictability mechanism (hooks vs custom code).
- Find the Cursor marketplace-distribution equivalent.
- Confirm GitHub's `depends-on` / `blocked-by` equivalents for DAG orchestration.
- Finalize Go tooling defaults.
