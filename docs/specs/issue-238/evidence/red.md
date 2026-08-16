# Evidence: the red run (T0)

The new and rewritten assertions, run against **unfixed** code. This is the counter-evidence
for the claim a bug fix is easiest to fake: two of these tests previously asserted the
`400` behaviour, and rewriting a test is only honest if the rewritten test is shown failing
first.

Captured 2026-08-16, on `claude/github-issue-238-cwdgone` at the commit before task 3.
Absolute paths are redacted to `/Users/…` and `<tmp>`; nothing else is edited.

## Python — `cli/tests/test_core_graphs.py`, `cli/tests/test_api_routers_integration.py`

```console
$ uv run pytest cli/tests/test_core_graphs.py cli/tests/test_api_routers_integration.py
=========================== short test summary info ============================
FAILED cli/tests/test_core_graphs.py::test_repo_resolves_agrees_with_resolve_repo
FAILED cli/tests/test_core_graphs.py::test_check_answers_a_vanished_checkout_instead_of_raising
FAILED cli/tests/test_core_graphs.py::test_the_unknown_position_answer_is_not_a_filesystem_oracle
FAILED cli/tests/test_api_routers_integration.py::test_graph_check_answers_a_checkout_that_has_been_deleted
========================= 4 failed, 19 passed in 1.21s =========================
```

The four failures, and why each is the right kind of red:

| Test | Failure against unfixed code |
|------|------------------------------|
| `test_repo_resolves_agrees_with_resolve_repo` | `AttributeError` — `graphs.repo_resolves` does not exist yet. |
| `test_check_answers_a_vanished_checkout_instead_of_raising` | `ValueError: repo path is not a directory: <tmp>/nope` — the behaviour being removed, raised from the call that should have returned. |
| `test_the_unknown_position_answer_is_not_a_filesystem_oracle` | Same `ValueError`, raised before the body it asserts on exists. |
| `test_graph_check_answers_a_checkout_that_has_been_deleted` | `assert 400 == 200` — the exact status code the ticket was opened about. |

The route-layer failure in full, since it is the one that mirrors the reported symptom:

```text
        response = client.post(
            "/api/v1/graph/check",
            json={"repo": str(tmp_path / "nope"), "workItem": "issue-1"},
        )
>       assert response.status_code == 200
E       assert 400 == 200
E        +  where 400 = <Response [400 Bad Request]>.status_code

cli/tests/test_api_routers_integration.py:101: AssertionError
```

The two tests that assert **unchanged** behaviour pass here as they must —
`test_a_resolving_repo_keeps_exactly_the_keys_it_always_had` and
`test_graph_check_says_nothing_new_about_a_checkout_that_is_there` are green before the
change and must stay green after it (R2.2).

## UI — `ui/src/state/useControlPlane.test.ts`

```console
$ cd ui && bun run test
- "outer": {},
+ "outer": {
+   "github:acme/widgets#7": {
+     "currentNode": "",
+     "nodes": [],
+     "ok": false,
+     "repoResolved": false,
+     "workItem": "issue-7",
+   },
+ },

 ❯ src/state/useControlPlane.test.ts:47:21
     45|     const reports = await fetchGraphs(api, [WORK_ITEM], [SESSION], new…
     46| 
     47|     expect(reports).toEqual({ outer: {}, inner: {} });
       |                     ^

 Test Files  1 failed | 7 passed (8)
      Tests  1 failed | 105 passed (106)
```

One of the two cases is red: `fetchGraphs` stores the unknown-position answer instead of
dropping it, which is precisely what would replace `railFromFrozen` with an empty rail.
The sibling case — a normal answer is stored — passes before the change and must keep
passing after it.

`bun run typecheck` is *also* failing at this point, because `GraphStatus` has no
`repoResolved` field yet. That is task 4's, not a second defect.
