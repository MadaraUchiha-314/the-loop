---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# T11 — the co-location and verbs checklist (manual)

> Run 2026-10-19 on one machine: the gateway and the instance `laptop-a` as separate
> processes with separate state roots under the scratchpad, both on loopback, no
> `exposed`, with the tokens named in `~/.the-loop/the-loop.env`. This machine's own
> instance (unnamed, polling the same test repository with `requireStartCommand: true`)
> kept running beside them. Paths and Slack ids are redacted.

## Bring-up, gateway first (R14.5, R14.2)

```text
the-loop gateway start --config <scratchpad>/e2e/gateway/gateway-config.yaml
spawned pid 876780; listening on http://127.0.0.1:8790; logging to <scratchpad>/e2e/gateway/state/logs/gateway.out

the-loop gateway status --config <scratchpad>/e2e/gateway/gateway-config.yaml
gateway: running (pid 876780)
  listen:  127.0.0.1:8790
  store:   <scratchpad>/e2e/gateway/state/gateway.db
  config:  <scratchpad>/e2e/gateway/gateway-config.yaml
  pidfile: <scratchpad>/e2e/gateway/state/gateway.pid
  log:     <scratchpad>/e2e/gateway/state/logs/gateway.out
  ingresses: gh-webhook=off, github-poll=running, jira-poll=off, jira-webhook=off, slack-http=off, slack-socket=running
  slack socket: up
  instances (lease live): none
  held on unassigned: 0

the-loop --config <scratchpad>/e2e/laptop-a/cli-config.yaml start
the-loop 20.2.1
service         started         [enabled]  started at http://127.0.0.1:4115; /mcp exposed
gh-webhook      disabled        [disabled]  off · gateway configured
poller          disabled        [disabled]  off · gateway configured
slack-listener  disabled        [disabled]  off · gateway configured
gateway-client  hosted          [enabled]  in the service process (pid 876807)

the-loop --config <scratchpad>/e2e/laptop-a/cli-config.yaml status
version     20.2.1
config      <scratchpad>/e2e/laptop-a/cli-config.yaml
state       <scratchpad>/e2e/laptop-a/state
instance    laptop-a [open] — 0 declared, 0 managed
service     running (pid 876807) [enabled] — http://127.0.0.1:4115, healthy
gh-webhook  not running [disabled] — off · gateway configured
poller      not running [disabled] — off · gateway configured
            last cycle: unknown — no heartbeat recorded
slack-listener not running [disabled] — off · gateway configured
gateway-client running (hosted in the service, pid 876807) [enabled] — connecting · attempt 1

the-loop gateway instances --config <scratchpad>/e2e/gateway/gateway-config.yaml
instance  lease  last fetch  backlog  committed  actors                                      claims
laptop-a  live   9s ago      0        0          github:MadaraUchiha-314, slack:U0…  -
```

Observations: the gateway's `slack-socket` and `github-poll` are `running`; the instance
hosts the `gateway-client` alone and its three local ingresses read `off · gateway
configured`; `gateway instances` lists `laptop-a` with a live lease and its registered
actors. The status line read `connecting · attempt 1` for the first long-poll and
`connected · long-poll http://127.0.0.1:8790` afterwards — the client now reports
`connected` as soon as its registration is answered (commit 84fdefd). One argument-order
defect was found and fixed here: `the-loop gateway start --config …` (the form this plan
writes) was rejected until the options moved onto each verb (same commit).

## Doctor (R9.3)

```text
the-loop --config <scratchpad>/e2e/laptop-a/cli-config.yaml doctor slack --no-heartbeat
slack doctor — ids and channel names only, never tokens; where a line says evidence it is not proof
app:
  channel kind: unrecognised — not a Slack conversation id (C…, G… or D…)
  probe:        conversations.info says private; granted bot scopes: chat:write, reactions:write, commands, channels:history, groups:history, im:history, mpim:history, channels:read, groups:read, users:read
  events:       the manifest subscribes the bot to message.channels, message.groups, message.im, message.mpim, app_mention — not verifiable through the API — Slack exposes no method that lists an app's event subscriptions, so an app imported from an older manifest reads as healthy here while hearing nothing. Test them: send the bot a mention (@the-loop) in the channel and watch the listener answer; if it does not, re-import the manifest (`the-loop channels manifest`) and Reinstall.
  [!] the app lacks the bot scope app_mentions:read — Slack never delivers app_mention, and since the mention is the address (issue-389) nothing typed reaches the-loop until it is added: re-import the manifest (`the-loop channels manifest`), then Reinstall. A direct message with the bot and a room declared `--listen all` still work.
  [!] the app lacks the bot scope files:read — a screenshot or a voice note attached to a message is named and linked for the session, never fetched, so it cannot read the image or Slack's transcript: re-import the manifest (`the-loop channels manifest`), then Reinstall.
channels:
  [ok] rr-and-the-loop → C0… (channels.slack.channel)
gateway:
  [ok] gateway reachable at http://127.0.0.1:8790 — client connected · long-poll http://127.0.0.1:8790
  [ok] the gateway's Socket Mode connection is up — the app's one listener
consumers:
  [?] this instance reads Slack through the gateway — the gateway's Socket Mode connection is the app's one listener; a local listener is not expected and the heartbeat probe is not run here
```

The gateway section reports the gateway reachable with the client connected and the
gateway's Socket Mode connection up as the app's one listener; the consumers section
says no local listener is expected. (The two `[!]` scope findings concern the author's
Slack app manifest, not this work item.)

## Subjects and instances (R9.2)

```text
the-loop gateway subjects --config …
no subjects yet
```

(before any event; after the live proof's first poll the table lists
`loop-github-MadaraUchiha-314-the-loop-testing-7` and `unassigned`, see `e2e-slack.md`).

## A start-time-only edit says restart required (R8.6); a bad edit keeps the config (R8.5)

```text
# listen.port 8790 → 8791 in the running gateway's file, after one reconcile tick:
gateway: running (pid 876780)
  listen:  127.0.0.1:8791  (not answering)
  listen:  127.0.0.1:8790
```

The reload recorded `config.reloaded` with `restartRequired: ["listen"]` and the
process kept listening on 8790. `gateway status` at that moment probed the file's new
port and read `not answering`: a defect, fixed in d3da68e — the process now records the
address it bound in `<state.root>/gateway.listen`, the verbs probe that, and status
says `listen: 127.0.0.1:8790 (the file says 127.0.0.1:8791 — restart to apply)`.
Appending `nonsense: true` to the file recorded `config.reload-failed` and left every
ingress running; restoring the file recorded `config.reloaded` again.

## Remaining steps

The reverse start order (instance first, then the gateway), `the-loop gateway restart`
applying the port change, and the tear-down are recorded below once the live Slack
proof (T4) has finished, so as not to interrupt it.
