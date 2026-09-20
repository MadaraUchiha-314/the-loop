# End-to-end Slack test, 2026-09-20 (re-run of 2026-09-19)

An operator-simulated re-run of one work item, driven from Slack after creation, against
the same cloud deployment as [the 2026-09-19 run](e2e-slack-test-2026-09-19.md) — now on
**the-loop 19.7.0**, which shipped the issue-393 fixes (PR #394) for that run's findings.
The purpose of this run is to validate those fixes live; items issue-393 deferred
(B5, B7/O6, O7, O9, O1/O4/O5) were observed but not re-litigated.

- Ops repo / instance: `<ghe-host>/<owner>/<ops-repo>`, instance label `<instance-label>`,
  the-loop 19.7.0 on `<workspace-A>`
- Work item repository: `<ghe-host>/<owner>/<test-repo>`, issue #3
  ("Add a repository stats summary — scripts/stats.sh + make stats"), delivered by PR #4
- Slack room: `#<test-room-2>` (`<room-2-channel-id>`, **private**, created 80 minutes
  before the run), bot `the-loop` (`<bot-user-id>`)
- Operator: `<operator-login>` / Slack `<operator-slack-id>`, again through the Slack MCP
  connector (typed messages only: no buttons, no checkboxes, no slash commands)
- The 2026-09-19 second-listener problem (B3 cause 2) was pre-eliminated: the stale
  19.1.0 instance on `<workspace-B>` is stopped, so this run also confirms the app's
  `app_mention` subscription was never missing

## Setup deltas from the previous run

Only one config change was needed before the run: `phase.progress` added to
`channels.slack.subscribe` (the new room-only event is subscribable, not on by default).
It hot-reloaded (`config.reloaded`) without a restart. Everything the previous run had to
create by hand — the arming labels, the `loop:*` label set, the repository declaration,
the event grants — was already in place from that run, so this run did not re-test F3's
label creation from a bare repo (the labels existed; nothing degraded).

## Timeline

| When (operator local) | Surface | Action | Observed |
|---|---|---|---|
| 08:31 | ops config | Subscribed `phase.progress`, pushed | `config.reloaded` ~60 s later, no restart |
| 08:35 | gh | Created issue #3 with both arming labels | — |
| 08:36 | ticket | `the-loop add-channel slack@#<test-room-2>` — **by name, a private channel** | **Declared**, 🎉, `listen: mentions`. **B1 fixed**: resolved via bot membership |
| 08:37 | Slack room | `@the-loop start` typed as plain text | The connector renders `@the-loop` as literal text, not a mention entity → dropped `not-addressed` (connector limitation, not a the-loop bug) |
| 08:37 | Slack room | `<@bot-id> start` (raw mention markup) | 👀 ✅; item started; room-opened notice, `phase.started`, and the phase checklist posted. **B3's mention path works** with one listener |
| 08:39 | Slack room | — | The checklist now renders **Block Kit checkboxes** + Execute, the outer-loop question as its own element, no adversarial copy (issue-393 R9 delivered) |
| 08:40 | Slack room | `<@bot-id> execute without capability-docs` | **Refused**: ⚠️, dropped `unskippable-phase`, explanation ephemeral (invisible to a connector). See **N1** |
| 09:02 | Slack room | `<@bot-id> execute without design-critic-review` (a name the checklist offers) | **Refused the same way** (N1) |
| 09:09 | Slack room | `<@bot-id> execute` (plain) | 👀 ✅; recorded; selection frozen (full process); session spawned in tmux |
| 09:12 | session | Brainstormed, committed `brainstorm.md`, asked 3 questions via `the-loop ask` | **B6 fixed**: the question arrived in the room in the agent's own words (🤔, the three questions, a full-text GitHub footer). `session.awaiting_input` reached the daemon's bus |
| 09:16 | pane | — | **O7 recurred**: an unsent, never-delivered reply sat pre-typed at the session's `❯` prompt ("all as proposed — direction settled, go ahead"). This time the real delivery **replaced it cleanly** — the phantom text never reached the session |
| 09:38 | Slack room | Answered the 3 questions as a mention-addressed thread reply | 👀 ✅, mirrored to the ticket as the answer of record, `session.reply_sent`; brainstorming converged ~30 s later |
| 09:33 | daemon | requirements-approval entered | **B8 fix visible**: `graph.parked … via=entry` — the gate parks in the same advance that publishes the approval request |
| 09:33 | Slack room | `<@bot-id> approved` — **first** reply under the pending message | `gate.feedback gate=open`. **B8 fixed** (last run: two attempts at every gate) |
| 09:37 | Slack room | `<@bot-id> approved, with one note: …fresh temporary git repository…` — first reply at design-approval | `gate.feedback gate=open` again; the note was honored (carried into task 1 and the tests) |
| 09:39–09:44 | session | tasks → implementation; PR #4 opened and linked (`session.pr_linked`) | — |
| 09:45–09:56 | session | verification → self-review → critic-review → security-review → evidence → capability-docs → reviewer-briefing | The whole chain rendered as **one room message edited in place** (`phase.progress`, five edits of one ts). Self-review found and fixed a real bug (a masked `sort` failure). **Critic round: see B9 below** |
| 09:56 | Slack room | `pr-review-pending` | **O8 fixed**: "👀 PR #4 is ready for review. Start there, then approve or request changes." + Approve / Request changes / Open buttons |
| 09:57 | Slack room | `<@bot-id> approved — the critic-round gap is noted and accepted…` — first reply | `gate.feedback gate=open` (3 gates / 3 first-reply successes); human-approval → complete |
| 09:57 | session | Squash-merged PR #4 itself ~20 s after the approval | O9 behaviour unchanged (deferred, expected) |
| 09:58 | Slack room | — | ✅ **"issue-3 complete"** summary in the agent's voice: what shipped, the evidence links, the accepted critic gap |
| 09:59 | daemon | Issue closed; poller detected; cleanup ran | `work-item.closed` posted; checkout removed; **B11 fixed**: `session.cleaned removed=["session"]` only — the tmux pane survives (verified attached afterwards) |
| 10:00 | gh | Label check | **B10 fixed**: exactly `loop:complete` plus the two arming labels — one phase label, not nine |

**Outcome:** one work item, filed on GitHub, driven entirely from Slack through brainstorm,
requirements, design, testing plan, tasks, implementation, verification, the review chain,
PR approval, merge and closure — **50 minutes** from `execute` to close (the previous run
took ~2 hours, ~55 minutes of it the critic detour). Every gate advanced on the **first**
typed answer. PR #4 merged: `scripts/stats.sh`, `tests/stats_test.sh` (11 scenarios),
`Makefile`, README, a capability doc, and the full spec chain with evidence under
`docs/specs/issue-3/`.

## Fix verification against the 2026-09-19 findings

| Finding | Status in this run | Evidence |
|---|---|---|
| B1 channel-name resolution | **Fixed** | A private channel created 80 min earlier resolved by name on the first try (bot-membership path) |
| B2 refused keyword unexplained | **Partly** | The fix targets `control.rejected`; this run's refusals were the *selection grammar's* (N1), whose explanation is ephemeral — invisible to a connector and absent from the ticket |
| B3 mentions never arrive | **Fixed** (by removing the second listener) | Raw-mention `start`/`execute`/gate answers all arrived; confirms the 19-09 diagnosis that Slack splits envelopes across connections |
| B4/F3 missing `loop:*` labels | **Not re-tested** | The test repo already carried the full label set from the previous run |
| B5 `read.mode` hot-reload | Deferred | Not exercised |
| B6 session's ask never reaches Slack | **Fixed** | The brainstorm question (the run's centrepiece) arrived in the room; `THE_LOOP_CLI_CONFIG` inheritance works |
| B7/O6 `graph status` stale | Deferred | Not exercised |
| B8 first gate answer misread | **Fixed, 3/3** | `graph.parked via=entry` at every human gate; every first reply classified `gate.feedback gate=open`, including "approved, with one note: …" |
| B9 critic wrapper timeout | **Wrapper fixed; critic still unavailable** | No 120 s cap: the session ran the round in the background per the new guidance, `critic policy` printed the 900 s timeout. But `the-loop critic run <critic-name>` still exited 2 "timed out", twice, with no envelope — a deployment-side `<critic-harness>` failure, not the wrapper. The session recorded the round as **unavailable** in `evidence/critic-review.md`, flagged it on the PR and in the briefing, and the human gate accepted the gap explicitly. Honest, but the deployment still has no working critic — needs its own investigation |
| B10 phase labels accumulate | **Fixed** | Exactly one `loop:*` label at every point; `loop:complete` alone at closure |
| B11 tmux killed despite retention | **Fixed** | `removed=["session"]` only; the pane (and the transcript, including the critic failure) survives closure |
| F1 untick phases from Slack | **Shipped but broken live** (N1) | Checkboxes render; the typed grammar refuses valid names |
| F2 `doctor slack` | **Works** | Prints the scope probe, the manifest's event list with the "cannot verify subscriptions" caveat, per-channel directory resolution, and heartbeat-based second-consumer detection (3/3, "evidence, not proof") |
| O2 digest cuts the outer-loop question | **Fixed** | The outer-loop question is its own Block Kit element, never digested away |
| O8 PR gate doesn't name the PR | **Fixed** | "PR #4 is ready for review", link goes to the PR |
| O7 phantom prompt text | **Recurred, contained** | Pre-typed text appeared again after the session's ask; the delivery replaced it, nothing was concatenated. Still worth root-causing — the containment looks accidental |
| O9 session merges its own PR | Deferred, unchanged | Merged ~20 s after approval, squash, no GitHub review objects |

