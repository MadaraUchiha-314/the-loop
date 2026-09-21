---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#415"
---

# Pull requests: the `/the-loop:init` onboarding a person can finish

| PR | Branch | Delivers | State |
|---|---|---|---|
| [#417](https://github.com/MadaraUchiha-314/the-loop/pull/417) | `claude/beautiful-meitner-axx4n7` | the whole work item — schema metadata, the procedure, the command, the docs, the test | open, awaiting review |

One PR rather than a spec PR plus an implementation PR: the spec chain and the change it
describes are the same diff's worth of reading, and splitting them would have put the
reviewer's context in one tab and the thing to judge in another.

`the-loop sessions link-pr` was **not** run — the CLI is not installed in this
environment, and the plugin's `PostToolUse` recorder (`hooks/the-loop-link-pr.py`) is not
active here either. The PR body carries `Closes #415`, which is one of the three linkages
the router reads, so the PR still resolves to this work item.
