---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#393"
status: draft
approvedBy: []
collaborators: [engineer, approver]
overrides: {}
---

<!-- Written per the `the-loop:writing` skill: front-load each section's
     conclusion, draw it rather than describe it (3+ named parts -> a mermaid
     diagram), and keep the formal registers formal (EARS, abuse cases,
     RFC-2119, API contracts, schema descriptions). No length limit — length
     follows the change; the test is whether a sentence can come out without
     losing information. A gated section stays even when it is empty. -->

# Requirements: five bugs from the end-to-end Slack test, 2026-09-19

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

[Issue #393](https://github.com/MadaraUchiha-314/the-loop/issues/393) is a distilled
write-up of an operator-driven, end-to-end run of one work item entirely through Slack
(`docs/reports/e2e-slack-test-2026-09-19.md`). Five bugs surfaced with a confirmed root
cause each; this work item fixes all five. (The same report's UX-rewrite proposal and
three feature requests are out of scope — see below.)

| ID | One line |
|---|---|
| B1 | A channel name never resolves in a large workspace — only its id does |
| B3 | A dropped Slack envelope (anything but `message`/`app_mention`) leaves no trace |
| B6 | A session's own `the-loop ask` never reaches the daemon's event bus when the daemon's config isn't at the default path |
| B8 | The first Slack answer after any human gate opens is always misread as a reply, not a gate answer |
| B9 | `the-loop critic run --timeout` above 120s is silently cut short by the CLI-to-service HTTP call, regardless of the value passed |

This work item also fixes one unrelated, already-public detail leak found while
auditing the repository for this contribution: `docs/specs/issue-377/bugfix.md` commits
a real internal hostname (`github.intuit.com/…`) in a worked example. It is redacted to
this project's existing fixture convention (`ghe.corp.example`, e.g.
`docs/decisions/decision-048.md`) alongside the five bugs, since both are "public repo
hygiene" fixes with no user-facing behavior change of their own.

## Requirements

### Requirement 1 — B1: resolve a Slack channel name in a large workspace

**User story:** As an operator declaring a Slack room by name in a large workspace, I
want `the-loop add-channel slack@#<name>` to find the bot's own channels, so that I am
not forced to hunt for a conversation id in the channel details pane.

**Root cause:** `SlackDirectory._read_conversations`
(`cli/the_loop/channels/directory.py:296-322`) resolves a name using only
`conversations.list`, paged at most `_MAX_PAGES = 20` times
(`cli/the_loop/channels/directory.py:443`). In a workspace with thousands of channels,
20 pages at 1,000 channels each is exhausted before reaching the bot's own — especially
private — channels, and a truncated listing is indistinguishable from "no such name".

#### Acceptance criteria (EARS)

1. WHEN a name is resolved via `SlackDirectory.conversation_id` THEN the system SHALL
   query `users.conversations` (`types=public_channel,private_channel`, the
   conversations the bot is a member of) before falling back to `conversations.list`.
2. IF `users.conversations` resolves the name THEN the system SHALL NOT call
   `conversations.list` for that lookup.
3. IF `users.conversations` does not resolve the name THEN the system SHALL fall back to
   the existing `conversations.list` pagination, for a public channel the bot has not
   joined.
4. IF the `conversations.list` fallback pagination is exhausted (`_MAX_PAGES` reached)
   while a `next_cursor` is still present THEN the system SHALL record that the listing
   was truncated, distinguishably from "the name does not exist" in whatever the caller
   surfaces (log line at minimum; see Requirement 1a below for the operator-facing
   half of this).

### Requirement 1a — B2 (related): a refused control keyword explains itself on the thread

**User story:** As an operator whose `add-channel` keyword was refused, I want the
refusal reason on the ticket thread, so that I do not have to read the daemon's log to
find out why.

> This is `B2` in the report — filed alongside B1 because the report's own B1 write-up
> depends on it for a good error message, and the fix is a two-line addition to the
> existing `control.rejected` path. Not a new requirement id; folded in here to avoid a
> requirement with no acceptance criteria of its own.

#### Acceptance criteria (EARS)

1. WHEN a control keyword is refused (`control.rejected`) THEN the system SHALL post one
   short, self-marked reply on the same thread quoting the rejection reason, the same way
   the Slack path already does for a collaborator's refused binding act.

### Requirement 2 — B3: an ignored Slack envelope is observable, not silent

**User story:** As an operator debugging why a mention or button press never arrived, I
want the listener to log every envelope type it declines to handle, so that "nothing
happened" is diagnosable from the log rather than indistinguishable from an app
misconfiguration.

