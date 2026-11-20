# Unit, abuse-case and migration tests (T1, T8, T9, T10)

Run on 2026-11-20 at `93ba24e5`, from `cli/`, with `THE_LOOP_CLI_CONFIG`,
`THE_LOOP_INSTANCE` and `THE_LOOP_WORK_ITEM` unset. Those variables point at the
operator's own config, which some unrelated tests read.

| Row | Command | Result |
|---|---|---|
| T1 | `uv run python -m pytest -q tests/test_channels_*.py tests/test_room_policy.py tests/test_voice.py tests/test_graph_refs.py` | 824 passed in 14.44s |
| T8 | `uv run python -m pytest -q tests -k "abuse or defuse or unauthorized or stale_press or casefold"` | 334 passed, 7019 deselected in 9.73s |
| T9 | within T1: `test_text_fallback_is_short_form` (`tests/test_channels_shortform.py`), `test_the_fallback_is_the_short_form` (`tests/test_channels_mrkdwn.py`) | passed |
| T10 | `uv run python -m pytest -q tests/test_configschema.py tests/test_channels.py tests/test_channels_outbox.py` | 195 passed in 5.75s |

## Migration cases (T10)

- A config that still sets `maxChars` / `longMessages` validates and warns once:
  `test_deprecated_slack_keys_validate`, `test_deprecated_slack_keys_warn_once`.
- Two bindings that differ only in case resolve to the first: `test_casefold_binding_first_wins`.
- An outbox entry written before the event id replays without a double post:
  `test_legacy_outbox_entry_without_id_replays`.

## Performance bound (T7, inside T8)

`test_abuse_64k_body_bounded_parts_and_time` (`tests/test_channels_render.py`)
renders a 65,536-character body within its time bound and part count.
