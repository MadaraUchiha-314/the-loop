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
- WHEN an event concerns a **PR that is linked to a GitHub issue** THEN it SHALL be
  delivered into the tmux session of that **issue** (one tmux session per work item, not
  one per GitHub object), and a from-scratch spawn SHALL be keyed to the issue's slug —
  see [webhook-triggers](webhook-triggers.md) for how the linkage is resolved
  (issue-93, [decision-036](../decisions/decision-036.md)).
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
- WHEN a session is spawned **or respawned** THEN — before either runner starts the
  harness — the harness's own user config SHALL be pre-seeded so the session does not
  open on an interactive dialog (`routing.harnessTrust`, default on). For Claude Code
  that means marking the **exact** spawn directory trusted
  (`projects[<dir>].hasTrustDialogAccepted` + `hasCompletedProjectOnboarding`,
  honouring `CLAUDE_CONFIG_DIR`) — never a parent — and, **only** when this harness's
  `harnessArgs` already ask for bypass mode, recording the bypass-permissions
  disclaimer acceptance (`acceptBypassPermissions: auto`; `always`/`never` decide
  explicitly). Neither dialog is a permission rule, so no CLI flag —
  `--dangerously-skip-permissions` included — silences them. Writes touch only those
  keys, merge into what is already there, go through a temp file + atomic replace, are
  **skipped entirely** when the value is already correct, and are never applied to a
  file that does not parse as JSON. Applied changes emit `workspace.trusted`; a
  failure warns, emits `workspace.trust_failed` and still spawns. A harness with no
  such config surface (cursor-agent) is a silent no-op.
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
| issue-93 | Events on a PR linked to a GitHub issue reuse that issue's tmux session instead of spawning a second one for the PR's own ref | [spec](../specs/issue-93/), [decision-036](../decisions/decision-036.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/93) |
| issue-90 | Pre-seed the harness's own config before every spawn/respawn so a session starts working instead of stalling on the workspace-trust dialog (and, when bypass mode is already configured, its disclaimer) | [spec](../specs/issue-90/), [decision-037](../decisions/decision-037.md) |
| issue-86 | Keep a finished work item's tmux session (and, via `remain-on-exit`, its pane) instead of killing it, guarded by a pane-liveness check so the respawn path still fires; announce a first-spawned session's attach command as a comment on the work item | [spec](../specs/issue-86/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/86) |
| issue-89 | Respawn now **resumes** the dead session's harness conversation (`claude --resume`, id kept in the registry) instead of booting a blank one, verified by a liveness probe with a fresh-conversation fallback (`resumeOnRespawn` / `resumeProbeSeconds`, `session.resume_failed`) | [spec](../specs/issue-89/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/89) |
