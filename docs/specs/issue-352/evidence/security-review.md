# Security review — issue-352

> The ready-to-ship security gate (`security.review.required`, mechanism `auto`).
> **Risk tier 4**, so `security.review.humanSignOffMinTier: 4` applies: the owner's
> approval of [PR #353](https://github.com/MadaraUchiha-314/the-loop/pull/353) is the
> named human sign-off, and their review directing the change is the paper trail.
> Date: 2026-09-12.

## What actually changed, from a security point of view

One sentence: **executable configuration left the one file a pull request to a
repository could edit, and the CLI stopped parsing anything a repository commits under
`.the-loop/`.** Two surfaces close (A1, A2); one guard that protected a now-absent read
stays because it protects a write too (A3); one ownership proof is untouched (A4).

## Abuse cases

| # | Case | Disposition | Test |
|---|---|---|---|
| A1 | A PR adds a hostile `reviews.critics[]` entry hoping the daemon runs it. | Closed by construction: `critics.load_critics` reads the resolved CLI config only. | `test_core_repo::test_critics_never_come_from_the_repositorys_harness_config`, `test_critics_integration` (the stand-in critic is declared in the CLI config) |
| A2 | A checkout carries a hook module nobody declared, hoping `load_graph(repo=…)` imports it. | Nothing is imported without `routing.graph.hooks` in the CLI config; `load_graph` with no declaration compiles the shipped graph. | `test_graph_extensions::test_no_declaration_imports_nothing`, `test_graph_extensions_integration::test_an_undeclared_module_in_a_checkout_is_never_run` |
| A3 | A `specDir` that escapes the checkout (`../elsewhere`, `/etc`). | The repository can no longer supply one; the operator's value is still bounded by `_is_contained` and refused with a `graph.skipped` record naming it. | `test_graphlink::test_a_spec_dir_that_escapes_the_checkout_is_refused` |
| A4 | A foreign checkout with a forged `origin` remote. | `_checkout_belongs_to` is unchanged: the remote must name the work item's repository before any graph is driven there. | `test_graphlink::test_a_foreign_checkout_is_never_coupled` |
| A5 | `migrate-config` silently drops an operator's `repoHooks: false`. | The key is removed **and reported**, with a note that hooks run only when declared here; there is nothing a dropped `false` could re-enable. | `test_migrations` (version `0.9.0`, the retired key) |
| A6 | A JSON `--doc` smuggles fields. | `collect_docs` reads `path` and `notes`; a doc's body never reaches the report (issue-132's boundary, still tested). | `test_instructions::test_doc_contents_never_reach_the_report`, `test_instructions_integration::test_a_hostile_doc_body_never_reaches_the_report` |

## Residual

- **One directory per instance.** An operator who points one daemon at repositories with
  different spec layouts gets `graph.skipped` records rather than silently wrong writes;
  the fix is a second instance or aligned layouts. Stated in decision-123.
- **Secrets in `critics[].env`.** The schema and docs say never; the entry now lives in
  the operator's file, where `env.file` (issue-318) is the intended place for values.
- **The harness config is still executable-adjacent for the agent** (autonomy tiers,
  security gates), so it stays in this repository's `sensitivePaths`; the CLI config joins
  it.

No finding blocks completion.
