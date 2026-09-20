# End-to-end Slack test, 2026-09-19

An operator-simulated run of one work item, driven from Slack after creation, against
the cloud instance configured in `<ghe-host>/<owner>/<ops-repo>`
(`.the-loop/cli-config.yaml`, the-loop 19.6.1, instance label `<instance-label>`).

- Work item repository: `<ghe-host>/<owner>/<test-repo>`
- Slack room: `#<test-room>` (`<room-channel-id>`, private), bot `the-loop` (`<bot-user-id>`)
- Operator: `<operator-login>` / Slack `<operator-slack-id>`, acting through the Slack MCP connector
  (which can send typed messages only: no buttons, no shortcuts, no slash commands)

## Timeline

| When (operator local time) | Surface | Action | Observed |
|---|---|---|---|
| 16:44 | ssh | Located the running instance: `<workspace-A>`, the-loop 19.6.1, unnamed/open instance. A second instance (`<workspace-B>`, named `<instance-B-name>`, addressed mode) runs the **same Slack app with the same tokens and the same channel** | Both listeners hold a Socket Mode connection to one app; see Observations |
| 16:46 | gh | Created labels `the-loop: auto-execute` and `<instance-label>` in the test repo | The kickoff path assumes the labels exist; a repo fresh from GitHub has neither |
| 16:47 | ops-repo config | Added `<ghe-host>/<owner>/<test-repo>` to `repositories` (commit 7a8e215) | Required: the poller only polls declared repositories |
| 16:48 | gh | Created issue #1 with both labels: "Add a repository health check (scripts/healthcheck.sh + make check)" | https://<ghe-host>/<owner>/<test-repo>/issues/1 |
| 16:50 | ops-repo config | Granted `context.added`, `decision.recorded`; subscribed `comment.agent` | Without the grants the two issue-389 acts are dropped as `unpublishable-event`; without `comment.agent` the phase checklist (and its Execute button) never reaches Slack |
| 16:46 | ticket | `the-loop add-channel slack@#<test-room>` | **Refused**, `missing-channel`, 😕 reaction, no explanation on the thread (B1, B2) |
| 16:50 | ticket | `the-loop add-channel slack@<room-channel-id>` | Declared, `listen: mentions`, 🎉 reaction. **No message in the room** says it is now the conversation until the item starts |
| 16:52 | Slack room | `@the-loop start` | Only the `message.*` copy arrived, dropped `not-addressed`. No `app_mention` (B3) |
| 16:54 | Slack room | `@the-loop help` | Same (B3) |
| 16:55 | ticket | `the-loop add-channel slack@<room-channel-id> --listen all` | Declared, `listen: all`. Workaround for B3 |
| 16:57 | Slack room | `the-loop start` (plain message) | 👀 then ✅ on the message; relayed as a control keyword onto the ticket; poller spawned on the next cycle |
| 16:58 | Slack room | — | Room-opened message ("Every update about … is posted in this channel"), then `phase.started` for **phase-selection**, "waiting on a person". `set-phase-label` hook degraded: `loop:phase-selection` label missing in the repo (B4) |
| 16:59 | Slack room | — | The phase checklist arrived as a digest with **Open on GitHub** and **Execute** buttons. The digest cut the text before the `outer-loop-on-pull-request` box (O2) |
| 17:01 | gh | Created every `loop:*` label the graph uses | Repo-side setup the daemon does not do itself |
| 17:00 | Slack room | `the-loop execute` (plain message; the connector cannot press buttons) | **Lost.** No reaction; the second instance logged `channel.dropped reason=unmapped` at 00:00:13Z (B3 confirmed) |
| 17:03 | second instance | Set `read.mode: off`, then `the-loop restart` because the hot reload left the listener running (B5) | `slack-listener not running [disabled]`; its one tmux session survived |
| 17:05 | Slack room | `the-loop execute` again, plus `@the-loop help` | 👀 ✅ on execute; recorded on the ticket; poller handed it to the graph; **phase-selection → brainstorming**, `phase.completed` + `phase.started` posted; Claude session spawned in tmux. The mention's second copy was dropped as `duplicate`, proving `app_mention` now arrives: the app subscription was never the problem |
| 17:07 | Slack room | `the-loop add-channel slack@<room-channel-id> --listen mentions` | 👀 ✅, declared `listen: mentions`. Room also received "phase selection recorded" and "started an interactive session" (comment.agent mirrors) |
| 17:08 | session | Wrote and pushed `brainstorm.md`; asked two questions with `the-loop ask` | Question on the ticket only. **Nothing in Slack** (B6) |
| 17:27 | Slack room | `@the-loop Defaults are fine on both questions …` | 👀 ✅; mirrored to the ticket; `session.reply_sent`; brainstorming passed; `phase.completed` + `phase.started` (requirements-definition) posted |
| 17:28 | session | Wrote and pushed `requirements.md`; claimed the node | `phase-approval-pending` posted to Slack with the requirements digest and **Approve / Request changes** buttons, then two comment.agent mirrors ("Requirements drafted", "requirements-approval is ready for review") |
| 17:35 | Slack room | `@the-loop approved` (top-level in the room) | 👀 ✅, but classified `work-item.reply gate=none`; mirrored as a **marked** comment; gate kept parking (B8) |
| 17:37 | session | Explained on the ticket that the approval was routed as a reply and asked for a direct GitHub comment | Recovery works, but sends the operator back to GitHub |
| 17:39 | Slack room | `@the-loop approved` as a **thread reply** under the approval request | `gate.feedback gate=open`; unmarked "answer to the open gate" on the ticket; **requirements-approval → design (approved)**; `phase.completed` + `phase.started` posted |
| 17:41 | session | `design.md` done; `design-critic-review` skipped (`not-selected`, as chosen); test-planning entered | `phase.completed` + `phase.started` posted |
| 17:42 | session | `testing-plan.md` done; **design-approval** gate opened | `phase-approval-pending` posted with buttons; three comment.agent mirrors followed |
| 17:45 | Slack room | `@the-loop approved, with one note: …fresh clone…` as a thread reply | `work-item.reply gate=none` again (B8: first answer after a gate opens). Delivered to the session as text; `graph.parked` followed 8 s later |
| 17:49 | Slack room | `@the-loop approved` (thread reply, second attempt) | `gate.feedback gate=open`; **design-approval → tasks-breakdown (approved)**; `phase.completed` + `phase.started` posted |
| 17:51 | session | `tasks.md` written; **tasks-breakdown → implementation** (no gate) | both phase notifications posted |
| 17:54 | session | Opened PR #2; the PostToolUse hook linked it (`session.pr_linked`, `graph.pull_request_linked via=session`); **implementation → verification** | both phase notifications posted |
| 17:55 | session | **verification → self-review** | `phase.completed verification: pass`, `phase.started needs-review (self-review)` posted. The `needs-review` label spans the whole review chain, and the message names the node in parentheses, which reads well |
| 17:59 | session | **self-review → critic-review**; the configured critic is `<critic-name>` | `the-loop critic run` failed twice at ~120 s (B9); the session ran `cursor-agent` directly, applied the findings (commit 86aa909) and pushed |
| 18:53 | session | **evidence → capability-docs → reviewer-briefing** | security-review and evidence passed in between; roughly 55 minutes spent in the review chain, almost all of it the critic |
| 18:55 | session | **reviewer-briefing → human-approval** | `pr-review-pending` posted with Approve / Request changes buttons, but no PR number or link (O8) |
| 18:55 | Slack room | `@the-loop approved` (thread reply, first attempt) | `work-item.reply gate=none` (B8, third gate in a row) |
| 18:56 | Slack room | `@the-loop approved` (second attempt) | `gate.feedback gate=open`; **human-approval → complete (approved)**; `work-item-complete` ("Done") and both phase notifications posted; the session merged PR #2 itself 21 s later (O9) |
| 18:58 | session | `graph.completed`; issue #1 closed by the session | poller detected the closure; `work-item.closed` posted to the room; harness terminated; workspace clone removed; **tmux session removed** despite `keepSessionOnClose: true` (B11) |

