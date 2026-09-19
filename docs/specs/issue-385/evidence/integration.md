---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#385"
---

<!-- Authored per the the-loop:writing skill. -->

# Integration evidence: committing the graph back to `main`

> Testing-plan row T2. `uv run --project cli python -m pytest -q cli/tests/test_graphify_commit_integration.py`

```text
6 passed in 1.15s
```

Each scenario builds a bare `origin` with one commit on `main` and drives the real
`scripts/graphify-commit.sh` from a clone, with `GRAPHIFY_PUSH_BACKOFF=0` so a retry does
not sleep.

```gherkin
Feature: Commit the knowledge graph back to main
  Scenario: The rebuild produced a byte-identical graph
    Given a clone whose graphify-out/ matches the branch tip
    When the commit script runs
    Then it exits 0 without creating a commit
    And the remote branch is untouched

  Scenario: The rebuild changed the graph
    Given a clone whose graphify-out/ differs from the branch tip
    And an unrelated modified file outside graphify-out/
    When the commit script runs
    Then exactly one commit is pushed to the remote branch
    And its message is a Conventional Commits chore naming the built commit
    And it carries only the files under graphify-out/

  Scenario: The release workflow pushed a bump commit while the graph was building
    Given a clone one commit behind the remote branch
    And a changed graphify-out/ in that clone
    When the commit script runs
    Then the push succeeds without --force
    And the remote branch carries the bump commit and the graph commit on top of it
    And the bump commit's file survives

  Scenario: The workflow's default depth-1 checkout
    Given a depth-1 clone of the remote branch with a changed graphify-out/
    And a commit that landed on the remote meanwhile
    When the commit script runs
    Then the push succeeds

  Scenario: The remote refuses every push
    Given a remote whose pre-receive hook rejects updates
    And a changed graphify-out/ in the clone
    When the commit script runs
    Then it retries a bounded number of times and exits non-zero
    And the remote branch is untouched

  Scenario: Somebody committed a different graphify-out/ to main meanwhile
    Given a clone with a changed graphify-out/graph.json
    And a remote commit that changed the same file differently
    When the commit script runs
    Then it aborts the rebase and exits non-zero
    And it never force-pushes over the remote commit
```

The second scenario is the one that found a defect (`evidence/unit.md` § Red → green):
the first script could not rebase over an unstaged file outside `graphify-out/`.
