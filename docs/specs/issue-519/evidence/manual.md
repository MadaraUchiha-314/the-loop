---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#519"
---

# Manual run: the loud failure on real processes, no Slack credential anywhere

Work item issue-519 — activity **T11** of `testing-plan.md`. Two real processes from this worktree's code (`uv run the-loop …`, 20.9.0): a gateway whose Slack token variables are unset, and an instance pointed at it with Slack enabled and no bot token. `THE_LOOP_SLACK_APP_TOKEN`, `THE_LOOP_SLACK_BOT_TOKEN`, `THE_LOOP_CLI_CONFIG` and `THE_LOOP_INSTANCE` were unset in every shell. Temporary paths are shown as `<tmp>`; no token value existed to redact.

What to look for: `slack posting: no-token` on the gateway (step 1); the one warning line `start` prints, the gateway-client row's suffix in `status`, the `posting:` line and `[!]` finding in `channels status`, the `[!]` gateway line in `doctor slack` (step 2); `slack posting: disabled` within the reload cadence and no `restart required` after `slack.post.enabled: false` was written, with the instance's suffix now naming `disabled` (step 3); both processes stopped (step 4).

A first attempt ran the installed 20.8.0 CLI by mistake (it refused the new key) and put the instance's `--config` after the verb; it was stopped and discarded, and this is the rerun.

