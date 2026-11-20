---
type: testing-plan
phase: test-planning
workItem: issue-549
status: approved
approvedBy: ["MadaraUchiha-314"]
overrides: {}
---

# Testing plan: a better Slack collaboration experience

> Derived from the approved [`requirements.md`](requirements.md) and the draft
> [`design.md`](design.md). It is reviewed with the design at `design-approval`, and
> completed at `verification`. **This file is executable content:** it names commands
> an agent will run. Credentials appear by reference only.

## The short version

Most of this change is proved offline, with three layers carrying the weight:

- **Unit tests (T1)** cover each component: placement, the short form, the renderer
  and splitter, the identity key, the status reactor, the recap and the bookkeeping
  filter.
- **Integration scenarios (T2)** drive the Slack channel against a recording client.
  They prove whole deliveries: room versus central channel, the lowercased-ref gate,
  a room press, an outbox replay, and progress edits.
- **Abuse-case tests (T8)** give one negative test to each of the nine abuse cases.

Slack does not document two behaviours, so they are proved **live**, against the
operator's Slack workspace, by an opt-in test (T4):

- how its `markdown` block draws tables and treats defused sequences;
- whether an edit keeps link previews off.

**Review closely:** T4's environment, because it posts to a real workspace, and T10,
because existing configs and split records must keep working.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | Placement table (R4); short-form choice, cap and built fallback (R3); defuse steps, splitter, code-block fallback and part marks (R1, R2); identity key (R11.2, R11.3); status-reaction state machine (R8); recap line (R9); bookkeeping filter (R10); mention selection and once-per-wait (R7); unfurl flags on every post (R5); deprecated-key warning (R1.3) | `cd cli && uv run python -m pytest -q tests/test_channels_*.py tests/test_room_policy.py tests/test_voice.py tests/test_graph_refs.py` |
| T2 | Integration (scenario) | yes | Whole deliveries through the channel with a recording Slack client, each test with a Gherkin docstring and `Requirement:` link | `cd cli && uv run python -m pytest -q tests/test_channels_integration.py tests/test_channels_declared_integration.py tests/test_channels_outbox_integration.py tests/test_bus_integration.py tests/test_gateway_slack_integration.py` |
| T3 | Contract (OpenAPI) | yes | `summary` on `POST /api/v1/work-items/comments` is in `docs/api-specs/openapi/the-loop.v1.yaml` and the routes match it | `cd cli && uv run python -m pytest -q tests/test_api_contract_parity.py` |
| T4 | End-to-end (live Slack) | yes | A real workspace draws the long form, tables and task lists; defused `<!here>` / `<@U…>` notify nobody; no unfurls after a post **or** an edit; reactions add and remove; parts arrive in order | `cd cli && THE_LOOP_LIVE_SLACK=1 uv run python -m pytest -q -m live_slack tests/test_slack_live.py` |
| T5 | UI / visual | yes | The design mock-up as locked, and the real Slack client showing the four shapes of the mock-up (room + thread, central reply, gate before/after press, recap) | manual: Slack client screenshots after T4; mock-up rendered with headless Chromium |
| T6 | Snapshot | n/a — block payloads are asserted structurally in T1/T2; a byte snapshot of Block Kit JSON would break on every unrelated field order change and prove nothing more | | |
| T7 | Performance | yes (bounded) | Abuse case 3: rendering a 65,536-character body finishes within a fixed bound and yields at most ⌈length ÷ budget⌉ + code-fallback parts | part of T8 |
| T8 | Security / abuse case | yes | One negative test per abuse case 1–9 in `design.md` §Security design | `cd cli && uv run python -m pytest -q -k "abuse or defuse or unauthorized or stale_press or casefold"` |
| T9 | Accessibility | yes (narrow) | Every message's `text` fallback is the short form, drawn as mrkdwn (R2.7), because screen readers and notifications read it | part of T1 |
| T10 | Migration / upgrade | yes | A config that still sets `maxChars` / `longMessages` validates and loads with one warning (R1.3); channel state holding two bindings that differ only in case resolves to the first (R11.3); outbox entries written before the event id replay without a double post | part of T1/T2 (`test_configschema.py`, `test_channels.py`, `test_channels_outbox.py`) |
| T11 | Manual exploratory | n/a at verification — a real press needs the daemon running this code, which happens only after merge. The press path is proved by T2 (R11.4) and T4 (live posting). After merge, the first gate approved from Slack on a real work item is reported on the ticket. | | |
| T12 | Full suite and lint (CI parity) | yes | Nothing else regresses; markdown, types and lint pass | `uv run pre-commit run --all-files` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.2, R1.3, R1.4 | deprecated keys ignored, one warning per process; `channels status` prints neither |
| T1 | R2.1–R2.6 | split falls between top-level blocks; never inside a table, code block, list item or word; oversized code splits at lines with the fence reopened; oversized table becomes code; `(n/m)` marks |
| T1 | R2.7, R2.8 | `text` fallback is the short form; markers stripped from both forms |
| T1 | R3.2–R3.6 | summary wins; runtime lead for runtime events; built fallback logs `channels.short_form_missing`; cap at 600 on a sentence |
| T1 | R4 | placement table: room, central thread, mention thread in a room, mention in central |
| T1 | R5 | every post and edit call carries `unfurl_links=false`, `unfurl_media=false` where accepted |
| T1 | R7 | awaiting message mentions resolved authorized users; none resolved → no mention; edit or re-announce → no second mention; non-awaiting → none |
| T1 | R8 | state per event; one reaction; old one removed; reaction failure does not fail delivery; never removes a reaction it did not add |
| T1 | R9 | recap only past 12 h since the last authorized human message; nothing changed → no line; counts toward the cap |
| T1 | R10 | `phase.started` / `phase.completed` and the session-started notice post nothing; the status reaction still updates |
| T1 | R11.2, R11.3 | identity key folds owner/repo only; host, provider, number exact; first-bound conversation wins |
| T2 | R4.1, R2.6 | `Scenario: a long comment in a declared room posts a short message and its long form in the thread` |
| T2 | R4.2 | `Scenario: the central channel gets the short form only` |
| T2 | R3.1, R3.8 | `Scenario: the-loop comment with a summary posts the summary to Slack and the whole text to GitHub` |
| T2 | R11.1, R11.2 | `Scenario: a gate opened under a lowercased ref posts its buttons in the work item's own thread` |
| T2 | R11.4 | `Scenario: a press in a declared room approves the gate` |
| T2 | R11.5 | `Scenario: a channel that cannot receive a press shows how to approve on GitHub` |
| T2 | R11.6 | `Scenario: a gate answered on GitHub edits its Slack message to show the outcome` |
| T2 | NFR idempotency | `Scenario: an outbox replay after a partial delivery posts only the missing parts` |
| T2 | R6.1, R6.2 | `Scenario: a progress edit in the central channel edits one message`; `Scenario: a progress edit with fewer parts deletes the surplus` |
| T2 | R10.1, R10.2 | `Scenario: a session-started notice reaches GitHub and not Slack` |
| T2 | R8, gateway | `Scenario: the gateway proxy forwards reactions.remove and chat.delete` |
| T3 | R3.1 | contract parity for `summary` |
| T4 | R2.1, R2.2, R5, R8, abuse 1–2 | live: table and task list drawn; `<!here>` and `<@U…>` inert; no `attachments` unfurl on the read-back message after post and after edit; reaction swap |
| T8 | abuse 1–9 | one test each, named in `design.md` §Security design |

