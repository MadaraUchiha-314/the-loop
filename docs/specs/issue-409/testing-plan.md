---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#409"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
riskTier: 3
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: the bus keeps an outbox, and `status` reads it

> Derived from [bugfix.md](bugfix.md) and [design.md](design.md), before `tasks.md`.
> Authored at `test-planning`, completed at `verification`.

## What is testable here, and what is not

Everything this change adds is a pure function over a JSON file, a guard inside `publish`,
a thread that calls one function, and a line of output — and the suite already drives all
four shapes: `test_bus.py` publishes with fake channels and a fake ledger,
`test_ask_reply_integration.py` runs the real `ask` verb with `gh` faked at its injection
point, and `test_service_lifecycle_integration.py` reads `status`'s report off a `tmp_path`
state root. No network, no real provider.

Two rows cannot run here. A real Slack outage (T11) needs a workspace and a rotated token.
Timing the backoff over real wall-clock (part of T7) is replaced by driving `drain` with an
injected clock, which is the same assertion without the wait.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `outbox.remember` under each guard (no config, injected channels, no channel asked, one channel took it), the entry's fields, the cap and its warning, the `Event`/`Principal` round trip, a corrupt and an absent file | `cd cli && uv run python -m pytest tests/test_channels_outbox.py` |
| T2 | Unit | yes | `outbox.drain`: an entry delivered is removed and dated; an entry refused keeps its attempt, error and backoff; the backoff is honoured then expires; the per-cycle budget bounds the work; one raising entry does not stop the rest; the drain never records | `cd cli && uv run python -m pytest tests/test_channels_outbox.py` |
| T3 | Integration (scenario) | yes | `publish` with a real state root: a failing channel queues the event and emits `channel.undelivered` at `warning`; a succeeding one queues nothing; `broadcast`'s injected-channel path queues nothing | `cd cli && uv run python -m pytest tests/test_bus_integration.py` |
| T4 | Integration (scenario) | yes | The report's whole scenario end to end: `the-loop ask` with a channel that refuses → the question on the ticket, the entry in the outbox, the verb's note on stderr, `channels_posted: 0` on the event; then the channel recovers → one drain delivers it, the file empties, `status` goes quiet | `cd cli && uv run python -m pytest tests/test_channels_outbox_integration.py` |
| T5 | Integration (scenario) | yes | `the-loop status` with a non-empty outbox: the line names the count, the age and the last error; `--format json` carries `channelDelivery`; an unreadable file still answers; the exit code does not move | `cd cli && uv run python -m pytest tests/test_channels_outbox_integration.py` |
| T6 | Contract (OpenAPI / GraphQL) | n/a — no HTTP surface changes. `status_all`'s report gains a field, and the API's own status route serves whatever that function returns; `docs/api-specs/openapi` describes no `channelDelivery`-shaped schema to update. | | |
| T7 | Performance / load | partial | Bounds rather than timings: the cap holds the file at `OUTBOX_CAP` entries under 500 `remember` calls, and one drain attempts at most `DRAIN_BUDGET` entries. Wall-clock backoff is asserted with an injected clock, not by waiting | `cd cli && uv run python -m pytest tests/test_channels_outbox.py -k "cap or budget"` |
| T8 | Security / abuse case | yes | The four claims in `design.md` § Security design: the drain posts and never records (no ledger call on a drain); the three new event-log lines carry no `event.text`; the path is declared local; the backlog is bounded | `cd cli && uv run python -m pytest tests/test_channels_outbox.py tests/test_state_portability.py` |
| T9 | Migration / upgrade | yes | A deployment with no outbox file behaves exactly as before (nothing printed, nothing drained); an outbox written with unknown keys or missing keys loads rather than raising; `EVENT_TYPES` documents every new event | `cd cli && uv run python -m pytest tests/test_channels_outbox.py tests/test_eventlog.py` |
| T10 | Regression | yes | The whole Python suite: the bus, the ask verb, the poller and webhook daemons, the status command and the state-portability rules are all touched | `make test` |
| T11 | Manual exploratory | yes | A real deployment: rotate the Slack token, ask, watch `status` count it, restore the token, watch the drain deliver it | an operator's workspace; not available in this environment |
| T12 | Documentation parity | yes | `docs/cli/state.md` classifies the new path (enforced by `test_state_portability.py`), and `docs/capabilities/channels.md` describes the outbox, the drain and the status line | `make lint`, `cd cli && uv run python -m pytest tests/test_state_portability.py` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.4 | `Scenario: an event no channel took is written to the outbox with its errors` |
| T1 | R1.2, R1.3 | `Scenario: a delivered event, and an event nobody was asked to take, queue nothing` |
| T1 | R1.5 | `Scenario: the oldest entry goes when the cap is reached, and says so` |
| T1 | R1.6 | `Scenario: an unwritable outbox never changes what publish returns` |
| T1, T9 | R1.4 | `Scenario: an entry written by another version loads with what it has` |
| T2 | R2.2 | `Scenario: a drained entry that a channel takes is removed and reported` |
| T2 | R2.3 | `Scenario: a refused entry keeps its attempt, its error and its backoff` |
| T2 | R2.4 | `Scenario: the drain posts to channels and never records on the ledger` |
| T2, T7 | R2.5 | `Scenario: one cycle attempts at most the budget, and one bad entry does not stop the rest` |
| T3 | R1.1, R4.1 | `Scenario: publish queues what no channel took and warns about it` |
| T3 | R1.2 | `Scenario: publish queues nothing when a channel took it or the caller injected the channels` |
| T4 | R2.1, R2.2, R4.2, R4.3 | `Scenario: a question refused by the channel is queued, noted to the session, then delivered when the channel recovers` |
| T4 | R4.4 | `Scenario: a channel outage never changes the ask's exit code` |
| T5 | R3.1, R3.3 | `Scenario: status names the backlog, and its JSON carries the same facts` |
| T5 | R3.2, R3.4, R3.5 | `Scenario: an empty or unreadable outbox is silent and never moves the exit code` |
| T8 | R4.1 | `Scenario: the undelivered warning names ids and counts, never the message` |
| T9 | R2.6 | `Scenario: a drain cycle that raises does not end the daemon's thread` |

