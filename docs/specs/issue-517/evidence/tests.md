# Tests: issue-517 handoff

Run on commit `0748cd25` (branch `the-loop/issue-517-handoff`), 2026-10-22, from the repository root.

## `make check` (T12, plus T1–T3, T6, T8, T10 inside `make test`)

The lint, markdownlint, format-check, typecheck (pyright, 0 errors) and validate stages
passed. The test stage reported:

```text
22 failed, 6666 passed, 2 warnings in 272.13s (0:04:32)
```

The 22 failures fail identically on `main` on this machine, and CI on `main` is green.
They come from this operator machine's environment: the tests read the live operator
`cli-config.yaml` and the running the-loop service, and none of them touches this
change. They are in
`test_poll_status` (13), `test_poll_command` (4), `test_instances_cmd` (2),
`test_lifecycle_cmd`, `test_critics` and `test_ask_reply_integration` (1 each).
The PR's own CI run is the clean-environment proof.

## The issue-517 test files and the suites they changed

```text
cd cli && uv run python -m pytest -q tests/test_handoff_record.py tests/test_handoff_state.py \
  tests/test_handoff_cmd.py tests/test_import_handoff.py tests/test_handoff_pickup.py \
  tests/test_handoff_selection.py tests/test_jira_api.py tests/test_jira_verbs.py \
  tests/test_jira_integration.py tests/test_mcp_integration.py tests/test_manager_integration.py \
  tests/test_state_portability.py tests/test_eventlog.py tests/test_pdlc_e2e
321 passed in 13.09s
```

| Row | New tests |
|---|---|
| T1, T6, T8 | `test_handoff_record.py` (92): parse/render round trips, every rejection, `STAGE_ENTRY`, parts at 65,536, snapshots, abuse cases 1–2 |
| T1, T10 | `test_handoff_state.py` (11): `requiresHandoff`, `no-handoff` skip, legacy state byte-identical |
| T2, T8 | `test_handoff_cmd.py` (23): `post`, `show`, `import` (tampered, missing part, `--from-dir`), `note` |
| T1, T2, T8 | `test_import_handoff.py` (17): demotion order, shape/hash refusal, approved-in-chat lock, instructions in a body |
| T2, T8 | `test_handoff_pickup.py` (19): branch checkout, unauthorized record, late record, Jira mirror, graph context |
| T2, T6 | `test_handoff_selection.py` (19): checklist snapshot, the five R6-table walks, no-handoff byte-identical |
| T2, T3 | Jira/MCP/manager/route contract cases for `issueType` and `parent` |

## `make validate` (T10)

```text
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
VALID   skills/the-loop/templates/gateway-config.yaml
```