**Outcome:** one work item, filed on GitHub, then driven entirely from Slack through
brainstorm, requirements, design, testing plan, tasks, implementation, verification, the
review chain, PR approval and closure, in about two hours of wall-clock time of which
roughly 55 minutes was the critic round. PR #2 merged: `scripts/healthcheck.sh`,
`tests/healthcheck_test.sh`, `Makefile`, a README section, a capability doc, and the full
spec chain with nine evidence files under `docs/specs/issue-1/`.

**What worked from Slack:** `the-loop start`, `the-loop execute`, `add-channel --listen`,
mention-addressed replies delivered into the waiting session, gate answers (on the second
try), and every daemon-published notification: room opened, every `phase.started` /
`phase.completed`, the phase checklist with its Execute button, both `phase-approval-pending`
digests with Approve / Request changes buttons, `pr-review-pending`, `work-item-complete`,
`work-item.closed`.

**What did not:** channel-name resolution (B1), any explanation of a refused keyword (B2),
sharing one Slack app between two instances (B3), phase labels on a repo the daemon did not
initialize (B4), hot-reloading `read.mode` (B5), the session's own question reaching Slack
(B6), `graph status` from a shell (B7), the first gate answer after every gate (B8), the
critic wrapper's timeout (B9), phase labels never being removed (B10), and tmux retention
on close (B11).

