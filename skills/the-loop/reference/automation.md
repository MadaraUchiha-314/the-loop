# Automation & distribution reference

How the-loop is delivered and the automation capabilities it provides in your project.
This describes what the-loop *does* today, in your project.

## Distribution

- the-loop ships as a plugin for **Claude Code** and **Cursor**. Personas across the PDLC
  (PM, design, architect, dev, QA) all work through an agent harness, so the-loop meets
  them there.
- It is hosted on GitHub and installed via each harness's **marketplace** construct,
  **directly from GitHub** — no bespoke marketplace publishing. The Claude Code manifest
  lives in `.claude-plugin/`, the Cursor manifest in `.cursor-plugin/`; both share the
  same `skills/`, `commands/` and templates (skills follow the Agent Skills open
  standard, so one `SKILL.md` serves both harnesses).

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
  - `the-loop gh-webhook start [--host --port --path --pidfile --secret-env --route]`
  - `the-loop gh-webhook stop [--pidfile]`
  - Verifies the GitHub `X-Hub-Signature-256` HMAC (secret from an env var), exposes
    `GET /health`, and logs deliveries. Defaults come from `webhooks.ghWebhook` in
    `.the-loop/config.yaml`.
- **Webhook → session routing** (`--route`; `webhooks.ghWebhook.routing`): a received
  event (PR/issue comment, `workflow_run` result, …) is matched to the registered
  session working that item and delivered by *resuming* that session through its
  official CLI (`claude -p … --resume` / `cursor-agent -p … --resume`) with a prompt
  that embeds the payload as untrusted data. Per-session FIFO, parallel across
  sessions; duplicates (`X-GitHub-Delivery`) processed at most once; unmatched events
  follow `routing.spawnOnUnmatched`. Design: `docs/specs/issue-15/design.md`,
  decision: `docs/decisions/decision-016.md`.
- **Session registration is a workflow step.** When the harness starts executing a
  work item (execute-tasks / work-on), it registers itself so events can find it —
  and closes the registration in finish-tasks:

  ```bash
  # Claude Code (session id is exposed to hooks/commands as $CLAUDE_SESSION_ID)
  the-loop sessions register --work-item github:OWNER/REPO#N \
      --harness claude --harness-session-id "$CLAUDE_SESSION_ID"
  # Cursor (use the chat id this agent was launched with)
  the-loop sessions register --work-item github:OWNER/REPO#N \
      --harness cursor --harness-session-id "<chat-id>"
  # on completion
  the-loop sessions close --work-item github:OWNER/REPO#N
  ```

  Registration is best-effort: if it fails, routing degrades to log-and-drop (or
  spawn), never blocking the session's own work.

## Predictability & execution guarantees

The PDLC is largely fixed; the harness should not re-derive it each run. Steps are made
predictable via:

- **Harness hooks** — force steps to run at lifecycle points. In Claude Code:
  `hooks/hooks.json` (SessionStart reminder). In Cursor: the always-applied rule
  `rules/the-loop.mdc` carries the same reminder (Cursor hook events have no
  SessionStart equivalent).
- **Custom code/scripts** (the CLI is a natural home) where hooks are insufficient.

## Self-improvement (learnings lifecycle)

the-loop is not expected to be perfect from the start; it captures learnings in your repo
so it measurably stops repeating mistakes — without letting the index grow unbounded and
blow the context budget. Learnings live in `learnings/learnings.md` (index) +
`learnings/learning-<nnn>.md` (detail), with overflow in `learnings/topics/<category>.md`.
Tuned by `config.selfImprovement` (`enabled`, `maxIndexLines`, `writeGateOccurrences`).
Sources: **user feedback** (requirements/design/tasks iteration, PR reviews) and **system
feedback** (repeated failures or insights). The skill implements this today; the Python
CLI can harden it later. Four stages:

1. **Capture.** At logical checkpoints the loop emits learning *candidates* from the
   pass/fail signals it already produces (a red check, a rejected review, a repeated
   reviewer comment) into a **git-ignored pending queue** (`.the-loop/learnings-pending/`).
2. **Write-gate.** A candidate becomes a durable, injected learning only once it
   **recurs** (`writeGateOccurrences`, rule-of-three) — or immediately for a clearly
   high-severity one-off. This keeps one-off noise out of the index.
3. **Consolidate.** At the end of a run, classify each candidate against the existing
   index as **ADD / UPDATE / DELETE** (on contradiction) / **NOOP**, then **prune to the
   size cap** (`maxIndexLines`) by evicting the least-important/least-recent entries into
   `learnings/topics/<category>.md`.
4. **Inject.** Load the **capped index** (first `maxIndexLines` lines) into each agent's
   prompt at the start of a run; overflow detail is read on demand from the topic files.

Everything durable is checked in so you can review it and give feedback.

## Reporting problems with the-loop

Feedback and bug reports about the-loop itself are filed as GitHub issues on the the-loop
repository.
