---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# T4 — the Slack Socket Mode path, end to end

> The author's one live proof (R12): one Slack app (the author's, tokens by variable
> name from `~/.the-loop/the-loop.env`), one gateway, one instance `laptop-a` with Slack
> disabled locally, against [the-loop-testing#7](https://github.com/MadaraUchiha-314/the-loop-testing/issues/7),
> gateway and instance on one machine (R14). Slack ids, paths and peer ids are redacted.

## Step 1 — arm through the gateway, routed by the author's registered actor

the-loop-testing#7 was opened with the two auto-execute labels. The gateway's poller
listed it and offered a presence event; the gateway routed it to `laptop-a` **by actor**
(the issue's author is `laptop-a`'s registered GitHub actor); `laptop-a` fetched it,
prepared its checkout and — `requireStartCommand` being on for the first attempt —
dropped it as `awaiting-start`, which the gateway's poll ledger learned from the commit
and offered again on the next cycle. With the start command requirement off, the next
presence spawned the work item's record: `laptop-a` posted the phase-selection checklist
on #7 and parked at the human start gate (`session.spawn_deferred:
parked-at-human-start-gate`). Its own checklist comment came back through the gateway
(routed by actor) and its router dropped it as `self-authored` — the self-marker check
running on the instance, as designed (R5.6).

Gateway log:

```text
08:29:24 gateway.received         provider=github kind=issues delivery_id=poll-presence-github:MadaraUchiha-314/the-loop-testing#7-<uuid> subject=loop-github-MadaraUchiha-314-the-loop-testing-7 event_id=1 summary=issues.labeled
08:29:24 subject.appended         event_id=1 subject=loop-github-MadaraUchiha-314-the-loop-testing-7 provider=github kind=issues delivery_id=poll-presence-github:MadaraUchiha-314/the-loop-testing#7-<uuid>
08:29:24 subject.routed           event_id=1 subject=loop-github-MadaraUchiha-314-the-loop-testing-7 to=["laptop-a"] by=actor
08:29:24 subject.committed        instance=laptop-a seq=1 outcome=dropped:awaiting-start
08:29:55 gateway.received         provider=github kind=issues delivery_id=poll-presence-github:MadaraUchiha-314/the-loop-testing#7-<uuid> subject=loop-github-MadaraUchiha-314-the-loop-testing-7 event_id=2 summary=issues.labeled
08:29:55 subject.appended         event_id=2 subject=loop-github-MadaraUchiha-314-the-loop-testing-7 provider=github kind=issues delivery_id=poll-presence-github:MadaraUchiha-314/the-loop-testing#7-<uuid>
08:29:55 subject.routed           event_id=2 subject=loop-github-MadaraUchiha-314-the-loop-testing-7 to=["laptop-a"] by=actor
08:29:57 gateway.registered       instance=laptop-a actors={"github": 1, "slack": 1}
08:29:57 subject.redelivered      instance=laptop-a seq=2 event_id=2 attempt=2
08:29:57 subject.redelivered      instance=laptop-a seq=2 event_id=2 attempt=3
08:29:57 subject.committed        instance=laptop-a seq=2 outcome=dropped:not-routed
08:29:57 gateway.received         provider=slack kind=events_api delivery_id=<uuid> subject=unassigned event_id=3 summary=events_api
08:29:57 subject.appended         event_id=3 subject=unassigned provider=slack kind=events_api delivery_id=<uuid>
08:29:57 subject.routed           event_id=3 subject=unassigned to=unassigned by=hold
08:29:58 gateway.received         provider=slack kind=events_api delivery_id=<uuid> subject=unassigned event_id=4 summary=events_api
08:29:58 subject.appended         event_id=4 subject=unassigned provider=slack kind=events_api delivery_id=<uuid>
08:29:58 subject.routed           event_id=4 subject=unassigned to=unassigned by=hold
08:30:27 gateway.received         provider=github kind=issue_comment delivery_id=poll-comment-IC_kwDOU4NUDc8AAAABdU4zjw subject=loop-github-MadaraUchiha-314-the-loop-testing-7 event_id=5 summary=issue_comment.created
08:30:27 subject.appended         event_id=5 subject=loop-github-MadaraUchiha-314-the-loop-testing-7 provider=github kind=issue_comment delivery_id=poll-comment-IC_kwDOU4NUDc8AAAABdU4zjw
08:30:27 subject.routed           event_id=5 subject=loop-github-MadaraUchiha-314-the-loop-testing-7 to=["laptop-a"] by=actor
08:30:27 subject.committed        instance=laptop-a seq=3 outcome=dropped:not-routed
```

Instance log (`gateway_event_id` beside the delivery id on every record, R10.2):

```text
08:29:24 routing.routed           gateway_event_id=1 delivery_id=poll-presence-github:MadaraUchiha-314/the-loop-testing#7-<uuid> gh_event=issues action=labeled work_items=["github:MadaraUchiha-314/the-loop-testing#7"] labeled=true
08:29:24 dispatch.dropped         gateway_event_id=1 delivery_id=poll-presence-github:MadaraUchiha-314/the-loop-testing#7-<uuid> reason=awaiting-start work_items=["github:MadaraUchiha-314/the-loop-testing#7"] gh_event=issues
08:29:55 ingress.hosted_stopped   ingress=gateway-client reason=shutdown
08:29:57 service.started          host=127.0.0.1 port=4115
08:29:57 gateway.connected        url=http://127.0.0.1:8790 instance=laptop-a peer=<peer>
08:29:57 routing.routed           gateway_event_id=2 delivery_id=poll-presence-github:MadaraUchiha-314/the-loop-testing#7-<uuid> gh_event=issues action=labeled work_items=["github:MadaraUchiha-314/the-loop-testing#7"] labeled=true
08:29:57 dispatch.queued          gateway_event_id=2 delivery_id=poll-presence-github:MadaraUchiha-314/the-loop-testing#7-<uuid> work_item=github:MadaraUchiha-314/the-loop-testing#7 gh_event=issues spawn=true
08:29:57 routing.dropped          gateway_event_id=2 delivery_id=poll-presence-github:MadaraUchiha-314/the-loop-testing#7-<uuid> reason=duplicate-delivery gh_event=issues action=labeled
08:29:57 channel.thread_opened    channel=slack work_item=github:MadaraUchiha-314/the-loop-testing#7 thread=<ts> channel_id=C0C… origin=start
08:29:58 workspace.prepared       work_item=github:MadaraUchiha-314/the-loop-testing#7 strategy=worktree checkout=<scratch>/e2e/laptop-a/workspace/.worktrees/github.com/MadaraUchiha-314/the-loop-testing/github-MadaraUchiha-314-the
08:30:01 graph.started            work_item=github:MadaraUchiha-314/the-loop-testing#7 node=phase-selection
08:30:01 graph.parked             work_item=github:MadaraUchiha-314/the-loop-testing#7 node=phase-selection
08:30:01 session.spawn_deferred   work_item=github:MadaraUchiha-314/the-loop-testing#7 harness=claude gh_event=issues action=labeled delivery_id=poll-presence-github:MadaraUchiha-314/the-loop-testing#7-<uuid> reason=parked-at-huma
08:30:27 routing.dropped          gateway_event_id=5 delivery_id=poll-comment-IC_kwDOU4NUDc8AAAABdU4zjw reason=self-authored gh_event=issue_comment action=created work_items=["github:MadaraUchiha-314/the-loop-testing#7"]
```

```text
the-loop gateway subjects --config …
subject                                          claimants  events  held  pending  oldest  dead
loop-github-MadaraUchiha-314-the-loop-testing-7  -          3       0     0        -       0
unassigned                                       -          2       2     0        -       0
```

The two events held on `unassigned` are the bot's own Slack messages (Slack delivers an
app's posts back over its connection; their `user` is the bot's id, which no instance
registers), so they wait for retention. Harmless; a follow-up may drop bot-authored
messages at the gateway.

## Step 2 — `the-loop execute` and a thread reply, through the gateway

The author replied `the-loop execute` on #7 (13:56 UTC) and then in the session's Slack
thread (13:58). The gateway routed the comment to `laptop-a` by actor; the instance's
control-command path handed it to the graph, which spawned the work item's session
(`session.spawned`, `gateway_event_id=6`), and the session's registration published its
claim (`gateway.claimed … role=driver`) — the next comment on #7 (the instance's own
"phase selection recorded") was routed **by claim** and dropped as `self-authored`. The
Slack reply reached `laptop-a` routed by actor (the author's Slack id is its registered
actor), the instance resolved the thread to #7 and dropped it as `not-addressed`: the
pre-existing room rule (issue-389) takes a plain thread message as input only when it
mentions the bot. The gateway's part — the right instance, once, with the thread
resolved — held; step 3 repeats the reply with a mention.

Gateway log:

```text
13:56:33 gateway.received         provider=github kind=issue_comment delivery_id=poll-comment-IC_kwDOU4NUDc8AAAABdah_Cw subject=loop-github-MadaraUchiha-314-the-loop-testing-7 event_id=6 summary=issue_comment.created
13:56:33 subject.appended         event_id=6 subject=loop-github-MadaraUchiha-314-the-loop-testing-7 provider=github kind=issue_comment delivery_id=poll-comment-IC_kwDOU4NUDc8AAAABdah_Cw
13:56:33 subject.routed           event_id=6 subject=loop-github-MadaraUchiha-314-the-loop-testing-7 to=["laptop-a"] by=actor
13:56:33 subject.redelivered      instance=laptop-a seq=4 event_id=6 attempt=2
13:56:33 subject.committed        instance=laptop-a seq=4 outcome=dropped:not-routed
13:56:37 gateway.claimed          subject=loop-github-MadaraUchiha-314-the-loop-testing-7 instance=laptop-a role=driver routed=0
13:57:04 gateway.received         provider=github kind=issue_comment delivery_id=poll-comment-IC_kwDOU4NUDc8AAAABdaibMQ subject=loop-github-MadaraUchiha-314-the-loop-testing-7 event_id=7 summary=issue_comment.created
13:57:04 subject.appended         event_id=7 subject=loop-github-MadaraUchiha-314-the-loop-testing-7 provider=github kind=issue_comment delivery_id=poll-comment-IC_kwDOU4NUDc8AAAABdaibMQ
13:57:04 subject.routed           event_id=7 subject=loop-github-MadaraUchiha-314-the-loop-testing-7 to=["laptop-a"] by=claim
13:57:04 subject.committed        instance=laptop-a seq=5 outcome=dropped:not-routed
13:58:51 gateway.received         provider=slack kind=events_api delivery_id=<uuid> subject=unassigned event_id=8 summary=events_api
13:58:51 subject.appended         event_id=8 subject=unassigned provider=slack kind=events_api delivery_id=<uuid>
13:58:51 subject.routed           event_id=8 subject=unassigned to=["laptop-a"] by=actor
13:58:51 subject.committed        instance=laptop-a seq=6 outcome=delivered
14:04:53 subject.routed           event_id=3 subject=loop-github-MadaraUchiha-314-the-loop-testing-7 by=binding
14:04:53 subject.committed        instance=laptop-a seq=7 outcome=delivered
14:09:46 gateway.registered       instance=laptop-b actors={"github": 1}
```

Instance log:

```text
13:56:33 routing.routed           gateway_event_id=6 delivery_id=poll-comment-IC_kwDOU4NUDc8AAAABdah_Cw gh_event=issue_comment action=created actor=MadaraUchiha-314 work_items=["github:MadaraUchiha-314/the-loop-testing#7"] labeled
13:56:33 control.command          gateway_event_id=6 delivery_id=poll-comment-IC_kwDOU4NUDc8AAAABdah_Cw command=execute work_item=github:MadaraUchiha-314/the-loop-testing#7 actor=MadaraUchiha-314 effect=handed-to-graph
13:56:33 dispatch.queued          gateway_event_id=6 delivery_id=poll-comment-IC_kwDOU4NUDc8AAAABdah_Cw work_item=github:MadaraUchiha-314/the-loop-testing#7 gh_event=issue_comment spawn=true
13:56:33 routing.dropped          gateway_event_id=6 delivery_id=poll-comment-IC_kwDOU4NUDc8AAAABdah_Cw reason=duplicate-delivery gh_event=issue_comment action=created
13:56:34 workspace.prepared       work_item=github:MadaraUchiha-314/the-loop-testing#7 strategy=worktree checkout=<scratch>/e2e/laptop-a/workspace/.worktrees/github.com/MadaraUchiha-314/the-loop-testing/github-MadaraUchiha-314-the
13:56:37 graph.advanced           work_item=github:MadaraUchiha-314/the-loop-testing#7 node=phase-selection to=brainstorming outcome=selected
13:56:37 session.registered       work_item=github:MadaraUchiha-314/the-loop-testing#7 harness=claude harness_session_id=<uuid> cwd=<scratch>/e2e/laptop-a/workspace/.worktrees/github.com/MadaraUchiha-314/the-loop-testing/github-Ma
13:56:37 session.spawned          work_item=github:MadaraUchiha-314/the-loop-testing#7 harness=claude harness_session_id=<uuid> runner=tmux interaction=work-item tmux_target=loop-github-MadaraUchiha-314-the-loop-testing-7 gh_event
13:57:04 routing.dropped          gateway_event_id=7 delivery_id=poll-comment-IC_kwDOU4NUDc8AAAABdaibMQ reason=self-authored gh_event=issue_comment action=created work_items=["github:MadaraUchiha-314/the-loop-testing#7"]
13:58:51 channel.dropped          gateway_event_id=8 delivery_id=<uuid> channel=slack reason=not-addressed work_item=github:MadaraUchiha-314/the-loop-testing#7 thread=<ts>
14:04:53 channel.dropped          gateway_event_id=3 delivery_id=<uuid> channel=slack reason=not-addressed
14:09:33 ingress.hosted_stopped   ingress=gateway-client reason=shutdown
```

### Two defects the records show, fixed on the branch

- **The thread binding never reached the gateway.** `channel.thread_opened` at 08:29:57
  ran in the service process with the gateway client attached, yet the gateway's
  `bindings` table stayed empty and event 8 was routed by actor, not by binding. Cause:
  the service stored the publisher on `ChannelState` as a class attribute and `bind`
  read it through the instance, so the function arrived bound with one argument too
  many and every publish died in `bind`'s catch-all (the service's stderr is
  `/dev/null`). Fixed: `bind` reads the ClassVar through the class; the loopback
  hosted test binds a thread and reads the binding back from the gateway's store. The
  binding above (`14:04:53 subject.routed … by=binding`) was posted by hand to the live
  gateway to confirm the server side, and it routed one held bot message onto
  `laptop-a`'s queue.
- **An in-flight dispatch was fetched again.** Seq 2 (attempts 3) and seq 4 (attempts
  2) were re-fetched within the second while their resume was spawning: the client's
  cursor was the server's `committed`, so the long-poll returned the held delivery at
  once, the gateway counted a redelivery, and the duplicate's outcome
  (`dropped:not-routed`) was recorded instead of `spawned`. With `maxAttempts: 3` a
  slower spawn would have dead-lettered a healthy delivery. Fixed: the cursor runs past
  what the process holds and falls back to `committed` once the dispatch settles; a
  unit test pins it (`test_a_delivery_whose_dispatch_is_in_flight_is_not_fetched_again`).

Both in commit `8071ad7`; `laptop-a` runs the fixed code from step 3 on.

## Step 3 — two replies while `laptop-a` is down, then `laptop-b`

`laptop-a` stopped at 14:09:27 UTC (`the-loop --config … stop`; the gateway's instances
view shows its lease `expired` and its claim kept). `laptop-b` started from its own
config (port 4116, actor `the-loop-nobody`): registered at 14:09:46, lease live, backlog
0, no claims — a second instance on the same gateway sees nothing of the first's queue.

```text
the-loop gateway instances --config …
instance  lease    last fetch  backlog  committed  actors                           claims
laptop-a  expired  18s ago     0        7          github:MadaraUchiha-314, slack:U0C…  loop-github-MadaraUchiha-314-the-loop-testing-7 (driver)
laptop-b  live     5s ago      0        0          github:the-loop-nobody           -
```

The author was asked (ticket, 14:11 UTC) for two mentioning replies in the thread while
`laptop-a` is down. Recorded below as they happen, with the restart, the duplicate-name
(`laptop-a` copy) and close steps.
