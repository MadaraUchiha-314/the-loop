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

- [x] T1 — `uv run --project cli python -m pytest -q cli`
- [x] T2 — `cd ui && bun run test`
- [x] T3 — `uv run --project cli python -m pytest -q cli/tests/test_stream_integration.py`
- [x] T4 — the OpenAPI parity test, plus `uv run python scripts/validate_config.py`
- [x] T6 — headless Chrome over CDP against `bun run dev`; screenshots + computed styles
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests/test_stream_integration.py -k capacity`
- [x] T9 — `uv run --project cli python -m pytest -q cli/tests/test_stream_integration.py -k abuse`
- [x] T10 — the assistive-technology tree asserted from the live DOM (no listening pass)
- [x] T11 — covered by T2; the migration cases are asserted explicitly in the evidence
- [x] T12 — live pass against a service built from this branch (service boundary)
- [x] T12 (browser) — measured: 0 requests while idle, then 283ms from append to refresh
- [x] T13 — a second service with `service.stream.enabled: false` answers 404 while healthy
- [x] T13 (browser) — the fallback state, **after fixing the defect this row found**
- [x] Full suite — `make check`, then `cd ui && bun run lint && bun run test && bun run build`
- [x] `the-loop scenarios` — all 13 of this work item's Gherkin scenarios are registered

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 — unit (Python) | `uv run --project cli python -m pytest -q cli/tests/test_api_stream.py` | pass — 31 passed | [`evidence/python-tests.md`](evidence/python-tests.md) |
| T2 — unit (UI) | `cd ui && bun run test` | pass — 144 passed (11 files) | [`evidence/ui-tests.md`](evidence/ui-tests.md) |
| T3 — integration, Gherkin | `uv run --project cli python -m pytest cli/tests/test_stream_integration.py -v` | pass — 14 passed in 17s, against real uvicorn on a loopback port | [`evidence/python-tests.md`](evidence/python-tests.md) |
| T4 — contract | `pytest cli/tests/test_api_contract_parity.py` + `scripts/validate_config.py` | pass — the served schema is the authored one; the 200 offers `text/event-stream` only | [`evidence/contract.md`](evidence/contract.md) |
| T8 — capacity | `pytest -k capacity`, and five live connections against a `maxSubscribers: 4` service | pass — REST answers with the stream full; the fifth connection is refused `503` before it exists | [`evidence/python-tests.md`](evidence/python-tests.md), [`evidence/live-stream.md`](evidence/live-stream.md) |
| T9 — abuse cases | `pytest -k abuse` | pass — 4 passed: capacity, malformed cursor, malformed filter, over-wide replay | [`evidence/python-tests.md`](evidence/python-tests.md) |
| T11 — migration | `cd ui && bun run test src/state/settings.test.ts` | pass — 13 passed, including the three pre-`refreshMode` store cases | [`evidence/ui-tests.md`](evidence/ui-tests.md) |
| T12 — live, service boundary | `curl -N` against a service built from this branch, seeded with issue-239 and **this session's own transcript** | pass — appended records arrive with byte-offset ids; a real `transcript` frame (1720 lines); **no `api.request` frames** despite the API traffic that produced them | [`evidence/live-stream.md`](evidence/live-stream.md) |
| T13 — older service | a second service, same build, `service.stream.enabled: false` | pass — `404` with the reason while `/health` answers `200` | [`evidence/live-stream.md`](evidence/live-stream.md) |
| Full suite | `make check`; `cd ui && bun run lint && bun run test && bun run build` | pass, **except five pre-existing Python failures** — four fail identically on `origin/main`, the fifth is load-flaky and filed as [#251](https://github.com/MadaraUchiha-314/the-loop/issues/251) | [`evidence/python-tests.md`](evidence/python-tests.md), [`evidence/ui-tests.md`](evidence/ui-tests.md) |
| Scenario registration | `the-loop scenarios --root "$(pwd)" --format markdown` | pass — all 13 scenarios listed with the requirement each proves | [`evidence/contract.md`](evidence/contract.md) |

| T6 — UI/visual | headless Chrome over CDP against the real bundle and a real service | pass — `overflow-y: auto`, `max-height: 495px` (= `clamp` at 900px), `position: sticky`, chat bar in viewport; both usable at 600px | [`evidence/browser.md`](evidence/browser.md), [`evidence/ui/`](evidence/ui/) |
| T10 — accessibility | the assistive-technology tree read from the live DOM | pass — `radiogroup` + `aria-label`, `role="status"` with the state **in the text**, trace panel `role="log"` + `tabindex="0"` | [`evidence/browser.md`](evidence/browser.md) |
| T12 — browser | streaming mode, idle page, another process appends one record | pass — **0 requests in 3 idle seconds**, then a refresh **283ms** after the append (against a 15s poll). Also proves R1.6/CORS parity, which no test client can | [`evidence/browser.md`](evidence/browser.md) |
| T13 — browser | the same page against the service with `stream.enabled: false` | **failed, then passed** — see below | [`evidence/browser.md`](evidence/browser.md) |

**T13 found a defect, which is what the row was for.** `EventSource` retries a *dropped*
connection, but a response it will not accept — a 404 from a service too old for the route
— is **terminal**: the browser closes the source and never tries again. The hook waited for
five consecutive failures before falling back, so against a 404 it got exactly one and sat
on `stream · reconnecting (1)` with a frozen board **forever** — the precise state R4.1
exists to prevent, reached through the mechanism meant to prevent it. Fixed (the transport
now reports whether the browser gave up) and covered by a regression test; the row then
passed, showing `stream unavailable · polling instead`.

**Not executed:** an actual screen-reader **listening** pass. What T10 asserts is the tree
a screen reader reads, not one particular reader's rendering of it — a real difference, and
the honest limit of what can be automated here.

*On the plan being wrong twice:* it assumed `TestClient` could read a stream (it buffers)
and that the browser rows needed the Chrome extension (Chrome plus CDP needs neither an
extension nor a new dependency). Both were replanned with the reason recorded rather than
worked around, and the second replan is what found the T13 defect.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.

### 2026-08-16 — approved

**@MadaraUchiha-314** — approved
