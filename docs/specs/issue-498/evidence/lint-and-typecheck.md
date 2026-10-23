# Full suite, lint and type check — T12 (issue-498)

Commit `08dbf02a`, session `THE_LOOP_*` variables unset.

| Command | Outcome |
|---------|---------|
| `uv run pytest cli/tests` | **6784 passed**, 0 failed |
| `make lint` (ruff + markdownlint, 1834 files) | 0 errors |
| `make format-check` | clean (after `ruff format`) |
| `make typecheck` (pyright) | 0 errors |
| `make validate` | exit 0 |

The first full run failed 30 tests: every one either used a keyword mid-sentence
("please the-loop start") or asserted the old quoted relay record. All were updated to
the new rule; one was a real defect in the Slack relay format, fixed in
`channels/bodies.py` (design §1).
