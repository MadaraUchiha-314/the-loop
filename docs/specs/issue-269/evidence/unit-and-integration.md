# Evidence — green run

Every command below was run from the repository root on the branch, after the fix. No
existing test was modified to accommodate the change; four test helpers were extended with
one optional argument each (`make_dispatcher`, `ServerFactory.__call__`, `_dispatcher`,
`_make` — all take `verifier=None`) and `FakeRun` in `test_announce.py` gained a `stderr`
parameter it should always have had.

## T1 — units (the verifier, provenance, the intake filter, the target seam)

```sh
uv run --project cli python -m pytest -q cli/tests/test_linkage.py cli/tests/test_routing.py
```

```text
........................................................................ [ 81%]
................................                                         [100%]
176 passed in 2.03s
```

## T2 — integration (both ingresses, Gherkin-documented)

```sh
uv run --project cli python -m pytest -q cli/tests/test_webhook_routing_integration.py \
                                        cli/tests/test_poller_integration.py
```

```text
.................................................                        [100%]
49 passed in 15.30s
```

The two that matter most are in `test_poller_integration.py` — they drive the **real**
`GitHubPollProvider` through the **real** `Poller` and `Dispatcher` against a canned `gh`,
which is the ingress the ticket was reported from:

- `test_a_branch_invented_work_item_never_becomes_the_start_target` — the reproduction; the
  start binds to `octo/repo#48` and the session spawns for it.
- `test_the_same_pull_request_still_starts_where_the_work_item_is_real` — the control; the
  same branch-derived ref, verified present, still spawns `octo/repo#285`.

## T8 — the payload → argv boundary

```sh
uv run --project cli python -m pytest -q cli/tests/test_linkage.py -k "hostile or hostname or provider"
```

```text
....                                                                     [100%]
4 passed, 21 deselected in 0.03s
```

Hostile owner/repo coordinates (`octo;rm -rf /`, `repo && curl evil`, `../..`) make **no**
`gh` call and answer "unknown", so a malformed payload can never delete a work item from
routing; a GitHub Enterprise ref is asked of its own host; a non-`github` provider is never
asked at all.

## The announcer and the event catalogue

```sh
uv run --project cli python -m pytest -q cli/tests/test_announce.py cli/tests/test_eventlog.py
```

```text
..................................                                       [100%]
34 passed in 0.84s
```

`test_every_emitted_event_type_is_documented` is the parity gate the two new event types
had to clear.

## Full suite

```sh
make test    # uv run --project cli python -m pytest -q cli
```

```text
2410 passed, 1 skipped in 141.93s (0:02:21)
```

Before this change the same command reported 2408 passed, 1 skipped — the two extra are the
poll-path reproduction and its control; the rest of the new tests are counted in the files
above (25 in `test_linkage.py`, 12 in `test_routing.py`, 3 in `test_announce.py`, 3 in
`test_webhook_routing_integration.py`).
