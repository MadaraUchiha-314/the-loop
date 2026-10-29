---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#529"
status: draft
approvedBy: []
overrides: {}
---

<!-- Written per the `the-loop:writing` skill. -->

# Testing plan: a Slack kickoff offers Do or Start, not Start alone

Everything is tested in this repository with no credentials. Slack is the fake web
client the kickoff suites already use (`UpdatingSlackClient`), and GitHub is the
monkeypatched `create_issue` / `post_issue_comment_with_url`. The press path from a
button to a `control.command` on the ticket is the one issue-337 already tests for
Start. The new tests drive that same path with Do. The dispatcher's `do` →
`pdlc-adhoc-loop` mapping is already tested by issue-225, so this plan re-runs those
tests instead of copying them. A real Slack workspace is not reachable from CI (T4).
The HTML mock is the visual reference, and the Block Kit payload is asserted field by
field.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `render_reply_blocks` with `{do, start}`: text section, then a description section (Do line before Start line, fixed words), then an actions block `[Do, Start]` whose values are the keywords. With `{start}` alone: one line, one button. With `{}`: text section only. `execute` gets no description line. `COMMAND_BUTTONS` / `BUTTON_NAMES` agree, and the latter has "Do". `KICKOFF_COMMANDS == ("do", "start")` | `cd cli && uv run python -m pytest -q tests/test_channels_buttons.py` |
| T2 | Integration (scenario) | yes | the kickoff reply from a top-level message carries `[do, start]`; a press on **Do** records an unmarked `the-loop do` on the new issue, which `parse_command` reads as `do`, and the reply is edited with "Do" named; a disabled `do` keyword renders Start alone; `/the-loop new` renders `[do, start]`; a picker answer's reply renders `[do, start]`. Gherkin-documented with `Requirement:` links | `cd cli && uv run python -m pytest -q tests/test_channels_integration.py tests/test_channels_commands.py tests/test_channels_kickoff_picker.py` |
| T3 | Contract (OpenAPI / GraphQL) | n/a. No HTTP API changes: the button rides the existing Slack interactivity path | | |
| T4 | End-to-end | n/a. Needs a real Slack app and workspace. T2 drives the same handlers with a fake web client. Pressing Do in a live workspace is offered to the author as an optional post-merge check | | |
| T5 | UI / visual | yes | the HTML mock `design/kickoff-reply.html` renders in light and dark and matches the asserted block order | open the file in a browser (chrome-devtools MCP), screenshot both themes |
| T6 | Snapshot | n/a. The Block Kit payload is asserted field by field in T1 | | |
| T7 | Performance / load | n/a. One extra block in one message per kickoff | | |
| T8 | Security / abuse case | yes | abuse 1: an unlisted member's Do press records nothing and edits nothing. Abuse 2: a crafted Do `action_id` with a non-keyword value arms nothing. Abuse 4: without `control.command`, or without push reachability, no Do button is rendered | `cd cli && uv run python -m pytest -q tests/test_channels_integration.py tests/test_channels_buttons.py -k "do_press or do_button"` |
| T9 | Accessibility | n/a. Slack renders Block Kit buttons with their own a11y. The labels are plain text and the descriptions are text, not colour | | |
| T10 | Migration / upgrade | n/a. No state, config or schema change | | |
| T11 | Manual exploratory | n/a. No live Slack workspace is reachable from this session (T4) | | |
| T12 | Regression (whole suite) | yes | the full CLI suite, including the issue-225 `do` → adhoc-loop tests and the issue-337 Start tests, plus lint, format, types and markdown | `uv run pre-commit run --all-files` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.2, R1.5 | `render_reply_blocks` with both commands: order, words and values |
| T1 | R1.4 | one command gives one line and one button; none gives the section alone |
| T2 | R1.1, R1.3, R2.1, R2.3 | `Scenario: A kickoff reply offers Do and Start, and pressing Do records the do keyword` |
| T2 | R1.3 | `Scenario: /the-loop new offers Do and Start` |
| T2 | R1.3 | `Scenario: A picker answer's reply offers Do and Start` |
| T2 | R1.4 | `Scenario: A disabled do keyword leaves Start alone` |
| T12 | R2.2, R2.5 | existing issue-337 Start press tests and the issue-225 typed-`do` tests, unchanged and green |
| T8 | Abuse 1, 2, 4 | `Scenario: An unlisted member's Do press arms nothing`; crafted value is plain text; no Do button without the grant |
| T5 | R1.2 | mock before and after a press, both themes |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. Slack and GitHub are faked in-process.
- **Fixtures & data:** the existing `UpdatingSlackClient`, `cli_config`, and `_press`
  helpers in `cli/tests/`.
- **Credentials:** none. The tests set `THE_LOOP_SLACK_BOT_TOKEN`-style variables to
  dummy values (`xoxb-test`) via `monkeypatch`.
- **Bring-up:** `cd cli && uv sync`. **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T8 | test summary | `unit.md` |
| T2 | scenario list and run output | `integration.md` |
| T5 | screenshots of the mock, light and dark | `ui/kickoff-reply-light.png`, `ui/kickoff-reply-dark.png`, indexed in `ui-visual.md` |
| T12 | pre-commit summary | `regression.md` |

## Verification activities

- [x] T1 — `cd cli && uv run python -m pytest -q tests/test_channels_buttons.py`
- [x] T2 — `cd cli && uv run python -m pytest -q tests/test_channels_integration.py tests/test_channels_commands.py tests/test_channels_kickoff_picker.py`
- [x] T8 — the abuse-case tests named above
- [x] T5 — screenshots of `design/kickoff-reply.html` in both themes
- [x] T12 — `uv run pre-commit run --all-files`

## Verification results

Every activity ran on this branch with the session's `THE_LOOP_*` variables unset (see
`evidence/unit.md` for why) and passed. T4 and T11 stay `n/a` as planned: no live Slack
workspace is reachable.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `cd cli && uv run python -m pytest -q tests/test_channels_buttons.py` | 35 passed (red first: ImportError) | [unit.md](evidence/unit.md) |
| T2 | `cd cli && uv run python -m pytest -q tests/test_channels_integration.py tests/test_channels_commands.py tests/test_channels_kickoff_picker.py` | 173 passed (red first: 4 failed) | [integration.md](evidence/integration.md) |
| T8 | the issue-529 scenarios and abuse cases, `-v` | 9 passed | [integration.md](evidence/integration.md) |
| T5 | headless Chromium screenshots of `design/kickoff-reply.html`, light and dark | both render the asserted block order | [ui-visual.md](evidence/ui-visual.md) |
| T12 | `uv run pre-commit run --all-files` | all hooks pass, 6803 tests | [regression.md](evidence/regression.md) |
