---
type: testing-plan
phase: test-planning
workItem: "issue-349"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: one question, one record, one answer — and every way of getting none

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs;
> credentials appear by reference only.

The plan's centre of gravity is **T11**, not T1. The behaviour this work item adds is
cheap to get right and expensive to get wrong: held state, a new payload branch, and a
value from an untrusted party that decides where an issue is written. Nine abuse cases,
nine negative tests, and the two bounds on a pick (the offered set *and* the declared
set) are asserted separately so that neither can be the only one standing.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `channels/kickoff.py`: `askable` partitions the six outcomes with `ok` and leaves only `empty-message` outside both; `text` is the stripped message on every outcome whose prefix was *read* and the raw message where none was; a prefix-only `ambiguous-repo`/qualified-`unknown-repo` message now resolves to `empty-message`; `question_text` names the prefix it quotes, teaches the `<repo>:` shortcut, and renders nothing of the member's message; `refusal_text` unchanged | `uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff.py` |
| T2 | Unit | yes | `channels/state.py`: `ask` writes a record and prunes; `pending` returns `None` past `PENDING_TTL_SECONDS` without writing; `claim` pops exactly once and returns `None` the second time; `restore` puts it back; `PENDING_CAP` drops the **oldest**; a pre-issue-349 file loads with an empty map and saves with the key; a corrupt file is empty, not an exception | `uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff_picker.py` (the file is sectioned by plan row) |
| T3 | Unit | yes | `channels/slack.py` rendering: ≤ `BUTTON_CHOICE_LIMIT` renders buttons, more renders a `static_select`, both under `KICKOFF_REPO_ACTION`; every option's text **and** value is the declared slug; `OPTION_LIMIT` caps the menu and the overflow is named in the prose; `_action_value` reads `selected_option.value` for a select and `value` for a button; `kickoff_picker` is true only for socket + the grant; `BUTTON_NAMES` names the picker for the press line | `uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff_picker.py` (the file is sectioned by plan row) |
| T4 | Unit | yes | `channels/inbound.py` the fork: `resolved`/`fallback` create immediately and ask nothing (R1.5); each askable outcome asks and creates nothing; `ambiguous-repo` offers only the matched candidates (R1.2); `empty-message` refuses (R1.4); `read.mode: poll` refuses with today's text (R5.1); nothing declared refuses (R5.3); a second message about an already-pending `ts` does not re-ask (R3.7); a failed `say` removes the record | `uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff_picker.py` (the file is sectioned by plan row) |
| T5 | Unit | yes | `process_kickoff_answer`: an accepted pick publishes the **same** `work-item.create` event `process_kickoff` publishes — same `repo`, `labels`, `thread`, same `principal_for` actor, same ledger (R4.3) — then binds with origin `kickoff` and replies with the Start button (R4.4); `report_press` is called for every press above the allow-list and removes the picker only on success (R4.5); a failed create restores the record (R3.5); the grant and Socket Mode are re-read at press time, so a revoked one refuses (R4.6) | `uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff_picker.py` (the file is sectioned by plan row) |
| T6 | Contract (OpenAPI / GraphQL SDL) | n/a — no API route, request or response shape changes; the control-plane surface is untouched | | |
| T7 | End-to-end | n/a — a true end-to-end run needs a live Slack workspace, a Socket Mode app token and a real `gh`; T8 exercises the same composition through the injected fakes the suite already uses for every other channel behaviour | | |
| T8 | Integration (scenario) | yes | the whole shape through `handle_socket_event` → `handle_socket_action` as they are actually composed, with Gherkin docstrings: a prefix-less message asks and creates nothing; the press then opens the issue, binds the thread, and a reply in that thread now reaches the work item; a second press of the same question opens nothing; an expired question opens nothing; the same message in `poll` mode is refused instead | `uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff_integration.py` |
| T9 | Snapshot | n/a — assertions are on Block Kit dicts, event fields, drop reasons and state maps, all asserted by shape rather than by a stored blob | | |
| T10 | Performance / load | n/a — one dict lookup in a file the pipeline already loads, bounded by `PENDING_CAP` (50) | | |
| T11 | Security / abuse case | yes | one negative test per abuse case A1–A10 (`requirements.md` § Security considerations): a crafted value outside the offered set; a value that is declared but was never offered **for this message**; an unauthorized presser, who gets no edit, no reaction and no post; an authorized presser who is not the message's author; an unauthorized member's top-level message asking nothing; a double press opening one issue; an expired pick naming no repository; a hostile message body neither rendered into nor sizing the question; a corrupt state file asking rather than creating; a grant revoked while the question was outstanding | `uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff_picker.py -k "abuse or mark or revoked or socket_mode"` plus scenarios 96-97 of the integration file |
| T12 | UI / visual | n/a — Block Kit is rendered by Slack, not by the-loop; the block structure is asserted as data in T3, and no UI of the-loop's own is touched | | |
| T13 | Accessibility | n/a — no UI of the-loop's own. The one accessibility-shaped choice (buttons for a few, a select for many) is a Slack-client affordance and is asserted as T3 | | |
| T14 | Migration / upgrade + `channels status` | yes | no config key and no schema change, asserted rather than assumed: schema parity unchanged, `CURRENT_CONFIG_VERSION` unchanged, a 14.0.0 config still validates; the new event name is in the event catalog; docs parity for the changed pages; the `kickoff` status line says whether it can ask and why not (R5.2) | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py && uv run --project cli python scripts/validate_config.py` |
| T15 | Manual exploratory | n/a — no Slack workspace is reachable from this session; the reviewer's walk-through is the PR briefing's "what to check" | | |
| T16 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T17 | Security review (gate) | yes | the-loop checklist against A1–A10, recorded as evidence. Tier 3 — below `security.review.humanSignOffMinTier: 4`, so no named human sign-off is required; the owner's PR approval is the gate | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1–R1.4, R1.6, R2.5 | Given a message, when it is resolved, then `askable` says whether a pick could answer it and `text` is what the issue would be composed from |
| T2 | R3.1, R3.2, R3.3, R3.4 | Given a pending record, when it is claimed / expires / overflows the cap, then it is answerable once, invisible after a day, and the oldest goes first |
| T3 | R2.1–R2.4, R4.2, R5.1 | Given N declared repositories, when the question is rendered, then the shape follows N and every value is the operator's own slug |
| T4 | R1.1–R1.5, R3.7, R5.1, R5.3 | Given a top-level message, when it cannot be resolved, then it is asked about where a press can be received and refused where it cannot |
| T5 | R4.3, R4.4, R4.5, R4.6, R3.5 | Given a pending question, when it is answered, then the work item opens through exactly the path a resolved prefix opens it through |
| T8 | R1.1, R3.4, R3.2, R4.1, R4.4, R5.1 | The five end-to-end shapes, as the transports actually compose them |
| T11 | A1–A10 | One negative test per abuse case |
| T14 | NFR "backward compatibility", "state file compatibility" | A 14.0.0 config and a pre-issue-349 `slack.json` both still work |

## Verification environment

- **Repositories:** this one. No second checkout, no service, no container.
- **Services:** none. Slack is exercised through the suite's existing injected
  `client_factory`; GitHub through the existing `create_issue` / `post_comment`
  injection points on `process_kickoff`.
- **Fixtures:** `tmp_path`-scoped CLI configs and `slack.json` state files, as every
  other channel test already builds them.
- **Credentials:** none. By reference only: the channel code reads
  `channels.slack.botTokenEnv` / `appTokenEnv`; no test sets a real token, and the
  presence-only rule for `channels status` is unchanged.
- **Commands:** the project's own, from the root — `make check` is the gate, and the
  per-row `pytest` invocations above are what narrows it while working.

## Evidence to capture

- `evidence/verification.md` — per-row command, outcome and raw output; the red→green
  transition for the new suites (they must not collect against `9dcb4a1`); and every
  pre-existing assertion that changed, with the reason.
- `evidence/security-review.md` — the checklist, A1–A10 each traced to the test that
  closes it, and any residual risk stated rather than implied.
- No screenshots: there is no UI of the-loop's own, and a Slack screenshot would need a
  live workspace this session cannot reach. The Block Kit payloads are asserted as data
  and quoted in the briefing instead.

## Activities checklist

- [x] T1 unit — the resolver
- [x] T2 unit — the pending record
- [x] T3 unit — the rendering and the payload read
- [x] T4 unit — the fork
- [x] T5 unit — the answer
- [x] T8 integration (Gherkin docstrings, `cli/tests/test_*_integration.py`)
- [x] T11 security / abuse cases A1–A10
- [x] T14 migration / compatibility
- [x] T16 `make check`
- [x] T17 security review recorded as evidence

## Verification results

> Filled at the `verification` node. Every activity below **ran**; the command, the
> outcome and the raw output are in [`evidence/verification.md`](evidence/verification.md).

| Row | Command | Outcome | Evidence |
|-----|---------|---------|----------|
| T1 | `pytest -q cli/tests/test_channels_kickoff.py` | 59 passed (43 on the base; 16 new) | [verification.md § T1](evidence/verification.md) |
| T2–T5, T11, T14-status | `pytest -q cli/tests/test_channels_kickoff_picker.py` | 51 passed | [§ T2–T5, § T11](evidence/verification.md) |
| T8 | `pytest -q cli/tests/test_channels_kickoff_integration.py` | 5 passed; scenarios 94–98 listed by `the-loop scenarios` | [§ T8](evidence/verification.md) |
| T14 | parity + docs + eventlog suites, `scripts/validate_config.py` | 22 passed; 5 configs VALID | [§ T14](evidence/verification.md) |
| T16 | `make check` | ruff, markdownlint (1073 files), format, pyright, config validation clean; **3543 passed, 1 skipped** | [§ T16](evidence/verification.md) |
| T17 | the-loop security checklist | pass; A1–A10 closed, 3 residual risks stated | [`evidence/security-review.md`](evidence/security-review.md) |

Nothing was replanned and nothing was skipped. The rows marked `n/a` in the matrix above
stayed `n/a` for the reasons given there.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
