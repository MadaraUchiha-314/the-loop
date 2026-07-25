---
type: requirements
phase: requirements-definition
workItem: "issue-89"
status: draft
approvedBy: []
collaborators: [product-manager, engineer]
overrides: {}
---

# Requirements: a respawned tmux session resumes the same harness conversation

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). Tier 3 (`human-approves-pr`): spec + code are
> approved together at the PR.

## Introduction

When a tmux-hosted session dies unexpectedly (the harness crashed, someone ran
`tmux kill-session`, the pane exited and was retained by `remain-on-exit`), the
next routed event for that work item takes the issue-80 **respawn** path: the
dispatcher starts a fresh harness TUI under the same `loop-<slug>` name and
delivers the pending event as its boot prompt.

Investigation for [issue #89](https://github.com/MadaraUchiha-314/the-loop/issues/89)
("is this happening already?"): **it is not**. `Dispatcher._respawn_tmux` mints a
brand-new `uuid4()` and spawns `claude --session-id <new-uuid>`, so the respawned
TUI is a **blank conversation**. Everything the agent had learned working the item
— the spec it locked, the branch it created, the review feedback it had already
answered — is gone, and the boot prompt is a bare webhook event with no context.
The registry even records the new id, so the original conversation becomes
unreachable.

This is asymmetric with the `process` runner, which has always resumed:
`ClaudeCodeAdapter._resume_argv` passes `--resume <session-id>` on every event.
Only the interactive (tmux) path throws the conversation away. The harness id it
needs is already in the registry — the spawn pre-assigns it (`--session-id
<uuid>`), so the transcript exists under exactly that id and `claude --resume
<uuid>` (run in the session's recorded `cwd`, where Claude Code scopes resume
lookups) picks it back up.

The catch that shapes the design: `claude --resume <unknown-id>` **exits 1
immediately** ("No conversation found with session ID: …"). Since
`tmux new-session -d` succeeds as long as tmux starts, a resume of an
unresumable id would register a "successful" respawn whose pane is already dead —
and, with `remain-on-exit`, every later event would repeat that respawn forever
while reporting success. So resuming must be **verified**, with a fallback to
today's fresh spawn.

Cursor: `cursor-agent` cannot host a tmux session at all (no pre-assignable id,
`interactive_argv` raises `UnsupportedRunnerError`), so there is no cursor tmux
session to resume — per the issue's own instruction, this ships for Claude, with
the seam expressed on the adapter contract so a future cursor interactive mode
can opt in.

## Requirements

### Requirement 1 — a respawn continues the same harness conversation

**User story:** As an operator whose tmux session died mid-work-item, I want the
respawned session to pick up the same agent conversation, so that the agent does
not restart from zero on a work item it was halfway through.

#### Acceptance criteria (EARS)

1. WHEN a routed event finds a work item's tmux session missing or its pane dead
   AND the registered session records a harness session id AND that session's
   harness supports interactive resume THEN the system SHALL respawn the harness
   TUI with its **resume** invocation for that recorded id (`claude --resume
   <id>`), in the session's recorded `cwd`, delivering the pending event as the
   boot prompt exactly as today.
2. WHEN a respawn resumes THEN the registry entry SHALL keep the **same**
   `harnessSessionId` (so a later respawn resumes the same conversation again),
   the same `cwd`/`tmuxTarget`, and the carried-over `recentDeliveries` history.
3. WHEN `webhooks.ghWebhook.routing.tmux.resumeOnRespawn` is `false` THEN the
   respawn SHALL start a fresh conversation with a newly minted id, i.e. the
   pre-issue-89 behaviour SHALL remain available as an opt-out.
4. IF the session's harness has no interactive-resume support (the adapter
   raises `UnsupportedRunnerError` — today, anything that is not Claude Code)
   THEN the system SHALL fall back to a fresh spawn without failing the
   dispatch.
5. IF the recorded harness session id does not match the conservative
   `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` shape (alphanumeric first character, so a
   flag can never masquerade as an id) THEN the system SHALL NOT pass it to the
   harness and SHALL fall back to a fresh spawn — a registry file is local state,
   but the id becomes a command-line argument and is treated defensively.
6. The `process` runner SHALL be untouched: it already resumes on every event
   through `HarnessAdapter.resume`.

### Requirement 2 — a resume that cannot work must not swallow events

**User story:** As an operator, I want a respawn that fails to resume to still
deliver the event, so that an unresumable conversation degrades to a fresh
session instead of silently dropping work.

#### Acceptance criteria (EARS)

1. WHEN a resume respawn has been started THEN the system SHALL verify the new
   tmux session is **live** (pane not dead) after
   `webhooks.ghWebhook.routing.tmux.resumeProbeSeconds` and SHALL treat a dead
   pane as a failed resume.
2. WHEN the resume attempt fails — `tmux new-session` failed, or the pane died
   inside the probe window — THEN the system SHALL respawn a **fresh** session
   with a newly minted id, delivering the same pending event as its boot prompt,
   and the dispatch SHALL succeed on that fallback.
3. WHEN both the resume and the fresh fallback fail THEN the dispatch SHALL fail
   exactly as it does today: `dispatch.failed` emitted, the delivery id
   discarded so a redelivery/poll retries.