## The room, read as a person: 31 messages, and the agent finally talks

The same shape of work item produced **31 bot messages against 41**, and — more important
than the count — the content changed character. What the 19-09 report asked for and got:

- **The machine header is gone.** No `phase.started` / `comment.agent` prefixes, no
  50-character ref on every message (the room-opened notice is the one survivor that
  still leads with `the-loop · github:<ref>`).
- **Every message leads with a state emoji** (🤔 📋 👀 ✅ 🎉 🔨), and the fixed pairs are
  collapsed: mid-run there are no `phase.completed` lines at all — a completed+started
  pair renders as one line.
- **The review chain is one message.** Six nodes (self-review → critic → security →
  evidence → capability-docs → reviewer-briefing) that were ~12 messages on 19-09 are a
  single 🔨 line **edited in place** five times (`phase.progress`). This is the single
  biggest visual improvement.
- **The session's voice is the room's content now.** The brainstorm question with its
  three numbered asks, "design drafted", "testing plan drafted", "task DAG derived", and
  the closing ✅ *"issue-3 complete — shipped: …, evidence: …"* are all the agent's own
  words with links. A person reading only the room could follow the whole run.
- The phase-selection message asks its question with real checkboxes and no
  "recorded against your name" copy.

What still reads wrong, in descending order of pain:

