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
  Enter`), FIFO per session; a delivery that fails while the session is alive discards
  the delivery id so the next redelivery/poll retries.
- WHEN a delivery finds the target tmux session **gone** (crashed or killed, i.e.
  `has-session` fails) THEN the dispatcher SHALL **respawn** the harness on a fresh
  `loop-<slug>` session — reusing the recorded harness/cwd/tmux-target — and deliver
  the pending event as its boot prompt, re-registering the session (preserving the
  processed-delivery history) and emitting `session.respawned`; a respawn that cannot
  proceed (harness CLI missing, `tmux new-session` fails) fails the dispatch and
  releases for retry. This is what stops a redelivery loop into a session that no
  longer exists (issue-80).
- WHEN a session is respawned AND `routing.tmux.resumeOnRespawn` is `true` (the
  default) THEN the respawned TUI SHALL **resume the recorded harness conversation**
  (`claude --resume <harnessSessionId>`, in the session's recorded cwd) rather than
  start a blank one, and the registry SHALL keep that same session id so repeated
  crashes converge on one conversation (`session.respawned` carries `resumed: true`).
  The respawn SHALL be verified live after `routing.tmux.resumeProbeSeconds`
  (default 2, `0` = check immediately) — `tmux new-session -d` succeeds the moment the
  pane forks, while a harness that cannot resume exits at once. WHEN the resume is
  opted out, unsupported by the harness (anything but Claude Code today — cursor-agent
  cannot be tmux-hosted at all), impossible (no recorded id, or one failing a
  conservative `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` check before it reaches an
  argv, so a flag can never masquerade as a session id) or unverified
  (tmux failed, or the pane came up dead) THEN the respawn SHALL fall back to a fresh
  conversation with a newly minted id, emitting `session.resume_failed` and
  `resumed: false` — never a silently-successful dispatch into a dead pane
  (issue-89). The `process` runner already resumed on every event and is unchanged.
- WHEN a tmux session is spawned THEN tmux's `remain-on-exit` SHALL be set on it
  (`routing.tmux.remainOnExit`, best-effort — an older tmux that rejects it only
  warns), so the pane and its scrollback survive the harness process exiting. A
  delivery therefore probes **liveness** (`has-session` **and** a non-dead pane), not
  mere existence: a retained-but-dead session takes the respawn path above instead of
  swallowing the event.
- WHEN a work item's PR is merged/closed (or `the-loop sessions close` runs) THEN the
  registry session SHALL be closed AND the tmux session SHALL be **kept running** so
  its transcript stays readable (`session.retained`); `routing.tmux.keepSessionOnClose:
  false` — or `sessions close --kill-tmux` — SHALL terminate it instead (best-effort
  when already gone). Retained sessions accumulate until killed, and a new spawn for
  the same work item reclaims the deterministic `loop-<slug>` name.
- WHEN a tmux-mode session is spawned THEN the-loop SHALL comment on the work item
  with the tmux session name and the `tmux attach -t loop-<slug>` command
  (`routing.announce`, default on), so the attach details reach the humans on the
  ticket. A **respawn** SHALL post nothing further — it reuses the same name, so the
  existing comment stays correct and a flapping session cannot bury the thread.
  Best-effort through the operator's own `gh` CLI: a failure never affects the
  dispatch, and a process-runner session, a non-GitHub work item or a missing `gh` is
  a no-op. The body is built only from registry fields — never from event payloads —
  and carries no filesystem paths, harness session ids or hostnames.
- `the-loop sessions list` SHALL show `Runner`/`Tmux` columns; `the-loop sessions
  attach --work-item <ref> [--read-only]` SHALL attach the caller's terminal to the
  session's tmux session — including one **retained after the work item closed** (with
  a note) — with clear errors for process-mode or genuinely absent sessions.
- WHEN `gh-webhook start --route` or `poll start` runs THEN the native dependencies
  (`tmux`; `ttyd` if `routing.webTerminal.enabled`) SHALL be verified with
  per-platform install guidance — silent when satisfied. Both ingress paths drive
  the same `Dispatcher`/`TmuxRunner`, so the preflight and the web terminal below
  behave identically regardless of which one is running (issue-65).
- WHEN `routing.webTerminal.enabled` THEN whichever ingress is running (`gh-webhook
  start --route` or `poll start`) SHALL serve a browser terminal via a ttyd child
  process bound to `127.0.0.1` by default (a shared `the-loop-hub` tmux session),
  stopped on shutdown; the-loop implements **no auth** — access control is
  environmental (localhost / VPN / hosting provider network).
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
| issue-65 | Fixed `poll start` never launching ttyd (it shared the tmux runner but had no web terminal start/stop of its own); factored ttyd lifecycle into a shared `the_loop.runner` helper used by both `gh-webhook start` and `poll start` | [issue](https://github.com/MadaraUchiha-314/the-loop/issues/65) |
| issue-80 | Respawn a crashed/killed tmux session on delivery (deliver the pending event as the fresh TUI's boot prompt) instead of looping redeliveries into a session that no longer exists | [spec](../specs/issue-80/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/80) |
| issue-86 | Keep a finished work item's tmux session (and, via `remain-on-exit`, its pane) instead of killing it, guarded by a pane-liveness check so the respawn path still fires; announce a first-spawned session's attach command as a comment on the work item | [spec](../specs/issue-86/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/86) |
| issue-89 | Respawn now **resumes** the dead session's harness conversation (`claude --resume`, id kept in the registry) instead of booting a blank one, verified by a liveness probe with a fresh-conversation fallback (`resumeOnRespawn` / `resumeProbeSeconds`, `session.resume_failed`) | [spec](../specs/issue-89/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/89) |