## The Slack experience, read as a person in the room

The operator's verdict after the run: *horrible; too much text; too dry; the phase-selection
message is trash; it does not feel like an agentic experience.* Reading the room top to
bottom bears that out. In two hours the bot posted **41 messages** for one small work item.
A person following on a phone would have muted the channel before the requirements were
drafted.

### What the room actually looks like

- **22 of the 41 messages are `phase.started` / `phase.completed` pairs**, posted seconds
  apart, in a fixed template: *"the-loop: issue-1 completed phase \*design\* (design: pass)."*
  followed by *"the-loop: issue-1 started phase \*test-planning\* (test-planning)."* Every one
  repeats the phase name twice, once bold and once in parentheses. Two of them are exact
  duplicates ("completed phase *complete* (complete: pass)" at 18:57:57 and 18:58:10).
- **Every message opens with a machine header**: the raw event type (`phase.started`,
  `work-item.closed`, `comment.agent` rendered as "The agent commented · @login") and the
  full ref `github:<ghe-host>/<owner>/<test-repo>#1`. The header is the same on all 41 and
  carries no information after the first message. The ref alone is 50 characters.
- **Each human gate is announced three times**: the `phase-approval-pending` digest with the
  buttons, then a mirrored agent comment "*design-approval* is ready for review — reply
  with an approval…", then the `phase.started` line. Only the first one is actionable. The
  three arrive within 60 seconds and push the buttons off the screen.
- **The gate digests are the spec file pasted in.** The requirements digest reproduces the
  document's front matter ("Phase 1 of 3 … Following the Kiro spec approach … This phase
  MUST be reviewed…"), the introduction, and Requirement 1's first EARS clause before
  cutting at 1,500 characters. Nobody approves a requirements document from its first
  1,500 characters on a phone. What a reviewer wants is the agent's own two-line summary of
  what it decided and what it is unsure about, and the link.
- **The "session started" message is a tmux cheat-sheet**: a table, a fenced shell block
  with two commands, and a paragraph about respawns. This is operator documentation; in the
  room it reads as noise addressed to nobody.
