# Capability: interactive-sessions

> Webhook-spawned harness sessions humans can watch and steer live — hosted in tmux,
> attachable from a local terminal, SSH, or a browser.

## What it is

The tmux runner: instead of the headless one-shot subprocess of the `process` runner,
`routing.runner: tmux` hosts each auto-executed work item as the harness's
**interactive TUI inside a named tmux session**, while webhook events keep flowing into
the same conversation.

## Current behaviour

- WHEN routing spawns a session and `routing.runner` is `tmux` THEN the harness TUI
  SHALL start detached in tmux session `loop-<work-item-slug>` with a **pre-assigned
  session id** (`claude --session-id <uuid>`), recorded in the registry as
  `runner`/`tmuxTarget`; cursor-agent has no pre-assignable id, so tmux-mode spawns for
  it fail with a clear error.
- WHEN a routed event matches a tmux-mode session THEN the rendered prompt SHALL be
  **bracketed-pasted** into the TUI (`load-buffer` → `paste-buffer -p` → `send-keys
  Enter`), FIFO per session; failed deliveries discard the delivery id so GitHub
  redelivery retries.
- WHEN a work item's PR is merged/closed (or `the-loop sessions close` runs) THEN the
  tmux session SHALL be terminated along with the registry close (best-effort when
  already gone).
- `the-loop sessions list` SHALL show `Runner`/`Tmux` columns; `the-loop sessions
  attach --work-item <ref> [--read-only]` SHALL attach the caller's terminal to the
  session's tmux session with clear errors for process-mode or dead sessions.
- WHEN the receiver starts with `--route` THEN the native dependencies (`tmux`; `ttyd`
  if `routing.webTerminal.enabled`) SHALL be verified with per-platform install
  guidance — silent when satisfied.
- WHEN `routing.webTerminal.enabled` THEN the receiver SHALL serve a browser terminal
  via a ttyd child process bound to `127.0.0.1` by default (a shared `the-loop-hub`
  tmux session); the-loop implements **no auth** — access control is environmental
  (localhost / VPN / hosting provider network).
- WHEN `routing.runner` is `process` or unset THEN behaviour SHALL be identical to the
  pre-issue-32 receiver; registry files from before issue-32 remain readable, and a
  registry may mix process- and tmux-mode sessions (the session's recorded runner
  wins).

## Design

[`docs/specs/issue-32/design.md`](../specs/issue-32/design.md) ·
[decision-021](../decisions/decision-021.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-32 | Introduced the tmux runner, `sessions attach`, the ttyd web terminal and dependency preflight | [spec](../specs/issue-32/), [decision-021](../decisions/decision-021.md) |
