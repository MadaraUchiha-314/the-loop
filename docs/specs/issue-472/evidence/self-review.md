---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#472"
---

# Self-review: make the phase-selection comment easier to read (issue-472)

> No critics are configured in this cloud checkout (`.the-loop/cli-config.yaml` declares
> none), so the critic rounds could not run. Round 3 found nothing new, which meets the
> stop rule (3 self, 3 critic, stop on no new findings).

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition |
|-------|----------|---------|------------------------|
| 1 | self (scope read) | new findings | (a) The Slack digest would show raw `<details>` and `<summary>` tags, and Slack reads `<…>` as link syntax. Added `_unfold` to `to_mrkdwn` and `condense`, with tests. (b) The Slack mirror reads any bare one-token bullet as a protected phase. Kept the protected list as bare bullets and added no other such line; a test pins `always` to the graph's protected list. |
| 2 | self (diff read) | new findings | (c) The closing line said the boxes are "what this work item walks", but settings are not walked. Reworded to "frozen as this work item's selection". (d) With no graph in context the comment showed an empty "Phases" heading. It is now omitted, with a test. (e) Four existing tests asserted the old wording; updated to the new default lines and headings. |
| 3 | self (adversarial read) | zero (converged) | — |
| — | critic | unavailable | — |

## Questions asked of the diff, and their answers

- **Can a reply be read differently now?** No. The rows keep their exact shape and
  order, and the parser did not change. The layout tests read the rows back with
  `selection_rows`, and the existing gate tests run unchanged.
- **Is a choice hidden behind a click?** No. No row sits inside `<details>` (tested).
  The only collapsed list is the protected phases, which are not choices.
- **Does GitHub render it?** The evidence files `checklist-before.md` and
  `checklist-after.md` are the generated comments; GitHub renders them the same way it
  renders the comment.
- **Was anything dropped?** No. A test lists every fact the old comment stated and
  checks that the new one still states it.
- **Is the comment longer?** In total, yes: 989 words become 1,176, mostly headings and
  default lines. The text visible before any click falls from 989 words to 554, and most
  of that is the rows themselves.