## Verification environment

This container, against the repository checkout: `uv sync` (with `uv` ≥ 0.12, which this
image needs installed over its own 0.8), then `cd cli && uv run python -m pytest -q` — the
same command `make test` and the `pytest` pre-commit hook run, from the same working
directory. Linting is `uv run ruff check cli hooks`, `uv run ruff format --check cli hooks`,
`uv run pyright cli` and `markdownlint-cli2`, matching `make check`. No network is used: the
GitHub writer and every channel are faked at their injection points.

## Evidence to capture

Under `docs/specs/issue-409/evidence/`:

- `verification.md` — each row of this matrix with its command, outcome and counts.
- `self-review.md` — the review cycles and every finding's disposition.
- `security-review.md` — the four claims of `design.md` § Security design, each with the
  test or the line of code that establishes it.
- `documentation.md` — the capability and state docs updated in this PR.

## Verification results

Recorded at the `verification` node in
[evidence/verification.md](evidence/verification.md): T1, T2, T3, T4, T5, T7, T8, T9, T10
and T12 pass; T6 is `n/a` as planned; T11 did not run for want of a real Slack workspace to
break, and the scenario it would walk is T4's, which runs against the real modules with the
SDK client faked at its injection point.

## Activities checklist

- [x] T1, T2 unit tests written red, then green
- [x] T3, T4, T5 integration scenarios written with Gherkin docstrings, red then green
- [x] T7 bounds asserted with an injected clock
- [x] T8 security assertions in the suite, not only in prose
- [x] T9 upgrade path proved on an absent, a partial and a corrupt file
- [x] T10 full `make test` green
- [x] T12 `docs/cli/state.md` and `docs/capabilities/channels.md` updated; lint green
- [x] Evidence committed
