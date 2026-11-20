# Contract (T3)

Run on 2026-11-20 at `93ba24e5`:

```text
cd cli && uv run python -m pytest -q tests/test_api_contract_parity.py
7 passed in 3.06s
```

`summary` on `POST /api/v1/work-items/comments` is in
`docs/api-specs/openapi/the-loop.v1.yaml` (`WorkItemCommentBody`). The served
routes match it, and `test_the_comment_body_carries_the_summary_as_the_contract_says`
compares the authored and served properties.
