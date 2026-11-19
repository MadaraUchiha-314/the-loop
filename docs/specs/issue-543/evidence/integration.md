---
type: evidence
workItem: issue-543
---

# Integration scenarios: PR-scoped specs

> Testing-plan row T2, run at commit `08fba802` on 2026-11-19. Each scenario drives the real
> runtime and the real verb over two real git checkouts, with GitHub stubbed.

`the-loop scenarios --glob cli/tests/test_pr_spec_integration.py --format markdown`:

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 1 | PR-scoped specs | a cross-repository PR cannot start implementation without a recorded PR spec | requirements.md R1.1, R4.1, R4.5 | cli/tests/test_pr_spec_integration.py:152 |
| 2 | PR-scoped specs | a changed chain blocks the PR at reviewer-briefing until it is re-derived | requirements.md R5.1, R5.2, R5.3 | cli/tests/test_pr_spec_integration.py:186 |
| 3 | PR-scoped specs | a single-PR work item walks past pr-spec untouched | requirements.md R1.2; NFR single-repository unaffected | cli/tests/test_pr_spec_integration.py:229 |
| 4 | PR-scoped specs | under never mode the outer implementation holds until every PR has a record | requirements.md R1.4, R1.6 | cli/tests/test_pr_spec_integration.py:250 |
| 5 | PR-scoped specs | a private origin will not publish a PR spec to a public repository without an authorized grant | requirements.md Security AC1, AC2 | cli/tests/test_pr_spec_integration.py:279 |

`cd cli && uv run python -m pytest -q tests/test_pr_spec_integration.py`: **5 passed in
0.51s.**

These scenarios cover behaviour built in tasks 7 and 9, so they passed on first run.
