---
type: pr-testing-plan
workItem: ""          # the work item, e.g. "github:octo/origin#15"
pullRequest: ""       # this pull request, e.g. "github:octo/api#12"
sourceRevision: ""    # the origin commit the chain was read at
chainDigest: ""       # printed by `the-loop graph pr-spec`; it refuses a mismatch
---

<!-- A PR spec (issue-543, decision-153): derived from the work item's approved chain,
     scoped to this pull request, never approved on its own — so it carries no
     `status`. Written per the `the-loop:writing` skill. Cite the work-item item
     each line comes from: [wi:R2], [wi:R2.3], [wi:design#<slug>], [wi:TP-T2],
     [wi:task-4]. `the-loop graph pr-spec` refuses a citation that does not resolve. -->

# PR testing plan: <what this pull request delivers>

## Context

This pull request is one part of <work item ref and title>, read at
<sourceRevision>. The full spec is `docs/specs/<id>/` in <origin repository>.

| Pull request | Delivers |
|---|---|
| <this PR> | <what this PR delivers> |
| <sibling PR> | <what it delivers> |

## Test matrix

The rows that run in this pull request. Every in-scope row cites the work-item row
or requirement it proves.

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|---|---|---|---|
| P1 | Unit | yes | <what it proves> [wi:TP-T1] | <command> |
