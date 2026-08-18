# Evidence: unit and integration tests (T1, T2, T8, T10, T12)

Captured on 2026-08-18, on the branch `claude/github-issue-248-o4u7z7`. No network, no
subprocess, no credentials: every test builds its repository under `tmp_path`.

## The whole suite

```text
$ make test
2412 passed, 1 skipped in 123.38s (0:02:03)
```

2405 of those passed before this change; the 7 new ones are the integration scenarios.

## This work item's tests

```text
$ uv run --project cli python -m pytest \
    cli/tests/test_graph_extensions.py \
    cli/tests/test_graph_extensions_integration.py \
    cli/tests/test_graph_model.py cli/tests/test_graph_contract.py \
    cli/tests/test_harness_config.py cli/tests/test_docs_parity.py \
    cli/tests/test_config_schema_parity.py -q
........................................................................ [ 52%]
..................................................................       [100%]
138 passed in 1.38s
```

- `test_graph_extensions.py` — 41 unit tests: the collector, declaration parsing, module
  loading and containment, attaching, the chain, and `load_graph`.
- `test_graph_extensions_integration.py` — 7 Gherkin scenarios: a repository's hook gating a
  node, one loader for CLI and daemon, a module that cannot be imported, inspection without
  importing, the operator's refusal, a repository that declares nothing, and the pre-rename
  `config.yaml`.
- The rest are the parity and contract suites this change had to keep green:
  `graph.hooks` in `READS` resolving in the schema and documented, the packaged schema
  matching the authored one, and the graph contract unchanged.

## Abuse cases (T8)

Each negative test named in `design.md` § Security design ran in the block above:

| Abuse case | Test |
|---|---|
| 1. repository hook passes where a shipped hook blocked | `test_a_repository_hook_cannot_rescue_a_blocked_chain` |
| 2. repository hook declares `outcome: approved` | `test_a_repository_hook_cannot_declare_an_outcome` |
| 3. module path escapes the repository | `test_a_module_outside_the_repository_is_refused`, `test_a_symlink_leaving_the_repository_is_refused` |
| 4. module shadows a shipped hook name | `test_a_module_registering_a_shipped_name_fails_to_load` |
| 5. two repositories, one `x-` name | `test_two_repositories_keep_their_own_implementations` |
| 6. attached hook raises | `test_a_raising_repository_hook_blocks` |
| 7. operator refuses repository hooks | `test_the_operator_kill_switch_imports_nothing`, `test_the_operator_can_refuse_repository_hooks` |
