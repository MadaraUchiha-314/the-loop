---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#239"
status: approved             # locked by the authoring node; the human gate is
                             # `design-approval`, reading design.md and
                             # testing-plan.md together
approvedBy: []
overrides: {}
---

# Testing plan: stream the-loop's service to the control plane

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md), before
> `tasks.md` — each task's `_Test:_` names a row below. Authored at `test-planning`,
> completed at `verification`: one file, written once as a plan and once as a record.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. It needs no credentials, and none appear.

**What this plan is built around:** three of the four design decisions are only provable
by *observing a stream*, not by inspecting code. The `api.request` exclusion, the
`Last-Event-ID` replay and the `maxSubscribers` refusal each get a named integration test
that opens a real connection against a real service, because each of them is a
plausible-looking implementation away from being silently wrong. The rest of the matrix is
ordinary.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (Python) | yes | `stream_config` defaults and clamping; the cursor arithmetic (offset → replay slice, truncation, over-wide gap); the frame encoder's SSE bytes; the log tailer's partial-trailing-line buffering | `uv run --project cli python -m pytest -q cli` |
| T2 | Unit (UI, vitest) | yes | The invalidation map (`graph.*` → one ref, everything else → lists, unknown type → lists); the settings v1→refreshMode migration (R3.6); `useStream`'s state machine over a stubbed `EventSource`, including the five-failure fallback | `cd ui && bun run test` |
| T3 | Integration (scenario, Gherkin) | yes | The stream end to end against a live service: delivery, filtering, keep-alive, `Last-Event-ID` replay, `desync` on truncation, the `api.request` exclusion, `maxSubscribers` refusal, and release on disconnect | `uv run --project cli python -m pytest -q cli/tests/test_stream_integration.py` |
| T4 | Contract (OpenAPI) | yes | The generated document is valid OpenAPI 3.1 and describes `GET /api/v1/stream`, its `text/event-stream` media type and the three frame schemas (R1.7) | `uv run python scripts/validate_config.py` + the repo's OpenAPI validation step |
| T5 | End-to-end | n/a — there is no second system to drive. The "end to end" that matters here is browser↔service, which T3 covers on the service side and T6/T12 cover on the browser side; a third layer would re-run both with more setup and no new information. | | |
| T6 | UI / visual | yes | The rendered detail page: the chat bar reachable without scrolling, the trace panel scrolling inside its bounds, and scroll anchoring following the newest entry only when already there (R6). Plus the four connection-indicator states (R4.3) | `cd ui && bun run dev`, driven in Chrome; screenshots + one GIF |
| T7 | Snapshot | n/a — the repo keeps no snapshot suite, and the two rendered surfaces this item adds are better served by T6's screenshots, which a human reads. Adding a snapshot baseline now would create a second thing to update per CSS change with no reviewer benefit. | | |
| T8 | Performance / load | yes, narrowly | R5.1 and R5.3: with `maxSubscribers` connections open and idle, `GET /api/v1/health` still answers, and the tailer does one file read per tick rather than one per subscriber. Measured, not asserted as a feeling | `uv run --project cli python -m pytest -q cli/tests/test_stream_integration.py -k capacity` |
| T9 | Security / abuse case | yes | One negative test per row of `design.md` §Security design — capacity, malformed cursor, malformed filter, over-wide replay, and a subscriber that stops reading | `uv run --project cli python -m pytest -q cli/tests/test_stream_integration.py -k abuse` |
| T10 | Accessibility | yes | The refresh-mode radio group is keyboard-operable and announced as a group; the connection indicator is text plus dot, never dot alone, in an `aria-live` region; the trace panel is keyboard-scrollable and the sticky chat bar traps no focus | Manual keyboard + screen-reader pass over T6's dev server, recorded in the evidence file |
| T11 | Migration / upgrade | yes | A browser holding `the-loop:settings:v1` written before this change keeps its base URL and lands on a valid mode (`pollSeconds: 0` → manual, otherwise poll) — covered by T2, called out as its own row because it is the one thing that can silently break an existing viewer | `cd ui && bun run test` |
| T12 | Manual exploratory | yes | The point of the whole work item: an agent's turn appears on screen with no poll interval and no refresh press. Also the fallback path, forced by pointing the page at a base URL that refuses the stream | Chrome against a live `the-loop start`, recorded as a GIF |
| T13 | Backward compatibility (older service) | yes | The new control plane against a service **without** `/api/v1/stream`: the connect answers 404, the UI states that and falls back to polling rather than showing a dead board (R4.1). This repo ships both halves, so it is the one combination CI would otherwise never build | Manual, with `service.stream.enabled: false` standing in for the older service |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.5, R5.2, R5.3 | `stream_config` fills defaults from the schema; a cursor beyond EOF resolves to *truncated*; a gap wider than the replay window resolves to *replay-window*; a partial trailing line is buffered, not emitted |
| T2 | R2.1, R2.2, R2.4, R3.6, R4.2, R4.4 | invalidation map per event family; unknown event type → lists; two frames inside 250ms → one refresh; v1 settings migration; five consecutive errors → fallback |
| T3 | R1.1, R1.2, R1.3, R1.4, R1.5 | `Scenario: an appended event reaches an open subscriber` · `Scenario: a work-item filter excludes another item's events` · `Scenario: an idle stream receives a keep-alive` · `Scenario: a reconnect with Last-Event-ID replays exactly the missed records` · `Scenario: the control plane's own API requests never reach the stream` |
| T4 | R1.7 | the OpenAPI document describes `streamEvents` and validates |
| T6 | R6.1, R6.2, R6.3, R6.4, R6.5 | chat bar visible without scrolling; trace scrolls within bounds; arrival follows newest when pinned; arrival does not move a scrolled-back panel; both usable at 600px viewport height |
| T8 | R5.1, R5.3 | `Scenario: the REST surface still answers with the stream at capacity` |
| T9 | R1.6, abuse cases 1–5 | `Scenario: a stream connection beyond the configured maximum is refused` · `Scenario: a malformed cursor is refused rather than silently ignored` · `Scenario: a malformed work-item filter is refused rather than streaming everything` · `Scenario: a subscriber that stops reading is bounded and desynced, not buffered without limit` |
| T10 | R4.3, and the accessibility non-functional requirement | keyboard traversal of the radio group; the indicator announced on change; trace panel focusable and scrollable by keyboard |
| T11 | R3.6 | a v1 settings document keeps its base URL and gains a valid mode |
| T12 | R2.1, R2.3, R4.1 | a turn appears without a poll; the transcript panel updates; a service that refuses the stream degrades visibly |
| T13 | R4.1 | the new UI against a service that answers 404 for the stream |