4. The probe SHALL NOT declare a healthy session dead: an unreadable pane state
   counts as **live**, per the existing `has_live_session` semantics.
5. WHEN `resumeProbeSeconds` is `0` THEN the system SHALL read the pane state
   immediately without waiting (used by tests and by operators who do not want
   the respawn to pause).
6. A resume fallback SHALL NOT post a second announcement comment — a respawn
   keeps the same `loop-<slug>` name, so issue-86's first-spawn-only rule is
   unchanged.

### Requirement 3 — observability

**User story:** As an operator debugging the trigger path, I want the event log
to say whether a respawn resumed or started fresh, so `the-loop events` explains
what the agent woke up with.

#### Acceptance criteria (EARS)

1. WHEN a session is respawned THEN the `session.respawned` record SHALL carry
   `resumed` (true when the conversation was resumed, false when a fresh id was
   minted) alongside the existing fields.
2. WHEN a resume attempt is abandoned for any reason (unsupported harness,
   malformed id, tmux failure, dead pane) THEN the system SHALL emit
   `session.resume_failed` at warning level with the work item, the harness, the
   attempted session id and the reason, and SHALL log it.
3. WHEN a respawn resumes successfully THEN the log line SHALL say so, naming
   the resumed harness session id and the attach command.

### Requirement 4 — configuration

**User story:** As an operator, I want resume-on-respawn to be configurable with
the rest of the routing policy, so I can turn it off without downgrading.

#### Acceptance criteria (EARS)

1. The feature SHALL be configured under `webhooks.ghWebhook.routing.tmux` as
   `resumeOnRespawn` (boolean, default **true**) and `resumeProbeSeconds`
   (number, default **2**), documented in `.the-loop/cli-config.schema.json` and
   present in the dogfood config and the packaged template.
2. Both keys SHALL hot-reload with the rest of the soft routing policy
   (`Dispatcher.reload`), taking effect on the next event.
3. Defaults SHALL keep the feature ON: continuing the conversation is the
   behaviour the issue asks for, and the verified fallback makes it safe.

## Non-functional requirements

- **Latency:** a resume respawn costs one extra `list-panes` probe and at most
  `resumeProbeSeconds` (default 2s) of waiting, inside the per-session dispatch
  worker that already serializes that work item's events. The dispatch timeout
  (`dispatchTimeoutSeconds`, default 1800s) is untouched.
- **No new runtime dependency.** tmux + the harness CLI, as today.

## Security considerations

> Threat-model-lite (`security.threatModel.required`).

- **Actors & trust.** Unchanged: webhook payloads remain untrusted, the session
  registry remains local operator-owned state. The one new value crossing into a
  command line is the recorded `harnessSessionId`, which the-loop itself minted
  (`uuid4`) and wrote — never anything payload-derived. AC1.5 still shape-checks
  it before use (the same defensive posture `announce.py` takes with
  owner/repo), so a corrupted or hand-edited registry file cannot smuggle extra
  argv into the harness invocation.
- **Trust boundaries & data.** No new data leaves the machine: no comment body,
  no network call, no new file. The resumed conversation lives where it already
  lived (the harness's own local session store, scoped to the recorded `cwd`).
- **Abuse cases (EARS).**
  1. WHEN a registry file carries a `harnessSessionId` containing shell
     metacharacters, or shaped like a flag (`--dangerously-skip-permissions`),
     THEN the system SHALL refuse to resume it and SHALL spawn fresh instead —
     the id can neither smuggle an option into the harness invocation nor reach
     a shell (`subprocess` is called without one).
  2. WHEN an attacker can trigger events for a work item THEN resuming SHALL NOT
     grant them anything a live session did not already grant: a live tmux
     session already pastes those events into the same continuing conversation,
     so resume restores parity rather than widening it.
- **Context continuity is the point, and it is a two-edged one.** A resumed
  agent still remembers untrusted payload excerpts from earlier events. That is
  identical to the live-session path (events are pasted into one long
  conversation), and the existing guards — `authorizedUsers` fail-closed, the
  "UNTRUSTED data" framing in the prompt template — are what bound it. No new
  boundary is crossed; this is written down rather than implied.
- **Fail closed on doubt.** Every doubt inside the resume path resolves to the
  *status quo ante* (a fresh session), never to a silently-succeeded dispatch:
  an unverifiable resume is abandoned, logged and retried as a fresh spawn, and
  if that fails too the delivery is released for retry.

## Out of scope

- Cursor interactive/tmux sessions — `cursor-agent` has no pre-assignable
  session id, so it cannot be tmux-hosted in the first place (issue-32); the
  adapter seam is there for when it can.
- Resuming a session whose *work item* was closed (`sessions close`), or
  reviving a retained session from `sessions attach` — a closed session is not a
  routing target.
- Any change to the `process` runner, which already resumes.
- Recovering the conversation of a session spawned **before** this change with a
  crashed harness that never wrote a transcript — unresumable by construction;
  the verified fallback covers it.

## Open questions

None blocking. Two defaults are the reviewer's call and are called out in the PR
briefing: `resumeOnRespawn: true` and `resumeProbeSeconds: 2`.