- **The phase-selection message is a list of 16 ☑ emoji.** The text says "Untick anything
  … right here on this comment", but on Slack there is nothing to untick: the boxes are
  glyphs in a numbered list. The one control offered is *Execute*, which freezes everything
  as ticked. The one question that actually matters to the operator ("Where should the
  outer loop happen?") is the line the digest cut off. And the copy threatens: "each box you
  untick is an omission recorded against your name".
- **Tone.** Every bot message reads like a log line or a policy document. The only emoji are
  the robot-face signature (`🤖 _the-loop, autonomous comment_`) stamped top and bottom of
  mirrored comments, and the checklist glyphs. There is no acknowledgement of the person, no
  "done, here is what I built", no sense that an agent is talking to a teammate.
- **The agent's real voice never reaches the room.** The one message in the whole run that
  sounded like a collaborator, the brainstorm question with two options and a stated default,
  was posted by the session and never mirrored to Slack (B6). What the room *does* get is
  the runtime's templates.

### What an agentic room would look like instead

One message per meaningful moment, written in the first person, with one emoji that
carries the state, and a link. A first draft of the whole run, 9 messages instead of 41:

| Moment | Today | Instead |
|---|---|---|
| Item starts | room-opened notice + `phase.started` + 16-line checklist digest + "phase selection recorded" + tmux table | 🚀 *Picking up #1 "Add a repository health check". I plan to run the full process: brainstorm → requirements → design → tests → build → review. Anything to skip?* **[Looks good] [Skip brainstorm] [Customize…]** |
| Agent has a question | nothing (B6) | 🤔 *Brainstorm's done. Two small calls, I'll take the defaults unless you say otherwise: (1) per-line or per-file findings? (2) stdout or stderr?* **[Defaults are fine]** |
| Artifact ready for approval | digest of the file + "ready for review" + `phase.started` | 📋 *Requirements are ready: 7 requirements, the three checks plus `make check`, no new attack surface. The one thing I'm least sure of: …* **[Approve] [Request changes] [Open]** |
| Approval received | `phase.completed` + `phase.started` | ✅ *Thanks, locked. On to the design.* (as a thread reply under the request, not a new message) |
| Long silent phase | up to 6 phase lines | 🔨 one message, **edited in place** as the review chain advances: *Building… → Verifying (5 tests green) → Self-review → Critic review (this one takes a while)…* |
| PR ready | "issue-1 is at *human-approval*" with no PR link (O8) | 👀 *PR #2 is ready: +840/−19 across 5 files, tests green, security review clean. Start with `scripts/healthcheck.sh`.* **[Approve] [Request changes] [Open PR]** |
| Done | "Done" + `phase.completed` ×2 + `phase.started` + `work-item.closed` | 🎉 *Merged and closed. Health check lives at `make check`. Took 2 h 1 m; the critic round was 55 min of it.* |
| Something went wrong | 😕 reaction on a ticket comment, nothing in the room | ⚠️ *I couldn't find a channel named `#<test-room>`. Try its id from "View channel details", or invite me to it.* |

Concrete rules that fall out of this:

1. **Collapse the lifecycle.** `phase.started` + `phase.completed` for consecutive nodes is one
   transition; post one line, or better, edit a single "progress" message. Never post the
   same event twice.
2. **Drop the header.** The room already knows which work item it is for; the event type is
   for the log. Lead with the emoji and the sentence.
3. **One announcement per gate**, and it is the one with the buttons. The "ready for review"
   agent comment and the `phase.started` line should be suppressed on Slack when a
   `*-pending` message was just posted for the same node.
4. **Summaries, not excerpts.** The gate message should carry the agent's own 2–3 sentence
   summary (what it decided, what it is unsure about), not the document's first 1,500
   characters. The digest algorithm cannot do this without a model; the session can, and
   `the-loop ask` / the approval hook should accept a `--summary`.
5. **Make phase selection a real control.** On Slack, a multi-select (Block Kit
   `checkboxes` or a modal) whose submission composes the signed `the-loop execute`, with
   the outer-loop question as a radio in the same view. Until then, at minimum say "to
   change phases, edit the checklist on GitHub" and stop saying "untick … right here".
6. **Reply in threads.** Acknowledgements ("locked, moving on") belong under the message
   they answer, so the channel keeps one message per moment.
7. **Write like a colleague.** First person, present tense, one emoji per message chosen for
   the state (🚀 🤔 📋 ✅ 🔨 👀 🎉 ⚠️), never the robot-face signature twice per message,
   never a policy sentence in a notification.
8. **Route the session's voice to the room.** Fixing B6 is the single biggest UX change:
   the agent's questions and summaries are the interesting content, and today none of it
   arrives.

## Bugs

### B1 — `add-channel slack@#<name>` cannot resolve a channel in a large workspace

- **Seen:** `the-loop add-channel slack@#<test-room>` on the ticket was refused
  with `control.rejected reason=missing-channel` and a 😕 reaction. No reply on the
  thread says *why* (see B2).
- **Cause:** `SlackDirectory._read_conversations` pages `conversations.list` at most
  `_MAX_PAGES = 20` times. Slack returns fewer than `limit=1000` per page, so the
  refreshed cache (`local/slack-directory.json`, fetched 23:47:38Z) holds 11,374 names,
  **zero** private channels, and neither `#<central-channel>` nor `#<test-room>`.
  In a large enterprise workspace the bot's own channels are never reached.
- **Impact:** the issue-375 "names instead of ids" feature does not work here at all;
  the operator must find the conversation id in the channel details pane.
- **Suggested fix:** resolve a name first against `users.conversations`
  (`types=public_channel,private_channel`), which lists only the conversations the bot
  is a member of, is small, and includes private channels. Fall back to
  `conversations.list` only for a public channel the bot has not joined, and say so
  when the page cap is hit rather than treating a truncated listing as "no such name".
- **Workaround used:** `the-loop add-channel slack@<room-channel-id>`.

### B2 — a refused control keyword leaves no explanation on the thread

- **Seen:** the refusal above produced only a 😕 reaction on the comment. The reason
  (`missing-channel`) and the resolver's helpful `ValueError` text (check the spelling,
  invite the bot, scopes, "its conversation id always works") live only in the daemon's
  log, which the person on the ticket or on a phone cannot see.
