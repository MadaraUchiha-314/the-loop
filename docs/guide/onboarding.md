# Onboarding: what `/the-loop:init` asks you

`/the-loop:init` is the-loop onboarding you, rather than you onboarding the-loop. It runs
in your editor, establishes two config files **with** you, and ends by telling you which
credentials are still missing. This page is what it will ask, so you can decide the two
questions that matter before you start.

If you want the short version: **run `/the-loop:init`, pick a rung on the autonomy
ladder, and read the `needs-user` list at the end.** Everything below is detail you can
skip until it matters.

```text
/the-loop:init              # the guided walkthrough
/the-loop:init --defaults   # no questions; sensible defaults; gaps listed at the end
/the-loop:init --dry-run    # shows what it would do and writes nothing
```

It is **idempotent**. Re-running it never re-asks a question you already answered and
never overwrites a file you own — it raises only what is still missing. Run it again
whenever you want to turn something on.

## The two questions only you can answer

Everything else has a sensible default. These two do not.

### 1. Where will the daemon run?

the-loop's CLI daemon is what watches your repository when no session is open. Where it
runs decides how GitHub reaches it:

| Your answer | What init proposes | Why |
|---|---|---|
| **A machine I close** — a laptop, a desktop | the **poller** (`polling`) | GitHub cannot reach a webhook receiver behind NAT or a firewall. The poller asks GitHub instead, on an interval. |
| **An always-on host** — a cloud box, a VM, a container | the **webhook receiver** (`webhooks.ghWebhook`) | Push instead of pull: lower latency, and it needs an inbound route plus a shared secret. |
| **Nowhere yet** | neither | Routing stays off. You can re-run init later. |

### 2. How much should it do while you are not looking?

This is the autonomy ladder. Pick the rung you are comfortable with **today** — moving up
later is one re-run.

| | `commands-only` | `watch-and-ask` *(recommended)* | `armed` |
|---|---|---|---|
| Watches your repository | no | yes | yes |
| Starts a work item | you, in a session | you, with `the-loop start` on the item | the labels alone |
| Merges an approved PR | you | you | itself |
| Files issues about its own repeated failures | no | no | yes |

- **`commands-only`** — the-loop is the slash commands in your editor. Nothing runs when
  you close the session. These are the shipped defaults, so this rung changes nothing: it
  exists so that *"not yet"* is an answer.
- **`watch-and-ask`** — the daemon follows every work item you arm with the auto-execute
  labels, but nothing spawns until an authorized user comments `the-loop start` on it.
  An approved pull request stops at approved; you merge it. **This is the one to start
  with:** you see the loop work while every irreversible act is still yours.
- **`armed`** — labelling an item is the go-ahead, and a pull request that clears its
  approval gate merges itself. The label is still required: an unlabelled item is
  received and ignored.

::: warning No rung buys away a human gate
The highest rung changes **who starts the work**, never **who approves it**. At every
rung, a work item still stops at the phase-selection checklist, at the `requirements.md`
approval, at the `design.md` approval, at the pull-request approval, and — at risk tier 4
and above — at a named human security sign-off. Those are rules of the process graph and
the skill, not settings, and no configuration can switch them off.
:::

## What init walks you through

| Step | What it establishes |
|---|---|
| Detect | Your languages, test runners, convention docs, API specs, git remote |
| Harness config | `.the-loop/harness-config.yaml` — custom instructions, testing conventions, people, API contracts |
| **Posture** | The two questions above |
| CLI config | `cli-config.yaml` — in this repo or in `~/.the-loop/`, then what is watched, how events arrive, and what happens when one matches |
| **Slack** | The app, the two tokens, the channel — or a clean skip |
| Scaffold | `.the-loop/`, `docs/specs/`, `docs/capabilities/`, `docs/decisions/`, `docs/learnings/` |
| Labels | The `loop:<phase>` labels and your auto-execute labels |
| Validate | Both configs, against the schemas that ship with the plugin |
| **Preflight** | Every credential the configs name — is it set? |
| Report | created · skipped · drifted · **needs-user** |

Three keys init will always ask about by name, because a deployment is quietly broken
without them and no default can fill them:

- **`routing.authorizedUsers`** — empty by default. Until somebody is named here, nobody
  can start, stop or approve anything from a comment. No autonomy rung fills it: who may
  drive the loop is established by name, never implied by a threshold you picked.
- **`routing.workspace.root`** — empty by default. The daemon runs independent of any
  repository, so without it a spawned session has nowhere to check your code out.
- **`routing.autoExecuteLabels`** — the labels that arm a work item. **Every one of them**
  must be on an item before anything spawns.

## Slack, in four sentences

Slack is a **channel**: one thread per work item, so you can answer the-loop from your
phone.

- **`subscribe`** is what the channel *hears* — which events get posted into it.
- **`publish`** is what a message there *may become* — a reply to the session, a gate
  answer, a control command, a new work item. This is the channel's **authority**, so
  everything is off except `work-item.reply` until you say otherwise.
- **GitHub stays the ledger.** Anything that starts in Slack is recorded on the work item
  first, and the loop reads it from there.

Init walks the four setup steps — import the app manifest `the-loop channels manifest`
prints, install for the bot token, mint an app-level token for Socket Mode, invite the bot
and take the conversation id — then runs `the-loop channels status --probe` so a missing
scope is named while you are still in the session. The [Slack integration](/guide/slack)
page is the full reference; you do not need it to get started.

## Credentials

Every secret the-loop uses is **named** in your config and **read** from your
environment. The config never holds a value. Init checks which of these names are set and
lists the rest under **needs-user**:

| Variable (default name) | Gates | Where it comes from |
|---|---|---|
| `THE_LOOP_SLACK_BOT_TOKEN` | posting, reading and reacting in Slack | Slack app → *OAuth & Permissions → Install* (`xoxb-…`) |
| `THE_LOOP_SLACK_APP_TOKEN` | Socket Mode: buttons, `/the-loop`, live replies | Slack app → *Basic Information → App-Level Tokens*, scope `connections:write` (`xapp-…`) |
| `THE_LOOP_GH_WEBHOOK_SECRET` | verifying that a webhook delivery really came from GitHub | you choose it, and paste the same value into the GitHub webhook |
| `GH_TOKEN` / `GITHUB_TOKEN` | the-loop's own GitHub API calls | `gh auth token`, or a personal access token |

**Init reports presence only** — whether the variable is set, never its value, and it
never writes a credential into any file.

Rather than exporting four variables before every `the-loop start`, point `env.file` at a
dotenv file and let the CLI load it. That file holds secrets: init will say so, check
that `.gitignore` covers it, and offer to add the line if it does not.

## When something is missing

The **needs-user** section of init's report is the list of things still in your way, each
with the exact key or variable and what it gates. Working through it and re-running
`/the-loop:init` is the intended loop — that is what "idempotent" buys you.

Two commands answer "is Slack actually working?" better than any config file can:

```bash
the-loop channels status --probe   # the channel, the scopes, the events, token presence
the-loop doctor slack              # the deployment-wide diagnosis
```

## Next

Run the [quickstart](/guide/quickstart) to take a single issue through the whole loop.
