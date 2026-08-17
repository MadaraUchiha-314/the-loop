---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#245"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: channels — back-and-forth user communication, starting with a Slack bot

> Derived from `requirements.md` and `design.md`, **before** `tasks.md` — each task's
> `_Test:_` names a row below. Authored at `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the pure core: config parsing (defaults, malformed → disabled), event filtering, verbosity rendering, binding/cursor state (caps, atomic writes, restart survival), the Slack channel against a fake client (token-at-call-time, thread reuse, missing token/channel), inbound pipeline steps (map, own-drop, allow-list, mirror composition, defang) | `uv run --project cli python -m pytest cli/tests/test_channels.py` |
| T2 | Integration (scenario) | yes | the two flows end-to-end through fake seams, Gherkin-documented: ask → work-item post + broadcast + binding recorded; a Slack thread reply → mirror on the ticket (marker-stamped) → delivery into a fake session; a socket-mode event through the same pipeline | `uv run --project cli python -m pytest cli/tests/test_channels_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API route is added; `the-loop channels` is CLI-only (requirements § Out of scope) | | |
| T4 | End-to-end (real Slack workspace) | n/a — needs a live workspace, a provisioned bot + app token and a human in Slack; the SDK boundary is one injected factory (design D7) and every call the fake receives is asserted argument-for-argument, which is what the live client would consume | | |
| T5 | UI / visual | n/a — no user-facing surface beyond CLI text and Slack messages whose text T1 asserts | | |
| T6 | Snapshot | n/a — the state file is asserted structurally in T1; no serialised artefact needs byte-stability | | |
| T7 | Performance / load | n/a — a poll cycle is one bounded API call per open thread (≤ the binding cap); Socket Mode is push | | |
| T8 | Security / abuse case | yes | the fail-closed contracts: empty `authorizedUsers` denies every reply (not mirrored, not delivered); an unauthorized member id likewise; the bot's own messages never re-enter; every mirror parses as self-authored and defangs control keywords; tokens never appear in state, status output or event payloads; no `channels` section → no watcher, no reads, no posts | `uv run --project cli python -m pytest cli/tests/test_channels.py cli/tests/test_channels_integration.py -k "unauthorized or empty_allowlist or own or marker or defang or token or disabled"` |
| T9 | Accessibility | n/a — no user-facing surface | | |
| T10 | Migration / upgrade | n/a — the config section and state file are both new and optional; an older config (no section) means today's behaviour exactly, asserted in T1; no existing key moves | | |
| T11 | Manual exploratory | no — deferred with reason: exercising a real bot needs a Slack workspace with the app installed, which this environment does not have; the dry surface (`the-loop channels status` against this repo's config) is asserted in T1/T2 instead | | |
| T12 | Whole-suite regression | yes | the daemon wiring, `ask` change and new verb break nothing; docs/schema parity gates (P1–P5, schema byte-parity, configschema keyword guard, `--types` parity) pass with the new section, command and event types | `make test` (or `uv run --project cli python -m pytest cli/tests`) |
| T13 | Lint / format / types | yes | the repo's own gates | `make lint`, `make format-check`, `make typecheck` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.4, R6.1 | absent section parses to no channels; malformed section logs and yields none; `from_mapping` defaults match the schema |
| T1 | R2.1 | an event type off the allow-list posts nothing; on it, posts once |
| T1 | R2.2 | quiet/normal/verbose render supersets of one another (summary+link ⊂ +question ⊂ +detail) |
| T1 | R3.1 | the fake client is constructed with the env token at call time; a token set after channel construction is seen; the token string never appears in the state file |
| T1 | R3.2 | first post for a work item starts a thread and records the binding; the second reuses the thread ts |
| T1 | R3.3 | missing token or missing channel id → `ChannelError` recorded, no raise to the caller |
| T1 | R4.6 | a processed reply advances the cursor; a re-fetch of the same messages processes nothing |
| T1 | R5.3 | the mirror quotes the reply, scrubbed and defanged, so `control.parse_command` finds nothing |
| T1 | D4 | past the binding cap the oldest thread is dropped; the state file round-trips atomically |
| T2 | R1.1–1.2, R2.3, R3.1–3.2 | `Scenario: An asked question lands on the work item and fans out to Slack` — the work-item post happens first and succeeds even when the channel raises |
| T2 | R1.3, R4.1, R4.4–4.6, R5.2–5.4 | `Scenario: A Slack thread reply is mirrored to the ticket and delivered to the waiting session` — marker asserted on the mirror, `reply_session` called with `comment=False` |
| T2 | R4.2 | `Scenario: A Socket Mode message reaches the same pipeline as a polled reply` |
| T2 | R4.1 | `Scenario: The channels watcher fetches on its interval and stops with its daemon` |
| T2 | R5.4 | `Scenario: A reply with no session left still lands on the work item` |
| T8 | R5.1 | empty allow-list and unlisted member id: dropped, no mirror, no delivery, `channel.dropped` emitted |
| T8 | R4.5 | a `bot_id`-authored and an own-user-authored message are dropped before authz |
| T8 | R1.3, R5.3 | every composed mirror `is_self_authored`; defang holds for every configured keyword |
| T8 | R3.1, R6.2 | no token value in `channels status` output or any emitted event payload |
| T12 | all, R6.1–6.2 | full CLI suite + parity gates (schema byte-parity, docs P1–P5, `EVENT_TYPES` ↔ `--types`) |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. No test opens a network connection: the Slack SDK
  boundary is the injected client factory (design D7), GitHub posting is the injected
  runner (`test_comments.py`'s house pattern), session delivery is `FakeTmux` /
  monkeypatched `reply_session`.
- **Fixtures & data:** in-repo (`cli/tests/conftest.py` autouse hermetic eventlog;
  per-test fake Slack clients returning canned `conversations.replies` /
  `chat.postMessage` payloads shaped like the real API's).
- **Credentials:** none. No test reads a real token; env vars are set to sentinels via
  `monkeypatch`.
- **Bring-up:** `uv sync` (implicit in `uv run`) · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8 | red-before/green-after runs of the new tests | `red.md`, `unit-and-integration.md` |
| T12 | full-suite output with counts | `unit-and-integration.md` |
| T13 | lint, format-check and typecheck output | `lint-and-typecheck.md` |

## Verification activities

- [ ] T1 — `uv run --project cli python -m pytest cli/tests/test_channels.py`
- [ ] T2 — `uv run --project cli python -m pytest cli/tests/test_channels_integration.py`
- [ ] T8 — the `-k` security selection above
- [ ] T12 — `uv run --project cli python -m pytest cli/tests -q`
- [ ] T13 — `make lint && make format-check && make typecheck`
- [ ] Red-first — the new tests fail before the implementation exists

## Verification results

> Completed at the `verification` node.

## Review comments

*None yet.*
