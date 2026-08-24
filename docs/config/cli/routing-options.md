---
configBase: routing
---

# Routing options

Options under the top-level `routing` key — what happens to an event once it has been
accepted. This is the largest block in the CLI config, and it is shared: the
[poller](/config/cli/polling-options) reuses the whole of it for dispatch, so everything here
applies to **both** ingresses.

::: warning Moved in issue-142
This block used to be nested under `routing`, which read as though it
were the receiver's — it never was. A config still declaring the old path is **refused**
rather than silently ignored, because `authorizedUsers` decides which logins may drive
your daemon. Run [`the-loop migrate-config`](/cli/commands/migrate-config) (or
`/the-loop:upgrade-the-loop`) to move it.
:::

The mental model these options configure is on [concepts](/cli/concepts). In short: an
event is matched to a work item, a work item maps to exactly one session, and a session is
resumed — or spawned, if policy allows and an authorized human has said so.

## Enabling and matching

### `enabled`

- **Type:** `boolean`
- **Default:** `false`

Whether the receiver dispatches at all. With routing off it still
verifies, logs and drops — useful for confirming deliveries arrive before letting anything
spawn.

### `authorizedUsers`

- **Type:** `string[]`
- **Default:** `[]`
- **Related:** [Guards](/cli/concepts#guards) · [decision-023](/decisions/decision-023)

::: danger Prompt-injection guard. Required, no fallback, fails closed.
GitHub logins whose actions the-loop may act on. A comment, review or label from anyone not
listed is ignored by **both** the receiver and the poller, before dispatch — judged by the
author of the action itself, so who opened the issue or PR it sits on is irrelevant.

- **REQUIRED.** There is **no** fallback to any repository's harness config. Which logins
  may drive your daemon is a property of your machine, not of a repo anyone can open a PR
  against.
- **Empty fails closed**: every human-authored event is ignored, with a warning at
  startup. Nothing runs.

Each operator runs their own instance for their own logins. CI and system events, which
carry no human instructions, still pass; and a `closed` event still auto-closes that
item's own session regardless of who closed it. Who closed it does decide one thing:
whether that closure also [cleans up](#controlkeywordscleanup) the item's local
resources, which only an authorized closer may cause.

**One decision does look at the work item's author, and only on the poll ingress:** whether
the poller starts work on a labelled item *by itself*. A listing carries the item's labels
but not who applied them, so an item opened by an unlisted login waits until an authorized
user arms it (`the-loop start` / `the-loop contribute`, or `the-loop sessions start`) — and
their comment gets through whoever opened the item.
[decision-074](/decisions/decision-074).
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
fixed vocabulary only and yields one of the declared commands — never text from the
comment.

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

### `control.keywords.execute`

- **Type:** `string`
- **Default:** `the-loop execute`

Answers the graph's [`phase-selection`](/capabilities/process-graph) gate
([issue-177](https://github.com/MadaraUchiha-314/the-loop/issues/177)): the authorized
user has chosen which phases this work item needs, so **freeze that selection and start
walking**. The tick state of the-loop's checklist comment at that moment is what gets
frozen — a checklist inside the execute comment itself wins over it.

Different in kind from the session commands, and worth knowing why: `execute` never
touches the session registry — it neither arms nor disarms anything — and the comment
carrying it is still **delivered**, because the gate's own exit chain is what reads the
selection. The authorization is identical: a named, allowlisted human, checked before
anything happens.

### `control.keywords.contribute`

- **Type:** `string`
- **Default:** `the-loop contribute`

Arms the work item exactly as `start` does — same spawn policy, same durable record,
same named-actor authorization — and additionally selects the **contribution loop**
(`pdlc-contribution-loop`,
[issue-185](https://github.com/MadaraUchiha-314/the-loop/issues/185)) for its outer
walk: the-loop joins an **existing, in-progress** issue or PR as a contributor rather
than owning it from scratch.

That loop refuses to begin until an authorized user has stated a **goal and success
criteria** — a `Goal:` line plus a `Success criteria:` bullet list, in one comment; the
comment carrying this keyword qualifies, so stating both there costs no extra round
trip. The criteria become the intervention's definition of done: its verification gate
holds until every one is met. See the
[process graph](/capabilities/process-graph) capability for the loop's phases.

### `control.keywords.do`

- **Type:** `string`
- **Default:** `the-loop do`

`contribute`'s sibling one loop over. Arms the work item exactly as `start` does — same
spawn policy, same durable record, same named-actor authorization — and additionally
selects the **ad-hoc loop** (`pdlc-adhoc-loop`,
[issue-225](https://github.com/MadaraUchiha-314/the-loop/issues/225)) for its outer
walk: a tactical task that runs **no PDLC process at all**.

That loop has three nodes — `work`, `review`, `complete` — and no spec chain, no
`goal-definition` gate, no phase-selection gate, no artifact gates and no review chain.
the-loop does the work, reports back on the thread, and treats **any** authorized reply
that is not a declaration of completion as more work, routing straight back to `work`.
The item ends when the requester says it is done, or when they close it.

:::note Typing this word is the declaration
There is no separate setting that turns the process off for a work item. The keyword
*is* the decision, and it is recorded like every other one — in the portable control
record, then in `graph-state.json`'s `loop` field — so a reviewer of the resulting
change can see that no review chain ran, and who decided that. Set this option to an
empty string to remove the word from the vocabulary entirely.
:::

See the [process graph](/capabilities/process-graph) capability for the loop's shape and
what it deliberately omits.

### `control.keywords.review`

- **Type:** `string`
- **Default:** `the-loop review`

The same shape a third time — arms exactly as `start` does, same spawn policy, same
durable record, same named-actor authorization — and additionally selects the **review
loop** (`pdlc-review-loop`,
[issue-279](https://github.com/MadaraUchiha-314/the-loop/issues/279)): the-loop becomes
the **reviewer** of the thread it was typed on, never its author.

Typed on a pull request, the review binds to the **pull request itself**, even when the
PR links a ticket — the subject of a review is the change, where every other keyword's
subject is the work item delivering one. Typed on a **work item**, one review
conversation spans every pull request delivering it: the fill-in template additionally
asks which pull requests are in scope, pre-filled with the ones the-loop detects from
its own `pr-loops/` state and the work item's linked pull requests. The loop refuses to
begin until an authorized user states a **review brief** — `Questions:` / `Angles:` /
`Validations:` bullet lists,
at least one section, in one comment; the comment carrying this keyword qualifies, and
otherwise the-loop posts the fill-in template and waits. Each round answers the frozen
brief and lands as one comment on the thread; **any** authorized reply that is not a
declaration of completion is another round. The review session changes **no code**: it
commits nothing, pushes nothing and opens no pull request — a finding worth fixing is a
new work item.

Set this option to an empty string to remove the word from the vocabulary entirely. See
the [process graph](/capabilities/process-graph) capability for the loop's shape.

### `control.keywords.cleanup`

- **Type:** `string`
- **Default:** `the-loop cleanup`

The other end of the life cycle
([issue-186](https://github.com/MadaraUchiha-314/the-loop/issues/186)): release the
**local** resources this work item accumulated on the machine running the-loop.

:::danger Destructive, and deliberately unconditional
Cleanup kills the tmux session of **every** endpoint (the work item's own, plus one per
pull request delivering it), removes the workspace checkout — **uncommitted work in it is
gone** — and deletes the machine-local session record. It ignores
[`tmux.keepSessionOnClose`](#tmuxkeepsessiononclose) and
[`workspace.keepCheckoutOnClose`](#workspacekeepcheckoutonclose): those answer "what
should survive the end of the work", and a retention default that silently made this a
no-op would be a verb that lies.
:::

What it does **not** touch: the portable record (`control`, `poll`, and the frozen
graph — that is persistence and tracking, not a resource), the shared per-repository
clone, the checked-in spec tree, the event log, and anything remote. No branch, pull
request, issue or label is changed.

It works **retroactively** on anything the-loop ever tracked, with or without a live
session — a checkout left behind by a crash is reclaimed from the work-item ref alone —
and it durably **disarms** the item, like `stop`, so nothing re-spawns afterwards. The
work item's graph pointer moves to the terminal `cleanup` node first, so the teardown is
a recorded transition with a `loop:cleanup` label rather than a silent side effect.

Closing the work item does this on its own **when the close event names an authorized
actor**. When it names none — a bot, an automation, or a ticketing system whose close
action carries no identity — the-loop closes the session, defers the cleanup and records
why; this keyword is the remedy, and it is exactly why it exists.

That split falls along the ingress. A **webhook** `closed` event carries `sender`, so a
closure by an authorized user cleans up by itself. A closure the **poller** detects is
reconstructed from the item's state and names nobody — so on a polling deployment every
closure defers, and this keyword is how cleanup happens.

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

### `graph.repoHooks`

- **Type:** `boolean`
- **Default:** `true`
- **Related:** [process-graph](/capabilities/process-graph) · [harness config](/config/harness-config) · [decision-096](/decisions/decision-096)

Whether this machine runs the **watched repositories' own graph hooks**. A repository
declares them under `graph.hooks` in its harness config, and that declaration is the opt-in:
a repository that declares none is unaffected whichever way this is set.

Left `true`, the-loop imports the modules a repository names and runs them at the boundaries
it named. **Those modules execute inside the-loop's own process, with its environment** — so
adopting a repository's hooks is adopting its code, the same statement `reviews.critics[]`
already carries for the critics a repository declares.

Set `false` to refuse the mechanism machine-wide. Nothing from any repository is imported,
and a repository that declared hooks is named in a warning rather than quietly losing its
gates — an absent gate somebody asked for is worse than a loud refusal.

```bash
# what a repository would run, without importing any of it
the-loop graph --repo /srv/checkouts/app hooks
```

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

Every spawned session is hosted as the interactive harness TUI in a named tmux session
(`loop-<slug>`) a human can attach to, watch and type into — see
[interactive-sessions](/capabilities/interactive-sessions). There is no runner choice: the
headless `process` runner was removed (issue-156, [decision-056](/decisions/decision-056)),
and a leftover `runner` key in the config is ignored with a startup warning. `tmux` is
therefore a required dependency of both ingress daemons.

### `tmux.keepSessionOnClose`

- **Type:** `boolean`
- **Default:** `true`

Leave the tmux session running when the work item's session is closed (PR merged/closed,
or `sessions close`), so the transcript stays attachable; the registry entry closes either
way. `false` restores kill-on-close.

Retained sessions **accumulate** until you kill them —
`the-loop sessions list --status closed` finds them, `sessions close --kill-tmux` ends one
— and a new spawn for the same work item **reclaims** the deterministic `loop-<slug>` name,
clearing whatever was retained under it. "Retained" means its harness has exited, which
the default `killHarnessOnClose: true` guarantees; a session whose harness is **still
running** is never reclaimed silently (issue-146). On the respawn path the pending event
is delivered into it instead (`session.respawn_averted`); on a from-scratch spawn, which
has no registered session to deliver into, the spawn fails with the remedy in the log —
`tmux kill-session -t loop-<slug>`, or `the-loop sessions reset --work-item <ref>`.

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

So a tmux session that was killed while the-loop still considered it active is recovered
on the next event *with its conversation intact*: a fresh `loop-<slug>` session running
`claude --resume <the recorded id>`, in the session's recorded cwd.

Anything doubtful falls back to a fresh conversation and says so — `session.resume_failed`
in [`the-loop events`](/cli/commands/events), plus `resumed: false` on
`session.respawned`. Doubtful means: the harness has no interactive resume (anything but
Claude Code today), the recorded id is missing or malformed, tmux failed, or the resumed
harness exited immediately, which is what an unresumable id looks like. A tmux session
already **holding** the name is not doubt about the conversation and is not reported as
such — it is handled by the occupancy rules under `tmux.keepSessionOnClose` above.

### `tmux.resumeProbeSeconds`

- **Type:** `number`
- **Default:** `2`

How long a resume waits before checking the harness is still running. `tmux new-session -d`
succeeds the moment the pane forks, while a harness that cannot resume exits in a fraction
of a second — without the probe such a respawn would report success forever while events
went nowhere. `0` checks immediately. A probe tmux is too busy to answer counts as **live**,
so a loaded server no longer discards a resume that in fact took (issue-146).

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

### `tmux.sessionPerPr`

- **Type:** `string` (`never` · `cross-repository` · `always`) — the legacy booleans still parse
- **Default:** `cross-repository`
- **Related:** [decision-064](/decisions/decision-064), [decision-088](/decisions/decision-088), [decision-092](/decisions/decision-092), [decision-093](/decisions/decision-093)

How many tmux+claude sessions a work item's pull requests get. A pull request that gets one
is recorded on the work item's single session record (`sessions list --format json` shows
them under `pullRequests`), spawned lazily by the first event that needs it, and announced
on the work item like any other spawn.

::: tip This is the **default**, not the verdict (issue-260)
Each work item states its own answer at `phase-selection` — three checklist rows,
`pr-sessions-never` / `pr-sessions-cross-repository` / `pr-sessions-always`, with the value
you set here already ticked. An authorized `the-loop execute` freezes the choice into that
work item's portable record, and routing reads it there first; this key answers for every
work item that left the rows alone, and for every work item started before the question
existed. One repository has both a one-repo bugfix and a three-repo migration, and they can
now differ. See [decision-093](/decisions/decision-093).
:::

| Value | A pull request in the work item's own repository | A pull request in another repository |
|---|---|---|
| `never` | the work item's session | the work item's session |
| `cross-repository` *(default)* | the work item's session | its own session |
| `always` | its own session | its own session |

- **`never`** is the pre-issue-172 shape: one work item, one conversation, whatever opens
  against it.
- **`cross-repository`** splits off the case the inner loop was built for (issue-183) — a
  contribution this work item makes elsewhere, which has a repository of its own to work in.
  A pull request in the work item's *own* repository is that work item's delivery: same
  branch, same checkout, and under `outer-loop-on-pull-request` the same conversation the
  work item's session is already holding on it.
- **`always`** is a conversation per pull request anyway (issue-258). Read the box below
  before setting it — as a default, or as a work item's own selection.

::: warning `always` needs a checkout per pull request — in practice `strategy: clone`
An endpoint gets a conversation only when it gets a **working tree of its own**
([decision-088](/decisions/decision-088) D2), in every mode. That rule is not relaxed by
`always`, because relaxing it is exactly the [#253](https://github.com/MadaraUchiha-314/the-loop/issues/253)
defect: two harness conversations on one branch, no lock, interleaved commits and duplicated
verification.

Under [`workspace.strategy: worktree`](#workspacestrategy) the work item's own session holds
the pull request's branch, and **two worktrees of one clone cannot both check out one
branch** — that is git, not policy. So a same-repository endpoint declines under `worktree`
and is served under [`clone`](#workspacestrategy), where it gets an independent clone that
really is on the pull request's code.

A decline is not a lost event: it is delivered into the work item's session and recorded as
`session.pr_session_declined`. If you set `always` and see one session, `the-loop events`
says which of `no-separate-checkout`, `workspace-failed` or `shared-worktree` it was.
:::

A cross-repository endpoint has the same requirement, and it is why
[`workspace.root`](#workspaceroot) must be set for any mode but `never` to produce a second
session at all.

A PR closing (merged or not) ends only **that PR's** session, through the same
`keepSessionOnClose`/`killHarnessOnClose` rules as any close; the work item's session
keeps running until the item itself ends. This is issue-101's several-PRs rule expressed
in the model rather than special-cased.

In every mode, *which* work item owns a PR's events is read from the session record, never
re-derived from GitHub on each event — and *how many conversations* those events are spread
across is read from the work item's own frozen selection, falling back to this key.

::: tip Upgrading from the boolean
`true` and `false` still validate and still mean what they mean today — `true` is
`cross-repository`, `false` is `never`. Nothing changes on upgrade unless you edit the file.
A value that is neither a boolean nor one of the three names resolves to `cross-repository`
with a warning, never to `always`.
:::

### `webTerminal.enabled`

- **Type:** `boolean`
- **Default:** `false`
- **Related:** [decision-021](/decisions/decision-021)

Serve the tmux sessions over HTTP via [ttyd](https://github.com/tsl0922/ttyd), verified at
receiver start.

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

The placeholders a template may declare:

| Placeholder | What it renders |
|---|---|
| `$work_item` | The work item's ref, e.g. `github:octo/repo#15` |
| `$event` / `$action` | The GitHub event name and its action |
| `$repository` | `owner/repo` |
| `$delivery_id` | The delivery id, for tracing against [`the-loop events`](/cli/commands/events) |
| `$interaction_directive` | Where this session takes its answers from — see [`interaction.mode`](#interactionmode). **Appended** if the template omits it |
| `$graph_context` | Where the item stands in the process graph; empty when there is no context |
| `$payload_excerpt` | What happened, distilled |

`$payload_excerpt` is **not** the raw webhook payload. Since issue-243 it is a field
allow-list per event: a comment renders as its body, its `html_url` and its author's
login — no `sender`, no `issue` object, no `api.github.com` URLs — an inline review
comment adds its `path` and `line` ahead of the body, and lifecycle and CI events keep
their number/title/state and name/status/conclusion. Free text is capped **per field**, so
a pasted 10 KB log costs its own tail and never the comment's URL, and the block is always
parseable JSON. The full payload is still what routing, `authorizedUsers`, control
keywords and reactions judge by — the distillation is what the *agent reads*. See
[webhook-triggers](/capabilities/webhook-triggers) for the per-event table.

### `spawnPromptTemplate`

- **Type:** `string`
- **Default:** `skills/the-loop/templates/webhook-autoexecute-prompt.md`

`string.Template` rendered into the prompt for a **newly spawned** (auto-execute) session —
it kicks off the `work-on` flow. Same fallback behaviour as `promptTemplate`.

### `interaction.mode`

- **Type:** `string` (`work-item` | `cli`)
- **Default:** `work-item`
- **Related:** [decision-052](/decisions/decision-052) ·
  [webhook-triggers](/capabilities/webhook-triggers)

Where a session the daemon drives takes its **answers** from. Before this existed, a
spawned session was never told whether a human was at its terminal, so the model guessed —
and both guesses fail. A session asking interactively when nobody ever attaches to its
tmux pane asks into a void; an operator sitting in an attached pane gets round-tripped
through GitHub for no reason.

| Mode | The agent asks… | Still records the decision on the ticket? |
|------|-----------------|------------------------------------------|
| `work-item` (default) | as a comment on the issue/PR — via [`the-loop ask`](/cli/commands/ask), which stamps the loop-prevention marker centrally and records the wait as `session.awaiting_input` — then **waits**: the reply arrives as the next event, or straight into the pane via `POST /api/v1/sessions/reply` | yes (it *is* the comment) |
| `cli` | interactively, in its own session | yes — the outcome, as a comment |

Like every option on this page, it is **not webhook-only**: the poller reads the same
`routing` block verbatim, so one declaration governs both ingresses.

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
:::

Independent of the mode, iteration on a **generated artifact** (`brainstorm.md`,
`requirements.md`/`bugfix.md`, `design.md`, `tasks.md`) always happens in pull-request
review. That is an invariant of the loop rather than a setting — see the skill's
`reference/collaboration.md`.

### `harnessTrust.enabled`

- **Type:** `boolean`
- **Default:** `true`
- **Related:** [decision-036](/decisions/decision-036), [decision-052](/decisions/decision-052)

Pre-seed the harness's own config before each spawn so the session starts working instead
of stopping on an interactive dialog.

Claude Code's **workspace-trust** dialog ("Accessing workspace: … Yes, I trust this
folder") and its one-time **bypass-permissions disclaimer** are not permission *rules*,
which is why no CLI flag — `--dangerously-skip-permissions` very much included — silences
them. And since every work item gets its own checkout, every spawn lands in a directory the
harness has never seen. The result was a daemon that looked healthy (`session.spawned`
logged, prompt pasted) while the TUI sat on a modal nobody was there to answer.

So before each spawn the-loop writes exactly what the harness is about to ask for, on the
**exact spawn directory**: `hasTrustDialogAccepted` and `hasCompletedProjectOnboarding`
(plus a wider entry per `harnessTrust.scope` below), and
`skipDangerousModePermissionPrompt` only per `acceptBypassPermissions`.

The writes are deliberately narrow: those keys only, merged into what is already there,
temp file plus atomic rename, `0600` on files it creates, **nothing written at all** when
the value is already correct, and a file that does not parse as JSON is reported and left
alone. Every applied change is auditable with `the-loop events --type 'workspace.trust*'`.
Failures are best-effort — a warning, a `workspace.trust_failed` record, and the spawn
still happens. `cursor-agent` has no such config surface, so it is a silent no-op there.

::: warning Know what "trusted" buys the checkout
Workspace trust is what lets a repository's **own** `.claude/settings.json` pre-approve
tool permissions and add directories to the workspace. Pre-trusting a clone therefore
honours grants authored by anyone who can push to that repository — the same thing you
would be agreeing to by answering the dialog by hand. `enabled: false` is the opt-out; it
brings the dialog back.
:::

### `harnessTrust.scope`

- **Type:** `'workspace-root' | 'directory'`
- **Default:** `workspace-root`

Whether trust **additionally** widens to an ancestor. The spawn directory itself is
trusted either way — that is not the choice here.

- `workspace-root` writes a **second** entry on `workspace.root`. The harness's base trust
  check walks **up** from the cwd, so every checkout beneath the root is covered —
  including folders the-loop never spawned into (a repo you clone there by hand, a nested
  repo the agent walks into).
- `directory` keeps trust on the exact spawn directory only — least privilege, one entry
  per work item. Use it when the workspace root holds more than the-loop's own checkouts.

::: tip Why the spawn directory is always written
`hasTrustDialogAccepted` has **two** readers in the harness and only one of them walks up.
The other reads the **exact** project key with no walk, and it is the one that decides
whether the dialog appears *anyway* — and whether the repo's own `permissions.allow` /
`additionalDirectories` load at all. Trusting only the root left every checkout of a repo
that ships `.claude/settings.json` grants sitting on the dialog, with its grants dropped
(`Ignoring N permissions.allow entries … this workspace has not been trusted`).
`hasCompletedProjectOnboarding` has no ancestor walk either, or root trust would silence
the dialog and reveal the onboarding screen behind it. See
[decision-052](/decisions/decision-052).
:::

Safety rails on `workspace-root`: a root that does not actually contain the spawn directory
is dropped, and a root broad enough to be meaningless (`/`, or your home directory itself)
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

### `harnessPlugins.enabled`

- **Type:** `boolean`
- **Default:** `true`
- **Related:** [decision-054](/decisions/decision-054)

Enable the-loop's **own plugin** in the harness before each spawn, so the session actually
has the loop.

Everything a spawned session knows about the loop ships in the plugin: the `the-loop`
skill, the `/the-loop:*` commands, and the SessionStart hook that states the operating
rules. Nothing else in the spawn path installs it — the-loop pre-seeded workspace trust so
the session *starts*, then handed it a work-on prompt for machinery that was not loaded. On
a machine where nobody ran `/plugin marketplace add` by hand, the session worked the ticket
as a plain agent: no phase labels, no spec chain, no gates.

So before each spawn the-loop writes what the harness reads, into the **user settings
file** (`<config dir>/settings.json`, honouring `CLAUDE_CONFIG_DIR`) — exactly what
`/plugin marketplace add` + `/plugin install` write:

```json
{
  "extraKnownMarketplaces": {
    "the-loop": { "source": { "source": "github", "repo": "MadaraUchiha-314/the-loop" } }
  },
  "enabledPlugins": { "the-loop@the-loop": true }
}
```

Same discipline as [`harnessTrust`](#harnesstrustenabled), and the same writer: those two
keys only, merged into what is already there, temp file plus atomic rename, **nothing
written** once both are set, and a file that does not parse as JSON is reported and left
alone. A value that already exists is never changed — your marketplace keeps pointing where
you pointed it, and an entry you deliberately set to `false` stays `false`. Failures are
best-effort: a warning, a `workspace.trust_failed` record, and the spawn still happens.
`cursor-agent` has no plugin-configuration surface, so it is a silent no-op there.

The two pre-spawn steps are **independent**: turning trust off does not turn this off, and
vice versa.

::: warning This one is user-global
`enabledPlugins` in the user settings file is not scoped to the-loop's checkouts. Enabling
the plugin there means its skill, commands and **SessionStart hook** also load in the Claude
Code sessions you start by hand.

That is what installing a plugin means, and it is the only form the harness offers — the
alternative, writing into each cloned checkout, would leave a file the daemon authored
inside a working tree the agent is about to open a PR from. `enabled: false` is the opt-out;
`/plugin` remains yours to manage.
:::

### `harnessPlugins.marketplaceRepo`

- **Type:** `string`
- **Default:** `MadaraUchiha-314/the-loop`

The `owner/repo` the `the-loop` marketplace is registered from. Point it at your fork to run
that fork's plugin — which means running whatever code that repository ships, in every
session on the machine.

Validated as `owner/repo`: anything else (a URL, a path, a value with shell metacharacters)
is refused and nothing is written. It is read only from your own config file, never from an
event payload or a cloned repository, so a work item cannot redirect it. Set it to `""` to
enable the plugin without registering any marketplace — the escape hatch when you register
the marketplace some other way.

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
and a non-GitHub work item or a missing `gh` is a no-op. The body
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
the spawn policy, the harness, per-harness args, prompt templates, the interaction
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