**Not covered by an automated row, on purpose.** Requirement 1.6's CORS parity cannot be
proved by a test client: `httpx` and `TestClient` send whatever `Origin` they are told to
and do not enforce the response, because *enforcement is the browser's*. The design's
answer is structural — SSE is an ordinary `GET`, so the existing `CORSMiddleware` governs
it and there is no second code path to get wrong. T12's manual pass confirms it from a
real browser by loading the page from a disallowed origin; a passing unit test here would
prove only that the test client ignores CORS, which it does.

## Verification environment

- **Repositories:** this repository only. No second checkout, no external service.
- **Services / containers:** none beyond the-loop's own. T3/T8/T9 use FastAPI's
  `TestClient` against an in-process app with a temporary event-log path, so no port is
  bound and no daemon is started. T6/T10/T12/T13 need a real pair: `the-loop start` on the
  workstation and `cd ui && bun run dev` pointed at it.
- **Fixtures & data:** a temporary `events.jsonl` per test (`tmp_path`), appended to
  directly — the tests exercise the tailer, so writing through `eventlog.emit` would test
  the wrong half. T12 uses a real work item's session, this one included.
- **Credentials:** none. The service carries no in-app auth, the stream adds none, and no
  test needs a GitHub token.
- **Bring-up:** `uv sync` · `cd ui && bun install --frozen-lockfile`.
  For the browser rows: `the-loop start`, then `cd ui && bun run dev` (http://localhost:5173).
- **Tear-down:** `the-loop stop`; the dev server is `Ctrl-C`. Temporary logs go with `tmp_path`.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate — an environment that will not come up does not pass
  the gate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T3, T8, T9 | command + pytest output, one section per row | `python-tests.md` |
| T2, T11 | command + vitest output | `ui-tests.md` |
| T4 | validation command + output | `contract.md` |
| T6 | screenshots: chat bar in reach at a tall and a 600px-tall viewport; trace scrolled mid-list; the four connection states | `ui/detail-*.png`, `ui/conn-*.png` |
| T6, T12 | one animated capture each — both are *flows*, not states: the panel following a new entry, and a turn arriving with no poll | `ui/trace-anchor.gif`, `ui/live-turn.gif` |
| T10 | the keyboard/screen-reader pass, step by step with what was announced | `accessibility.md` |
| T13 | screenshot of the fallback banner + the console showing the 404 | `ui/fallback-404.png` |
| — | the full suite, as CI runs it | `full-suite.md` |

**Redaction before committing.** These captures show a real control plane: work-item refs,
`cwd` paths under `/Users/…`, tmux target names and transcript text. Paths are cropped or
masked in every screenshot, and the transcript shown is this work item's own. A capture
that cannot be redacted is not committed — the row says so instead.

## Verification activities

- [ ] T1 — `uv run --project cli python -m pytest -q cli`
- [ ] T2 — `cd ui && bun run test`
- [ ] T3 — `uv run --project cli python -m pytest -q cli/tests/test_stream_integration.py`
- [ ] T4 — the OpenAPI validation step, plus `uv run python scripts/validate_config.py`
- [ ] T6 — Chrome against `bun run dev`; screenshots and `trace-anchor.gif`
- [ ] T8 — `uv run --project cli python -m pytest -q cli/tests/test_stream_integration.py -k capacity`
- [ ] T9 — `uv run --project cli python -m pytest -q cli/tests/test_stream_integration.py -k abuse`
- [ ] T10 — keyboard + screen-reader pass, recorded in `accessibility.md`
- [ ] T11 — covered by T2; assert the migration case explicitly in the evidence
- [ ] T12 — live pass against `the-loop start`; `live-turn.gif`
- [ ] T13 — the same page against `service.stream.enabled: false`; `fallback-404.png`
- [ ] Full suite — `make check`, then `cd ui && bun run lint && bun run test && bun run build`
- [ ] `the-loop scenarios --format markdown` — the Gherkin scenarios above are registered and queryable

## Verification results

*Not yet executed.*

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |

**Not executed:** *none yet.*

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.

### 2026-08-16 — approved

**@MadaraUchiha-314** — approved
