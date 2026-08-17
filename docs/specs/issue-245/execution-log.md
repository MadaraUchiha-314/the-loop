---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#245"
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: channels — back-and-forth user communication, starting with a Slack bot

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-17 | @MadaraUchiha-314 | Declared by the owner filing [#245](https://github.com/MadaraUchiha-314/the-loop/issues/245) and starting this cloud session on it. The ticket states the abstraction (channels), the first provider (a Slack bot, credentials in a configurable env var), both read transports (with and without polling), the source-of-truth rule and the magic-marker rule; the owner's comment adds "Use python SDK for slack". `brainstorming` skipped (the idea is not fuzzy); `design-critic-review` not selected (no critic configured in this repository). See *Deviations from the standard gates*. |
| requirements-definition | 2026-08-17 | pending — PR for this branch | `requirements.md`: six requirements; the inbound-authorization one (R5) written in formal register — it is the contract the security review gates on. |
| design | 2026-08-17 | pending — PR for this branch | Reuse-first: the issue-64/104 marker contract for loop prevention, `reply_session`'s fail-closed delivery, the issue-242 `redact` helpers for the mirror, the self-diagnosis watcher shape for the poll transport. Six alternatives recorded as rejected. Risk tier 4 (schema touched; inbound text gains a path into sessions). |
| test-planning | 2026-08-17 | pending — PR for this branch | 13 rows, 5 in scope; every `n/a` carries a reason; T4 (live Slack) and T11 (manual) deferred with reasons — no workspace in this environment. |
| tasks-breakdown | 2026-08-17 | | 12 tasks, two independent red roots. |
| implementation | 2026-08-17 | | TDD: red captured before the code (`evidence/red.md`). |
| verification | 2026-08-17 | | Every applicable activity ran; T4/T11 deferred with reasons (no Slack workspace here). |
| needs-review | 2026-08-17 | | |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#267](https://github.com/MadaraUchiha-314/the-loop/pull/267) | The whole work item — the spec chain and the feature. | open |

## Progress entries

### 2026-08-17 — mapped the seams before designing

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** mapped every surface the ticket touches. Outbound today is one shape:
  `integrations.slack` `post-message` (incoming webhook) fired by the graph's `notify`
  hook — write-only, unconfigurable per event. Inbound is GitHub-only: poller +
  webhook router, both dropping `SELF_COMMENT_MARKER` bodies before authz
  (issue-64/104). `the-loop ask` posts to the work item and emits
  `session.awaiting_input`; `reply_session` delivers into the tmux pane fail-closed
  (never spawns, refuses paused) and is the delivery seam a channel reply needs.
- **Found, and it decided the design:** the poller's `PollProvider` seam looks like
  the obvious inbound port but synthesises GitHub-webhook-shaped payloads — a Slack
  reply forced through it would impersonate a GitHub comment (actor semantics, authz
  and reactions all read GitHub keys). So channels got their own inbound pipeline that
  converges on the existing *reply* path instead of the *event* path.
- **Also decided:** the mirror is composed by the-loop (quoting the reply), so it may
  and must carry the marker; the reply reaches the session via `reply_session`, so the
  marker never suppresses processing — it suppresses *re*-processing. That is the
  ticket's "not processed twice" rule, implemented with zero new marker machinery.

### 2026-08-17 — red first, then one package

- **Phase:** implementation
- **Did:** wrote the 36 guarding tests first and captured their failure as
  [`evidence/red.md`](evidence/red.md); then the `channels/` package (`base`,
  `state`, `slack`, `broadcast`, `inbound`, `watcher`), the `ask_session`
  broadcast seam, the two daemon wiring lines, the `channels` verb, the schema
  section (both copies, byte-identical), the six `channel.*` event types, the
  `channels_dir` state-layout entry and the docs pages.
- **Two findings from the self-review rounds, both fixed before commit:**
  1. `eventlog.emit(event, ...)` collides with a field named `event` — the exact
     issue-242 lesson; the broadcast events carry `event_type` instead.
  2. `SlackBotChannel` bound `build_client` at construction time, which would
     have defeated both the test seam and a late-set env var; the factory is now
     resolved at call time, matching the token rule.
  A third suspicion — the state file racing between poll and socket transports —
  was checked and accepted: both load-modify-save through atomic replace, and
  the two transports are documented as alternatives (`read.mode`), not
  simultaneous readers.
- **Checkpoint/tests:** 2369 passed, 1 skipped; `make lint`, `make format-check`,
  `make typecheck`, `make validate` clean. Evidence in [`evidence/`](evidence/).

### 2026-08-17 — verification executed the plan

- **Phase:** verification
- **Did:** ran T1 (29 passed), T2 (7 passed), the T8 security selection
  (11 passed — empty allow-list denial, own-message drop, marker on every
  mirror, defang, token hygiene, disabled-section inertness), T12 (the full
  suite with every parity gate) and T13. Results recorded in
  [`testing-plan.md`](testing-plan.md) § Verification results; T4/T11 (live
  Slack) deferred with the reason stated there and a first-live-run activity
  called out for the reviewer.

## Deviations from the standard gates

- **`phase-selection` was answered by direct instruction, not by the checklist
  comment.** This work started from the owner's cloud-session request on the ticket
  rather than from `the-loop start`, so no checklist was posted and no
  `the-loop execute` reply exists. The owner's filed ticket is the authorization; the
  spec chain exists in full rather than being skipped.
- **The artifacts are `in-review`, not `approved`.** Nothing here has been through a
  human gate yet; the pull request carries the whole chain for review in one place. No
  phase claims an approval it does not have.
- **Risk tier 4 without a pre-implementation spec approval.** `autonomy.tiers["4"]` is
  `human-approves-pr`, so the gate this work needs is the PR itself — and
  `security.review.humanSignOffMinTier: 4` also applies: the PR briefing explicitly
  requests a named human security sign-off on the inbound-authorization and
  loop-prevention contracts (R4.5, R5.1, R1.3).
- **No `loop:<phase>` label on #245 from the harness** — the known #73 gap: a cloud
  session has no daemon. The phase state is this file.

## Capability docs

- **New:** [`docs/capabilities/channels.md`](../../capabilities/channels.md) — the
  capability's current-behaviour contract, indexed in
  [`capabilities.md`](../../capabilities/capabilities.md) and the VitePress
  sidebar. Minted product-feature shaped: the behaviour is one coherent surface
  (filter → fan out → read back → mirror → deliver), not a slice of an existing
  doc.
- **Updated:** [`docs/capabilities/observability.md`](../../capabilities/observability.md)
  (history row: the six `channel.*` event types) and
  [`docs/capabilities/cli.md`](../../capabilities/cli.md) (history row: the
  `channels` verb).
- **Decision:** [`decision-094`](../../decisions/decision-094.md), indexed in
  `decisions.md` — the channels-vs-integrations split, the mirror-first rule and
  the recorded deferrals.

## Documentation

- `docs/config/cli/channels-options.md` — the `channels` block, every leaf with
  Type and Default (P3–P5 gated), plus rows in `docs/config/cli/index.md` and
  `docs/config/index.md`.
- `docs/cli/commands/channels.md` — the verb (P1/P2 gated), its row in
  `docs/cli/commands/index.md`, and both VitePress sidebar lists.
- `docs/cli/state.md` — the channel conversation state: tree entry,
  classification row, its own section, and the `.gitignore` recipe line
  (mirrored into this repo's `.gitignore`, as the state-portability tests
  require).
- **Skill/reference docs:** `reference/observability.md` (the channel bullet in
  the event-log answers) and `reference/collaboration.md` § Where questions go
  (how channels compose with the interaction mode and the marker rule).
- **README:** one highlights line (`the-loop channels poll`) in the CLI section —
  the section is a deliberate highlights list, and a new conversation surface
  belongs in it the way `events --follow` does.
- **Config instances:** commented `channels:` blocks in `.the-loop/cli-config.yaml`
  and the shipped `skills/the-loop/templates/cli-config.yaml`.
