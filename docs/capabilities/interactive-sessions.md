# Capability: interactive-sessions

> Daemon-spawned harness sessions humans can watch and steer live — hosted in tmux,
> attachable from a local terminal, SSH, or a browser.

## What it is

How every daemon-spawned session runs: each auto-executed work item is hosted as the
harness's **interactive TUI inside a named tmux session**, while events keep flowing
into the same conversation. tmux is the **only** runner — issue-156 removed the
headless one-shot `process` runner and the `routing.runner` choice with it (a config
still carrying the key is warned about and otherwise ignored).

## Current behaviour

- WHEN routing spawns a session THEN the harness TUI
  SHALL start detached in tmux session `loop-<work-item-slug>` with a **pre-assigned
  session id** (`claude --session-id <uuid>`), recorded in the registry as
  `tmuxTarget`; cursor-agent has no pre-assignable id, so spawns for
  it fail with a clear error (cursor remains usable as a critic harness only).
- WHEN a tmux session name is derived for a work item THEN it SHALL be spelled the way
  **tmux** spells it: `.` and `:` are rewritten to `_`, because they are tmux's own
  target grammar (`session:window.pane`) and tmux rewrites them itself on creation
  (issue-154). The slug keeps its dots — it is also the registry *file* name — so a repo
  like `octo/foo.js`, or any work item on a non-default host, is affected; before this
  the-loop recorded, logged and **posted on the ticket** a name tmux had already renamed,
  so the published `tmux attach -t …` command answered `can't find pane: …`, every
  liveness probe read the live session as absent, and the respawn collided with it. A
  `tmuxTarget` read back from the registry is normalised the same way, so a record
  written before the fix addresses the session that exists — no migration, and nothing is
  renamed in tmux. A slug without `.`/`:` is unchanged. The rewrite is not injective:
  two work items whose slugs differ only in a `.`/`_` position share one name, which is
  tmux's own limitation (it cannot host both at once either) and is bounded by the rule
  below that a live occupant is never spawned over.
- WHEN an event concerns a **PR that is linked to a GitHub issue** THEN it SHALL be
  delivered into the tmux session of that **issue** (one tmux session per work item, not
  one per GitHub object), and a from-scratch spawn SHALL be keyed to the issue's slug —
  see [webhook-triggers](webhook-triggers.md) for how the linkage is resolved
  (issue-93, [decision-036](../decisions/decision-036.md)).
- WHEN a routed event matches a session THEN the rendered prompt SHALL be
  **bracketed-pasted** into the TUI and then submitted by a second, **unbracketed** paste
  of a carriage return (`load-buffer` → `paste-buffer -p` → `load-buffer` →
  `paste-buffer`), FIFO per session; a delivery that fails while the session is alive
  discards the delivery id so the next redelivery/poll retries.
- **A delivery SHALL issue no tmux command that resolves a client** (issue-240). The
  submit was `send-keys … Enter` until then, and `send-keys` resolves its *target client*
  from `-c` — or, with no `-c`, from the session's current client, never from `-t`. So an
  operator attached with `sessions attach --read-only` (`tmux attach -r`) became the
  target client, and tmux ≥ 3.7 refused every delivery with `client is read-only`: the
  documented safe way to observe a session silently destroyed its only input path.
  `paste-buffer` consults no client — it writes into the `-t` pane — so **observing a
  session, read-only or not, SHALL NOT affect what the daemon can deliver into it**.
- WHEN a delivery finds the target tmux session **gone** (crashed or killed, i.e.
  tmux answers that there is no such session) THEN the dispatcher SHALL **respawn**
  the harness on a fresh
  `loop-<slug>` session — reusing the recorded harness/cwd/tmux-target — and deliver
  the pending event as its boot prompt, re-registering the session (preserving the
  processed-delivery history) and emitting `session.respawned`; a respawn that cannot
  proceed (harness CLI missing, `tmux new-session` fails) fails the dispatch and
  releases for retry. This is what stops a redelivery loop into a session that no
  longer exists (issue-80).