- **Suggested fix:** on `control.rejected`, post one short self-marked reply quoting
  the reason, as the Slack path already does ephemerally for a collaborator's refused
  binding act.

### B3 — `@the-loop …` in the declared room never arrives as `app_mention`

- **Seen:** `@the-loop start` (16:52:13) and `@the-loop help` (16:54:56), both rendered by
  Slack as real mentions (`<@<bot-user-id>|the-loop>`), each produced exactly one event on
  the target instance: the `message.*` copy, dropped as `not-addressed`. No `app_mention`
  arrived on either instance. No reaction, no reply, nothing on the ticket.
- **Two candidate causes, neither verifiable from the daemon:**
  1. The installed Slack app (`<slack-app-id>`) may lack the **`app_mention` bot event
     subscription**. `channels status --probe` reports the *scope* `app_mentions:read` as
     granted, but Slack exposes no API for a bot to check its own event subscriptions,
     so the probe cannot see this.
  2. A second instance (`<workspace-B>`, the-loop **19.1.0**, instance
     `<instance-B-name>`) holds a Socket Mode connection to the **same app with
     the same tokens**. Slack delivers each event to one connection only; an
     `app_mention` envelope that lands on the 19.1.0 listener is discarded without a log
     line (`if event.get("type") != "message": return`).
- **Confirmed (17:00):** the plain `the-loop execute` message sent at 17:00:08 local never
  reached the target instance at all. The second instance's log shows
  `channel.dropped reason=unmapped` at 00:00:13Z, and another at 23:58:07Z. Slack
  delivers each Socket Mode envelope to **one** of the app's connections, so with two
  listeners on one app roughly half of every inbound message, mention, button press and
  slash command lands on the instance that does not own the room and is discarded.
  Cause 2 is real; cause 1 may also be true and remains unverifiable from the daemon.
- **Action taken:** set `channels.slack.read.mode: off` in the second instance's
  `<ops-repo>/.the-loop/cli-config.yaml` (backup at
  `/tmp/cli-config.yaml.before-e2e` on that host, uncommitted). Revert by
  restoring `mode: socket`.
- **Suggested fixes:** (1) `channels status` should print the manifest's event list
  next to the scope probe and say plainly "the-loop cannot verify event subscriptions;
  test with `@the-loop help`". (2) Warn loudly when two listeners share one app: Slack
  splits events across connections, so a second listener on the same app-level token
  silently halves every kind of inbound. A cheap detector: `apps.connections.open` succeeds
  for both, but each instance could post a heartbeat and see the other's. At minimum,
  document it. (3) Log an ignored envelope type at debug in the listener.
- **Workaround used:** `the-loop add-channel slack@<room-channel-id> --listen all` on the ticket,
  so plain room messages are input (the pre-389 behaviour) and the rest of the flow can
  be exercised.

### B4 — the daemon assumes the `loop:*` labels exist in the work item's repository

- **Seen:** `graph.hook_degraded node=phase-selection hook=set-phase-label error="gh issue
  edit 1 failed: 'loop:phase-selection' not found"`. The test repo was never
  `/the-loop:init`-ed, so it had none of the labels `init` creates.
- **Impact:** the phase label, the one thing a ticket reader and the dashboards use to
  see where an item stands, is silently absent for any repository the daemon works that
  was not initialized. The Slack `phase.started` posts still arrive, so nobody notices.
