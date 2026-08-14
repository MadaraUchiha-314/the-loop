# Evidence: T1, T2, T8 — the ad-hoc loop's own suite

Rows T1 (unit), T2 (integration/scenario) and T8 (security/abuse cases) of
[`testing-plan.md`](../testing-plan.md). All commands run from `cli/`. No network, no
subprocess, no credentials — every case is an in-process filesystem test against
`tmp_path` with the suite's stubbed GitHub integration.

## T1 + T2 + T8 — the whole new suite

```console
$ uv run pytest tests/test_graph_adhoc.py -q
.........................................................                [100%]
57 passed in 0.14s
```

## T2 — the walk, on its own

```console
$ uv run pytest tests/test_graph_adhoc.py -k Walk -q
...                                                                      [100%]
3 passed, 54 deselected in 0.05s
```

The two Gherkin-documented scenarios in `TestAdhocWalk`:

- `Scenario: the requester asks for more, then declares it done` — proves the whole
  edge set (`work → review`, `review → work` on `more-work`, `review → complete` on
  `done`), that an unauthorized reply leaves the gate waiting, and that no spec-chain
  artifact exists in the spec directory at any point.
- `Scenario: the review gate posts one self-marked request` — proves every comment the
  loop posts carries the loop-prevention marker, so the harness cannot answer its own
  gate.

## T8 — the abuse cases

```console
$ uv run pytest tests/test_graph_adhoc.py -q \
    -k "unauthorized or refused or invented or self_authored or empty_allowlist or prose"
........                                                                 [100%]
8 passed, 49 deselected in 0.21s
```

One test per abuse case in [`requirements.md`](../requirements.md) §Security
considerations:

| Abuse case | Test |
|---|---|
| 1 — unauthorized arming | `test_an_unauthorized_reply_leaves_the_gate_open`, plus the shared `authorizedUsers` gate exercised in `TestAdhocWalk` |
| 2 — two keywords in one comment | `test_do_plus_another_command_is_refused` |
| 3 — the harness declaring its own item done | `test_the_harness_cannot_declare_its_own_work_item_done` |
| 4 — an invented loop name in agent-writable state | `test_build_runtime_refuses_an_invented_loop_name`, `test_resolve_outer_loop_is_the_one_fail_closed_decision` |
| 5 — an unauthorized reply at the gate | `test_an_unauthorized_reply_leaves_the_gate_open`, `test_an_empty_allowlist_reads_nothing` |
| (keyword safety) | `test_do_does_not_fire_on_prose` — `the-loop does/done/docs/dominate` all refused by the existing token boundary |
