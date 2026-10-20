---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#507"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: answer a Slack mention in the thread it came from

Unit and integration tests prove this fix, and both run in-process against the fake
Slack client the channel tests already use. The regression test (T2, scenario 1) is
written first and must be red on `origin/main`. Lint and type checks close it out. No
live Slack workspace is needed: the change is which `thread_ts` one `chat.postMessage`
call carries, and the fake client records exactly that.

## Test matrix

| Testing type | In scope? | Reason / approach |
|---|---|---|
| Unit | yes | `_delivery_record` keeps and coerces the two new fields; `room_policy.is_progress` |
| Integration | yes | real `SlackBotChannel` + real `inbound.handle_socket_event` + `FakeSlackClient` + real state file: the whole mention → answer path (`cli/tests/test_channels_reply_thread_integration.py`, Gherkin docstrings) |
| Contract | n/a | no API, event type or schema changes |
| End-to-end | n/a | a live Slack workspace adds nothing the fake client does not observe: the only output is the `thread_ts` on a post |
| UI / visual | n/a | no UI |
| Snapshot | n/a | no rendered output changes; block rendering is untouched |
| Performance | n/a | one extra read of a record already loaded under the same lock, and one small write per delivered reply |
| Security / abuse-case | yes | abuse case 1 (unauthorized mention does not set the thread) and 2 (other channel ignored), in the integration file |
| Accessibility | n/a | no UI |
| Migration | yes | a state file written before this change (no `replyThread`) loads and posts top-level (unit) |
| Manual | n/a | covered by the integration tests above |

## Scenarios & requirement trace

| Row | Requirement | Scenario |
|---|---|---|
| T2.1 | R1.1, R1.2, R1.4, R3.3 | mention in room thread T → `comment.agent` posted with `thread_ts = T`; `PostResult.thread == T` (regression, red first) |
| T2.2 | R1.3 | two `comment.agent` in a row both go to T |
| T2.3 | R2.1 | mention in thread T, then thread U → answer in U |
| T2.4 | R2.2 | mention in T, then a top-level mention → answer top-level |
| T2.5 | R2.3 | mention in T, then `phase.started` → posted top-level, and the next `comment.agent` is top-level |
| T2.6 | R2.3 | mention in T, then `phase.progress` → the next `comment.agent` still goes to T |
| T2.7 | R1.5 | in an agentic room, a mirrored session-started cheat-sheet is still dropped while a reply thread is set |
| T2.8 | R2.4 | no mention → `comment.agent` top-level, as today |
| T3.1 | abuse 1 | an unauthorized member's thread mention is refused and leaves no reply thread |
| T3.2 | abuse 2, R3.2 | a reply thread whose channel differs from the conversation's → top-level |
| T1.1 | Data model | `_delivery_record` round-trips `replyChannel` / `replyThread`; non-strings coerce to `""` |
| T1.2 | Migration | a record without the fields loads with both `""` |
| T1.3 | R2.3 | `is_progress` is true for `phase.progress`, `session.progress`, `x.progress`; false for `comment.agent`, `phase.started` |
| T4 | R3.1 | a state save that raises while noting the thread: the reply is still delivered, the answer posts top-level |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. Slack is `FakeSlackClient` from `cli/tests/test_channels.py`.
- **Fixtures & data:** `tmp_path` state roots and portable stores, via the
  `cli_config` / `declare` helpers.
- **Credentials:** none (a dummy `SLACK_BOT_TOKEN` env set by the fixture).
- **Bring-up:** `uv sync --locked` · **Tear-down:** none.
- **If bring-up fails:** record it below, leave the dependent activities unticked, and
  escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T4 | pytest summary | `unit.md` |
| T2, T3 | red-on-main note, run output, scenario list (`the-loop scenarios`) | `integration.md` |
| T5 | pre-commit summary | `lint-and-typecheck.md` |

## Verification activities

- [ ] T1 — `cd cli && uv run python -m pytest -q tests/test_channels_reply_thread.py`
- [ ] T2 — `cd cli && uv run python -m pytest -q tests/test_channels_reply_thread_integration.py` (and red on `origin/main` for T2.1)
- [ ] T3 — `cd cli && uv run python -m pytest -q tests/test_channels_reply_thread_integration.py -k abuse`
- [ ] T4 — `cd cli && uv run python -m pytest -q tests/test_channels_reply_thread_integration.py -k save_fails`
- [ ] T5 — `uv run pre-commit run --all-files`

## Verification results

## Review comments
