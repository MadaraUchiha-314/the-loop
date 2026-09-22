---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#409"
---

# Verification: the bus keeps an outbox, and `status` reads it

> The `verification` node's record, against
> [testing-plan.md](../testing-plan.md)'s matrix. Run in this container at
> commit `0dd2bf4`, on the repository checkout, with `uv` 0.12.17 installed over the
> image's own 0.8.17 (`pyproject.toml` requires `>=0.12,<0.13`).

## Results

| # | Type | Command | Outcome |
|---|------|---------|---------|
| T1 | Unit | `cd cli && uv run python -m pytest -q tests/test_channels_outbox.py` | **pass** — 19 tests (10 of them T1's: the entry's fields, the round trip, a foreign file, four corrupt shapes, the unwritable path, the cap, the summary) |
| T2 | Unit | same file | **pass** — the drain's 8: delivered-and-removed, refused-and-backed-off, the backoff's own arithmetic, the budget, the raising provider, source/subscription skipping, the unreadable entry, the empty queue |
| T3 | Integration | `cd cli && uv run python -m pytest -q tests/test_bus.py` | **pass** — `publish` queues under the three guards and nothing under the other three; a raising `remember` leaves the `PublishResult` untouched |
| T4 | Integration | `cd cli && uv run python -m pytest -q tests/test_channels_outbox_integration.py` | **pass** — the report's walk: ask with a refusing Slack → ticket written, `asked: true`, exit 0, one entry queued, the verb's note, `channels_posted: 0`, `channel.undelivered` at `warning` with no question text in it; then recovery → one drain delivers, the room has the question, `channel.delivered_late`, the queue empties |
| T5 | Integration | same file | **pass** — `status_all`'s `channelDelivery`, the line's count/age/error, the "nothing is draining them" variant, the unreadable-outbox path, and `ok` unmoved |
| T6 | Contract | — | **n/a as planned** — no HTTP surface changes; nothing in `docs/api-specs/openapi` describes the status document's fields |
| T7 | Performance | `cd cli && uv run python -m pytest -q tests/test_channels_outbox.py -k "cap or budget"` | **pass** — 3 selected: 203 `remember` calls leave 200 entries and three drop warnings; one cycle attempts exactly its budget; the backoff is asserted with an injected clock, never a wall-clock wait |
| T8 | Security | `cd cli && uv run python -m pytest -q tests/test_channels_outbox.py tests/test_state_portability.py` | **pass** — the drain fails the test if it reaches `bus.publish`; the `channel.undelivered` payload is asserted free of the question's text; the new path is declared local and documented (12 portability tests) |
| T9 | Migration | `cd cli && uv run python -m pytest -q tests/test_channels_outbox.py tests/test_eventlog.py` | **pass** — an absent outbox is an empty backlog everywhere; a file with unknown and missing keys loads; the drainer survives a raising cycle; `EVENT_TYPES` documents all three new events (the catalog-drift test) |
| T10 | Regression | `cd cli && uv run python -m pytest -q` | **pass** — 4517 passed, 1 skipped, 178s |
| T11 | Manual exploratory | — | **not run** — needs a real Slack workspace and a token to rotate; unavailable in this container. The scenario it would walk is T4, which runs against the real modules with the SDK client faked at its injection point |
| T12 | Documentation parity | `npx markdownlint-cli2@0.18.1` over the changed pages; `pytest tests/test_state_portability.py` | **pass** — 0 errors over 8 files; the state page classifies `<root>/channels/undelivered.json` as local, matching `GENERATED_PATHS` |

Lint and types, the rest of `make check`'s parity: `uv run ruff check cli hooks` — all
checks passed; `uv run ruff format --check cli hooks` — 353 files already formatted;
`uv run pyright cli` — 0 errors, 0 warnings.

## What the run proves, in one line each

- An event every channel refused is **on disk** before `publish` returns, with everything
  a later process needs to post it (T1, T3).
- The first drain after a channel recovers **delivers it**, and the queue empties (T2, T4).
- The operator's own `status` **names the backlog** until it is gone, and says when nothing
  is draining it (T5).
- The recovery path is bounded on all three axes — entries, posts per cycle, wait per entry
  (T7).
- A replayed entry **cannot reach the ledger** (T8), and the event log still carries no
  message text (T8).

## Activities checklist

- [x] T1, T2 unit tests written red, then green
- [x] T3, T4, T5 integration scenarios written with Gherkin docstrings, red then green
- [x] T7 bounds asserted with an injected clock
- [x] T8 security assertions in the suite, not only in prose
- [x] T9 upgrade path proved on an absent, a partial and a corrupt file
- [x] T10 full suite green
- [x] T12 `docs/cli/state.md`, `docs/cli/commands/status.md` and the two capability docs
      updated; markdownlint green
- [x] Evidence committed
