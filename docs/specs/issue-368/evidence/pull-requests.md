---
type: evidence
record: pull-requests
workItem: "github:MadaraUchiha-314/the-loop#368"
---

# Pull requests: one rule for where a work item's attributes live

## Pull requests

| Pull request | Repository | Carries |
|---|---|---|
| [#369](https://github.com/MadaraUchiha-314/the-loop/pull/369) | `MadaraUchiha-314/the-loop` | the whole work item: the spec chain, the implementation, the docs and the evidence |

One repository, one pull request. The work item declares no contributing repositories
beyond its own, so `await-inner-loops` passes vacuously and no inner loop was started.

The pull request opened with the spec chain alone and was reviewed twice by the owner
before implementation began:

1. a review comment on `design.md` — *"why are we replicating PR information in the
   local file?"* — answered inline and resolved, and folded into requirements R5.1 and
   design D10;
2. a review — *"there's N files that are created for each work item in the portable
   directory… only one file in portable for each work-item"* — folded into audit finding
   F8, requirement R10 and design D9;
3. the approval — *"LGTM. implement"* — on commit `6fd1cd9`, which is what unlocked the
   implementation and locked the three artifacts.
