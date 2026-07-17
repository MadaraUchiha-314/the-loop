# Decision 021: tmux runner for observable/interactive webhook-spawned sessions

- **Status:** accepted
- **Date:** 2026-07-17
- **Deciders:** @MadaraUchiha-314 (issue #32, PR #33/#35 reviews)
- **Work item:** issue-32
- **Spec:** `docs/specs/issue-32/`

## Context

Webhook-spawned sessions run as invisible headless subprocesses
(`claude -p … --output-format json`, decision-016); nobody can watch or steer the
agent. Issue #32 asked for tmux-hosted sessions attachable locally, over SSH, or via a
web terminal — and for the architecture/alternatives to be worked out.

## Decision

Add an opt-in, **receiver-global** `routing.runner: tmux` (default `process`,
unchanged): the dispatcher spawns the harness's **interactive TUI inside a detached
tmux session** (`loop-<work-item-slug>`), with:

- **Event delivery = bracketed-paste injection** (`load-buffer` → `paste-buffer -p` →
  `send-keys Enter`), serialized by the dispatcher's existing per-session FIFO; GitHub
  redelivery is the retry path. The hybrid "headless `-p --resume` when idle" was
  rejected — a concurrent headless resume races the live TUI on conversation state,
  and reliable idle-detection doesn't exist.
- **Session identity = pre-assigned UUID** (`claude --session-id <uuid>`) exposed via
  a per-adapter `interactive_argv`; cursor-agent has no pre-assignable chat id, so
  tmux-mode spawns for cursor fail cleanly until its CLI supports one.
- **Web terminal ships**: an optional ttyd child of the receiver serving a shared
  `the-loop-hub` tmux session, bound to `127.0.0.1` by default. **Access control is
  environmental** (localhost / VPN / hosting provider network) — the-loop builds no
  auth (owner ruling, PR #33).
- **Installability**: tmux/ttyd are native host binaries a Python wheel cannot carry;
  the receiver verifies them at start with per-platform guidance. Auto-install via
  system package managers was rejected; static-binary auto-download parked.

Alternatives rejected in the brainstorm: GNU screen, dtach/abduco, Zellij (weaker or
younger automation surfaces), asciinema (observe-only), vendor-hosted sharing
(defeats self-hosting), per-work-item runner selection (deferred; registry records the
runner per session, so it stays a zero-migration extension).

## Consequences

- New module `cli/the_loop/runner.py` (`TmuxRunner`, `check_dependencies`); registry
  entries gain `runner`/`tmuxTarget`; new config `routing.runner` +
  `routing.webTerminal`; `the-loop sessions` gains `attach` and tmux-aware
  `list`/`close`.
- Sessions survive receiver restarts (the tmux server owns them); PR-close also kills
  the tmux session.
- Turn completion is not tracked in tmux mode (paste-and-return); humans attached to
  the TUI see events arrive live.
- **Re-evaluation triggers:** cursor-agent gaining a pre-assignable/queryable chat id
  (enable cursor in tmux mode); harness CLIs gaining a first-class "inject message
  into running session" API (replace paste injection); a third runner appearing
  (introduce a runner abstraction).
