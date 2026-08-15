# Evidence: the refactor changed nothing, and the contract cannot drift (issue-212)

Testing-plan rows **T3**, **T4** and **T5**.

## T4 — the whole suite, before and after the refactor

The tasks file sets a checkpoint after T4: *"the refactor is complete and behaviour-neutral:
the whole existing suite must pass with no test adapted. If a test needed changing, the
refactor was not neutral."* It held. The run below is immediately after T1–T4 (routes
extracted to `api/routes.py`, per-request behaviour moved onto the route class,
`build_lifespan` extracted, `build_app` given an optional allowlist) and **before** a single
line of `the_loop/sdk/` existed:

```console
$ uv run --project cli pytest cli/tests -q
2041 passed, 1 skipped in 98.85s (0:01:38)
```

No test file was touched to get there. That is the whole claim of D1/D2: `create_app` lost
its middleware and its three exception handlers, and the served surface is identical.

## T4 — the whole suite, with the SDK

```console
$ uv run --project cli python -m pytest -q cli
2098 passed, 1 skipped in 96.29s (0:01:36)
```

57 new tests, no regressions, the skip is the pre-existing one.

## T3 + T5 — the parity gates

```console
$ uv run --project cli python -m pytest cli/tests/test_sdk_docs_parity.py \
      cli/tests/test_api_contract_parity.py -q
......                                                                   [100%]
6 passed in 1.49s
```

Four of the six are new or extended:

| Assertion | What it stops |
|-----------|---------------|
| `test_the_router_carries_exactly_the_apps_operations` | a route reaching the standalone app but not the embeddable router (they are the same object; this is what proves it stayed that way) |
| `test_p1_every_public_symbol_is_documented` | shipping a public SDK name nobody wrote up |
| `test_p2_every_namespace_method_reaches_core` | a rename in `core` leaving an SDK method that raises at runtime |
| `test_p3` / `test_p4` | `REQUIREMENTS` and `docs/sdk/environment.md` naming different binaries, in either direction |

The pre-existing `test_served_schema_matches_the_authored_contract` still passes unchanged,
so the chain is complete: **router == served app == authored OpenAPI contract**.

## Gate: how many operations

`mount()` reports 29 operations; the host application's OpenAPI document shows 28 *paths*
under the prefix. Both are right — `/api/v1/config` carries `GET` and `POST` on one path.