- WHEN a tmux session is probed THEN the answer SHALL distinguish **live** (a pane is
  running), **dead** (retained, every pane exited), **absent** (tmux itself answered
  "no such session") and **unknown** — tmux did not answer at all, because the probe
  timed out on a busy/attached server, the call raised, or the binary is missing.
  An unknown answer SHALL NEVER be read as absence (issue-146): a delivery treats it
  as live and *attempts the paste*, failing transiently if the session really is gone,
  rather than respawning over a session that is still running. That conflation is what
  sent live sessions into the respawn path, where they collided with themselves.
- WHEN a spawn or respawn would create `loop-<slug>` AND a session already holds that
  name THEN the-loop SHALL decide by what holds it, never by killing blindly
  (issue-146). `loop-<slug>` is derived from the work item, so an occupant is almost
  always that work item's own agent — the exception being the `.`/`_` alias above, which
  this rule is what keeps harmless: a **live** occupant is NEVER killed or spawned
  over — on the respawn path the pending event is delivered into it and the averted
  respawn recorded as `session.respawn_averted` (the registry already points there, so
  nothing is re-registered); on the first-spawn path, where there is no registered
  session to deliver into, the spawn SHALL fail **loudly** with the operator's remedy
  (`tmux kill-session -t loop-<slug>`, or `the-loop sessions reset`) rather than
  destroy a running agent. A **dead** (retained) occupant SHALL be cleared and the
  clear **verified** — a `kill-session` that reports failure against a session that is
  nonetheless gone counts as cleared — before `new-session` runs. WHEN a dead occupant
  cannot be cleared THEN the dispatch SHALL be **skipped**: `dispatch.dropped` with
  `reason: session-occupied`, at error level, and the delivery id deliberately
  **kept** — releasing it is what made every later cycle re-run the identical
  collision. WHEN `tmux new-session` reports `duplicate session` anyway (the
  pre-flight probe went unanswered, or lost a race) THEN tmux's answer SHALL be
  treated as authoritative: re-decide from a fresh probe and spawn at most **once**
  more, never in a loop.
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
  (issue-89).
- WHEN a tmux session is spawned THEN tmux's `remain-on-exit` SHALL be set on it
  (`routing.tmux.remainOnExit`, best-effort — an older tmux that rejects it only
  warns), so the pane and its scrollback survive the harness process exiting. A
  delivery therefore probes **liveness** (`has-session` **and** a non-dead pane), not
  mere existence: a retained-but-dead session takes the respawn path above instead of
  swallowing the event.
- WHEN a session is **paused** (issue-106 — the pause keyword, or
  `the-loop sessions pause`) THEN its tmux session SHALL be left exactly as it is:
  pausing suppresses *delivery*, it does not touch the hosted TUI, so the conversation
  is intact when the work item is resumed. Attaching to a paused session still works
  (and is still writable — a human at the terminal is not what a pause holds off).
- WHEN a work item is **reset** (issue-137 — `the-loop sessions reset`) AND it has a live
  session THEN that session SHALL be ended through the same close path above, so its tmux
  session is retained or killed by exactly the configured policy; the difference from a
  stop is what happens **after** — the registry record is deleted rather than left closed,
  so the retained tmux session is no longer reachable through
  `sessions attach --work-item` and is read back with `tmux attach -r -t loop-<slug>`
  directly, or cleaned up with `tmux kill-session`. A reset SHALL therefore always report
  that it ended a live session, and SHALL report a removed workspace checkout separately,
  because uncommitted work in it does not survive.
