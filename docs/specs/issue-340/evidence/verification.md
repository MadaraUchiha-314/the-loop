# Verification: `the-loop progress`

> The record for [`testing-plan.md`](../testing-plan.md). Run on 2026-10-19 against
> `main` at `31ebc08` (v20.2.1), Python 3.12.

## Results

| Gate | Result |
|------|--------|
| `ruff check cli hooks` | passed |
| `ruff format --check cli hooks` | passed |
| `pyright cli` | 0 errors, 0 warnings |
| `pytest` (full CLI suite) | 6169 passed, 1 skipped |
| `scripts/validate_config.py` | every config valid |
| `markdownlint-cli2@0.18.1 "**/*.md"` | 0 errors over 1686 files |

The baseline before the change was 6148 passed, 1 skipped, so the change adds 21 tests and
breaks none. One baseline run hit a flake in
`test_channels_integration.py::test_a_restarted_work_item_keeps_its_thread` under
`pytest-xdist`; it passed alone and in every later run.

## Tests added

| Plan row | File | Tests |
|----------|------|-------|
| T1, T2, T3 | `cli/tests/test_progress.py` | 19 |
| T4 | `cli/tests/test_room_policy.py` | 1 |
| T5 | `cli/tests/test_channels_declared_integration.py` | 1 |
| T6 | existing parity tests, now covering the new route, command, config block and event | 0 new |

## Mutation check

The tests were written alongside the code, so there is no red run. Instead each guard was
broken in turn and the targeted tests rerun; each break was caught.

| Mutation | Result |
|----------|--------|
| the label gate always passes | 2 tests fail |
| the rate limit never applies | 1 test fails |
| the report is not shortened | 1 test fails |
| Slack does not defuse the text | 1 test fails |
| the live line is keyed by phase | 1 test fails |

The Slack defusing test found a real gap while it was being written: the first version
defused only the Block Kit blocks, and `<!channel>` survived in the plain-text fallback that
Slack also parses. The defusing moved to `SlackBotChannel.post`, before any rendering.

## Not verified

- **A live Slack workspace.** `FakeSlackClient` pins the calls made (one post, one
  `chat.update`); it cannot show how Slack renders or notifies. Plan row T9.
- **A real label read** against github.com or a Jira site. The read is a monkeypatched
  double, and the GitHub path is checked only down to the client call's arguments.
- **A self-review, a critic review and a security review** by someone other than the author.
  The security considerations are written in `requirements.md` and unreviewed.
