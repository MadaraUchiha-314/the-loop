---
type: evidence
workItem: issue-553
---

# Security review: a context-gathering phase before the spec chain

> The `security-review` node's proof. See `reference/security.md`.

## Security review (gate)

- **Mechanism:** Claude Code's built-in `/security-review` skill, run on the branch's
  diff. A read-only subagent looked for vulnerabilities in the production code; nothing
  met the reporting bar, so there was nothing for the false-positive pass to filter.
- **Outcome:** pass, with one observation below the bar fixed.
- **Findings:** none at or above the skill's bar (a concrete exploit path at more than
  80% confidence). The six boundaries it examined and why each holds:

  | Boundary | Why it holds |
  |---|---|
  | handoff record → entry node | `context-settled` maps only to `context-approval`, a human gate, and must carry exactly `current-state.md`; a record counts only from an authorized author |
  | handoff → selection | the ticked row is a proposal; an authorized reply still freezes it, and a tick adds a gate |
  | hook result → state | a demotion's selection needs an opt-in node, demoted in the same result, not yet entered; it only adds a node to the walk |
  | comment → gate verdict | the changed `classify-feedback` is stricter: an entered gate now needs a decisive comment from an authorized user; a removed file still blocks |
  | carried file → spec folder | the existing symlink, containment, hash and shape checks; the name comes from the closed list |
  | file → prompt | existence only, symlinks and unreadable files refused, fixed text and the id; no byte of the file |

- **Observation (confidence 4 of 10, fixed):** the prompt line called the file "as
  approved for this work item". That is not always true: the line is emitted whenever
  the file exists, including when `context-gathering` was ticked without its gate, and
  after a demotion re-authors the file with the gate unselected. *Fixed:* the words are
  removed from the prompt file and from four commands, and a test pins that the line
  does not say "approved". This departs from the wording in the approved design. The
  other half of the observation, that a demotion selects the producer and not the gate,
  is left as designed and is raised to the reviewer in the briefing.
- **Human sign-off:** n/a (risk tier below 4: no new permission, credential, network
  call or data store).