- WHEN a work item is **cleaned up** (issue-186 — the `the-loop cleanup` keyword,
  `the-loop sessions cleanup`, or a closure by an **authorized** user) THEN the tmux
  session of **every** endpoint on its record SHALL be killed — the work item's own and
  one per pull request delivering it, the harness inside each ended first with the same
  grace period a close uses, the work item's own session **last** — AND its workspace
  checkout SHALL be removed AND its machine-local registry record SHALL be deleted
  (`session.cleaned`). This is the one path that ignores
  `routing.tmux.keepSessionOnClose` and `routing.workspace.keepCheckoutOnClose`: those
  answer what should survive the end of the *work*, and cleanup is the operator saying
  they are done with all of it — so **uncommitted work in the checkout does not
  survive**. The **portable** record (`control`, `poll`, the frozen graph) SHALL be
  kept, which is the whole difference from a reset, and no remote object SHALL be
  touched. A cleanup SHALL run with or without a live session and with or without a
  record — a checkout left behind by a crash is located from the work-item ref alone —
  and SHALL record `cleanup` as the item's last control command, so a torn-down item
  cannot re-spawn on the next event.
- WHEN a work item is closed AND the close event names an actor who is in
  `routing.authorizedUsers` THEN the cleanup above SHALL run after the session is
  closed; WHEN it names **no** actor, or one that is not authorized, THEN the session
  SHALL be closed exactly as before and the cleanup SHALL be **deferred**, recorded as
  `cleanup.deferred` with `reason: no-actor | unauthorized-actor` (issue-186). Fails
  closed on purpose: a close action need not carry the identity of whoever performed it,
  and destroying an operator's uncommitted work on an unattributable event is not a
  trade worth making — an authorized user's `the-loop cleanup` is the remedy, and it
  works on a closed work item exactly as on an open one.
- WHEN a work item ends — the registered item itself closed or merged (one of its
  *linked* PRs closing does not end it, issue-101), or `the-loop sessions stop` /
  `the-loop sessions close` run —
  THEN the registry session SHALL be closed AND the tmux session SHALL be
  **kept** so its transcript stays readable (`session.retained`);
  `routing.tmux.keepSessionOnClose: false` — or `sessions close --kill-tmux` — SHALL
  terminate it instead (best-effort when already gone). Retained sessions accumulate
  until killed, and a new spawn for the same work item reclaims the deterministic
  `loop-<slug>` name — but only when its harness has actually exited (the default
  `killHarnessOnClose: true` ensures that). A retained session whose harness is still
  running is never reclaimed silently: see the occupancy rules above (issue-146).
- WHEN a tmux session is **kept** on close AND `routing.tmux.killHarnessOnClose` is
  `true` (the default) THEN the harness process running in its pane SHALL be ended —
  `SIGTERM`, escalating to `SIGKILL` after `routing.tmux.harnessKillGraceSeconds`
  (default 5, `0` = immediately) — so a finished work item leaves a *record*, not a
  live TUI a stray keystroke, paste or `send-keys` could resume (issue-94).
  `remain-on-exit` SHALL be re-set first so the pane and its scrollback survive the
  process. Only pids tmux reports for **that session's own panes** are ever signalled —
  a recorded `tmuxTarget` that is not a `loop-<slug>` name is refused before any pane is
  listed, and a non-positive pid is never passed to `os.kill` — and the whole step is
  best-effort: a missing session, an already-dead pane, an exited
  process or a refused signal is logged (`session.harness_terminated`) and the close
  completes regardless. `killHarnessOnClose: false` keeps the pre-issue-94 behaviour
  (a retained session keeps its harness running).
- WHEN a session is spawned THEN the-loop SHALL comment on the work item
  with the tmux session name and the `tmux attach -t loop-<slug>` command
  (`routing.announce`, default on), so the attach details reach the humans on the
  ticket. A **respawn** SHALL post nothing further — it reuses the same name, so the
  existing comment stays correct and a flapping session cannot bury the thread.
  Best-effort through the operator's own `gh` CLI: a failure never affects the
  dispatch, and a non-GitHub work item or a missing `gh` is
  a no-op. The body is built only from registry fields — never from event payloads —
  and carries no filesystem paths, harness session ids or hostnames, and it SHALL carry
  the loop-prevention marker plus a visible attribution line
  (`the_loop.authz.mark_self_authored`) so neither trigger path feeds the announcement
  back into the session it announces (issue-104).
