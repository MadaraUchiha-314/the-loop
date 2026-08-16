---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#247"
---

# Evidence: the red run (issue-247)

The three tests of tasks 2-4, run against the **unfixed** `record_feedback`. Captured
before the fix, per `tdd.mode: standard`.

## `uv run --project cli python -m pytest -q cli/tests/test_graph_integration.py`

```text
repo = PosixPath('/tmp/pytest-of-root/pytest-1/test_a_recorded_review_never_w0')

    def test_a_recorded_review_never_writes_emphasis_alone_on_a_line(repo):
        """
        Feature: the-loop's process graph
        Scenario: a recorded approval passes the project's markdown linter
          Given a gate approving with comments from two reviewers
          When record-feedback appends them to the artifact
          Then no line of the artifact is emphasized text and nothing else
        Requirement: docs/specs/issue-247/bugfix.md#R1.1
        """
        text = _record(
            repo,
            [
                {"author": "owner", "body": "approved, but tighten the nit"},
                {"author": "second", "body": "lgtm"},
            ],
        )
    
        assert "@owner" in text and "@second" in text
>       assert not _emphasis_only_lines(text)
E       AssertionError: assert not ['**@owner**', '**@second**']
E        +  where ['**@owner**', '**@second**'] = _emphasis_only_lines('---\nstatus: approved\n---\n\n# D\n\n## Review comments\n\n### 2026-08-16 — approved-with-comments\n\n**@owner**\n\napproved, but tighten the nit\n\n**@second**\n\nlgtm\n')

cli/tests/test_graph_integration.py:232: AssertionError
______ test_a_comment_with_no_body_is_recorded_without_a_blank_line_pair _______

repo = PosixPath('/tmp/pytest-of-root/pytest-1/test_a_comment_with_no_body_is0')

    def test_a_comment_with_no_body_is_recorded_without_a_blank_line_pair(repo):
        """
        Feature: the-loop's process graph
        Scenario: an approval submitted with no comment text is still recorded
          Given a reviewer who approves without writing anything
          When record-feedback appends the review to the artifact
          Then the reviewer is still attributed and no two blank lines are adjacent
        Requirement: docs/specs/issue-247/bugfix.md#R1.2
        """
        text = _record(
            repo,
            [
                {"author": "owner", "body": "approved"},
                {"author": "second", "body": "   "},
            ],
        )
    
        assert "@second" in text  # an empty approval is still a fact about the gate
>       assert "\n\n\n" not in text
E       AssertionError: assert '\n\n\n' not in '---\nstatus...cond**\n\n\n'
E         
E         '\n\n\n' is contained here:
E           **@second**
E         ?            +

cli/tests/test_graph_integration.py:253: AssertionError
=========================== short test summary info ============================
FAILED cli/tests/test_graph_integration.py::test_an_approval_with_comments_is_recorded_in_the_artifact
FAILED cli/tests/test_graph_integration.py::test_a_recorded_review_never_writes_emphasis_alone_on_a_line
FAILED cli/tests/test_graph_integration.py::test_a_comment_with_no_body_is_recorded_without_a_blank_line_pair
3 failed, 18 passed in 0.55s
```
