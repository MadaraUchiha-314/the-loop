# Evidence: unit, embedding-integration and abuse-case tests (issue-212)

Testing-plan rows **T1**, **T2** and **T10**. Run on the work-item branch,
`claude/github-issue-212-n81fy7`, at the commit this PR carries. No network, no `gh`, no
harness binary: every test builds its own CLI config and state root under `tmp_path`.

## T1 — unit (`test_sdk_client.py`, `test_sdk_environment.py`)

```console
$ uv run --project cli python -m pytest cli/tests/test_sdk_client.py cli/tests/test_sdk_environment.py -q
......................................                                   [100%]
38 passed in 0.57s
```

Covers construction (path / dict / both / missing / unparseable — R4.1, R4.2, R4.5, R4.6),
the reload path (R4.3), the import-cost assertion in a fresh interpreter (NFR2), every
namespace and its operations (R1.2), delegation to core (R1.3), the exception contract
(R1.4), the `mount()` report (R2.4, R3.6), the prefix refusals, and the environment table's
per-configuration `required` predicates and `ok` arithmetic (R5.1–R5.4).

## T2 + T10 — embedding integration and abuse cases

```console
$ uv run --project cli python -m pytest cli/tests/test_sdk_embedding_integration.py \
      cli/tests/test_sdk_security_integration.py -v
test_sdk_embedding_integration.py::test_a_host_application_serves_the_loop_under_its_own_prefix PASSED [  7%]
test_sdk_embedding_integration.py::test_core_errors_translate_without_host_exception_handlers PASSED [ 14%]
test_sdk_embedding_integration.py::test_the_host_middleware_sees_every_the_loop_request PASSED [ 21%]
test_sdk_embedding_integration.py::test_an_injected_dependency_gates_every_operation PASSED [ 28%]
test_sdk_embedding_integration.py::test_mcp_answers_under_a_prefix_with_the_host_lifespan_still_running PASSED [ 35%]
test_sdk_embedding_integration.py::test_mounting_mcp_without_the_lifespan_refuses_instead_of_serving PASSED [ 42%]
test_sdk_embedding_integration.py::test_the_caller_can_compose_the_lifespan_themselves PASSED [ 50%]
test_sdk_embedding_integration.py::test_a_config_edited_on_disk_is_live_on_the_next_embedded_request PASSED [ 57%]
test_sdk_embedding_integration.py::test_an_embedded_operation_lands_in_the_event_log PASSED [ 64%]
test_sdk_embedding_integration.py::test_mounting_twice_is_the_callers_business_not_a_crash[get-/the-loop/api/v1/health] PASSED [ 71%]
test_sdk_security_integration.py::test_a_rejecting_dependency_cannot_be_bypassed_by_choosing_a_path PASSED [ 78%]
test_sdk_security_integration.py::test_mounting_adds_no_middleware_no_handlers_and_no_cors PASSED [ 85%]
test_sdk_security_integration.py::test_an_empty_prefix_with_mcp_is_refused PASSED [ 92%]
test_sdk_security_integration.py::test_the_config_write_path_is_not_the_callers_to_choose PASSED [100%]
============================== 14 passed in 2.27s ==============================
```

Every one of these carries a Gherkin docstring naming its scenario and the requirement it
traces (`testing.gherkinDocstrings: required`); `the-loop scenarios` renders the table.

Two are worth calling out because they are the ones a reviewer should be sceptical of:

- **`test_a_rejecting_dependency_cannot_be_bypassed_by_choosing_a_path`** does not spot-check
  one route. It reads the *host application's own* `/openapi.json`, walks every path under the
  mount prefix and every method on it, and asserts `401` for each — then asserts the count
  equals the `operations` figure `mount()` reported (29). A route that slipped past the
  dependency would change that count.
- **`test_mounting_adds_no_middleware_no_handlers_and_no_cors`** snapshots the host app's
  middleware stack, exception handlers, title and doc URLs *before* the mount and compares
  after, then confirms a request carrying the-loop's own default CORS origin
  (`https://madarauchiha-314.github.io`) gets no `access-control-allow-origin` — i.e. the
  standalone service's allowlist was not installed on somebody else's application.
