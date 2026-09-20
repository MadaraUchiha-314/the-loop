---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#393"
status: in-review            # draft | in-review | approved — reviewed with design.md at the design-approval gate on the spec PR
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: the Slack room becomes a colleague — five e2e bugs, the message rework, and deployment self-service

> Derived from the approved [`requirements.md`](requirements.md) and
> [`design.md`](design.md), before `tasks.md`. Authored at `test-planning`, completed at
> `verification` — plan and record in one diff.
>
> **This file is executable content.** Credentials appear **by reference only**. The
> live-run environment is named **by placeholder only** (the redaction convention of
> [the e2e report](../../reports/e2e-slack-test-2026-09-19.md)): this repository is
> public, and the operator's deployment is not.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | RoomPolicy rule table (one test per rule); voice rendering (emoji, first-person, no header in rooms, single signature); directory membership-first resolution + truncated refusal wording; critic `--timeout` threading regression; `Event.summary` escape/cap/mention-stripping; skip-grammar parsing; `ensure_labels` idempotence + declared-repo guard | `cd cli && uv run pytest tests/ -k 'not integration'` |
| T2 | Integration (scenario) | yes | routing behaviour end-to-end in-process, Gherkin-docstringed per `testing.gherkinDocstrings: required` | `cd cli && uv run pytest tests/ -k integration` |
| T3 | Contract (OpenAPI) | n/a — no control-plane API surface changes; `docs/api-specs/openapi` untouched | | |
| T4 | End-to-end (live) | yes | the report's timeline re-run against a real daemon + Slack workspace: all five bug fixes observed live, the room's message shape recorded (count as trend evidence, no numeric gate — owner decision) | operator deployment, by placeholder (below) |
| T5 | UI / visual | yes | the locked design mockup renders at phone (~400 px) and desktop widths; screenshots per `design.uiArtifacts.screenshotEvidence`; live-run screenshots of the redesigned room states | local browser + the live run |
| T6 | Snapshot | n/a — the voice table's exact strings are asserted directly in T1; a snapshot layer would duplicate it | | |
| T7 | Performance / load | n/a — no hot path changes; RoomPolicy is one in-memory decision per event on an already-serialized per-item path | | |
| T8 | Security / abuse case | yes | one negative test per abuse case in `requirements.md` §Security (unauthorized gate answer; unauthorized checkbox submit; hostile summary; hostile skip-grammar; undeclared-repo labels) | `cd cli && uv run pytest tests/ -k 'abuse or unauthorized'` (markers set in tasks) |
| T9 | Accessibility | n/a — the surface is Slack's own client; our obligation (typed-grammar parity with every button, R9.3) is proven functionally in T2 | | |
| T10 | Migration / upgrade | yes (small) | `channels.slack.room.style` schema addition validates; absent key ⇒ `agentic` default; a pre-change `ChannelState` file loads and degrades to classic delivery, never crashes | `cd cli && uv run pytest tests/ -k 'config or state'` |
| T11 | Manual exploratory | yes | the operator drives the live run from a phone-shaped mindset: are the room's messages readable as a conversation (the report's core complaint) | the T4 run, operator judgment recorded |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1 | membership listing resolves a private channel a 20-page workspace listing misses; truncated listing refuses with "truncated", not "no such name" |
| T1 | R5 | `--timeout 300` reaches `subprocess.run` verbatim; default is 900; timeout error names the flag |
| T1 | R6, R7, R11 | each RoomPolicy rule row; voice table: one emoji, first person, no header in rooms, one signature |
| T1 | R8 | summary present ⇒ leads the message; absent ⇒ digest fallback; oversized/markup summary ⇒ escaped/capped |
| T1 | R9 | `execute without 1,3` / `skip brainstorming` parse; unknown phase refused with reason |
| T1 | R13 | `ensure_labels` creates only missing labels; undeclared repo untouched |
| T2 | R4 (B8) | `Scenario: the first authorized answer after a gate publishes advances the gate` — reproduces the e2e sequence (`graph complete` into a human node, one inbound answer, no prior evaluation) |
| T2 | R3 (B6) | `Scenario: a spawned session publishes to the daemon's bus` — spawn env carries the config path; `Scenario: ask warns when the bus names no channels` |
| T2 | R6.2 | `Scenario: a gate's mirror and lifecycle lines are suppressed after its pending message` |
| T2 | R6.3/R10 | `Scenario: progress edits in place within a phase`; `Scenario: an approval acknowledgement threads under the approval request` |
| T2 | R9 | `Scenario: checkbox submission composes the signed execute`; `Scenario: without an interactivity grant the message points at the GitHub checklist` |
| T2 | R12 | `Scenario: the session's question reaches the room with its default as a button`; `Scenario: a session-authored summary suppresses the template announcement` |
| T2 | R2 | `Scenario: an ignored envelope logs its type and reason`; `Scenario: a refused keyword posts its reason as a marked reply` |
| T8 | §Security 1–5 | the five negative scenarios, one per abuse case |
| T10 | NFR config compat | schema round-trip; legacy `ChannelState` degradation |
| T4 | all bug fixes + rework | live re-run of the report's timeline (below) |
| T5 | R6–R12 | mockup screenshots (2 widths); live room screenshots per redesigned state |