- `the-loop sessions list` SHALL show a `Tmux` column; `the-loop sessions
  attach --work-item <ref> [--read-only]` SHALL attach the caller's terminal to the
  session's tmux session — including one **retained after the work item closed**, which
  SHALL always be attached **read-only** (with a note) whether or not `--read-only` was
  passed — with a clear error for a genuinely absent session, and for a record with no
  `tmuxTarget` yet ("no tmux session recorded yet…" — see the lazy-healing rule below).
- WHEN the receiver (with routing enabled) or the poller runs THEN the native dependencies
  (`tmux`; `ttyd` if `routing.webTerminal.enabled`) SHALL be verified with
  per-platform install guidance — silent when satisfied. Both ingress paths drive
  the same `Dispatcher`/`TmuxRunner`, so the preflight and the web terminal below
  behave identically regardless of which one is running (issue-65).
- WHEN `routing.webTerminal.enabled` THEN whichever ingress is running (the receiver
  or the poller) SHALL serve a browser terminal via a ttyd child
  process bound to `127.0.0.1` by default (a shared `the-loop-hub` tmux session),
  stopped on shutdown; the-loop implements **no auth** — access control is
  environmental (localhost / VPN / hosting provider network).
- WHEN a session is spawned **or respawned** THEN — before **any** harness start,
  meaning both halves of a respawn (the conversation-resume attempt
  above as well as the fresh-conversation fallback) — the harness's own user config
  SHALL be pre-seeded so the session does not
  open on an interactive dialog (`routing.harnessTrust`, default on). For Claude Code
  that means writing **both** `hasTrustDialogAccepted` and
  `hasCompletedProjectOnboarding` on the **exact spawn directory**, under **every**
  `scope`, because the harness reads each of those keys from the exact project key on at
  least one path: the check that gates the dialog for a repo shipping
  `.claude/settings.json` grants does not walk ancestors, and neither does onboarding.
  `scope` decides only whether trust *additionally* widens — the default
  `workspace-root` writes a second `hasTrustDialogAccepted` entry on the workspace root,
  so the harness's ancestor walk covers checkouts the-loop never spawned into;
  `scope: directory` trusts the spawn directory alone (least privilege). A root that
  does not contain the spawn directory, or one as broad as `/` or the home directory, is
  dropped and only the spawn directory is trusted. Trust is what lets a checkout's own
  `.claude/settings.json` pre-approve tool permissions and add directories, so
  pre-trusting a clone honours grants authored by anyone who can push to that repository
  — `enabled: false` is the opt-out. All honouring `CLAUDE_CONFIG_DIR`. And, **only**
  when this harness's
  `harnessArgs` already ask for bypass mode, recording the bypass-permissions
  disclaimer acceptance (`acceptBypassPermissions: auto`; `always`/`never` decide
  explicitly). Neither dialog is a permission rule, so no CLI flag —
  `--dangerously-skip-permissions` included — silences them. Writes touch only those
  keys, merge into what is already there, go through a temp file + atomic replace, are
  **skipped entirely** when the value is already correct, and are never applied to a
  file that does not parse as JSON. Applied changes emit `workspace.trusted` naming
  **every** directory that was trusted; a failure warns, emits `workspace.trust_failed`
  and still spawns. A harness with no such config surface (cursor-agent) is a silent
  no-op.
- WHEN a session is spawned or respawned THEN — in that same pre-spawn step, before any
  harness start — **the-loop's own plugin** SHALL be enabled in the harness's user
  settings file (`routing.harnessPlugins`, default on), because everything the session
  knows about the loop (the `the-loop` skill, the `/the-loop:*` commands, the
  SessionStart hook stating the operating rules) ships in the plugin and nothing else in
  the spawn path installs it. For Claude Code that means
  `extraKnownMarketplaces["the-loop"]` (from `marketplaceRepo`, default
  `MadaraUchiha-314/the-loop`) and `enabledPlugins["the-loop@the-loop"]: true` in
  `<config dir>/settings.json` — exactly what `/plugin marketplace add` +
  `/plugin install` write, honouring `CLAUDE_CONFIG_DIR`. A value that already exists is
  **never** changed: a marketplace of the operator's keeps pointing where it points, and
  an entry already set to `false` stays `false`. `marketplaceRepo` is validated as
  `owner/repo` and read only from the operator's own config, never from an event payload
  or a cloned repository. That settings file is **user-global**, so the plugin also loads
  in sessions the operator starts by hand — `enabled: false` is the opt-out. The step is
  independent of `harnessTrust` (either may be off without the other), shares its write
  discipline and its `workspace.trusted` / `workspace.trust_failed` events, and is a
  silent no-op for cursor-agent.
