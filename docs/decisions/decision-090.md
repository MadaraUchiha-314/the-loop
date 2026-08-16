# Decision 090: self-diagnosis is a policy over the event log, behind an allow-list, and its issues are never armed

- **Status:** proposed
- **Date:** 2026-08-16
- **Work item:** [issue-242](https://github.com/MadaraUchiha-314/the-loop/issues/242)
- **Deciders:** maintainer (via ticket); harness (proposal)

  > **Numbering.** Written as 089 and renumbered to 090 on the rebase:
  > [PR #255](https://github.com/MadaraUchiha-314/the-loop/pull/255) (issue-247) landed
  > 089 on `main` while this branch was in flight. Same collision
  > [decision-088](decision-088.md) records; the next branch to take a number should
  > check `main` rather than its own base.

## Context

When the-loop's own machinery fails, the evidence is already in the event log — and
until now, that is where it stayed.
[#240](https://github.com/MadaraUchiha-314/the-loop/issues/240) was the archetype: a
read-only tmux observer broke every `send-keys`, the poller retried and gave up
permanently, and the whole story sat in `events.jsonl` as `dispatch.failed` ×3 →
`poll.comment_failed (will_retry: false)` until a human replayed the file and wrote the
issue by hand. The ticket for issue-242 asks the-loop to do that itself: detect its own
errors, debug them in an isolated agent harness, and post a well-formed report to
the-loop's tracker — opt-in and off by default, with **all** PII and environment data
redacted, labeled `the-loop: self-diagnosed`, and never self-armed.

Four questions had to be settled, and each had a tempting wrong answer.

## Decision

1. **Detection is a policy over event-log records, not an exception hook.** #240-style
   defects never surface as uncaught exceptions — the poll loop and the dispatch worker
   swallow-and-continue *by design*. The trigger set is therefore `level: error` plus
   terminal give-ups (`will_retry: false`), read from the log by a scanner: a watcher
   thread inside the two ingress daemons plus a manual `the-loop diagnose`. No fourth
   lifecycle service, no hook inside `eventlog.emit`.
2. **The diagnosis agent is a critic-shaped one-shot.** `critics.run_critic` already is
   "one agent, one process, one JSON envelope, no shell, under a timeout"
   (decision-043); self-diagnosis feeds it a synthetic entry rather than growing a
   second spawn mechanism. The run is isolated: a private temp directory, no work-item
   session, no ticket context.
3. **Redaction is an allow-list first, a scrubber second.** The dossier — the only text
   that reaches the agent's prompt *or* the issue — copies a closed set of named fields
   (event types, levels, enums, counters); free text passes a scrubber (home, username,
   hostname, paths, e-mails, tokens, sensitive env values). This is `excerpt.py`'s
   argument ([decision-086](decision-086.md)) re-won: a deny-list rots as fields are
   added; an
   allow-list makes the safe outcome the default. Work-item refs and repository names
   are deliberately **not** allow-listed — an operator's private repo name is
   environment data.
4. **"Never armed" is achieved by omission, then enforced anyway.** Nothing applies
   `routing.autoExecuteLabel`, nothing posts a control keyword, nothing records an
   arming — and on top of that, control keywords in the composed body are visibly
   defanged (the agent's prose may legitimately mention `the-loop start`, and
   `parse_command` matches anywhere in a body), and the body carries the self-authored
   marker so both ingress paths drop it (issue-104). Storms are bounded by fingerprint
   dedup, a retry cap per fingerprint, a rolling daily cap that defers rather than
   drops, and a per-scan lock.

## Consequences

- the-loop's deployments can feed its own tracker: bugs like #240 arrive as issues with
  a debugged hypothesis and a suggested fix, at the cost of one agent run per new
  failure fingerprint.
- Publishing is consent-gated twice: the operator must set `enabled: true`, and
  `the-loop diagnose --dry-run` shows exactly what would leave the machine before they
  do.
- Prompt-injection risk is accepted and documented rather than pretended away: a
  crafted error string reaches the diagnosis agent's prompt. The agent runs isolated,
  its output is treated as untrusted (scrubbed, defanged, self-marked), and the feature
  is opt-in precisely because the residual risk is the operator's to take.
- Cross-deployment dedup is out of scope: two machines hitting the same bug may each
  file once; the label keeps triage cheap.

## Alternatives considered

Recorded with reasons in
[`docs/specs/issue-242/design.md`](../specs/issue-242/design.md#alternatives-considered):
an `eventlog.emit` hook, a fourth lifecycle service, a `create-issue` graph-integration
op, deny-list-only scrubbing, posting the dossier when the agent fails, and searching
GitHub for duplicates before filing.