**Root cause:** the Socket Mode `handle()` closure
(`cli/the_loop/channels/slack.py:2538-2542`) does
`if event.get("type") != "message": return` with no log line — any event type Slack
delivers that is not `message` or `app_mention` (already handled above it) vanishes
without a trace. The report also surfaced a second, non-code cause: two the-loop
instances holding a Socket Mode connection to the **same** Slack app/token silently
split event delivery between them (Slack delivers each envelope to exactly one
connection) — this is documented Slack behavior, not a the-loop defect, and is handled
by a warning rather than a code fix (Requirement 2c).

#### Acceptance criteria (EARS)

1. WHEN the Socket Mode listener receives an `events_api` envelope whose event type is
   neither `message` nor `app_mention` THEN the system SHALL log it at `debug` level,
   naming the event type, before returning.

### Requirement 2b — B3 related: `channels status` states what it cannot verify

**User story:** As an operator running `the-loop channels status --probe`, I want it to
say plainly that it cannot verify the app's event *subscriptions* (only its OAuth
*scopes*), so that a passing probe is not mistaken for proof that mentions will arrive.

#### Acceptance criteria (EARS)

1. WHEN `the-loop channels status --probe` prints its scope findings THEN the system
   SHALL also print one line stating that event subscriptions cannot be verified from
   the Slack API, and suggest confirming with `@the-loop help`.

### Requirement 2c — B3 related: warn when a second listener may share one Slack app

**User story:** As an operator running two the-loop instances against the same Slack
app, I want a warning that a second Socket Mode connection on one app-level token
silently halves event delivery, so that I do not spend an end-to-end test discovering it
by trial and error.

#### Acceptance criteria (EARS)

1. WHEN the Socket Mode listener starts THEN the system SHALL log a one-time warning at
   startup stating that Slack delivers each Socket Mode envelope to exactly one
   connection, so a second the-loop instance's listener sharing the same app-level token
   will silently receive roughly half of all inbound events.

> No live detection is required (the report's F2 — a cross-instance heartbeat check —
> is a feature request, out of scope here); a static, always-shown warning is sufficient
> to close the report's "document it, at minimum" ask.

### Requirement 3 — B6: a spawned session's own events reach the daemon's bus

**User story:** As an operator running the daemon from a non-default config path, I want
a session it spawns (and that session's `the-loop ask`) to publish to the same event bus
the daemon reads, so that `session.awaiting_input` — and everything else the session
publishes — actually reaches Slack and the dashboard.

**Root cause:** `TmuxRunner.spawn`/`_spawn` (`cli/the_loop/runner.py:379-390`) exports
only `INSTANCE_ENV_VAR` and `WORK_ITEM_ENV_VAR` into a spawned tmux session's
environment — never `CLI_CONFIG_ENV` (`THE_LOOP_CLI_CONFIG`,
`cli/the_loop/cli_config.py:42`). A session with no inherited `THE_LOOP_CLI_CONFIG`
resolves the default `~/.the-loop/cli-config.yaml` (absent, or a bus nobody subscribes
to) instead of the daemon's own resolved config, wherever the operator keeps it. The same
class of fix already exists for the control-plane **service**'s own child process
(`cli/the_loop/core/lifecycle.py:154`, via `cli_config.child_env()`,
`cli/the_loop/cli_config.py:152-165`) — the tmux spawn path never adopted it.

#### Acceptance criteria (EARS)

1. WHEN the runner spawns (or resumes) a tmux session for a work item THEN the system
   SHALL export `THE_LOOP_CLI_CONFIG`, set to the daemon's own resolved config path, into
   that session's environment — the same value `cli_config.child_env()` computes for the
   service's own child process.
2. IF the daemon's own config was resolved from the default path (no explicit `--config`
   or `$THE_LOOP_CLI_CONFIG`) THEN the exported value SHALL still be that default path,
   absolutized — so a session's behavior does not depend on how the daemon happened to be
   started.
3. WHEN `the-loop ask` (or any other event a session publishes) resolves its config THEN,
   given Acceptance Criterion 1, the system SHALL publish to the same event bus the
   daemon itself reads and dispatches from.

### Requirement 3a — B6 related: `the-loop ask` warns when it publishes to nothing

**User story:** As a session asking a question through `the-loop ask`, I want a warning
on the ticket when the event I just published has no subscribed channel, so that the
person on the other end is not left assuming Slack was told.

#### Acceptance criteria (EARS)

1. WHEN `the-loop ask` publishes `session.awaiting_input` and the publish result reports
   no channel subscribed to that event (an empty `channels: []` outcome, the same signal
   `sideeffects.notify` already detects) THEN the system SHALL post one additional short
   line on the ticket saying the question was recorded but not delivered to any channel.

### Requirement 4 — B8: the first Slack answer after a gate opens is read correctly