- A registry record SHALL carry no `runner` field (issue-156). A record with an empty
  `tmuxTarget` — one self-registered via `the-loop sessions register`, or written
  before issue-156, an old `runner: "process"` record included — SHALL be healed
  **lazily**: its next dispatched event takes the respawn path above, resuming the
  recorded conversation when possible and starting a fresh one otherwise. There is no
  migration tool, and pre-issue-156 registry files remain readable as they are.

## Design

[`docs/specs/issue-32/design.md`](../specs/issue-32/design.md) ·
[decision-021](../decisions/decision-021.md)

## Sessions that are not a work item's

Since issue-277 tmux hosts a second kind of session:
[standing sessions](standing-sessions.md), which belong to no work item and are addressed
by name (`loop-standing-<name>`). They share this runner and the harness adapters, and
nothing else: they have their own registry, their own verbs, and no path from a routed
GitHub event. Everything on this page about how a pane is spawned, pasted into,
terminated and retained applies to them; everything about *which work item* an event
belongs to does not.

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-277 | The runner learned to be addressed by **target** rather than by work item (`spawn_in`, `deliver_to`, `kill_target`, `terminate_harness_in`), so a session with no work item can be hosted the same way; the four work-item entry points delegate and keep their exact refusals. The first caller is [standing-sessions](standing-sessions.md) | [spec](../specs/issue-277/), [decision-099](../decisions/decision-099.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/277) |
| issue-240 | A read-only observer no longer blocks delivery: the submit keystroke is a second, unbracketed `paste-buffer` instead of `send-keys … Enter`, so no tmux command in the delivery resolves a client. tmux ≥ 3.7 refused `send-keys` with `client is read-only` whenever anyone was attached with `--read-only`, and `-t` could not avoid it — the guard tests the *target client*, which is resolved from `-c`/the current client | [spec](../specs/issue-240/), [webhook-triggers](webhook-triggers.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/240) |
| issue-186 | `the-loop cleanup` — a control keyword, a CLI/API/MCP verb and an authorized closure all release a finished work item's **local** resources: every endpoint's tmux session, the workspace checkout and the machine-local registry record, ignoring the two retention settings. The portable record is kept and nothing remote is touched; a closure that names no authorized actor defers to the keyword rather than destroying state on an unattributable event | [spec](../specs/issue-186/), [cli](cli.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/186) |
| issue-156 | Process runner removed; tmux is the only runner (2026-08-05): `routing.runner` left the schema (ignored with a warning), tmux became a required daemon dependency, registry records dropped their `runner` field, and a record without a `tmuxTarget` heals lazily through the respawn path on its next event | [spec](../specs/issue-156/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/156) |
| issue-154 | Fixed the tmux session name the-loop recorded and posted not being the one tmux gave the session: a slug's `.`/`:` are now rewritten to `_` (tmux's own `session_check_name`) where the name is minted and where a registry record is loaded, so the announced `tmux attach -t …` command resolves, probes stop reading a live session as absent, and `terminate_harness`'s guard rejects the target-grammar shape outright | [spec](../specs/issue-154/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/154) |
| issue-146 | Fixed a respawn colliding with the session it was replacing: an unanswered tmux probe is no longer read as "session gone", a **live** `loop-<slug>` occupant is delivered into rather than killed or spawned over, a `duplicate session` refusal is resolved once instead of recurring, and an unclearable dead occupant **skips** the event (`session-occupied`) instead of releasing it to fail identically forever | [spec](../specs/issue-146/), [decision-055](../decisions/decision-055.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/146) |
| issue-143 | The pre-spawn step now also enables the-loop's own plugin (`extraKnownMarketplaces` + `enabledPlugins` in the harness's user settings, `routing.harnessPlugins`), so a spawned session has the skill, commands and hooks the work-on prompt assumes instead of running the ticket as a plain agent; existing values are never overwritten | [spec](../specs/issue-143/), [decision-054](../decisions/decision-054.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/143) |
| issue-136 | Fixed the pre-spawn trust write missing the checkout it was for: the trust key has a second reader that does **not** walk ancestors, so the default `scope: workspace-root` left every checkout of a repo shipping `.claude/settings.json` grants on the dialog. Both keys are now written on the exact spawn directory under every scope; `scope` only widens | [spec](../specs/issue-136/), [decision-052](../decisions/decision-052.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/136) |
| issue-137 | `sessions reset` ends a live session through that same close path and then **deletes** its registry record, so the work item starts over on a fixed CLI; a tmux session retained by policy outlives the record and is read back with `tmux attach -r -t loop-<slug>` | [spec](../specs/issue-137/), [decision-050](../decisions/decision-050.md), [cli](cli.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/137) |
| issue-106 | `paused` sessions (delivery suppressed, tmux session and conversation untouched) and `sessions stop`, which ends a session through the same close path a merge takes | [spec](../specs/issue-106/), [decision-040](../decisions/decision-040.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/106) |
| issue-104 | The session-announcement comment is now marked as the-loop's own, so the poller stops pasting "the-loop started an interactive session for …" into that very session | [spec](../specs/issue-104/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/104) |
| issue-32 | Introduced the tmux runner, `sessions attach`, the ttyd web terminal and dependency preflight | [spec](../specs/issue-32/), [decision-021](../decisions/decision-021.md) |
| issue-65 | Fixed `poll start` never launching ttyd (it shared the tmux runner but had no web terminal start/stop of its own); factored ttyd lifecycle into a shared `the_loop.runner` helper used by both `gh-webhook start` and `poll start` | [issue](https://github.com/MadaraUchiha-314/the-loop/issues/65) |
| issue-80 | Respawn a crashed/killed tmux session on delivery (deliver the pending event as the fresh TUI's boot prompt) instead of looping redeliveries into a session that no longer exists | [spec](../specs/issue-80/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/80) |
| issue-93 | Events on a PR linked to a GitHub issue reuse that issue's tmux session instead of spawning a second one for the PR's own ref | [spec](../specs/issue-93/), [decision-036](../decisions/decision-036.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/93) |
| issue-90 | Pre-seed the harness's own config before every spawn/respawn so a session starts working instead of stalling on the workspace-trust dialog (and, when bypass mode is already configured, its disclaimer) | [spec](../specs/issue-90/), [decision-037](../decisions/decision-037.md) |
| issue-86 | Keep a finished work item's tmux session (and, via `remain-on-exit`, its pane) instead of killing it, guarded by a pane-liveness check so the respawn path still fires; announce a first-spawned session's attach command as a comment on the work item | [spec](../specs/issue-86/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/86) |
| issue-94 | A retained session is now a **record, not a live agent**: closing the work item ends the harness in its pane (SIGTERM→SIGKILL, `killHarnessOnClose` / `harnessKillGraceSeconds`) with `remain-on-exit` re-set so the scrollback survives, and `sessions attach` forces read-only for a closed session | [spec](../specs/issue-94/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/94) |
| issue-89 | Respawn now **resumes** the dead session's harness conversation (`claude --resume`, id kept in the registry) instead of booting a blank one, verified by a liveness probe with a fresh-conversation fallback (`resumeOnRespawn` / `resumeProbeSeconds`, `session.resume_failed`) | [spec](../specs/issue-89/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/89) |
