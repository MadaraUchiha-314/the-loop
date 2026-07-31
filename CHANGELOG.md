## v3.0.2 (2026-07-31)

### Fix

- **issue-123**: honour the repository's own workflow.specDir on the daemon path (#126)

## v3.0.1 (2026-07-30)

### Fix

- **issue-119**: honour a control command that predates first sight (#120)

## v3.0.0 (2026-07-30)

### BREAKING CHANGE

- `reviews.critics[].command` is now the executable (argv[0]),
not a free-form invocation phrase; arguments belong in `args`. A value like
`"cursor-agent review"` is rejected with a diagnostic instead of being silently
mis-run.

### Feat

- **issue-108**: make the configured critic harness runnable (#115)

## v2.1.0 (2026-07-29)

### Feat

- **issue-113**: drive the process graph from the ingress (#114)

## v2.0.1 (2026-07-29)

### Fix

- **cli**: the session registry lists the files it wrote, not the whole directory (issue #111) (#112)

## v2.0.0 (2026-07-29)

### BREAKING CHANGE

- the CLI config now carries a `version` (0.2.0) and the three
`webhooks.ghWebhook.routing.{control,reactions,announce}.ghBinary` keys are
removed in favour of one `integrations.github.cli.binary`. A config still
declaring a removed key makes the CLI refuse to start rather than silently
ignore a value the operator set. `the-loop migrate-config` (and
`/the-loop:upgrade-the-loop`, which now shells out to it) performs the move.

### Feat

- **issue-109**: the PDLC as an executable graph of nodes with entry/exit hooks (#110)

## v1.0.0 (2026-07-26)

### BREAKING CHANGE

- with routing.control.requireStartCommand at its default true,
labelling a work item no longer starts a session on its own — comment
`the-loop:start-execution` or run `the-loop sessions start`. Set it to false to
keep the previous behaviour.

### Feat

- **cli**: authorized execution control (start/stop/pause/resume) + one state root (issue #106) (#107)

## v0.22.1 (2026-07-26)

### Fix

- **cli**: mark the daemon's own comments so the poller stops feeding them back (issue #104) (#105)

## v0.22.0 (2026-07-25)

### Feat

- **cli**: a PR closing ends only its own session — a work item may have several PRs (issue #101) (#102)

## v0.21.0 (2026-07-25)

### Feat

- **cli**: make PyYAML a required runtime dependency (issue #97) (#99)

## v0.20.0 (2026-07-25)

### Feat

- **cli**: pre-seed the harness config before spawning so sessions don't stall on the trust dialog (issue #90) (#92)

## v0.19.0 (2026-07-25)

### Feat

- **cli**: close the harness session when its work item is closed or merged (issue #94) (#96)

## v0.18.1 (2026-07-25)

### Fix

- **cli**: route an event on a PR to its linked issue first (issue #93) (#95)

## v0.18.0 (2026-07-25)

### Feat

- **cli**: resume the harness conversation when a dead tmux session is respawned (issue #89) (#91)

## v0.17.0 (2026-07-24)

### Feat

- **cli**: retain tmux sessions after completion + announce attach on the ticket (issue #86) (#87)

## v0.16.0 (2026-07-24)

### Feat

- **cli**: dispatch-lifecycle emoji reactions on the triggering entity (issue #84) (#85)

## v0.15.0 (2026-07-24)

### Feat

- **config**: single-source notification config in collaborators.yaml; rename plugin config to harness-config.yaml (#83)

## v0.14.2 (2026-07-24)

### Fix

- **cli**: bounded per-event retry policy + respawn dead tmux sessions (issue #80) (#81)

## v0.14.1 (2026-07-24)

### Fix

- **cli**: derive --version from package metadata (issue #78) (#79)

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