## Verification environment

- **Repositories:** this repository only, at the PR branch.
- **Offline (T1–T3, T8–T10, T12):** no services. `uv sync --locked` once, then the
  commands in the matrix, run from the repository root as CI does.
- **Live Slack (T4, T5):**
  - **Workspace and app:** the operator's Slack workspace and the-loop app already
    configured on this machine (`the-loop channels status` shows it).
  - **Channel:** a dedicated test channel the bot is a member of, named by reference
    in `THE_LOOP_LIVE_SLACK_CHANNEL` (a conversation id). It must not be the central
    channel or any work item's room.
  - **Credentials, by reference only:** `THE_LOOP_SLACK_BOT_TOKEN` (posting),
    `THE_LOOP_SLACK_APP_TOKEN` (not needed by T4). Never written into this file or
    into evidence.
  - **Bring-up:**
    1. `the-loop channels status` (confirms the token is set).
    2. Export `THE_LOOP_LIVE_SLACK=1` and `THE_LOOP_LIVE_SLACK_CHANNEL=<id>`.
    3. Run T4.
  - **Tear-down:** T4 always deletes what it posted. Live checks are not for people
    to read, so nothing is kept. A run with `THE_LOOP_LIVE_SLACK_CLEANUP=1` deletes
    what an interrupted run left. T4 refuses a channel where the bot already posts
    for people.
  - **The live test is opt-in.** It carries a new pytest marker, `live_slack`, and
    skips unless `THE_LOOP_LIVE_SLACK=1`, so CI never posts to Slack.
- **Mock-up screenshot (T5):** `chromium --headless=new --screenshot=… --window-size=1200,2100
  file://$PWD/docs/specs/issue-549/design/slack-messages.html`.
- **If bring-up fails:** if the test channel or the token is unavailable, T4 and T5
  stay unticked, the reason goes under Verification results, and the author is asked
  on PR #550 for a channel id. The gate is not passed without T4: it is the only proof
  of R5 on edits and of Slack's handling of defused sequences.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T8, T9, T10 | test summary per command (counts, duration) | `unit.md` |
