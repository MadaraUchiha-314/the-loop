# Automation & distribution reference

How the-loop is delivered and the automation capabilities it provides in your project.
This describes what the-loop *does* today, in your project.

## Distribution

- the-loop ships as a **Claude plugin**. Personas across the PDLC (PM, design, architect,
  dev, QA) all work through an agent harness, so the-loop meets them there.
- It is hosted on GitHub and installed via Claude's **marketplace** construct, **directly
  from GitHub** — no bespoke marketplace publishing.

## Footprint tracking

- Every file the-loop creates/maintains/tracks in your repo is listed in
  `.the-loop/manifest.yaml`. Meta files the-loop uses live under `.the-loop/`.

## CLI companion (`the-loop`, Python)

the-loop is primarily a plugin, but it ALSO ships a lightweight, extensible **Python
CLI** (`cli/`, package `the_loop`) for quality-of-life commands the plugin itself can
use. Python is deliberate — future self-learning/ML capabilities are mostly exposed as
Python SDKs. The core has **zero runtime dependencies** (stdlib only).

- Primary CLI: **`the-loop`**. Add a command by subclassing `Command`, `@register`-ing
  it, and dropping the module under `the_loop/commands/`.
- GitHub webhook receiver:
  - `the-loop gh-webhook start [--host --port --path --pidfile --secret-env]`
  - `the-loop gh-webhook stop [--pidfile]`
  - Verifies the GitHub `X-Hub-Signature-256` HMAC (secret from an env var), exposes
    `GET /health`, and logs deliveries. Defaults come from `webhooks.ghWebhook` in
    `.the-loop/config.yaml`.
  - It receives and verifies events today; wiring received events through to harness
    actions is a capability still being built.

## Predictability & execution guarantees

The PDLC is largely fixed; the harness should not re-derive it each run. Steps are made
predictable via:

- **Claude hooks** (`hooks/hooks.json`) — force steps to run at lifecycle points.
- **Custom code/scripts** (the CLI is a natural home) where hooks are insufficient.

## Self-improvement (learnings)

the-loop is not expected to be perfect from the start; it captures learnings in your
repo so it improves over time:

- `learnings/learnings.md` (index) + `learnings/learning-<nnn>.md` (detail).
- Sources: **user feedback** (during requirements/design/tasks iteration and PR reviews)
  and **system feedback** (repeated failures or insights the harness discovers).
- Checked in so you can review them and give feedback.

## Reporting problems with the-loop

Feedback and bug reports about the-loop itself are filed as GitHub issues on the the-loop
repository.