```text
# T11 — the loud failure on real processes, no Slack credential anywhere
the-loop 20.9.0 from this worktree; THE_LOOP_SLACK_APP_TOKEN and THE_LOOP_SLACK_BOT_TOKEN unset in every shell below

## Step 1 — a gateway whose token variables are unset

$ timeout 60 uv run the-loop gateway start --config <tmp>/gateway-config.yaml
spawned pid 3338220; listening on http://127.0.0.1:8799; logging to <tmp>/gw/logs/gateway.out

$ timeout 30 uv run the-loop gateway status --config <tmp>/gateway-config.yaml
gateway: running (pid 3338220)
  listen:  127.0.0.1:8799
  store:   <tmp>/gw/gateway.db
  config:  <tmp>/gateway-config.yaml
  pidfile: <tmp>/gw/gateway.pid
  log:     <tmp>/gw/logs/gateway.out
  ingresses: gh-webhook=off, github-poll=off, jira-poll=off, jira-webhook=off, slack-http=off, slack-socket=failed:missing-secret
  slack socket: off
  slack posting: no-token
  instances (lease live): none
  held on unassigned: 0

$ timeout 30 uv run the-loop gateway status --config <tmp>/gateway-config.yaml --format json
{
  "running": true,
  "pid": 3338220,
  "pidfile": "<tmp>/gw/gateway.pid",
  "logfile": "<tmp>/gw/logs/gateway.out",
  "configPath": "<tmp>/gateway-config.yaml",
  "listen": "127.0.0.1:8799",
  "listenInFile": "127.0.0.1:8799",
  "store": "<tmp>/gw/gateway.db",
  "reachable": true,
  "ingresses": {
    "gh-webhook": "off",
    "jira-webhook": "off",
    "slack-http": "off",
    "slack-socket": "failed:missing-secret",
    "github-poll": "off",
    "jira-poll": "off"
  },
  "slackSocket": "off",
  "slackPosting": "no-token",
  "queues": {},
  "held": 0,
  "instancesLive": [],
  "restartRequired": [],
  "secretsSet": {
    "SLACK_SIGNING_SECRET": false,
    "THE_LOOP_SLACK_APP_TOKEN": false,
    "THE_LOOP_SLACK_BOT_TOKEN": false
  }
}

## Step 2 — an instance pointed at it, Slack enabled, no bot token

$ timeout 120 uv run the-loop --config <tmp>/cli-config.yaml start
slack: outbound posts cannot be delivered — THE_LOOP_SLACK_BOT_TOKEN is unset and the gateway at http://127.0.0.1:8799 reports posting no-token; a failed post waits in the outbox
the-loop 20.9.0
service         started         [enabled]  started at http://127.0.0.1:4199; /mcp exposed
slack-listener  disabled        [disabled]  off · gateway configured
gateway-client  hosted          [enabled]  in the service process (pid 3338557)

$ timeout 30 uv run the-loop --config <tmp>/cli-config.yaml status
version     20.9.0
config      <tmp>/cli-config.yaml
state       <tmp>/inst
instance    t11 [open] — 0 declared, 0 managed
service     running (pid 3338557) [enabled] — http://127.0.0.1:4199, healthy
gh-webhook  not running [disabled]
poller      not running [disabled]
            last cycle: unknown — no heartbeat recorded
slack-listener not running [disabled] — off · gateway configured
gateway-client running (hosted in the service, pid 3338557) [enabled] — connected · long-poll http://127.0.0.1:8799 — outbound Slack needs THE_LOOP_SLACK_BOT_TOKEN on this instance (the gateway reports posting no-token)

$ timeout 30 uv run the-loop --config <tmp>/cli-config.yaml channels status
ledger:         github
slack:
  enabled:      true
  channel:      C0000000000
  subscribe:    session.awaiting_input
  publish:      work-item.reply
  verbosity:    normal
  maxChars:     1500
  longMessages: digest — above maxChars: the ask first, choices numbered, code and traces as pointers, cut at a sentence, the link for the rest
  read:         gateway — events arrive through the gateway client (http://127.0.0.1:8799); no Socket Mode connection here
  posting:      unavailable — THE_LOOP_SLACK_BOT_TOKEN is unset and the gateway at http://127.0.0.1:8799 reports posting no-token
  [!] outbound Slack needs THE_LOOP_SLACK_BOT_TOKEN on this instance — THE_LOOP_SLACK_BOT_TOKEN is unset and the gateway at http://127.0.0.1:8799 reports posting no-token; a failed post waits in the outbox
  channel kind: public channel or private channel — needs bot scope channels:history / groups:history and bot event message.channels / message.groups
  buttons:      Approve / Request changes: off · Execute / Start: off — a press reaches this instance only through the gateway client. Still needed:
                  1. add to channels.slack.publish: gate.feedback (Approve / Request changes), control.command (Execute / Start)
                  2. the-loop restart — the service hosts the listener; `the-loop status` shows the slack-listener row, and this line reads on
  kickoff:      off — channels.slack.publish does not grant work-item.create
  commands:     /the-loop through the gateway — work-item: not granted · create: not granted · instance: not granted · standing: not granted
  mentions:     @the-loop is the address in every channel — app_mention through the gateway; needs the bot scope app_mentions:read (`--probe` measures it). A DM with the bot and a room declared --listen all also hear plain messages
  shortcuts:    Add as the-loop context / Record the-loop decision (the-loop:record-context, the-loop:record-decision) through the gateway — each exactly the typed mention
  rooms:        0 declared room(s); 0 hear(s) every message (--listen all), the rest mentions only
  reactions:    received=eyes / completed=white_check_mark / error=warning (on the accepted message; needs reactions:write)
  authorized:   0 member id(s) among 0 routing.authorizedUsers entries
  bot token:    unset (THE_LOOP_SLACK_BOT_TOKEN)
  app token:    unset (THE_LOOP_SLACK_APP_TOKEN)
  conversations: 0 work item(s) in 0 bound thread(s), 0 cursor(s) — `the-loop channels threads` lists them
jira:
  integration:  not configured (integrations.jira)
subscribable events ([x] = in channels.slack.subscribe):
  [x] session.awaiting_input — An agent asked a human a question (`the-loop ask`) and is waiting — the conversation starter, and the default subscription.
  [ ] decision-pending — The graph reached a point where a human decision or opinion is genuinely required.
  [ ] phase-approval-pending — A spec-chain phase (requirements, design + testing plan, tasks) is ready for its human gate.
  [ ] pr-review-pending — A pull request delivering the work item is ready for human review.
  [ ] security-sign-off-pending — The work item's risk tier requires a named human security sign-off.
  [ ] conflict-escalated — The loop hit a genuine block, logged the conflict and escalated once.
  [ ] work-item-complete — The work item reached `complete`.
  [ ] phase.started — A phase of the work item's loop began — the node carrying the next `loop:<phase>` label was entered (published by the runtime on every walk, so every graph fires it; a human node says it waits on a person).
  [ ] phase.completed — A phase ended — the loop left its last node on a satisfied outcome, or finished at a terminal one (published by the runtime).
  [ ] phase.progress — The loop stepped to a new node WITHIN the current phase — the review chain walking self-review → critic-review → security-review is the loud case (published by the runtime, issue-393). Not recorded on the ledger: in an agentic room it edits that phase's one message in place, so a long phase shows where it is rather than going silent until it ends.
  [ ] work-item.closed — The work item ended on the ledger — its issue was closed, or the pull request that is the work item merged or closed — and this deployment released it (published by the dispatcher before the item's room is forgotten).
  [ ] comment.agent — The agent's own comment on the work item (marker-stamped) — the requirements summary, the phase checklist, a review note.
  [ ] comment.human — A human's comment the ledger accepted — an authorized user's, or a work-item collaborator's.
  [ ] standing.started — A standing session (issue-277) came up and opened its thread — no ticket, so nothing to record.
publishable events ([x] = granted in channels.slack.publish):
  [x] work-item.reply — A message on a channel, delivered into the waiting session as input — the default grant, and today's behaviour.
  [ ] gate.feedback — A message on a channel that answers an open human gate — recorded on the ledger unmarked, so the ledger's ingress classifies it.
  [ ] control.command — A control keyword typed on a channel — recorded on the ledger unmarked, so the ledger's ingress executes it through the control seam.
  [ ] work-item.create — A top-level message on a channel that opens a work item — the record is the issue, created in `kickoff.repo` with `kickoff.labels`.
  [ ] context.added — A thread a member handed the loop as context (`@the-loop record-context`) — snapshotted onto the ticket as a marked record and delivered into the session, which appends it to context.md.
  [ ] decision.recorded — A decision an authorized member recorded from a channel (`@the-loop record-decision <text>`) — a marked record attributed to them by its envelope, never a gate answer, delivered into the session, which writes the decision record.
  [ ] instance.command — A slash command on a channel that addresses this instance itself — status, restart, upgrade — run through the core facade the API exposes; not recorded (no ticket): the event log is its paper trail.
  [ ] standing.command — A slash command on a channel that lists, starts, stops or restarts a standing session — run through the core facade; not recorded (no ticket): the event log is its paper trail.

$ timeout 60 uv run the-loop --config <tmp>/cli-config.yaml doctor slack --no-heartbeat
slack doctor — ids and channel names only, never tokens; where a line says evidence it is not proof
app:
  channel kind: public channel or private channel — needs bot scope channels:history / groups:history and bot event message.channels / message.groups
  probe:        not probed — no bot token — THE_LOOP_SLACK_BOT_TOKEN is unset
  events:       the manifest subscribes the bot to message.channels, message.groups, message.im, message.mpim, app_mention — not verifiable through the API — Slack exposes no method that lists an app's event subscriptions, so an app imported from an older manifest reads as healthy here while hearing nothing. Test them: send the bot a mention (@the-loop) in the channel and watch the listener answer; if it does not, re-import the manifest (`the-loop channels manifest`) and Reinstall.
channels:
  [?] C0000000000 — unverifiable: the directory could not be read (channels.slack.channel) — no token, a missing channels:read / groups:read scope, or a transport error
gateway:
  [ok] gateway reachable at http://127.0.0.1:8799 — client connected · long-poll http://127.0.0.1:8799
  [!] the gateway's Socket Mode connection is off — no Slack event reaches any instance
  [!] outbound Slack needs THE_LOOP_SLACK_BOT_TOKEN on this instance — the gateway reports posting no-token; a failed post waits in the outbox
consumers:
  [?] this instance reads Slack through the gateway — the gateway's Socket Mode connection is the app's one listener; a local listener is not expected and the heartbeat probe is not run here

## Step 3 — slack.post.enabled: false, hot-reloaded

$ timeout 30 uv run the-loop gateway status --config <tmp>/gateway-config.yaml
gateway: running (pid 3338220)
  listen:  127.0.0.1:8799
  store:   <tmp>/gw/gateway.db
  config:  <tmp>/gateway-config.yaml
  pidfile: <tmp>/gw/gateway.pid
  log:     <tmp>/gw/logs/gateway.out
  ingresses: gh-webhook=off, github-poll=off, jira-poll=off, jira-webhook=off, slack-http=off, slack-socket=failed:missing-secret
  slack socket: off
  slack posting: disabled
  instances (lease live): t11
  held on unassigned: 0

$ timeout 30 uv run the-loop --config <tmp>/cli-config.yaml status
version     20.9.0
config      <tmp>/cli-config.yaml
state       <tmp>/inst
instance    t11 [open] — 0 declared, 0 managed
service     running (pid 3338557) [enabled] — http://127.0.0.1:4199, healthy
gh-webhook  not running [disabled]
poller      not running [disabled]
            last cycle: unknown — no heartbeat recorded
slack-listener not running [disabled] — off · gateway configured
gateway-client running (hosted in the service, pid 3338557) [enabled] — connected · long-poll http://127.0.0.1:8799 — outbound Slack needs THE_LOOP_SLACK_BOT_TOKEN on this instance (the gateway reports posting disabled)

## Step 4 — stop both

$ timeout 90 uv run the-loop --config <tmp>/cli-config.yaml stop
poller          not-running     [disabled]  poller is not running
gh-webhook      not-running     [disabled]  gh-webhook is not running
slack-listener  not-running     [disabled]  slack-listener is not running
service         stopped         [enabled]  stopped (pid 3338557)

$ timeout 60 uv run the-loop gateway stop --config <tmp>/gateway-config.yaml
stopped the gateway (pid 3338220)
```
