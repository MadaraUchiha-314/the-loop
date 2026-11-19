---
type: evidence
workItem: issue-543
---

# Contract and snapshot: PR-scoped specs

> Testing-plan rows T3 and T6, run at commit `08fba802` on 2026-11-19 from `cli/`.

| Row | Command | Outcome |
|-----|---------|---------|
| T3 | `uv run python -m pytest -q tests/test_api_contract_parity.py` | 6 passed in 2.72s |
| T6 | `uv run python -m pytest -q tests/test_graph_loops.py tests/test_manifest_schemas.py tests/test_writing_parity.py` | 85 passed in 1.71s |

- **T3:** `graphPrSpec` (`POST /api/v1/graph/pr-spec`) was authored in
  `docs/api-specs/openapi/the-loop.v1.yaml` first (2 failed), then served (green) for both
  the worker and the manager.
- **T6:**
  - The four `templates/pr-spec/` files point at the writing skill and carry the
    sections the verb requires (`test_required_sections_match_the_templates`).
  - The inner assignment names `/the-loop:derive-pr-spec`, and that command names both
    verbs.
  - The PR briefing links the PR spec first (`test_the_pr_briefing_links_the_pr_spec_first`),
    and its Jira golden was regenerated to match.
