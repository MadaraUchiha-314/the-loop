# Verification — issue-325

> The testing plan executed (`testing-plan.md`, rows T1, T2, T8, T10, T12). Commands run
> from the repository root at the head of `claude/github-issue-325-b62wbf`. Every token
> in the tests is a fixture (`xoxb-test`, `xoxb-supersecret`); every Slack id is a
> fixture (`C123`, `UHUMAN`, `UBOT`). Nothing here needed redaction.

## Red → green, per task

The new tests were written first. Against `1920a03` (13.4.0) the unit module does not
even import:

```text
uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_channels_integration.py -k "reaction or acknowledged or kickoff_is or dropped_message or refuses"
E   ImportError: cannot import name 'DEFAULT_REACTIONS' from 'the_loop.channels.slack'
17 deselected, 1 error in 0.57s
```

and the three integration scenarios fail on `client.reactions == []` — the fake Slack
client records no `reactions.add` because nothing calls it.

| Task | Red (before the change) | Green |
|------|-------------------------|-------|
| 1 config + schema | `SlackReactionConfig`, `DEFAULT_REACTIONS`, `REACTION_STATES` absent; no `reactions` leaf in the schema | `test_reaction_config_defaults_match_the_schema`, `test_a_config_without_the_block_reacts_with_the_defaults`, `test_reactions_can_be_disabled_or_skipped_per_state`, `test_a_malformed_reaction_name_is_refused_and_the_state_skipped`, `test_colons_around_a_reaction_name_are_stripped`, `test_a_non_mapping_reactions_block_keeps_the_defaults`; `test_config_schema_parity.py` |
| 2 react + events | no `react` on the channel; `channel.reaction_*` unknown to the catalog | `test_react_adds_the_named_reaction_on_the_message`, `test_react_uses_the_replys_channel_id_over_the_configured_one`, `test_react_never_raises_and_records_the_failure`, `test_react_without_a_token_is_a_quiet_noop`, `test_react_disabled_or_skipped_makes_no_call`; `test_eventlog.py::test_every_emitted_event_type_is_documented` |
| 3 pipeline + transports | `client.reactions == []` on every accepted path; `handle_socket_*` took no `client_factory` | the fourteen pipeline, kickoff and drop tests; the three T2 scenarios |
| 4 docs | — | `make lint` (markdownlint over 985 files), `test_docs_parity.py` |

Baseline before the change: `test_channels.py` + `test_channels_integration.py` 90
passed. After: 120 passed — 27 new unit tests (23 functions, one parametrized over five
drops) and 3 new scenarios. Existing assertions changed: one — `channels status` now
prints a `reactions:` line, asserted in `test_channels_status_shows_presence_never_values`.

## Rows T1, T2, T8, T10

```text
== T1
uv run --project cli python -m pytest -q cli/tests/test_channels.py
100 passed in 0.53s
== T2
uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py
20 passed in 3.76s
== T8
uv run --project cli python -m pytest -q cli/tests/test_channels.py -k reaction
15 passed, 85 deselected in 0.12s
== T10
uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py
22 passed in 0.80s
```

## Row T12 — `make check`

```text
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 985 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
281 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
uv run --project cli python -m pytest -q cli
3138 passed, 1 skipped in 152.24s (0:02:32)
```

## Not executed

T3–T7, T9, T11: `n/a` with reasons in the plan. No Slack workspace is reachable from
this session, so the live 👀 / ✅ on a real message is the reviewer's walk-through in the
PR briefing.