1. **Each gate is still announced three times** within seconds: the 📋 digest with the
   buttons, a 🔨 "*X* reached *gate*" line, then a 💬 "*gate* is ready for review" mirror.
   Only the first is actionable; RoomPolicy's gate-collapse rule is not suppressing the
   other two live (they arrive as distinct event types around the park). 9 of the 31
   messages are these duplicates.
2. **The tmux cheat-sheet still posts to the room** — the operator-docs suppression did
   not fire for it.
3. **The `phase.started` template still stutters**: "started phase *design* (design)" —
   the phase name twice, third person, on all 11 lifecycle lines.
4. **The endgame is five messages in two minutes** (🎉 at-complete, 🔨 started-complete,
   ✅ completed-complete, the ✅ summary, 🎉 closed). The agent's summary plus one closed
   line would do; the `complete` node's own started/completed pair says nothing.
5. **Gate digests still paste the document** (they cut mid-sentence — "Answer with…" —
   though the full-text footer always follows). The `--summary` path exists but the
   session did not use it; the spawn prompt should tell the session to pass `--summary`
   (and `--default`) so the gate message leads with the 2–3 sentences the fix built for.
   The "Defaults are fine" button consequently never appeared either.

## New findings

### N1 — `execute without <phase>` is refused live for names the checklist offers

- **Seen:** `execute without capability-docs` and `execute without design-critic-review`
  (both rows of the live checklist, one ticked, one optional) were each refused:
  ⚠️ reaction, `channel.dropped reason=unskippable-phase`, explanation ephemeral.
