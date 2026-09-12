# Verification — issue-352

> The testing plan's rows, executed. Commands as run; outputs summarised, with the
> full numbers from the final `make check` on the PR head.

## Rows

| Row | Command | Result |
|---|---|---|
| T1 | `pytest cli/tests/test_graph_extensions.py` | green |
| T2 | `pytest cli/tests/test_critics.py` | green |
| T3 | `pytest cli/tests/test_core_repo.py cli/tests/test_cli.py` | green |
| T4 | `pytest cli/tests/test_instructions.py` | green |
| T5 | `pytest cli/tests/test_graphlink.py` | green |
| T6 | `pytest cli/tests/test_graph_contribution.py cli/tests/test_graph_review.py cli/tests/test_graph_loops.py cli/tests/test_graph_refs.py` | green |
| T7 | `pytest cli/tests/test_migrations.py` | green |
| T8 | the seven integration files named in the plan | green |
| T9 | `pytest cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_configschema.py cli/tests/test_manifest_schemas.py` and `uv run python scripts/validate_config.py` | green; every config `VALID` |
| T10 | the abuse-case tests named in `security-review.md` | green |
| T11 | `make check`; `grep -rn "harness_config\|harness-config.default\|repoInitialized\|allow_repo_hooks\|\.adopt(" cli/the_loop`; a second grep over every shipped file for a dotted reference to a removed policy key (`autonomy.`, `security.review`, `tokenEconomy.`, `userInteraction.`, `externalTools.`, …) | green; the first grep is empty; the second finds only two past-tense history sentences in `docs/capabilities/writing-style.md` |

## The whole suite

Final `make check` on the PR head (2026-09-12, after the second review's pass):

| Check | Result |
|-------|--------|
| `ruff check cli hooks` | All checks passed |
| `ruff format --check cli hooks` | no drift |
| `pyright` | 0 errors, 0 warnings |
| `markdownlint-cli2 "**/*.md"` | 1086 files, 0 errors |
| `scripts/validate_config.py` | every config validates against its schema |
| `pytest` | 3491 passed, 1 skipped (the schema-read length-limit test in `test_writing_parity` is gone with the key it read) |

## Red first

Before the code changed, the removed reader's tests and the new assertions failed as
expected: `test_harness_config.py` (deleted with the module), the graph-extension tests
on the `routing.graph.hooks` shape, `test_core_repo`'s "a committed critic is inert", and
`test_graphlink`'s "the repository's harness config is not consulted" all went red against
`6bbd1e5` (the base) and green on the PR head.