**User story:** As a reviewer answering a `phase-approval-pending` request in Slack, I
want my first reply to be read as the gate answer it is, so that I do not have to send
the same approval twice.

**Root cause:** entering a human-actor node
(`cli/the_loop/graph/runtime.py:1147-1170`) calls `state.enter(target)` and runs the
node's entry chain — which is what publishes `phase-approval-pending`
(`cli/the_loop/graph/hooks/sideeffects.py`'s `notify` hook) — but never calls
`state.park(...)`. Parking happens later, only inside `advance()`'s `WAIT` branch
(`cli/the_loop/graph/runtime.py:1073-1076`), which runs on the **next** evaluation —
triggered by the next inbound event, which is the human's first reply itself.
`GraphContext.at_human_gate` (`cli/the_loop/graphlink.py:272-274`) already treats both
`"waiting"` and `"parked"` as a gate, but `_context_from`
(`cli/the_loop/graphlink.py`, the `elif state.parked:` branch) can only assign either
status once `state.parked` is set — until then a freshly-entered human node's status
falls through to `"in-progress"`, and `_at_human_gate` (`inbound.py:157-194`) reads
`False`. The first reply that arrives is thus classified `work-item.reply`, not
`gate.feedback`.

#### Acceptance criteria (EARS)

1. WHEN the graph enters a human-actor node THEN the system SHALL park that node
   (`state.park(target, …)`) in the same step that runs the node's entry chain and
   publishes its `*-pending` notification, before any inbound event is processed against
   it.
2. WHEN an authorized Slack reply arrives immediately after a `phase-approval-pending` (or
   any other human-gate) notification — with no intervening reply — THEN the system SHALL
   classify it `gate.feedback`, not `work-item.reply`.
3. IF a work item has no session record yet, or the graph coupling is disabled THEN the
   system's existing "cannot tell" (`None`) behavior of `_at_human_gate` SHALL be
   unchanged — this requirement narrows the false-negative on a freshly entered gate, it
   does not touch the "no session"/"no graph" cases.

### Requirement 5 — B9: `the-loop critic run --timeout` is honored end to end

**User story:** As a session running a critic round with a high-reasoning model, I want
`the-loop critic run --timeout <N>` to actually wait `N` seconds for the service's
response, so that a critic that legitimately needs more than two minutes is not reported
as failed while it is still working.

**Root cause:** `the-loop critic run` is routed through the control-plane service
(`cli/the_loop/commands/critic_cmd.py`, via `client.routing.routed`). `args.timeout` is
placed inside the JSON request **body** (`cli/the_loop/commands/critic_cmd.py:209-227`)
and correctly reaches the server-side subprocess timeout
(`cli/the_loop/critics.py:433`, `limit = timeout if timeout is not None else
critic.timeout_seconds`, default `DEFAULT_TIMEOUT_SECONDS = 900.0`). But the **HTTP
request itself** — `Client.post` (`cli/the_loop/client/__init__.py:161-162`) — calls
`_request("POST", …, body=body)` with no `timeout=` argument, so it always falls back to
`_request`'s own default (`cli/the_loop/client/__init__.py:76`,
`timeout: float = 120.0`). The client's socket gives up at 120 seconds regardless of what
`--timeout` says, independent of whether the server-side subprocess is still legitimately
running.

#### Acceptance criteria (EARS)

1. WHEN `Client.post` (and `Client.get`, for symmetry) is called with an explicit
   `timeout` THEN the system SHALL use it as the underlying HTTP request's timeout,
   instead of `_request`'s built-in default.
2. WHEN `the-loop critic run --timeout <N>` is invoked and routed through the service
   THEN the system SHALL pass a client-side HTTP timeout of at least `N` (plus a fixed
   margin, so the client does not race the server's own subprocess deadline) to
   `Client.post`.
3. WHEN `the-loop critic run` is invoked with no `--timeout` THEN the client-side HTTP
   timeout SHALL be derived from the critic's configured `timeoutSeconds` (falling back
   to `DEFAULT_TIMEOUT_SECONDS`) with the same margin — never the unrelated `120.0`
   general-purpose default.
4. WHEN `the-loop critic policy` reports a critic's configuration THEN the system SHALL
   surface its effective timeout (already resolved server-side per critic), so an
   operator can see what a bare `the-loop critic run` will actually wait for.

### Requirement 6 — an existing internal hostname is redacted from the public repository

**User story:** As a maintainer of an open-source project, I want no internal/enterprise
hostnames in checked-in documentation, so that the public repository never carries
details specific to one company's internal infrastructure.

#### Acceptance criteria (EARS)

1. WHEN `docs/specs/issue-377/bugfix.md` is read THEN the system SHALL show the worked
   `session.spawned` example using this project's existing fixture host
   (`ghe.corp.example`, as used throughout `docs/decisions/decision-048.md` and
   elsewhere), not a real enterprise hostname.
