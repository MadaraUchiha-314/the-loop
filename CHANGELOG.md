## v0.14.0 (2026-07-23)

### Feat

- **cli**: clone event repos into per-work-item git worktrees (issue #76) (#77)

## v0.13.0 (2026-07-23)

### Feat

- **config**: split CLI daemon config out of the per-repo plugin config (issue #63) (#69)

## v0.12.2 (2026-07-23)

### Fix

- **cli**: drop the-loop's own replies before they can re-enter the trigger loop (#68)

## v0.12.1 (2026-07-23)

### Fix

- **poll**: launch and stop ttyd for the web terminal (issue #65) (#67)

## v0.12.0 (2026-07-23)

### Feat

- **skill**: read user-provided custom instruction docs while working (issue #59) (#61)

## v0.11.0 (2026-07-23)

### Feat

- **release**: bump plugin manifests in lockstep with releases via commitizen (issue #46) (#55)

## v0.10.0 (2026-07-23)

### Feat

- **skill**: checkpoint-then-reset context-window management (issue #48) (#53)

## v0.9.0 (2026-07-23)

### Feat

- **workflow**: security as a first-class, gated concern across the phase gates (issue #47) (#54)

## v0.8.0 (2026-07-23)

### Feat

- **token-economy**: brainstorm + config-driven token-reduction levers (issue #37) (#41)

## v0.7.0 (2026-07-22)

### Feat

- **cli**: structured JSONL event log — end-to-end o11y of the CLI's actions (issue #50) (#52)

## v0.6.0 (2026-07-22)

### Feat

- **init**: guided, schema-driven config onboarding with sensible defaults (issue #49) (#51)

## v0.5.1 (2026-07-22)

### Fix

- **templates**: keep templates internal to the-loop instead of copying to every repo (issue #36) (#44)

## v0.5.0 (2026-07-22)

### Feat

- **cli**: poll — provider-agnostic pull ingress to spawn/route harness sessions (#34) (#45)

## v0.4.0 (2026-07-21)

### Feat

- **sessions**: tmux runner — attachable interactive harness sessions (issue #32) (#35)

## v0.3.1 (2026-07-07)

### Fix

- **init**: detect existing project tooling instead of hardcoded defaults (#1) (#31)

## v0.3.0 (2026-07-07)

### Feat

- **capabilities**: specs organization via living capability docs (issue #25) (#26)

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
