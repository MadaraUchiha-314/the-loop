# Green run — unit, integration and the full suite (issue-270)

Same tests as [`red.md`](red.md), after the change. Commands are run from the repository
root; `make test` is the whole suite.

## T1 — unit (dispatcher, poller, event catalogue, prompt templates)

```console
$ uv run --project cli python -m pytest -q cli/tests/test_routing.py cli/tests/test_poller.py \
    cli/tests/test_eventlog.py cli/tests/test_interaction.py
...............................................................          [100%]
351 passed in 2.43s
```

## T2, T10 — integration (the reproduction, the restart, the upgrade)

```console
$ uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py
........................                                                 [100%]
24 passed in 1.93s
```

## T8 — the settlement tests on their own (the muting direction included)

```console
$ uv run --project cli python -m pytest -q cli/tests/test_routing.py cli/tests/test_poller.py \
    -k "settle or settled"
..............                                                           [100%]
14 passed, 290 deselected in 0.14s
```

The one that matters for T8 is
`test_a_delivery_a_session_received_outranks_a_settlement`: a delivery a session actually
recorded still answers `done`, so a suppression on one endpoint can never baseline a comment
another endpoint received. Its companion,
`test_a_spawn_policy_drop_still_releases_its_id_and_settles_nothing`, pins the other
direction — the one refusal that wants a retry still gets one.

## Full suite

```console
$ make test
uv run --project cli python -m pytest -q cli
.............................                                            [100%]
2476 passed, 1 skipped in 127.67s (0:02:07)
```

Re-run after rebasing onto `main` at `ede4630` (which had gained issue-248): **2476 passed, 1
skipped**, of which 18 are this work item's — 17 written red-first, plus
`test_the_settled_vocabulary_is_exactly_the_five_documented_outcomes`, added in self-review
round 1 to pin a constant nothing was reading. (Before the rebase, against `main` at
`fc3adcf`: 2428 passed, 1 skipped, up from 2410.) No test was changed to
accommodate the fix; the two edits to existing test code are additive — a `delivery_outcome`
method and a settlement switch on the poller's `RecordingDispatcher` double.