- **Repro attempted:** on the daemon's own host, with the daemon's own installed 19.7.0
  and the live config, the full pipeline passes in isolation —
  `_selection_checklist` reads the live checklist (3,926 chars), `selection_rows` parses
  all 17 rows, `without_clause` extracts the item (the connector's appended
  "*Sent using*" second line does not interfere), and `apply_without` composes with an
  **empty refusal** for both names. `strip_mention` + `parse_command` on the exact
  inbound text also behave (a bare `execute …` after mention-strip parses to no control
  command in isolation, yet the live listener clearly reached the grammar — the inbound
  normalization differs from what the components see in isolation).
- **Impact:** F1's typed fallback — the only phase-shaping gesture a connector or
  phone-first operator has, since they cannot tick checkboxes — does not work at all
  here. Fail-closed (nothing wrongly frozen), but the person gets a ⚠️ and no reason.
- **Suggested next steps:** log the grammar's refusal *text* (not just
  `unskippable-phase`) in the event log so a live refusal is diagnosable; distinguish the
  three refusal families (`unknown-name`, `always-runs`, `checklist-unreadable`) in the
  drop reason; and mirror the refusal onto the ticket the way B2's fix does for
  `control.rejected`, since the ephemeral is invisible to any integration.

### N2 — the gate-collapse and operator-docs room rules do not suppress live

The RoomPolicy rules exist and are unit-tested, but in the live room each gate still
arrived three ways (finding 1 above) and the tmux cheat-sheet still posted (finding 2).
Worth one debugging pass over `decide()`'s inputs in the daemon: the duplicates arrive as
different event types (`phase-approval-pending`, `phase.progress`/`phase.started`,
`comment.agent`) and the delivery memory may not be keyed the way the live events look.

### N3 — the connector cannot produce a mention

The Slack MCP connector sends `@the-loop` as literal text, so `listen: mentions` (the
default) hears nothing from it; raw `<@bot-id>` markup works. Not a the-loop bug, but
worth one line in the channels doc: "an integration that cannot render a mention entity
should send `<@BOT_USER_ID> …` verbatim, or the room can be declared `--listen all`".

### Minor observations

- The room-opened notice still carries the old machine header and repeats the full ref
  twice; it predates the binding so the voice path has no room memory for it yet.
- One `poll.scope_error` (transient, one occurrence in ~90 minutes, retried clean).
- `session.autoclosed` logs `merged: false` for an issue whose delivering PR had merged
  three minutes earlier — cosmetic, but a closure record that says "merged" truthfully
  would read better.
- The daemon's hosted service logs to `/dev/null` on this deployment (stdout/stderr both);
  every `logger.debug` diagnostic the fixes added is unreachable in operation. The event
  log carries the structured trail, but a file for the process log would have shortened
  the N1 investigation considerably.

## Verdict

The 2026-09-19 run needed 13 operator interventions and two hours to push one small
feature through; this run needed **five Slack messages** (start, execute, one brainstorm
answer, two approvals — plus one design note) and 50 minutes, with every answer counting
the first time. The room went from an event log to something close to the "agentic room"
the last report sketched: the agent asks, summarizes, and closes in its own voice, and
the review chain is one breathing message.

## Fixes applied after this run

Every finding above was fixed on branch `fix/n1-selection-grammar-refusal-reason`
(see `docs/reports/followups/` for the per-item detail):

- **N1** — the typed selection grammar now distinguishes a transient
  `checklist-unreadable` failure from a rejected `unskippable-phase` name, and mirrors
  the refusal to the ticket as a marked comment (a connector/phone cannot see the
  ephemeral).
- **N2** — RoomPolicy now collapses the gate node's `phase.progress` (not just
  `phase.started`), reads the nodeless "ready for review" mirror's node from its own
  text, recognises the tmux cheat-sheet as operator docs by its lead, and collapses the
  terminal node's empty lifecycle pair (endgame-collapse). The three-times-per-gate and
  cheat-sheet-in-room noise is gone.
- **N3** — the critic timeout error leads with the observed duration and names the
  caller's tool timeout when a round dies short; the skill now tells the session to pass
  `--summary`/`--default`; the channels doc documents the mention-less-connector
  workaround. (The deployment's own `cursor-agent` failure is a deploy-side issue, not a
  code one.)
- **O7** — the deliver path clears the input line before each paste, so a leftover
  unsent prompt line can never be concatenated with the delivered reply.
- **O9** — `routing.mergeOnApproval` (default true) governs whether an approval merges,
  and the `pr-review-pending` message states which behaviour is in effect before the tap.
