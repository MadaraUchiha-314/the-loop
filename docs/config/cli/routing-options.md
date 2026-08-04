---
configBase: webhooks.ghWebhook.routing
---

# Routing options

Options under `webhooks.ghWebhook.routing` — what happens to an event once it has been
accepted. This is the largest block in the CLI config, and it is shared: the
[poller](/cli/commands/poll) reuses the whole of it for dispatch, so everything here
applies to **both** ingresses.

The mental model these options configure is on [concepts](/cli/concepts). In short: an
event is matched to a work item, a work item maps to exactly one session, and a session is
resumed — or spawned, if policy allows and an authorized human has said so.

## Enabling and matching

### `enabled`

- **Type:** `boolean`
- **Default:** `false`

Default for `gh-webhook start --route / --no-route`. With routing off the receiver still
verifies, logs and drops — useful for confirming deliveries arrive before letting anything
spawn.

### `authorizedUsers`

- **Type:** `string[]`
- **Default:** `[]`
- **Related:** [Guards](/cli/concepts#guards) · [decision-023](/decisions/decision-023)

::: danger Prompt-injection guard. Required, no fallback, fails closed.
GitHub logins whose actions the-loop may act on. Comments, reviews, labels and items
authored by anyone not listed are ignored by **both** the receiver and the poller, before
dispatch.

- **REQUIRED.** There is **no** fallback to any repository's harness config. Which logins
  may drive your daemon is a property of your machine, not of a repo anyone can open a PR
  against.
- **Empty fails closed**: every human-authored event is ignored, with a warning at
  startup. Nothing runs.

Each operator runs their own instance for their own logins. CI and system events, which
carry no human instructions, still pass; and a `closed` event still auto-closes that
item's own session regardless of who closed it.
:::

### `autoExecuteLabel`

- **Type:** `string`
- **Default:** `the-loop: auto-execute`

Issue/PR label that **arms** a work item for autonomous execution. Read straight from the
webhook payload — no extra API call. Necessary but not sufficient: with
`control.requireStartCommand` left at its default (see
[execution control](#execution-control)), an armed item still waits for an explicit start.

### `spawnOnUnmatched`

- **Type:** `'never' | 'always' | 'labeled'`
- **Default:** `never`

Policy for an event that matches no registered session:

| Value | Behaviour |
|-------|-----------|
| `never` | Log and drop. Sessions must be registered by hand with [`sessions register`](/cli/commands/sessions). |
| `labeled` | Spawn only when the issue/PR carries `autoExecuteLabel`. |
| `always` | Spawn and register for any unmatched event. |

`always` widens **which** items may spawn — never **who** may start them.
`authorizedUsers` and `control` still apply.

### `defaultHarness`

- **Type:** `'claude' | 'cursor'`
- **Default:** `claude`

Harness used when spawning a session for an unmatched event.

## Execution control

`authorizedUsers` says **who** may be an input and `autoExecuteLabel` says **which** items
may run. These say **when**. A comment carrying a declared keyword is interpreted by
the-loop and is **not** forwarded to the agent.

Control parsing runs strictly *after* the self-comment marker check and *after*
`authorizedUsers`, so it never becomes a second, weaker way in. The parser recognises the
fixed vocabulary only and yields one of four commands — never text from the comment.

### `control.enabled`

- **Type:** `boolean`
- **Default:** `true`

Recognise control keywords in comments. `false` forwards every comment to the harness as
before issue-106 — and disables the start requirement with it.

### `control.requireStartCommand`

- **Type:** `boolean`
- **Default:** `true`

Makes the auto-execute label **necessary but not sufficient**. A labelled work item is
*armed*; a session spawns only once an authorized user has issued the start command for it
(by comment, or [`the-loop sessions start`](/cli/commands/sessions)).

An accepted start is **durable**: it survives a daemon restart, and a later `stop`/`pause`
disarms the item again — so a stopped work item does not re-spawn on the next event. A
start on an item that is *not* armed is refused and remembers nothing; labelling it
afterwards will not start it.

::: warning Upgrading from ≤ 0.22
With the default `true`, labelling an issue no longer starts a session on its own —
comment `the-loop start`, or run `the-loop sessions start`. Set `false` for the
old behaviour.
:::

::: warning Upgrading from ≤ 4.2 (issue-135)
The default keywords changed shape from `the-loop:<verb>-execution` to `the-loop <verb>`.
If you rely on the shipped defaults (never set `keywords` explicitly), your comment
habit changes; an explicit `keywords` override in your own config is unaffected.
:::

### `control.keywords.start`

- **Type:** `string`
- **Default:** `the-loop start`

Start (or resume) execution for the work item.

### `control.keywords.stop`

- **Type:** `string`
- **Default:** `the-loop stop`

Close the session and end its harness.

### `control.keywords.pause`

- **Type:** `string`
- **Default:** `the-loop pause`

Hold events; the session keeps its conversation.

### `control.keywords.resume`

- **Type:** `string`
- **Default:** `the-loop resume`

Deliver events again.

Keywords match as **whole tokens, case-insensitively, anywhere** in a comment body.
Setting one to an empty string disables that command. A comment carrying **two different**
keywords is refused outright — nothing executed, nothing forwarded. Commands live in
**comments**: a keyword in an issue body or a PR description is not one. Opening an issue
that already carries the label arms it, exactly like labelling an existing one.

## Process graph

### `graph.enabled`

- **Type:** `boolean`
- **Default:** `true`
- **Related:** [process-graph](/capabilities/process-graph) · [`the-loop graph`](/cli/commands/graph)

Couple dispatch to the-loop's [process graph](/capabilities/process-graph). Before this,
the ingress and the graph never met: spawning a session left the work item's graph
unentered, so the entry hooks never wrote the `loop:<phase>` labels, and an arriving
comment never reached the human gate waiting for it.

With it on, a spawn enters the graph's start node and a delivered event advances **at most
one** node boundary, carrying the event's comments to the gate's `classify-feedback`.
Best-effort by design: a graph failure is logged (`graph.link_failed`) and never costs the
delivery. `false` restores the pre-issue-113 behaviour, where the graph moves only when a
human or CI runs `the-loop graph advance`.

### `graph.specDir`

- **Type:** `string`
- **Default:** `""` (unset — each repository's own `workflow.specDir` is used)
- **Related:** [decision-044](/decisions/decision-044) · [harness config](/config/harness-config)

An **optional override**. Leave it unset: where a repository keeps its specs is that
repository's to declare, so the daemon reads `workflow.specDir` from the work item's own
checkout (defaulting to `docs/specs`) — after `_checkout_belongs_to` has proved via the
`origin` remote that the checkout really is that repository's.

That is the only thing that works here. This is **one flat value** for every watched
repository, and the daemon is meant to watch several, so two repositories with different
layouts cannot both be served by a value set here. Setting it overrides *every* watched
repository; it exists for a checkout that carries no harness config at all.

A work item with no directory under the resolved path is skipped, which is what makes the
coupling inert for repositories that keep no specs. The skip is recorded as
`graph.skipped` in [`the-loop events`](/cli/commands/events) with the resolved directory
and the reason — a work item that is labelled, armed and spawned but whose graph never
moves is answerable from the event log.

::: warning This used to default to `docs/specs` (fixed in issue-123)
And because the value reaches the graph runtime as an explicit override, that default
meant a watched repository's `workflow.specDir` was **never** honoured: a repository that
kept its specs elsewhere had its graph silently skipped while its deliveries still
counted as successful. If you set this key to work around that, unset it.
:::

## Where sessions run

### `spawnWorkdir`

- **Type:** `string`
- **Default:** `.`

Working directory for sessions spawned on unmatched events. Used **only** when
`workspace.root` is unset; with a workspace configured, each spawned session runs in its
own per-work-item checkout instead.

### `workspace.root`

- **Type:** `string`
- **Default:** `""` (workspace disabled)
- **Related:** [decision-034](/decisions/decision-034)

Path to the workspace root where repositories are checked out, e.g.
`~/.the-loop/workspace` — `~` **is** expanded here, unlike
[`state.root`](/config/cli/#state-root). When set, the dispatcher checks out each event's repository under
this root and runs the spawned session there instead of the static `spawnWorkdir` — so
concurrent work items never share a working tree. Empty (the default) disables it.

Auth is the operator's own git credentials (`gh auth setup-git`, an SSH key, a credential
helper). The daemon holds no token of its own.

### `workspace.strategy`

- **Type:** `'worktree' | 'clone'`
- **Default:** `worktree`

Checkout layout:

| Value | Layout | Trade-off |
|-------|--------|-----------|
| `worktree` | one shared clone per repo at `<root>/<host>/<owner>/<repo>`, plus one git worktree per work item under `<root>/.worktrees/…` | concurrent work items on a repo share objects — cheap |
| `clone` | one folder per work item at `<root>/.work-items/<slug>/`, holding a full clone of each repo it touches | self-contained, simpler to reason about and clean up when a work item spans several repos, at the cost of a full clone each |

### `workspace.cloneProtocol`

- **Type:** `'https' | 'ssh'`
- **Default:** `https`

Preferred clone URL scheme. `https` uses the payload's `clone_url` (or
`https://<host>/<owner>/<repo>.git`); `ssh` uses `ssh_url` (or
`git@<host>:<owner>/<repo>.git`).

### `workspace.defaultHost`

- **Type:** `string`
- **Default:** `github.com`

Host directory used when the event payload carries no `html_url` to infer it from — the
poller's leaner payloads, for instance. Set it to your enterprise domain on a GitHub
Enterprise deployment.

### `workspace.keepCheckoutOnClose`

- **Type:** `boolean`
- **Default:** `false`

Keep a work item's checkout after its PR is merged or closed, for post-mortem, instead of
removing it — the worktree under `worktree`, the work-item folder under `clone`. The
shared per-repo clone is always kept under `worktree` regardless.

### `workspace.gitBinary`

- **Type:** `string`
- **Default:** `git`

Path or name of the git binary used for clone and worktree operations.

## How sessions are hosted

### `runner`

- **Type:** `'process' | 'tmux'`
- **Default:** `process`
- **Related:** [interactive-sessions](/capabilities/interactive-sessions) · [decision-021](/decisions/decision-021)

Receiver-global choice of how spawned sessions are hosted:

- `process` — a headless one-shot subprocess.
- `tmux` — the interactive harness TUI in a named tmux session (`loop-<slug>`) a human can
  attach to, watch and type into.

### `tmux.keepSessionOnClose`

- **Type:** `boolean`
- **Default:** `true`

Leave the tmux session running when the work item's session is closed (PR merged/closed,
or `sessions close`), so the transcript stays attachable; the registry entry closes either
way. `false` restores kill-on-close.

Retained sessions **accumulate** until you kill them —
`the-loop sessions list --status closed` finds them, `sessions close --kill-tmux` ends one
— and a new spawn for the same work item **reclaims** the deterministic `loop-<slug>` name,
clearing whatever was retained under it.

### `tmux.remainOnExit`

- **Type:** `boolean`
- **Default:** `true`

Set tmux's `remain-on-exit` on spawned sessions, so the pane and its scrollback survive the
harness process exiting. Best-effort: an older tmux that rejects it only warns. Events
delivered to a session whose pane has died still trigger a respawn — a dead pane never
silently swallows an event.

### `tmux.resumeOnRespawn`

- **Type:** `boolean`
- **Default:** `true`

When a dead tmux session is respawned, continue the **same** harness conversation
(`claude --resume <recorded id>`) instead of booting a blank one, so the agent keeps what
it knew about the work item. The registry keeps that id, so repeated crashes converge on
one conversation.

Anything doubtful falls back to a fresh conversation and says so — `session.resume_failed`
in [`the-loop events`](/cli/commands/events), plus `resumed: false` on
`session.respawned`. Doubtful means: the harness has no interactive resume (anything but
Claude Code today), the recorded id is missing or malformed, tmux failed, or the resumed
harness exited immediately, which is what an unresumable id looks like.

### `tmux.resumeProbeSeconds`

- **Type:** `number`
- **Default:** `2`

How long a resume waits before checking the harness is still running. `tmux new-session -d`
succeeds the moment the pane forks, while a harness that cannot resume exits in a fraction
of a second — without the probe such a respawn would report success forever while events
went nowhere. `0` checks immediately.

### `tmux.killHarnessOnClose`

- **Type:** `boolean`
- **Default:** `true`

When the work item closes and its tmux session is **kept**, end the harness process inside
it — so the retained pane is a *record* of what happened, not a live TUI a stray keystroke
or paste could resume. SIGTERM, escalating to SIGKILL; `remain-on-exit` is re-set first so
the scrollback survives the process.

### `tmux.harnessKillGraceSeconds`

- **Type:** `number`
- **Default:** `5`

How long the harness gets to exit after SIGTERM before SIGKILL. `0` escalates immediately.

### `webTerminal.enabled`

- **Type:** `boolean`
- **Default:** `false`
- **Related:** [decision-021](/decisions/decision-021)

Serve the tmux sessions over HTTP via [ttyd](https://github.com/tsl0922/ttyd), verified at
receiver start. Applies to `runner: tmux` only.

::: danger ttyd has no authentication of its own
Access control is entirely environmental — localhost, a VPN, or your hosting provider's
network. A browser terminal onto a tmux session is a shell on your machine. Leave this off
unless you have deliberately put something in front of it.
:::

### `webTerminal.host`

- **Type:** `string`
- **Default:** `127.0.0.1`

Interface/IP ttyd binds. Keep `127.0.0.1` unless the network layer protects wider exposure.

### `webTerminal.port`

- **Type:** `integer` (1–65535)
- **Default:** `7681`

ttyd listen port.

## Invoking the harness

### `harnessArgs.claude`

- **Type:** `string[]`
- **Default:** `[]`

Extra CLI args passed to Claude Code, e.g. `["--permission-mode", "acceptEdits"]`. The
dispatcher never widens permissions itself — whatever you put here is exactly what is
passed.

### `harnessArgs.cursor`

- **Type:** `string[]`
- **Default:** `[]`

Extra CLI args passed to `cursor-agent`, e.g. `["--force"]`.

### `promptTemplate`

- **Type:** `string`
- **Default:** `skills/the-loop/templates/webhook-event-prompt.md`

`string.Template` rendered into the prompt that **resumes** a session. This is the-loop's
internal template; the dispatcher falls back to a built-in default when the path is absent,
which is the normal case in a project repository that does not carry the-loop's templates.
Set a repo-relative path to override.

### `spawnPromptTemplate`

- **Type:** `string`
- **Default:** `skills/the-loop/templates/webhook-autoexecute-prompt.md`

`string.Template` rendered into the prompt for a **newly spawned** (auto-execute) session —
it kicks off the `work-on` flow. Same fallback behaviour as `promptTemplate`.

### `interaction.mode`

- **Type:** `string` (`work-item` | `cli`)
- **Default:** `work-item`
- **Related:** [decision-051](/decisions/decision-051) ·
  [webhook-triggers](/capabilities/webhook-triggers)

Where a session the daemon drives takes its **answers** from. Before this existed, a
spawned session was never told whether a human was at its terminal, so the model guessed —
and both guesses fail. A `process`-runner session asking interactively asks into a pipe
nobody reads; an operator sitting in an attached tmux pane gets round-tripped through
GitHub for no reason.

| Mode | The agent asks… | Still records the decision on the ticket? |
|------|-----------------|------------------------------------------|
| `work-item` (default) | as a comment on the issue/PR, then **waits** — the reply arrives as the next event | yes (it *is* the comment) |
| `cli` | interactively, in its own session | yes — the outcome, as a comment |

The resolved mode reaches the agent through the `$interaction_directive` placeholder in
[`promptTemplate`](#prompttemplate) / [`spawnPromptTemplate`](#spawnprompttemplate). A
custom template that omits the placeholder gets the directive **appended** rather than
dropped, so the rule cannot be lost to a template edit. The mode also appears on
`session.spawned` in [`the-loop events`](/cli/commands/events).

::: tip Why the default is `work-item`
A tmux session is *attachable*, not *attended* — the-loop announces the `tmux attach`
command precisely because nobody is there yet. So the default is the channel that reaches
a human who was not watching. An unrecognised value resolves to `work-item` with a warning,
never to `cli`: a wrong `work-item` leaves a visible comment awaiting a reply, a wrong `cli`
leaves a question in a void.

Setting `cli` while [`runner`](#runner) is `process` warns at startup and on reload: a
headless one-shot session has no terminal for a human to answer in. A warning, not a
refusal — your declaration stands.
:::

Independent of the mode, iteration on a **generated artifact** (`brainstorm.md`,
`requirements.md`/`bugfix.md`, `design.md`, `tasks.md`) always happens in pull-request
review. That is an invariant of the loop rather than a setting — see the skill's
`reference/collaboration.md`.

### `harnessTrust.enabled`

- **Type:** `boolean`
- **Default:** `true`
- **Related:** [decision-036](/decisions/decision-036)

Pre-seed the harness's own config before each spawn so the session starts working instead
of stopping on an interactive dialog.

Claude Code's **workspace-trust** dialog ("Do you trust the files in this folder?") and its
one-time **bypass-permissions disclaimer** are not permission *rules*, which is why no CLI
flag — `--dangerously-skip-permissions` very much included — silences them. And since every
work item gets its own checkout, every spawn lands in a directory the harness has never
seen. The result was a daemon that looked healthy (`session.spawned` logged, prompt pasted)
while the TUI sat on a modal nobody was there to answer.

So before each spawn the-loop writes exactly what the harness is about to ask for:
`hasTrustDialogAccepted` (scope below), `hasCompletedProjectOnboarding` on the spawn
directory always, and `skipDangerousModePermissionPrompt` only per
`acceptBypassPermissions`.

The writes are deliberately narrow: those keys only, merged into what is already there,
temp file plus atomic rename, `0600` on files it creates, **nothing written at all** when
the value is already correct, and a file that does not parse as JSON is reported and left
alone. Every applied change is auditable with `the-loop events --type 'workspace.trust*'`.
Failures are best-effort — a warning, a `workspace.trust_failed` record, and the spawn
still happens. `cursor-agent` has no such config surface, so it is a silent no-op there.

`false` leaves your harness config untouched.

### `harnessTrust.scope`

- **Type:** `'workspace-root' | 'directory'`
- **Default:** `workspace-root`

How wide the trust entry goes.

- `workspace-root` writes **one** entry on `workspace.root`. The harness's trust lookup
  walks **up** from the cwd, so every checkout beneath the root is covered — including
  folders the-loop never spawned into (a repo you clone there by hand, a nested repo the
  agent walks into).
- `directory` writes trust on the exact spawn directory only — least privilege, one entry
  per work item. Use it when the workspace root holds more than the-loop's own checkouts.

Onboarding is written per spawn directory under **either** scope, because
`hasCompletedProjectOnboarding` is read from the exact project key with no ancestor walk —
otherwise root trust would silence the trust dialog and leave the onboarding screen behind
it in every fresh checkout.

Safety rails on `workspace-root`: a root that does not actually contain the spawn directory
is ignored, and a root broad enough to be meaningless (`/`, or your home directory itself)
degrades to per-directory trust with a warning. With no workspace root configured, the two
scopes behave identically.

### `harnessTrust.acceptBypassPermissions`

- **Type:** `'auto' | 'always' | 'never'`
- **Default:** `auto`

Whether to also record the one-time bypass-permissions disclaimer acceptance
(`skipDangerousModePermissionPrompt`, plus the legacy `bypassPermissionsModeAccepted` for
older builds). Without it, a session configured for bypass mode is prompted, or silently
downgraded to `default`.

- `auto` records it **only** when this harness's `harnessArgs` already ask for bypass mode
  (`--dangerously-skip-permissions` or `--permission-mode bypassPermissions`) — the-loop
  never widens permissions you did not request.
- `always` records it regardless; `never` never does.

::: warning This one is user-global, and the asymmetry is worth a conscious decision
The trust key is **per directory**, but `skipDangerousModePermissionPrompt` is a
**user-global** setting. Accepting it removes the bypass-mode confirmation from *every*
Claude Code session on that account — interactive ones you start by hand included, not just
the ones the-loop spawns.

That is the only form the harness exposes. If you would rather keep the confirmation on
your own sessions, set `never` and drop `--dangerously-skip-permissions` from
`harnessArgs`; a narrower `--permission-mode acceptEdits` needs no acceptance at all.
:::

## Feedback on the ticket

### `reactions.enabled`

- **Type:** `boolean`
- **Default:** `true`

Dispatch-lifecycle emoji reactions on the triggering GitHub entity. When the dispatcher
picks an event up it reacts with `started` on the comment that triggered it — or on the
issue/PR itself for presence, label and review events — then adds `completed` or `error`
from the outcome. So a human watching the thread can see the-loop working before any reply
comment exists.

Best-effort by design: reactions post through your own `gh` CLI (the daemon holds no
token), a reaction failure never affects the dispatch, and a missing `gh`, a non-GitHub
provider or an event with no reactable target is a silent no-op. Shared by the receiver and
the poller, and hot-reloaded with the rest of `routing`.

Reacting is the daemon's one **write** to GitHub, and it is reaction-only — no text. Set
`false` to opt out.

### `reactions.started`

- **Type:** palette name, or `""`
- **Default:** `eyes` (👀)

Reaction added when the event is dequeued for delivery or spawn. `""` skips this state.

### `reactions.completed`

- **Type:** palette name, or `""`
- **Default:** `hooray` (🎉)

Reaction added when the dispatch succeeds. `""` skips this state.

### `reactions.error`

- **Type:** palette name, or `""`
- **Default:** `confused` (😕)

Reaction added when the dispatch fails or the worker crashes. `""` skips this state.

GitHub's reaction palette is fixed — `+1`, `-1`, `laugh`, `confused`, `heart`, `hooray`,
`rocket`, `eyes`. There is no ✅ and no ⁉️, so the defaults are the closest supported match.

### `announce.enabled`

- **Type:** `boolean`
- **Default:** `true`

When a tmux-mode session is spawned for a work item, comment on it with the tmux session
name and the `tmux attach -t loop-<slug>` command, so the humans reading the ticket can
watch it work without digging through daemon logs.

A **respawn** posts nothing further — it reuses the same session name, so the comment
already there stays correct and a flapping session cannot bury the thread.

Best-effort via your own `gh` CLI, like reactions: a failure never affects the dispatch,
and a process-runner session, a non-GitHub work item or a missing `gh` is a no-op. The body
is built only from registry fields — work-item ref, tmux target, harness — never from event
payloads, and carries no filesystem paths, harness session ids or hostnames.

This posts **text** to GitHub with your own `gh` auth. Set `false` to opt out.

## Registry and throughput

### `registryDir`

- **Type:** `string`
- **Default:** `<state.root>/local`

Directory of per-session registry JSON files — the machine-**local** half of a work item's
state (a harness conversation id, its `cwd`, its tmux target). Unset resolves under
[`state.root`](/config/cli/#state-root) — with the default root, `.the-loop/local`.

Never track it in git. A copied session record is still counted *live*, so the
duplicate-session guard would refuse the spawn the other machine needs
([decision-046](/decisions/decision-046)). The portable half — what was armed, what has
been seen — lives in `<state.root>/portable/` and does not move with this setting; see
[State on disk](/cli/state).

### `maxConcurrentDispatches`

- **Type:** `integer`
- **Default:** `4`

Cap on harness dispatches running in parallel. Dispatch *within* a session is always
serialized — one event at a time per session, in parallel across sessions.

### `dedupCacheSize`

- **Type:** `integer`
- **Default:** `1024`

Bounded LRU of `X-GitHub-Delivery` ids, giving at-most-once processing across GitHub's
redeliveries.

### `dispatchTimeoutSeconds`

- **Type:** `integer`
- **Default:** `1800`

Timeout for a single harness resume/spawn subprocess.

## Hot reload

While the receiver runs, edits to `routing` and `events` are picked up on the **next
received event** — no restart. The soft policy swaps live: the events filter, the label,
the spawn policy, harness and runner, per-harness args, prompt templates, the interaction
mode. The dedup cache,
the per-session queues and the registry are preserved.

These still need a restart, because they are infrastructural:
[`host`](/config/cli/webhook-options#host), [`port`](/config/cli/webhook-options#port),
[`path`](/config/cli/webhook-options#path),
[`secretEnv`](/config/cli/webhook-options#secretenv), `maxConcurrentDispatches`,
`dedupCacheSize`, `registryDir`, `webTerminal`.

An invalid edit is logged and the previous config kept.

## Next

- [Polling options](/config/cli/polling-options) — the pull-based ingress that reuses all
  of the above.
- [Concepts](/cli/concepts) — the model these options configure.