- **Suggested fix:** `set-phase-label` should create a missing label (`gh label create`)
  before retrying the edit, or the spawn path should ensure the label set once per
  repository. At minimum, post the degradation on the ticket once.
- **Workaround used:** created the twelve `loop:*` labels with `gh label create`.

### B5 — `channels.slack.read.mode` is hot-reloaded in the config but not in the process

- **Seen:** after changing `read.mode: socket` to `off` on the second instance,
  `config.reloaded` fired, and `the-loop status` printed
  `slack-listener running (hosted in the service, pid …) [disabled]`. The listener kept
  its Socket Mode connection and kept consuming events until a restart.
- **Suggested fix:** either stop/start the hosted listener on reload (as the poller is
  re-armed), or list `read.mode` among the boot-only keys the control plane reports as
  `restartRequired`, and have `status` say "restart to apply" instead of the contradictory
  `running [disabled]`.

### B6 — a spawned session's `the-loop ask` never reaches the daemon's bus, so Slack is not told the loop is waiting

- **Seen:** at 17:08 the session drafted `brainstorm.md`, committed it, and asked two
  questions with `the-loop ask` (a ticket comment). The pane says "The wait is
  recorded as session.awaiting_input". The daemon's event log has **no**
  `session.awaiting_input`, Slack received **nothing**, and the room's last message is
  still the session-started notice. The one notification this whole test exists to check,
  "the-loop waits for a human", did not fire.
- **Cause:** the daemon runs with `--config <ops-repo>/.the-loop/cli-config.yaml`,
  but the spawned session only gets `THE_LOOP_WORK_ITEM` in its environment. Inside the
  work-item checkout there is no `.the-loop/`, so `the-loop ask` resolves the default
  `~/.the-loop/cli-config.yaml` (absent), uses the default state root, and wrote its event
  to `~/.the-loop/logs/events.jsonl`, a bus nobody subscribes to. The ask
  comment itself is stamped self-authored, so the poller drops it too and it is never
  mirrored as `comment.agent`.
- **Impact:** every daemon whose config is not at the default path loses every
  `session.awaiting_input` (and any other event a session publishes) from Slack and from
  the dashboard's event stream. The question exists only on GitHub.
- **Suggested fix:** `cli_config.py` already honours `$THE_LOOP_CLI_CONFIG` at the same
  priority as `--config`. The spawner (`runner.py`, which already exports
  `THE_LOOP_WORK_ITEM`) should export `THE_LOOP_CLI_CONFIG=<the daemon's resolved config
  path>` into the tmux session too. Separately, `the-loop ask` should warn on the ticket
  when it publishes to a bus with no channels (`channels: []`), which is exactly what its
  own log line recorded here.
- **Follow-up (17:27):** the human reply sent from Slack as `@the-loop …` was delivered
  (`session.reply_sent`), the brainstorming node passed, and `phase.completed` /
  `phase.started` reached the room. Notifications published by the **daemon** work;
  those published by the **session** do not.

### B7 — `the-loop graph status <ref>` reports a stale node

- **Seen:** after the event log recorded `graph.advanced` to brainstorming (00:06),
  requirements-definition (00:27) and requirements-approval (00:28), `the-loop --config
  <daemon config> graph status github:…#1` still printed "at phase-selection · waiting for
  an authorized user to choose the phases", run both from the daemon's config directory and
  from inside the work item's own checkout (where `docs/specs/issue-1/work-item-state.json`
  exists and is current).
- **Impact:** the one read-only CLI view of "where is this item" is wrong for a daemon-run
  item, so an operator debugging from a shell is misled.
