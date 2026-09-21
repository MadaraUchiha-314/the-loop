---
type: bugfix
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#413"
status: in-review            # draft | in-review | approved — tier 3: the PR approval is the human gate
approvedBy: []
severity: high
collaborators: [engineer]
overrides: {}
riskTier: 3                  # the listener gains a periodic self-check and one additive config key; no grant, scope or authorization change
---

<!-- Authored per the the-loop:writing skill. -->

# Bugfix spec: a second Socket Mode consumer eats half of everything inbound, and only the hand-run doctor can see it

> Phase 1 of 4 (bugfix → design → testing plan → tasks). Source:
> [issue-413](https://github.com/MadaraUchiha-314/the-loop/issues/413), filed from a live
> incident on 2026-09-21.

## Summary

When a second Socket Mode consumer holds the app-level token, Slack load-balances
envelopes across the open connections and roughly half of everything inbound vanishes:
mentions, button presses, select-menu picks, slash commands. **Nothing in the-loop
notices.** `the-loop status` stays green, `channels status --probe` reports every scope
present, and the one check that does detect it — the doctor's heartbeat probe
([issue-393](https://github.com/MadaraUchiha-314/the-loop/issues/393) F2) — runs only
when an operator already suspects Slack and types `the-loop doctor slack`.

The reporter lost a kickoff mention and four repository-picker presses across ~40 minutes
of live use, and found the cause only by tailing the event log while pressing buttons.

The loss is visible **only as an absence**. On the healthy instance there is no
`channel.dropped`, no `channel.*` record, nothing to grep — the envelope was never
offered to this process. Slack's client even answers the member's press with
`{"ok": true}`, because acceptance is not delivery.

## Steps to reproduce

1. Run one the-loop instance with `channels.slack.enabled: true` and
   `read.mode: socket`, listener hosted in the service.
2. From any other host, open a second Socket Mode connection with the **same** app-level
   token — a stale `the-loop channels listen`, an abandoned workspace's instance, a bare
   `slack_sdk` script. It need do nothing with what it receives.
3. In the configured channel, mention the bot and press a repository-picker button,
   several times each.
4. Run `the-loop status` and `the-loop channels status --probe`.

## Expected vs actual

| | Expected | Actual |
|---|---|---|
| a mention or press that Slack routed to the phantom | the deployment reports that inbound is being split | nothing: no event, no log line, no status change |
| `the-loop status` | says the listener is hearing only part of its traffic | `slack-listener running (hosted in the service)` |
| `channels status --probe` | same | every scope granted, channel resolved, healthy |
| the operator's next move | named by the tool | tail the event log while pressing buttons |
| the remedy, once found | documented | documented nowhere; the working fix (rotate the app token) is in no page |

## Root cause

Three separate gaps, each of which alone would have hidden the incident.

**1. The detection is a verb, not a behaviour.** `doctor.probe_second_consumer` measures
the split correctly — it posts nonce heartbeats and counts the echoes — but it is reached
only from `the-loop doctor slack`. Nothing calls it on a schedule. An operator runs the
doctor when they already suspect Slack, and this failure's whole signature is that
nothing looks suspicious.

**2. Nothing carries the finding out of the process that made it.** The probe returns a
dict to its command and exits. There is no event, no state file, and therefore nothing
for `status` or `channels status` to read. A finding that does not outlive its process
cannot reach a surface the operator was already looking at.

**3. The remedy text stops one step short.** `doctor.consumer_verdict_text` says "find
every process connected with this app-level token … and stop all but one". In the live
incident the phantom's host was never found, and **restarting the healthy service did not
help**. What worked was rotating the app-level token — revoke, regenerate, update the env
file, restart — which fences out every holder without needing to find any of them. That
sentence exists in no shipped page.

### Evidence from the incident (redacted)

- `the-loop doctor slack` heartbeats across runs minutes apart: `2/3` → `1/3` → `3/3` →
  `1/3`, while `channels status --probe` reported every scope granted and `status` showed
  the listener `running (hosted in the service)`.
- A top-level kickoff mention produced no event of any kind at its timestamp. A retry
  five minutes later arrived with its `message.*` copy logged and its `app_mention` copy
  missing — per-envelope loss, the split's signature.
- A repository-picker press: client POST `/api/blocks.actions` → `{"ok": true}`; zero
  events server-side.
- After the app-level token was rotated: heartbeats `3/3` on every run, and the same
  press landed within a second (`channel.created`, `press_reported: landed`).

The `3/3` in the middle of that sequence is itself a requirement. A single cycle is a
coin toss, so **the deployment's report must not be a single cycle's verdict** — an
operator who happens to look during a clean cycle must still see that the last hour was
not clean.

## Requirements

### Requirement 1 — the listener checks itself, on a cadence, without being asked

**User story:** As an operator, I want the running listener to measure whether it is
hearing all of its traffic, so that a split is found by the deployment rather than by me
noticing that a member's press did nothing.

#### Acceptance criteria (EARS)

1. WHEN the Socket Mode listener connects THEN the system SHALL run one split check
   before it begins its idle loop.
2. WHEN `channels.slack.read.catchUpSeconds` is non-zero THEN the system SHALL run a
   split check every `catchUpSeconds` for as long as the listener runs.
3. WHEN `channels.slack.read.catchUpSeconds` is `0` THEN the system SHALL run the check
   at connect only, matching the reconcile's own connect-only contract.
4. WHEN a split check runs THEN the system SHALL post `read.splitCheckBeats` fixed-format
   nonce heartbeats into the configured channel, count how many the listener itself
   receives within the window, and delete every heartbeat it posted afterwards.
5. WHEN `channels.slack.read.splitCheckBeats` is `0` THEN the system SHALL run no split
   check at all and SHALL post nothing.
6. WHEN a split check cannot run — no configured channel, no bot token, the channel does
   not resolve — THEN the system SHALL record `unverifiable` with the reason and SHALL
   NOT record `ok`.
7. WHEN a split check raises for any reason THEN the system SHALL log it and continue
   listening; a diagnostic SHALL NEVER end the listener.
8. WHEN the listener is stopped during a check's window THEN the system SHALL abandon the
   window and stop within one tick of the existing loop.

### Requirement 2 — a miss is an event and a state, not a return value

**User story:** As an operator, I want a short check to leave a record the rest of the
deployment can read, so that the finding survives the process that made it.

#### Acceptance criteria (EARS)

1. WHEN a split check hears fewer heartbeats than it posted THEN the system SHALL emit
   `channel.split_suspected` at `warning`, carrying beats, echoed, the window, the
   channel id and how many consecutive checks have now been short.
2. WHEN consecutive short checks continue THEN the system SHALL emit
   `channel.split_suspected` on the first one and then at most once every
   `SPLIT_ESCALATE_EVERY` checks, so a persistent split is a periodic warning and not a
   storm.
3. WHEN a check is clean after one or more short checks THEN the system SHALL emit
   `channel.split_cleared` at `info` and SHALL reset the consecutive-miss count.
4. WHEN any check completes THEN the system SHALL write its outcome to a machine-local
   state file, replacing the previous one atomically.
5. WHEN the state file cannot be written THEN the system SHALL warn once and continue;
   observability SHALL NEVER break ingress.
6. WHEN the system writes that state THEN it SHALL carry ids, counts and timestamps only
   — never a token, never message text, never a nonce that is still in flight.

### Requirement 3 — the operator's existing surfaces say it

**User story:** As an operator, I want `status` and `channels status` to tell me inbound
is being split, so that I learn it from the command I already run rather than from a verb
I only reach once I suspect Slack.

#### Acceptance criteria (EARS)

1. WHEN the recorded state says the most recent check was short, or that any check within
   the retained window was short, THEN `the-loop status` SHALL print a `slack` report
   naming what was measured and the remedy.
2. WHEN every retained check is clean, and whenever no check has ever run, THEN
   `the-loop status` SHALL print no such report.
3. WHEN `status --format json` is asked THEN the system SHALL carry the same facts under
   `slackSplit`.
4. WHEN a split is suspected THEN `the-loop channels status` SHALL print it as a `[!]`
   finding; WHEN it is not THEN `channels status` SHALL state the check's cadence and its
   last verdict in one line.
5. WHEN the `/the-loop status` slash command renders THEN it SHALL carry the same one
   line as `the-loop status`.
6. WHEN a split is reported anywhere THEN the report SHALL state that the measurement is
   **evidence, not proof** — Slack exposes no API that lists an app's connections.
7. WHEN the state is reported THEN a split finding SHALL NOT change `status`'s `ok` or
   its exit code: `ok` means every enabled service is running, and a split is an
   observation about the world, not about whether a service runs.

### Requirement 4 — the finding names the remedy that works

**User story:** As an operator staring at a split I cannot locate, I want the tool to tell
me the fix that does not require finding it.

#### Acceptance criteria (EARS)

1. WHEN a split is reported by any surface THEN the text SHALL name both remedies in
   order: stop every other holder of the app-level token, or — when the holder cannot be
   found — rotate the token: revoke, regenerate, update the env file, restart.
2. WHEN the remedy is stated THEN it SHALL be the same sentence in the event, in `status`,
   in `channels status` and in `doctor slack`, so an operator reads it once and
   recognises it.
3. WHEN the remedy is documented THEN the Slack guide SHALL carry the rotation procedure
   as steps, including that restarting the healthy instance does not fence the phantom
   out.

## Security considerations

- **No new secret handling.** The check reads the same two token environment variables
  the listener already read to connect. No token, and no fingerprint of one, is written
  to the state file, the event log or any rendered line. (Abuse case: an operator pastes
  `status` output into a ticket — it must carry nothing that is not already public in the
  workspace.)
- **No new scope.** Posting and deleting the heartbeat uses `chat:write`, which the
  listener holds already; the check is refused rather than escalated if it does not.
- **The state file is machine-local and forgeable**, like the poller heartbeat: anyone
  who can write `state.root` can write a verdict. It therefore drives a *report* and
  never a decision — no gate, no authorization and no routing reads it.
- **Abuse case — a member forges a heartbeat.** A message matching the heartbeat marker
  and a nonce the check is waiting for could be posted by any member of the channel, and
  would make a short check look clean. It cannot make a clean check look short, so the
  failure direction is a missed warning, never a false accusation; the nonce is 8 random
  bytes, so guessing one inside a 5-second window is not a practical attack. Recorded
  rather than mitigated.
- **Abuse case — noise as denial of service.** A check posts at most
  `splitCheckBeats` messages per `catchUpSeconds` and deletes each one. The default (2
  beats per 900s) is bounded and far below any rate limit; `0` turns it off entirely.

## Out of scope

- **The outbound silence** — [issue-409](https://github.com/MadaraUchiha-314/the-loop/issues/409)
  is a failed *post* that does not reach the operator. Same theme, disjoint mechanism.
- **Finding the phantom.** Slack exposes no API that lists an app's connections, so
  nothing here can name the other host. The check measures; the operator fences.
- **Automatic remediation.** Rotating a token is a credential operation with an operator's
  name on it. The-loop names the procedure; it does not perform it.

## Open questions

None. The one judgement call — whether a single clean check clears the report — is
settled against the reporter's own evidence in `design.md` § Trade-offs.
