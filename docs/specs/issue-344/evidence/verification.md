# Verification evidence — issue-344

> The testing plan, executed. Every row that `testing-plan.md` marks *applies* has its
> command, its outcome and its raw output here. Commands are run from the project root.
> Date: 2026-09-12. Base: `c2fbeb2` (15.0.0).

## Red before green

The three new suites do **not collect** against the base code — the module they
describe did not exist. Captured by stashing the implementation (`cli/the_loop`,
`.the-loop`, `skills`) and running the suites against what remained:

```console
$ git stash push -u -- cli/the_loop .the-loop skills
$ uv run --project cli python -m pytest -q \
    cli/tests/test_lifecycle_hooks.py cli/tests/test_hooks_cmd.py \
    cli/tests/test_lifecycle_hooks_integration.py
    from the_loop import lifecycle_hooks as lh
E   ImportError: cannot import name 'lifecycle_hooks' from 'the_loop' (/home/user/the-loop/cli/the_loop/__init__.py)
ERROR cli/tests/test_lifecycle_hooks.py
ERROR cli/tests/test_hooks_cmd.py
ERROR cli/tests/test_lifecycle_hooks_integration.py
!!!!!!!!!!!!!!!!!!! Interrupted: 3 errors during collection !!!!!!!!!!!!!!!!!!!!
3 errors in 0.25s
$ git stash pop
```

Two defects the tests then caught in the first green attempt, both fixed before this
record: a bare YAML `on:` key parses as the boolean `true` (the GitHub Actions trap the
graph loader already handles for edges — the declaration now reads both spellings, with a
unit test pinning it), and the `hooks.failed` record's field for the observed event could
not be called `event` because `emit`'s first parameter is (it is `on`, mirroring the
attachment key).

## T1–T5 — the declaration, the loader, the dispatch, `forward-event`, the seam

```console
$ uv run --project cli python -m pytest -q cli/tests/test_lifecycle_hooks.py \
    cli/tests/test_hooks_cmd.py cli/tests/test_lifecycle_hooks_integration.py
........................................................................ [ 97%]
..                                                                       [100%]
74 passed in 3.51s
```

The 74 break down as 66 in `test_lifecycle_hooks.py` (T1 `-k declaration`: 26 incl. the
parametrised malformed shapes and `forward-event` parameter refusals; T2 `-k load`: 10;
T3 `-k dispatch` and the runtime: 11; T4 `-k forward`: 5; T5 `-k seam`: 5; install/reset:
2), 4 in `test_hooks_cmd.py` (T6) and 4 in `test_lifecycle_hooks_integration.py` (T7).
The asynchronous tests wait on `drain()`; none sleeps.

## T6 — `the-loop hooks`

Covered above (4 tests: registered; reports without importing — a module that leaves a
mark on import is declared and the mark is absent after both the text and the json
report; an empty declaration; a malformed block exits 2). The command against this
repository's own config, which declares no block:

```console
$ uv run the-loop hooks
attach points: 147 event types (`the-loop events --types`; hooks.* excluded)
shipped lifecycle hooks (1): forward-event

no lifecycle hooks declared (`hooks` in the CLI config, .the-loop/cli-config.yaml)
```

## T7 — integration, through the real seams

Covered above (4 Gherkin-docstringed scenarios): work start and work finish reach a
declared hook through the real `configure_from_file` and `emit`; a checkout module nobody
declared never runs (A1, with the checkout as cwd); `forward-event` end to end against a
local `http.server` with the token from the environment and absent from the config and
the log (A6); a broken declaration fails the entry point (A8).

## T8 — contract: schema copies, docs parity, event catalog, config validation

```console
$ uv run --project cli python -m pytest -q cli/tests/test_configschema.py \
    cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py \
    cli/tests/test_eventlog.py cli/tests/test_manifest_schemas.py
........................................................................ [ 98%]
.                                                                        [100%]
73 passed in 2.80s
$ uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

Two of these failed on the way and pinned two decisions: P1/P4 failed until the command
page and the five `hooks.*` option headings existed (the parity gate doing its job), and
`test_the_schemas_use_no_keyword_the_validator_ignores` refused a `oneOf` for `on` — the
runtime validator implements `type` lists, not `oneOf`, so the schema says
`type: [string, array]`.

## T9 — abuse cases

Each of A1–A9 is a named negative test; the mapping is the table in
[`security-review.md`](security-review.md). All are in the 74 above.

## T10 — regression: the graph hooks after the loader refactor

```console
$ uv run --project cli python -m pytest -q cli/tests/test_graph_extensions.py \
    cli/tests/test_graph_extensions_integration.py
...............................................                          [100%]
47 passed in 0.67s
```

Unchanged suites, unchanged messages (`load_module`, `_contained` and `read_modules`
default to `routing.graph.hooks`, `GraphConfigError` and "the repository root").

## T11 — the whole repository check

```console
$ make check
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Linting: 1097 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
297 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   … (six files, as above)
uv run --project cli python -m pytest -q cli
3575 passed, 1 skipped in 151.90s (0:02:31)
```

Base was 3501 passed, 1 skipped; the 74 new tests are the difference.

One regression surfaced by the full suite and fixed before this record:
`test_instance_integration.py` installs a log double with only an `emit` method, and the
first version of the module-level `emit` called `build`/`write` on it. `emit` now keeps
the old contract for any object that offers only `emit` and builds the sinks' copy of the
record the same way the log would.

## the-loop's own gate on this spec chain

```console
$ uv run the-loop check issue-344 --recompute
issue-344: UNMET (at phase-selection)
  WAIT   phase-selection
         · waiting for an authorized user to choose the phases and reply `the-loop execute`
  ····   6 node(s) not reached yet
```

`WAIT`, not `block`: the CI gate (`--fail-on block`) passes, and the artifacts' front
matter and required sections validate. The selection itself is recorded on the ticket, as
every cloud-session work item in this repository records it.
