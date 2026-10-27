---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#524"
---

# Verification: a review session is never told to heal a check

The spec chain was skipped by declaration at phase selection, so there is no testing plan;
this record is the verification for the change as the issue states it.

## What is proved

| Claim | Proved by |
|-------|-----------|
| A failing check matched only to a review session reaches no pane, is dropped as `ci-review-loop`, is settled, and spends no attempt (no `ci.*` event) | `test_a_review_session_is_not_told_to_heal_a_check` |
| With the authoring session and a reviewer both matched, only the author gets the heal section (attempt 1 of 3); the reviewer's drop is recorded | `test_a_reviewer_beside_the_author_leaves_the_heal_to_the_author` |
| `ci-review-loop` is in the settled vocabulary and the event catalogue | `test_the_settled_vocabulary_is_exactly_the_thirteen_documented_outcomes` |

Both scenarios live in `cli/tests/test_ci_autofix_integration.py`.

## Before the fix (red)

With the gate's review check disabled (`if True:` in place of `if not self._reviews(session):`),
`uv run --extra dev pytest -q tests/test_ci_autofix_integration.py -k review`:

```text
FAILED tests/test_ci_autofix_integration.py::test_a_review_session_is_not_told_to_heal_a_check
FAILED tests/test_ci_autofix_integration.py::test_a_reviewer_beside_the_author_leaves_the_heal_to_the_author
2 failed, 11 deselected in 0.20s
```

## After the fix (green)

The full suite, run from `cli/`. The session's own `THE_LOOP_*` variables were unset: they
leak into 22 pre-existing tests (`test_poll_status`, `test_instances_cmd`, …) that fail the
same way on unmodified `main`.

```text
6791 passed, 3 warnings in 228.16s (0:03:48)
```

`uv run pre-commit run --all-files`: ruff, markdownlint and the config schema check pass.