## Verification environment

- **Repositories:** this repo (fixes under test, installed as the CLI from the working
  tree: `cd cli && uv pip install -e .`); a **throwaway test repository**
  `<ghe-host>/<owner>/<test-repo-2>` on the operator's GitHub host, created for this
  run with one seeded work item mirroring the report's issue #1 ("add a repository
  health check").
- **Services / containers:** the operator's the-loop daemon (poller + Slack Socket Mode
  listener) restarted on the patched build; one Slack workspace with the `the-loop`
  app installed and a private test room `#<test-room-2>`; a second instance is
  **deliberately started on the same app token** for the T4 step that proves the F2
  doctor's second-consumer probe, then stopped.
- **Fixtures & data:** the ops-repo config declaring `<test-repo-2>` under
  `repositories` and the room under `channels`; the test repo starts with **no**
  `loop:*` labels (that is R13's fixture, not an omission).
- **Credentials:** by reference only — the daemon host's existing `SLACK_BOT_TOKEN` /
  `SLACK_APP_TOKEN` environment and the operator's `gh` login on `<ghe-host>`. Nothing
  is copied into this repository.
- **Bring-up:** operator-side: install the patched CLI, `the-loop restart`, confirm
  `the-loop status` and `the-loop doctor slack` are green, seed the test issue.
  **Tear-down:** `the-loop stop` the second instance, close the test issue, archive the
  room.
- **If bring-up fails:** record under Verification results, leave T4/T5-live/T11
  unticked, escalate — the gate does not pass on an environment that never came up.
- **Redaction rule (hard):** every capture from this environment — logs, transcripts,
  screenshots, message text — is rewritten to the report's placeholder convention
  (`<ghe-host>`, `<owner>`, `<test-repo-2>`, `<test-room-2>`, `<operator-login>`,
  `<bot-user-id>`, `<operator-slack-id>`) **before** it is written under `evidence/`.
  Raw captures never enter the working tree; screenshots are cropped/masked of
  workspace names, avatars and real ids. A capture that cannot be redacted is not
  committed — the results row says so instead.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1 | test summary (counts, duration) | `unit.md` |
| T2 | scenario table + run output | `integration.md` |
| T8 | abuse-case table + run output | `security-tests.md` |
| T10 | config/state compat output | `compat.md` |
| T4 | redacted timeline of the live run: per-bug before/after observation (B1 name resolution, B3 doctor detection, B6 question in the room, B8 first answer counts, B9 detached critic), the room's full message list with count | `live-run.md` |
| T5 | mockup screenshots (phone + desktop); redacted live-room screenshots: kickoff checkboxes, question w/ default button, gate w/ summary + threaded ack, edited progress message, PR-ready, done | `ui/mockup-{phone,desktop}.png`, `ui/live-{state}.png` |
| T11 | the operator's verdict, verbatim, beside the report's original verdict | `live-run.md` §verdict |

## Verification activities

- [ ] T1 — `cd cli && uv run pytest tests/ -k 'not integration'`
- [ ] T2 — `cd cli && uv run pytest tests/ -k integration`
- [ ] T8 — `cd cli && uv run pytest tests/ -k 'abuse or unauthorized'`
- [ ] T10 — `cd cli && uv run pytest tests/ -k 'config or state'`
- [ ] T4 — live re-run of the report's timeline on the operator deployment (bring-up
      above); observe each of B1/B3/B6/B8/B9 fixed at its original failure step;
      record the room's message shape
- [ ] T5a — mockup screenshots at ~400 px and desktop widths
- [ ] T5b — redacted live-room screenshots of the six redesigned states
- [ ] T11 — operator's readability verdict recorded

## Verification results

_Not yet executed._

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |

**Not executed:** —

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
