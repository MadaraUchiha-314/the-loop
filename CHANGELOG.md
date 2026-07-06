## v0.2.1 (2026-07-06)

### Fix

- make first-release baseline tag local-only so release publishes (issue #21) (#24)

## v0.2.0 (2026-07-05)

### Feat

- publish CLI to PyPI as the-loopy-one via Trusted Publishing (issue #21) (#22)
- track UI/UX design artifacts in the design phase (issue #18) (#20)
- add optional brainstorm phase (root artifact) + /brainstorm command (issue #17) (#19)
- webhook→harness session routing — spec + implementation (issue #15) (#16)
- package the-loop as a Cursor plugin (shared skills/commands, rule-based reminder)
- Gherkin scenario docstrings on integration tests + contract-first API specs
- trigger mandatory user-education via a required PR-briefing gate
- adopt eight review-driven robustness features (issues #3-#10)
- expose granular per-phase commands (work-on is the superset)
- translate issue §5 user-interaction principles into artifacts

### Refactor

- keep the-loop's internal roadmap out of the published skill
- use commitizen for Conventional Commits instead of custom code
