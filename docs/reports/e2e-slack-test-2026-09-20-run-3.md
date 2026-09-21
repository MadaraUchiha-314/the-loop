# End-to-end Slack test, 2026-09-20 run 3 (re-run of the same day's run 2)

The third operator-simulated run of one work item driven from Slack, against the same
cloud deployment as [run 2](e2e-slack-test-2026-09-20.md) — now on **the-loop 19.8.3**,
which shipped the run-2 fixes (PR #402: N1–N3, O7, O9). The purpose of this run is to
validate those fixes live. A **fresh private room** was used, created ~4 minutes before
the run, with the bot invited by the operator at creation.

- Ops repo / instance: `<ghe-host>/<owner>/<ops-repo>`, instance label `<instance-label>`,
  the-loop 19.8.3 on `<workspace-A>`
- Work item repository: `<ghe-host>/<owner>/<test-repo>`, issue #5
  ("Add a TODO/FIXME scanner — scripts/todos.sh + make todos"), delivered by PR #6
- Slack room: `#<test-room-3>` (`<room-3-channel-id>`, **private**), bot `the-loop`
  (`<bot-user-id>`)
- Operator: `<operator-login>` / Slack `<operator-slack-id>`, again through the Slack MCP
  connector (typed messages only; raw `<@bot-id>` mention markup per the N3 workaround,
  now documented in the channels doc)
- **Zero setup deltas.** Unlike runs 1 and 2, nothing was configured before this run: the
  config, subscriptions, grants and labels were all already right, and the new room needed
  only the bot invite. `add-channel` to closure with no operator detour into config.

## Timeline

| When (operator local) | Surface | Action | Observed |
|---|---|---|---|
| 13:01 | Slack | Room created, bot invited | — |
| 13:05 | ticket | `the-loop add-channel slack@#<test-room-3>` — by name, private, 4 min old | **Declared** on the next poll, 🎉, `listen: mentions`; room-opened notice posted. B1 path still good |
| 13:05 | Slack room | `<@bot-id> start` | 👀 ✅; item started; phase-selection checklist posted with checkboxes + Execute |
| 13:20 | Slack room | `<@bot-id> execute without capability-docs` | **Refused**: ⚠️ + `channel.dropped reason=unskippable-phase` — but the refusal text is now **mirrored to the ticket and the room** (the N1 visibility fix works). See **P1**: the text contradicts itself |
| 13:20 | Slack room | `<@bot-id> execute without 14` — the numeric form the refusal itself suggests | **Refused identically** (P1) |
| 13:20 | Slack room | `<@bot-id> execute` (plain) | 👀 ✅; selection frozen (full process); clean "phase selection recorded" summary; session spawned in tmux. **The tmux cheat-sheet did not post to the room** (N2 suppression works) |
| 13:24 | session | Brainstorm | **New behaviour since run 2:** the brainstorm posted its 3 open questions with stated leanings and **did not block** — it folded the leanings into `requirements.md` as asserted positions and advanced, telling the operator the requirements gate is where to confirm or amend. One gate replaces an extra ask/answer round-trip |
| 13:26 | daemon | requirements-approval | `graph.parked … via=entry` (B8 fix still holding). **One gate message** with Approve / Request changes buttons — no "reached gate" line, no "ready for review" mirror. **N2 gate-collapse works live** |
| 13:42 | Slack room | `<@bot-id> approved — all three leanings confirmed: …` — first reply | `gate=open` first try; → design |
| 13:45 | daemon | design-approval | Parked `via=entry`, again one gate message |
| 13:46 | Slack room | `<@bot-id> approved, with one note: the --fail-on-hit test must assert the output is unchanged…` — first reply | Opened first try. The note was honored **verbatim**: the task DAG says "the `--fail-on-hit` scenario asserts stdout byte-equal to the flagless run", and the shipped test does exactly that |
| 13:47–13:52 | session | tasks → implementation; PR #6 opened and linked | — |
| 13:52–14:01 | session | verification → self-review → critic → security → evidence → capability-docs → reviewer-briefing | The whole chain was **two room messages** (started + reached-briefing; the `phase.progress` edits landed in place). Critic still unavailable (see below) |
| 14:03 | Slack room | `pr-review-pending` | "👀 PR #6 is ready for review. … **Approving will merge this PR and close the work item.**" — the O9 fix: the merge behaviour is declared before the tap (`routing.mergeOnApproval` default true) |
| 14:15 | Slack room | `<@bot-id> approved — reviewed PR #6 … critic gap noted and accepted` — first reply | Opened first try (3/3 gates). **The PR merged** (squash, 14:16) on the approval, as the gate message had declared |
| 14:17 | daemon | Merge's `Closes #5` closed the issue; poller autoclosed; cleanup | 🎉 closed posted; checkout removed; `session.cleaned removed=["session"]` only; the tmux pane survives. **But see P2**: the session was killed mid-summary |

**Outcome:** one work item, filed on GitHub, driven entirely from Slack through
requirements, design, testing plan, tasks, implementation, verification, the review chain,
PR approval, merge and closure — **56 minutes** from `execute` to close, ~12 of them the
operator reading the PR at the final gate. **Five essential Slack messages** (start,
execute, three first-try approvals; the two `without` probes were deliberate). PR #6
merged: `scripts/todos.sh`, `tests/todos_test.sh`, `Makefile`, README, a capability doc,
and the full spec chain with evidence under `docs/specs/issue-5/`.

## Fix verification against the run-2 findings

| Finding | Status in this run | Evidence |
|---|---|---|
| N1 selection-grammar refusal invisible | **Half fixed** | The refusal now reaches the ticket *and* the room as a marked agent comment — no more silent ⚠️. But the grammar itself still refuses every valid argument (P1) |
| N2 gate-collapse / operator-docs suppression | **Fixed** | Every gate arrived as exactly one actionable message; the tmux cheat-sheet never posted; the endgame was two 🎉 lines (at-complete, closed), not five — the terminal node's empty lifecycle pair is gone |
| N3 connector cannot produce a mention | **Documented as designed** | Raw `<@bot-id>` markup used throughout, per the channels doc's new workaround note |
| O7 phantom prompt text | **Not exercised** | No `the-loop ask` round-trip this run (the brainstorm no longer blocks), so the deliver-path clear had nothing to clear; the pane stayed clean |
| O9 session merges its own PR | **Fixed** | The gate message states the merge-on-approval behaviour up front, and the merge followed the approval exactly as declared |
| B9 critic unavailable (deployment) | **Unchanged, still honest** | `cursor` critic timed out twice with no envelope, same as runs 1–2; recorded as *unavailable* in `evidence/critic-review.md`, mitigated with a forked reviewer + security subagent, flagged in the briefing, accepted explicitly at the gate. Still needs the deployment-side investigation |
| B1 / B8 / B10 / B11 (older fixes) | **All holding** | Private room resolved by name; 3/3 gates parked `via=entry` and opened on the first reply; exactly `loop:complete` at closure; only the session record removed at cleanup |

## The room, read as a person

~25 bot messages against 45 posted events — the 8 `phase.progress` land as in-place
edits and every completed+started pair renders as one line. The three-per-gate noise of
run 2 is gone: each gate is one message with buttons, and each drafted artifact
(brainstorm, requirements, design, testing plan, task DAG) is one agent-voice message
with links and a real summary of the decisions it froze. The room is close to readable
end-to-end; what still reads wrong:

1. **The agent's closing summary is missing entirely** — the run's biggest regression in
   room quality, caused by P2 below, not by the voice path.
2. **The `phase.started` stutter persists**: "started phase *design* (design)" on every
   lifecycle line (run 2's pain point 3; it was never in the fix scope).
3. **The room-opened notice still leads with the machine header** and the full ref
   (run 2's minor observation, unchanged).
4. **Gate digests still paste the document.** The requirements gate led with the doc's
   own introduction and cut off mid-"Definitions" with the full-text footer. The
   `--summary`/`--default` path the run-2 fix built (and told the session to use via the
   skill) was not used by the session; the "Defaults are fine" button has still never
   been seen live.

## New findings

### P1 — the typed selection grammar refuses *every* `without` argument, and its refusal text contradicts itself

- **Seen:** `execute without capability-docs` → ⚠️, mirrored refusal: *"that name is not
  a phase this checklist offers"* — followed by a numbered list of the 17 phases the
  operator may leave out, **item 14 of which is `capability-docs`**. The message suggests
  `execute without 2, 5`; `execute without 14` was then refused with the **identical**
  text. The logged drop reason is still `unskippable-phase` even though the copy is the
  unknown-name family.
- **Impact:** F1's typed fallback — the only phase-shaping gesture a connector or
  phone-first operator has — remains completely non-functional live (0 for 4 across runs
  2–3), while now *claiming* the valid name it just refused is offered. Fail-closed, but
  actively misleading.
- **Next step:** the run-2 repro showed every component passing in isolation, so the
  fault is in the live inbound normalization between mention-strip and the grammar.
  Instrument the live path (log the exact string handed to `parse_command`/`without_clause`
  and the branch taken) rather than re-testing components. The mirrored refusal (which
  now works) is the natural carrier for that diagnostic.

### P2 — merge-on-approval closes the issue out from under the session's endgame

- **Seen:** the approval's merge landed with `Closes #5`, GitHub closed the issue
  immediately, the close-poller fired, and cleanup **SIGTERM'd the session (pane status
  143) while it was composing its completion summary** — its last words in the pane:
  "The merge's `Closes #5` already closed the ticket, so the closing comment didn't post
  — posting the completion summary separately". The summary never reached the room or
  the ticket. In run 2 the session merged its own PR and got its summary out before the
  poller noticed; run 3 lost the same race.
- **Impact:** the best message of run 2's room — the agent's ✅ "what shipped, the
  evidence links, the accepted gaps" — is structurally lost whenever
  `mergeOnApproval: true` and the PR body says `Closes #N`. The retained tmux pane is
  now also a dead pane (the transcript survives; the process does not).
- **Suggested fix:** on `issue-closed` autoclose, give a live session a grace window (or
  a final-summary handshake) before SIGTERM; or have the daemon post the completion
  summary itself from the briefing; or delay the merge's issue-close until the session
  reports done.
- **Related cosmetic recurrence:** `session.autoclosed` again logged `merged: false`
  seconds after the delivering PR merged.

### Minor observations

- One transient `poll.scope_error` (~75 min window, retried clean) — same shape as run 2.
- The hosted service still logs to `/dev/null`; the event log remains the only
  observable. (Run 2's ask for a process-log file stands — P1's live-path diagnosis
  needs it.)

## Verdict

Runs 1 → 2 → 3: 13 interventions/2 h → 5 messages/50 min → **5 messages/56 min with zero
setup**, every gate first-try, the room quiet enough to read, and the merge policy stated
before the button. The two fixes that shipped between runs behaved as designed except
where they collided: the merge on approval now races the session's own endgame and
silences the closing summary (P2), and the typed selection grammar — patched for
visibility, not yet for parsing — still refuses everything it is offered while quoting
the offer back (P1). Both are precisely scoped for a follow-up.

## Fixes applied after this run

Both findings were filed as
[issue-405](https://github.com/MadaraUchiha-314/the-loop/issues/405) and fixed there
(spec chain under `docs/specs/issue-405/`; per-item detail in
[`followups/`](followups/README.md)):

- **P1** — the `without` clause read *everything* to the end of the line as phase
  names, so a connector's same-line signature (`*Sent using* @Claude`) or markup became
  one more "phase" — one that is not token-shaped, hence *"that name"*. The clause now
  drops the signature wherever it sits, strips Slack markup and invisible format
  characters around each item, refuses a word it cannot read by its **position**, and
  drops under its own family (`unknown-phase` | `unskippable-phase` | `empty-clause` |
  `checklist-unreadable`). The exact text handed to the grammar and the items it read
  are logged, and the `channel.dropped` record carries `read` — the diagnostic this
  report asked for.
- **P2** — a closure that reaches a live session standing on the graph's **terminal
  node** is now **held** for up to `routing.tmux.finishGraceSeconds` (default 300): the
  session's `the-loop graph complete <id>` claim ends the hold at once, the deadline ends
  it regardless (`session.closing`, then `session.autoclosed` with `waited_seconds` /
  `finished`). A session anywhere else in the graph closes immediately as before. The
  `finish-tasks` command and the skill state the endgame order — summary, claim, then
  the ticket close if still open. `session.autoclosed` says `merged: true` when a pull
  request recorded on the work item merged.
