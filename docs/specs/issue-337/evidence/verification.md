# Verification — issue-337

> Executed at `verification` on 2026-09-11, head of `claude/github-issue-337-8kq481`,
> from the repository root with the configured tooling (`uv`, `pytest`, `ruff`,
> `pyright`, `markdownlint`). Nothing here is a credential: every token, member id,
> channel id and URL in the tests is a fixture.

## Red → green

The new tests were written first. Against `a8acc96` (13.9.0) the unit module did not
import (`ImportError: cannot import name 'BUTTON_NAMES' from 'the_loop.channels.slack'`)
and the four scenarios failed on the missing `chat_update` path and the absent buttons;
after tasks 1–5 every row below passed. Three pre-existing pins in `test_channels.py`
asserted full equality of a *processed* outcome dict and were extended with the two new
keys (`url`, `error`) — the dropped shapes are unchanged.

## T1 — unit

```text
$ uv run --project cli python -m pytest -q cli/tests/test_channels_buttons.py
..............................                                           [100%]
30 passed in 3.81s
## T2
## T10
........................................................................ [ 90%]
.......................                                                  [100%]
```

## T2 — integration scenarios

```text
$ uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py -k "press or button"
.....                                                                    [100%]
5 passed, 24 deselected in 0.12s
```

The five: the four issue-337 scenarios (an Execute press records what a typed
`the-loop execute` records and the message says so; a kickoff reply carries Start and its
press records the start keyword; an unlisted member's press leaves the message untouched;
a press whose record was refused keeps its button) plus the issue-325 pin that a button
press is acknowledged on the pressed message.

## T8 — abuse cases

```text
$ uv run --project cli python -m pytest -q cli/tests/test_channels_buttons.py cli/tests/test_channels_integration.py -k "unauthorized or unlisted or crafted or grant or press_report or socket_and_the_grant or twice or refused_update or echoes"
...........                                                              [100%]
11 passed, 48 deselected in 0.18s
```

A1–A7 each closed by a named test — the table is in [`security-review.md`](security-review.md).

## T10 — migration, parity, the catalog, the existing suites

```text
$ uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py cli/tests/test_channels.py cli/tests/test_channels_integration.py cli/tests/test_bus.py cli/tests/test_channels_commands.py
........................................................................ [ 90%]
.......................                                                  [100%]
239 passed in 4.84s
```

No schema key was added, so both schema copies are untouched and identical; the event
catalog knows `channel.press_reported` and `channel.press_report_failed`
(`test_every_emitted_event_type_is_documented`); the packaged manifest and the guide's
copy agree (`test_the_guide_reproduces_the_packaged_manifest`) — its one changed comment
names the new buttons.

## T12 — `make check`

The repository's own gate — ruff, ruff format, markdownlint over every markdown file,
pyright, `validate_config`, the full suite — as pre-commit and CI run it. The first run
on this branch stopped at markdownlint on a placeholder line in this very file; the run
below is on the tree the PR carries (this file's fenced result block was pasted in after
it and linted on its own).

```text
make check
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Linting: 1034 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
285 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
uv run --project cli python -m pytest -q cli
3297 passed, 1 skipped in 175.53s (0:02:55)
exit=0
```
