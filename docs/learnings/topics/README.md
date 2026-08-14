# Learnings — topic overflow

Overflow detail for the learnings lifecycle (see
`skills/the-loop/reference/automation.md` §Self-improvement). When the injected index in
`<learningsDir>/learnings.md` exceeds `config.selfImprovement.maxIndexLines`, the least-
important/least-recent entries are consolidated into `<learningsDir>/topics/<category>.md`
files here and read **on demand** — keeping the always-injected index small while nothing
is lost.

`<learningsDir>` is `config.workflow.learningsDir` (default `docs/learnings`, and what
this repository sets) — the same key that put this directory where it is.

Pending, not-yet-durable learning candidates live in the git-ignored
`.the-loop/learnings-pending/` queue until they pass the write-gate
(`config.selfImprovement.writeGateOccurrences`).