2. WHERE this work item touches any other file, THEN the system SHALL NOT introduce any
   new internal hostname, organization name, username, Slack member/channel id, or
   internal tool/registry reference — every example uses this project's established
   fixture conventions (`ghe.corp.example`, `octo/repo`, `<placeholder>` markers per
   `docs/reports/e2e-slack-test-2026-09-19.md`'s own convention).

## Non-functional requirements

- **Backward compatibility:** none of the five fixes changes a public CLI flag, config
  key, or event schema. `Client.post`/`Client.get` gain an optional `timeout` parameter
  with the current behavior as its default when omitted (Requirement 5.1) — every
  existing caller is unaffected until it opts in.
- **Observability:** Requirements 2 and 2b/2c are entirely new log lines / probe output;
  they add no new metric or event type.
- **Test cost:** each requirement is unit-testable without live Slack or a live service —
  `SlackDirectory` and the Socket Mode `handle()` already take an injectable client/config
  in tests; `graph/runtime.py`'s node-entry path already has integration test coverage to
  extend; `Client`/`_request` already have a monkeypatch seam (`THE_LOOP_SERVICE_LOCAL`).

## Security considerations

> Threat-model-lite, captured with the requirements (always required). "No new attack
> surface" is a valid answer — written down and justified, never implied by omission.
> See `reference/security.md`.

- **Actors & trust:** the same actors as before these fixes — an authorized Slack user
  answering a gate (Requirement 4), an operator running CLI commands locally
  (Requirements 1, 2b, 2c, 5), and the daemon's own spawned session (Requirement 3). No
  new actor is introduced.
- **Trust boundaries & data:** Requirement 1's `users.conversations` call uses the same
  bot token and the same trust boundary (Slack's API, over the network) as the existing
  `conversations.list` call it supplements — no new credential, no new boundary.
  Requirement 4's fix moves *when* a node is marked parked, not *what* is trusted to
  answer a gate — `_at_human_gate`'s authorization check (an authorized user, per
  `routing.authorizedUsers`) is unchanged. Requirement 3 exports a config **path**, never
  a secret, into a spawned session's environment — the same class of value
  `child_env()` already exports for the service's own child.
- **Abuse cases (EARS):**
  1. WHEN an unauthorized Slack member replies immediately after a `phase-approval-pending`
     notification THEN the system SHALL still refuse to treat it as a gate answer — the
     Requirement 4 fix only changes the *parked* classification, not the *authorization*
     check `_at_human_gate`'s caller applies afterward.
  2. WHEN a name resolved via the new `users.conversations` call (Requirement 1) is one
     the bot is *not* actually a member of (a malformed or replayed API response) THEN
     the system SHALL NOT declare a channel it cannot post to — the existing
     `conversation_id`/`add-channel` refusal path (an unresolvable name refuses, per
     `directory.py`'s public contract) is unchanged and still the final authority.
- **Fail closed:** every fix here narrows a false negative (a real event silently
  dropped, a real gate answer silently misclassified) or removes an artificial timeout —
  none of them relaxes an existing authorization or validation check. Where a lookup
  still fails (Requirement 1's fallback exhausted, Requirement 5's service still
  unreachable) the existing refusal/error path is unchanged.

## Out of scope

- The report's UX-rewrite proposal (41 messages → 9, first-person tone, collapsed
  lifecycle notifications, phase selection as a real Slack control) — a separate,
  larger, design-heavy work item.
- **F1** (untick phases from a Slack reply), **F2** (a `the-loop doctor slack` /
  cross-deployment probe), **F3** (the daemon owning repository label setup on first
  contact) — feature requests, not bugs; separate work items.
- **B4** (missing `loop:*` labels on an uninitialized repo), **B5** (`read.mode` hot-reload
  vs. restart-required), **B7** (`graph status` reading a stale/wrong state file), **B10**
  (stale phase labels never removed), **B11** (tmux session removed despite
  `keepSessionOnClose: true`) — real bugs from the same report, deliberately left for a
  follow-up work item to keep this one reviewable.
- **O1–O9** — observations in the report that are neither bugs nor feature requests;
  none require code changes on their own.

## Open questions

None outstanding — all five root causes were confirmed by reading the current source
(see each requirement's **Root cause**), not just inferred from the report's hypotheses.
Requirement 4 and Requirement 5's root causes are more precise than the report's own
guesses (the report guessed `graphlink.py:272`'s status check itself was wrong; it is
correct — the bug is that nothing sets `"waiting"`/`"parked"` early enough. The report
guessed the critic *subprocess* timeout was hardcoded at 120s; it is not — the CLI's
HTTP call to its own service is).

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