- **Suggested fix:** find out which state file `graph status` resolves (the portable
  record? the daemon's `state.root`?) and make it read the same `work-item-state.json` the
  runtime writes, or print the path it read from.
- **Filed as** [#396](https://github.com/MadaraUchiha-314/the-loop/issues/396) (with O6)
  and fixed there: the ref is translated to the spec id, the session's checkout is
  resolved through the session registry, and the state path is printed.

### B8 — an approval typed in a declared room is not read as a gate answer

- **Seen:** with the item parked at `requirements-approval` (the daemon itself posted
  `phase-approval-pending` to the room at 17:28:56, with Approve / Request changes
  buttons), a top-level `@the-loop approved` in the room at 17:35:54 was classified
  `kind=work-item.reply gate=none`. It was mirrored onto the ticket as the-loop's own
  **marked** comment and typed into the session as text; the gate hook never saw an
  unmarked authorized answer and kept parking (`graph.parked node=requirements-approval`
  four times in the next minute).
- **Hypothesis:** the open-gate lookup is keyed by the bound **thread**, and a room in
  channel mode has `thread: ""`, so no gate is ever found for a top-level room message.
  If so, the Approve button would work (its value names the gate) but every typed answer
  in a room silently degrades to a reply.
- **Impact:** in a room, a human who types the words the message asks for ("Reply with an
  approval…") does not advance the gate and gets no hint that it did not count. The ✅
  reaction says the opposite.
- **Result, and the real cause:** the same words as a **thread reply** (17:39:15) were
  classified `gate.feedback gate=open` and advanced the gate. But at the *next* gate the
  thread reply failed the same way (17:45:39, `gate=none`) and a resend succeeded. Thread
  versus top-level is irrelevant. The event log lines up exactly with `graph.parked`:

  | Gate entered (`graph.advanced`) | First `graph.parked` | Slack answer | Read |
  |---|---|---|---|
  | requirements-approval 00:28:56Z | 00:36:02Z | 00:35:55Z | `none` |
  | | | 00:39:15Z | `open` |
  | design-approval 00:42:13Z | 00:45:47Z | 00:45:39Z | `none` |
  | | | 00:49:37Z | see timeline |

  `_at_human_gate` (`channels/inbound.py`) answers from `graphlink.py:272`:
  `return self.actor == "human" and self.status in ("waiting", "parked")`. When the
  session's `graph complete` enters a human node the status is neither yet; the dispatcher
  sets it on its next evaluation. Entering a human node via the session's `graph complete` posts
  `phase-approval-pending` but parks nothing; the first ingress event afterwards (here,
  the mirrored reply itself) is what parks it. So **the first answer to every gate from
  Slack is always misread as a reply**, and only a second answer counts.
- **Suggested fix:** derive "at a human gate" from the current node's actor in
  `work-item-state.json` (the same source `phase-approval-pending` is published from),
  not from the parked flag; or park the node in the same step that publishes the
  approval request.
- **Meanwhile the session noticed** (17:37): it read the daemon's own log line, explained
  on the ticket that the approval had been routed as a reply, and asked for a direct
  GitHub comment. Good recovery, wrong remedy for a Slack-first operator.

### B9 — `the-loop critic run --timeout` is ignored; the wrapper gives up at ~120 s

- **Seen (session pane, 18:05):** the first `the-loop critic run <critic-name> …`
  exited with code 2; the retry with `--timeout` was still cut short; the session then
  wrote "the CLI wrapper has a hard 120s cap that ignores --timeout" and ran
  `cursor-agent -p --model <critic-model> …` directly, redirecting output to
  `.the-loop/critic-round-1-output.md`.
- **Impact:** a high-reasoning critic model routinely needs more than two minutes, so the
  configured critic never completes through the-loop's own command; the review round
  depends on the agent noticing and bypassing the wrapper, which also loses the JSON output
  contract (`--output-file`).
- **Suggested fix:** honour `--timeout` in `the-loop critic run` (and surface the effective
  timeout in `the-loop critic policy`); default it well above 120 s for harnesses that
  spawn a full agent.

### B10 — `set-phase-label` adds the new label but never removes the previous one

- **Seen:** at closure the issue carried **every** phase label at once: `loop:brainstorming`,
  `loop:requirements-definition`, `loop:design`, `loop:test-planning`, `loop:tasks-breakdown`,
  `loop:implementation`, `loop:verification`, `loop:needs-review`, `loop:complete`.
- **Impact:** the label is documented as *the* position marker ("the work item's position
  is tracked by a `loop:<phase>` label"), and every dashboard query in
  `docs/reports/labels-and-dashboards.md` assumes one label per item. With all of them
  present, a board shows the item in every column.
- **Suggested fix:** the hook should remove any other `loop:*` label in the same
  `gh issue edit` call (`--remove-label`), or the runtime should compute the label set as
  exactly one.

### B11 — the tmux session is removed on close although `keepSessionOnClose: true`

- **Seen:** the close path logged `session.retained tmux_target=…` and then, 300 ms later,
  `session.cleaned removed=["tmux","session"]` from the `close-event` source; the pane is
  gone (`can't find pane`). The config on this instance has
  `routing.tmux.keepSessionOnClose: true`, and the session-started comment promised "The
  session is kept after the work completes, so this transcript stays readable".
- **Impact:** the transcript the ticket points a reader to no longer exists; the one place
  to see *why* the critic round took 55 minutes is gone.
- **Suggested fix:** the issue-closed cleanup path should honour `keepSessionOnClose` the
  way the graph-complete path does, or the two paths should share one retention decision.

## Feature requests

- **F1 — untick phases from Slack.** The digest already numbers the phases. Let a reply
  `@the-loop execute without 1, 3` (or `skip brainstorming`) untick before freezing, so a
  phone-only operator can shape the run. Record it as the same signed `the-loop execute`.
- **F2 — a `the-loop doctor slack` (or `channels status --probe`) that speaks for the
  whole deployment**, not one instance: detect a second Socket Mode consumer on the same
  app (see B3) and check the daemon's own channel is in the resolved directory (see B1).
- **F3 — let the daemon own repository setup.** Labels the graph needs (`loop:*`) and the
  arming labels should be created on first contact with a repository, so a repo does not
  have to be `/the-loop:init`-ed before the daemon can label it (see B4).

## Observations that are neither

- **O1 — declaring a room is silent until the item starts.** `add-channel` was accepted
  at 16:50 (🎉 on the ticket) but the room heard nothing until `the-loop start` at 16:58,
  when the "Every update about … is posted in this channel" message appeared. The docs
  say "the-loop posts one message saying so"; it does, but only on the first post. A
  person who declared the room from the ticket has no confirmation in the room itself.
- **O2 — the phase-selection digest cuts before the outer-loop question.** With
  `maxChars: 1500` the Slack digest ends at "*Where should the outer loop happen?*" and
  the `outer-loop-on-pull-request` checkbox is not shown. The default (unticked) applied,
  which was fine here, but a phone reader cannot see that choice exists.
- **O3 — nothing on Slack can untick a phase.** The checklist is edited on GitHub; from
  Slack the only gesture is Execute / `the-loop execute`, which freezes everything as
  ticked. See F1.
- **O4 — the `help` answer is ephemeral**, so it is invisible to any integration acting
  on the person's behalf (including this connector). Fine for a human, worth knowing.
- **O5 — the Slack connector appends "*Sent using* @Claude"** as a second line on every
  message. the-loop's keyword parser reads the first line only, so this never interfered.
- **O7 — text appeared in the session's prompt that nobody submitted.** Twice, right
  after the session asked a question and stopped, the tmux pane showed a fully typed but
  unsent reply on the `❯` line ("Defaults are fine — converged, go ahead", then "Approved,
  proceed to design."). The daemon's log shows no delivery at those times. Either a person
  was attached to the pane, or something primes the prompt. Worth confirming, because an
  unsent line in the prompt is concatenated with the next delivered reply.
- **O8 — the `pr-review-pending` message does not name the pull request.** It reads
  "issue-1 is at *human-approval* (pr-review-pending)" with an *Open on GitHub* button that
  goes to the **issue**. A reviewer on a phone has to find PR #2 themselves; the
  `phase-approval-pending` messages, by contrast, carry the artifact's digest. Include the
  PR number, title and link, and the reviewer briefing's first lines.
- **O9 — the session merged its own PR.** After the Slack approval satisfied
  `human-approval`, the session merged PR #2 within 21 seconds and closed the issue, with
  zero GitHub reviews on the PR. The Slack "approved" was the human PR approval the tier
  requires, so this is consistent with the tier rules, but a repository with branch
  protection would have refused the merge, and some teams will want "approved" to mean
  "you may merge" rather than "merged". Worth a config knob, or at least a line in the
  approval request saying what approving will do.
- **O6 — `the-loop graph status <ref>` from the daemon's config directory reported
  "at phase-selection" after the event log had already advanced the item to
  brainstorming.** Probably read from a different checkout than the session's; worth a
  look at which `work-item-state.json` the CLI resolves when run outside the work item's
  checkout. Filed with B7 as
  [#396](https://github.com/MadaraUchiha-314/the-loop/issues/396) and fixed there.
