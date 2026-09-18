---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#382"
---

<!-- Authored per the the-loop:writing skill. -->

# Integration evidence: the poll clocks are this machine's, not the repository's

> Testing-plan row T4. `uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py`

```text
32 passed in 2.33s
```

## The scenario this work item adds

```gherkin
Feature: Poll GitHub and close finished work items
  Scenario: A restarted poller does not re-ask about an item it polled a moment ago
    Given a labelled issue by an unlisted author, listed once (a poll-only record, no session)
    When the poller process is replaced by a new one over the same state root
    And the issue has left the listing
    Then the new process does not ask GitHub about it — the window has not passed
    And the tracked record it reads carries no timestamp of its own
```

It is the claim the split has to keep: the schedule survives a restart because the clock
is on disk, and it survives it **without** the tracked record holding the clock. Both
halves are asserted — `summary.ledger_checks == 0` and no new `repos/octo/repo/issues/15`
call against the fake GitHub, and `"lastPolledAt" not in` the record's `poll` section
while `poll-clocks.json` has it.

## The scenario that changed

`test_a_closed_ledger_only_item_is_stamped_after_the_window` (issue-332) ages the ledger
to force the window open. Ageing it now means ageing the **clocks**, through the poller's
own store — the file is loaded once per process — and its `closureCheckedAt` assertion
reads the clock file, with `"closureCheckedAt" not in` the record asserted beside it. The
scenario's Gherkin is unchanged: what it proves did not change, only where the date lives.