| T2 | `the-loop scenarios --glob 'cli/tests/test_*_integration.py' --format markdown` filtered to this work item's scenarios, plus run output | `integration.md` |
| T3 | contract test output | `contract.md` |
| T4 | live run output, plus read-back of each posted message via `conversations.history`/`conversations.replies`, reduced to block types, part order, `attachments` (unfurls) and reactions. Message ids redacted, no token. | `live-slack.md` |
| T5 | screenshots: the locked mock-up, and the Slack client for room + thread, central reply, gate before and after a press, recap | `ui/mockup.png`, `ui/room-thread.png`, `ui/central-reply.png`, `ui/gate-before.png`, `ui/gate-after.png`, `ui/recap.png` |
| T12 | pre-commit summary | `ci-parity.md` |

Before anything is committed, redact the following, and leave out any screenshot that
cannot be redacted:

- workspace, channel and member names and ids (replace them with `<channel>` and
  `<member>`);
- any token-shaped string;
- any message text that is not test content.

## Verification activities

- [x] T1 — `cd cli && uv run python -m pytest -q tests/test_channels_*.py tests/test_room_policy.py tests/test_voice.py tests/test_graph_refs.py`
- [x] T2 — `cd cli && uv run python -m pytest -q tests/test_channels_integration.py tests/test_channels_declared_integration.py tests/test_channels_outbox_integration.py tests/test_bus_integration.py tests/test_gateway_slack_integration.py`
- [x] T2 — `uv run the-loop scenarios --root "$PWD" --glob 'cli/tests/test_*_integration.py' --format markdown` (the trace above appears)
- [x] T3 — `cd cli && uv run python -m pytest -q tests/test_api_contract_parity.py`
- [x] T4 — `cd cli && THE_LOOP_LIVE_SLACK=1 uv run python -m pytest -q -m live_slack tests/test_slack_live.py`
- [x] T5 — mock-up screenshot (headless Chromium); the Slack client view moves to the post-merge report (replanned, see below)
- [x] T8 — `cd cli && uv run python -m pytest -q -k "abuse or defuse or unauthorized or stale_press or casefold"`
- [x] T10 — migration cases pass within T1/T2 (named in `unit.md`)
- [x] T12 — `uv run pre-commit run --all-files`

## Verification results

Run on 2026-11-20 at the PR branch (`93ba24e5` and its parent). Offline runs had
`THE_LOOP_CLI_CONFIG`, `THE_LOOP_INSTANCE` and `THE_LOOP_WORK_ITEM` unset, because
they point at the operator's own config, which some unrelated tests read.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | channels, room-policy, voice and refs unit tests | 824 passed | [`unit.md`](evidence/unit.md) |
| T2 | the five integration files | 111 passed | [`integration.md`](evidence/integration.md) |
| T2 | `the-loop scenarios --root "$PWD" …` | all 12 trace titles present (16 issue-549 scenarios) | [`integration.md`](evidence/integration.md) |
| T3 | `tests/test_api_contract_parity.py` | 7 passed | [`contract.md`](evidence/contract.md) |
| T4 | live Slack test in a dedicated test channel | 1 passed: table drawn as a `table` block, parts in order `(1/2)`, `(2/2)`, no previews after post **and** edit, defused sequences inert, reaction ⏳ → ⚙️ → none | [`live-slack.md`](evidence/live-slack.md) |
| T5 | mock-up rendered with headless Chromium | captured | [`ui/mockup.png`](evidence/ui/mockup.png) |
| T5 | Slack client screenshots of the four shapes | replanned: post-merge, with T11 | — |
| T7 | 64 KB body within the time bound and part count (in T8) | passed | [`unit.md`](evidence/unit.md) |
| T8 | `-k "abuse or defuse or unauthorized or stale_press or casefold"` | 334 passed | [`unit.md`](evidence/unit.md) |
| T9 | `text` fallback is the short form (in T1) | passed | [`unit.md`](evidence/unit.md) |
| T10 | config schema, channel state, outbox migration cases | 195 passed | [`unit.md`](evidence/unit.md) |
| T12 | `uv run pre-commit run --all-files` | exit 0: ruff, format, pyright, full pytest, markdownlint, config schema | [`ci-parity.md`](evidence/ci-parity.md) |

The first T4 run failed on two assumptions in the test, not in the feature:

- Slack stores a `markdown` block as the `rich_text`, `header` and `table` blocks it
  drew from it.
- `reactions.get` needs a scope the bot does not have.

The test was corrected (`93ba24e5`), and the second run passed. Details are in
`live-slack.md`.

**Replanned:** T5's Slack client screenshots. No browser logged in to the workspace
could be reached from the verifying session. The first T4 run kept its messages for
the author to look at, in the channel the author named, which is this work item's
room. The author asked on PR #550 that live checks never show in a Slack channel
people read. So:

- the kept messages were deleted;
- T4 no longer keeps anything, and refuses a channel where the bot posts for people;
- the Slack client view of the four shapes moves to the post-merge report on the
  ticket, with T11. There they are real messages about real work, not test posts.

What stands in for them before merge: the shapes are asserted structurally in T2,
and T4 read back the room shape (short message and long-form thread) from a real
workspace.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).

### 2026-11-19 — approved

**@MadaraUchiha-314** wrote:

approved
