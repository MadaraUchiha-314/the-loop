# Learning 017: a the-loop session's own environment skews the-loop's test suite

- **Date:** 2026-10-20
- **Source:** system-feedback
- **Work item:** issue-503

## What happened

Inside a session the-loop launched, the full suite failed 21 tests in files this change
never touched, such as `test_poll_status.py` and `test_lifecycle_cmd.py`. The daemon
exports `THE_LOOP_CLI_CONFIG` (and `THE_LOOP_WORK_ITEM`) into the session, pointing at
the operator's live config. The tests inherited it, so config resolution read the real
file instead of the fixture in `cwd`. With both variables unset, every test passed. CI
never sets them, so a red local run here was not a regression.

## Learning

When building the-loop *with* the-loop, run its tests with the session's own variables
unset: `env -u THE_LOOP_CLI_CONFIG -u THE_LOOP_WORK_ITEM uv run pre-commit run
--all-files`. Treat a failure that disappears without them as environmental, and say so
in the evidence rather than "fixing" a test. A test that resolves the CLI config from
`cwd` should also clear the variable itself; the suite's autouse fixtures do not yet.

## Action

None in code yet. This is the first occurrence (rule of three). The issue-503 evidence
records the clean-environment command.
