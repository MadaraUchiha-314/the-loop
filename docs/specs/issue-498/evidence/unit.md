# Unit evidence — T1 (issue-498)

Commit `08dbf02a`. Environment: the checkout, with the session's `THE_LOOP_*` variables unset
([learning-017](../../../learnings/learning-017.md)).

| Command | Outcome |
|---------|---------|
| `uv run pytest cli/tests/test_control.py` | **86 passed** |
| Same new cases against the pre-fix parser (`git checkout 13c915d5 -- cli/the_loop`, `-k "anywhere_but_the_start or mention_of_another"`) | **13 failed** — red before the fix, as R1.6 requires |

Cases covered: leading keyword with leading whitespace (R1.1); the #496 body, mid-line,
backticks, bold, parentheses, `>` quote, fenced block, indented line, list item, later
line of a prose body (R1.2); several `add-collaborator` lines, with a mid-line mention
ignored (R1.3); `pause` then a line opening with `resume` → ambiguous (R1.4).
