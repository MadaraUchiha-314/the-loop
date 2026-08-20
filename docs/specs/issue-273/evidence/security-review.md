# Security review (issue-273)

- **Mechanism:** the checklist in `skills/the-loop/reference/security.md`
  (`security.review.mechanism: auto` → no built-in security-review skill was available in
  this session, so the checklist is the recorded fallback).
- **Effective risk tier:** 3 (`autonomy.defaultTier`; no `sensitivePaths` touched — no
  schema, no workflow file, no `harness-config.yaml`). Below
  `security.review.humanSignOffMinTier: 4`, so no named human security sign-off is required;
  human approval of the pull request still applies (tier 3 = `human-approves-pr`).
- **Reviewed against the diff:** `cli/the_loop/graphlink.py`, the four test modules, and the
  two capability docs.
- **Outcome:** pass, no findings.

## Checklist

| # | Item | Verdict | Evidence in the diff |
|---|---|---|---|
| 1 | every trust boundary in `design.md` §Security design is enforced where the design says it is | **pass** | the gate order in `_guarded` is unchanged above the relaxed predicate: `config.enabled` → `spec_id_for` → `_awaiting_start` → `_checkout_belongs_to` → `_is_contained` → `_adopt` → the `is_dir()` check. The diff touches only the last of those, and only for two actions |
| 2 | untrusted inputs validated/constrained at their ingress; injection surfaces covered | **pass** | nothing untrusted enters the new code. `_pending_context` reads the compiled graph (`rt.graph.node(rt.graph.start)`) and the loaded state's own `surface`/`loop`; the `pending` block is fixed literals plus that node's id, phase and actor. No comment body, title, label, ref or author reaches it — the same rule the rest of `render_graph_context` follows |
| 3 | untrusted content cannot steer privileged behaviour | **pass** | `phase-selection` keeps `required: true`, `classify-feedback` remains the only route from a comment to an edge, and it still filters by `authorizedUsers`. `test_the_gate_still_waits_for_an_authorized_human` is the negative test: an unauthorized `the-loop execute` on a freshly started graph moves nothing. A `pending` context is deliberately not `at_human_gate`, so no event is handed to a gate on its account |
| 4 | no secrets in code, config, logs or fixtures | **pass** | no new event type and no new log field. The `_FakeGitHub`/`_OfflineGitHub` test doubles carry no credentials and reach no network |
| 5 | AuthZ checks fail closed | **pass** | `_awaiting_start` runs **before** the relaxed predicate, so an unarmed work item is refused without the spec directory ever being considered — the ordering is what makes the exemption safe. `_checkout_belongs_to` likewise precedes any checkout read, unchanged |
| 6 | least privilege | **pass** | one new write reachable: `<specDir>/<id>/graph-state.json` (plus the git-ignored `graph-state.lock`) inside a checkout the same seam already writes `.the-loop/harness-config.yaml` into one step earlier, behind the identical gates. `_is_contained` keeps the declared `specDir` inside the checkout, so the exemption cannot select a write target elsewhere on the operator's machine |
| 7 | every abuse case from the requirements has a passing negative test | **pass** | "could this start a graph on a work item nobody armed?" → the unchanged `test_an_item_nobody_started_is_skipped` and `test_the_quiet_skip_paths_stay_quiet`; "could a foreign checkout be written to?" → `test_a_foreign_checkout_is_never_adopted` and `test_a_foreign_checkouts_harness_config_is_never_read`; "could an escaping `specDir` now be used?" → `test_a_spec_dir_that_escapes_the_checkout_is_refused`; "could an arriving comment start a graph?" → `test_an_advance_still_requires_the_spec_directory` |
| 8 | new dependencies justified and from trusted sources | **n/a** | none added |

## Residual risk, accepted and recorded

The-loop now creates `<specDir>/<id>/` in checkouts where it previously left the tree
untouched — for any work item that is armed, spawned and in its own repository. That is the
intended behaviour (the directory is where the work item's spec chain goes), and for a
repository that never adopted the-loop `Runtime.start` keeps the spec tree out of git
(`repoInitialized is False` → `_exclude_spec_root`), a path that until now never got the
chance to run for these work items. No accepted risk beyond that.
