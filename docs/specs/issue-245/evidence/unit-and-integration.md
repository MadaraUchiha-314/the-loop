# Unit, integration and security-selection runs — green

Executed at verification (testing-plan rows T1, T2, T8, T12).

## T1 — units

```
$ uv run --project cli python -m pytest cli/tests/test_channels.py -q
.............................                                            [100%]
29 passed in 0.11s
```

## T2 — integration scenarios (Gherkin-documented)

```
$ uv run --project cli python -m pytest cli/tests/test_channels_integration.py -q
.......                                                                  [100%]
7 passed in 0.10s
```

## T8 — the security selection

```
$ uv run --project cli python -m pytest cli/tests/test_channels.py cli/tests/test_channels_integration.py -k "unauthorized or empty_allowlist or own or marker or defang or token or disabled" -q
...........                                                              [100%]
11 passed, 25 deselected in 0.32s
```

## T12 — whole-suite regression (parity gates included)

```
$ uv run --project cli python -m pytest cli/tests -q
2369 passed, 1 skipped in 122.71s (0:02:04)   # from the make check run
```

The suite includes the parity gates that red-build an undocumented surface:
docs parity P1–P5 (command pages, config leaves), schema byte-parity
(.the-loop/ ↔ cli/the_loop/schemas/), the configschema keyword guard, the
EVENT_TYPES ↔ `events --types` catalog test and the state-portability ↔
docs/cli/state.md classification test — all passing with the new
channels section, verb, state file and event types.

## Convergence round (PR #267 review — owner: "converge right now")

After re-pointing the `notify` hook through channels and removing
`integrations.slack` behind the 0.5.0 migration:

```
$ uv run --project cli python -m pytest cli/tests -q     # via make check
2358 passed, 1 skipped in 129.18s (0:02:09)
```

The count moved from 2369 because `test_graph_slack_url_integration.py` and the
webhook-transport unit tests went with the integration they pinned, while five
migration tests and the notify-through-channels scenario joined. Lint,
format-check, pyright and config validation: clean on the same run.
