## v11.1.0 (2026-08-18)

### Feat

- **issue-248**: a repository may bring its own hooks to the process graph (#268)

## v11.0.1 (2026-08-18)

### Fix

- **issue-269**: a branch name must not invent a work item (#271)

## v11.0.0 (2026-08-17)

### BREAKING CHANGE

- integrations.slack is no longer a valid CLI-config
key; run the-loop migrate-config (or /the-loop:upgrade-the-loop) and
configure channels.slack instead.

### Feat

- **issue-245**: channels — back-and-forth user communication through a Slack bot (#267)

## v10.6.0 (2026-08-17)

### Feat

- **issue-260**: the work item chooses how many sessions its pull requests get (#261)

## v10.5.0 (2026-08-17)

### Feat

- **issue-258**: the operator chooses how many sessions a work item's pull requests get (#259)

## v10.4.1 (2026-08-16)

### Fix

- **issue-251**: the suite is swept — two tests waited on the attempt, not the outcome (#256)

## v10.4.0 (2026-08-16)

### Feat

- **issue-242**: the-loop diagnoses its own failures and files the bug itself (#257)

## v10.3.1 (2026-08-16)

### Fix

- **issue-247**: record-feedback writes markdown its own linter accepts (#255)

## v10.3.0 (2026-08-16)

### Feat

- **issue-239**: stream the-loop's service to the control plane (#244)

## v10.2.5 (2026-08-16)

### Fix

- **issue-253**: a work item's own pull request is the work item's session (#254)

## v10.2.4 (2026-08-16)

### Perf

- **issue-243**: a forwarded event carries the instruction, not GitHub's metadata (#252)

## v10.2.3 (2026-08-16)

### Fix

- **issue-240**: a read-only tmux observer must not block every delivery (#250)

## v10.2.2 (2026-08-16)

### Fix

- **issue-246**: the poller reads reviews and review threads, not just comments (#249)

## v10.2.1 (2026-08-16)

### Fix

- **issue-238**: a vanished checkout must not keep failing /graph/check (#241)

## v10.2.0 (2026-08-16)

### Feat

- **issue-230**: readable session streams, a sessions tree, and a chat bar in the control plane (#237)

## v10.1.0 (2026-08-15)

### Feat

- **issue-212**: a Python SDK that embeds the-loop into somebody else's service (#235)

## v10.0.0 (2026-08-15)

### BREAKING CHANGE

- the `the-loop poll` command (start/stop/status) is removed.
Use `the-loop start|stop|status` driven by polling.enabled, or
`python -m the_loop.daemon_entry poller [--once]` for the foreground/cron
form. No config migration required: keys were added, none removed.
- `the-loop gh-webhook` and `the-loop service` are removed
alongside `the-loop poll`. Use `the-loop start|stop|status|restart` driven
by the config's enabled flags, or `python -m the_loop.daemon_entry
<poller|gh-webhook>` for a foreground daemon.

### Feat

- **issue-228**: one lifecycle surface — `the-loop start|stop|status|restart` per config-enabled services (#229)

## v9.15.0 (2026-08-14)

### Feat

- **issue-225**: ad-hoc tasks run a fourth loop, not a stretched `contribute` (#227)

## v9.14.0 (2026-08-14)

### Feat

- **issue-224**: make the learnings directory configurable and default it into docs/ (#226)

## v9.13.0 (2026-08-14)

### Feat

- **issue-222**: make the CLI config editable from the Control Plane UI (#223)

## v9.12.0 (2026-08-14)

### Feat

- **issue-220**: ship the-loop's config schemas with the plugin, not with your repo (#221)

## v9.11.0 (2026-08-12)

### Feat

- **issue-209**: serve the harness's own JSONL over /api/v1 — GET /sessions/transcript (#218)

## v9.10.0 (2026-08-12)

### Feat

- **issue-208**: route agent questions through `the-loop ask` + POST /api/v1/sessions/reply (#216)

## v9.9.0 (2026-08-12)

### Feat

- **issue-211**: configurable CORS, defaulting to the published dashboard's origin (#214)

## v9.8.0 (2026-08-12)

### Feat

- **issue-207**: control-plane dashboard over `/api/v1` (#210)

## v9.7.1 (2026-08-11)

### Refactor

- **issue-205**: the poller's heartbeat carries no pid (#206)

## v9.7.0 (2026-08-10)

### Feat

- **issue-203**: an inline `url` for the Slack integration (#204)

## v9.6.3 (2026-08-10)

### Fix

- **issue-201**: adopt an unconfigured repository before the session is spawned (#202)

## v9.6.2 (2026-08-10)

### Fix

- **issue-197**: the item's author gates spawning, and nothing else (#198)

## v9.6.1 (2026-08-10)

### Fix

- **issue-199**: a contribution has no outer loop, and its arming comment answers its first gate (#200)

## v9.6.0 (2026-08-10)

### Feat

- **issue-193**: a default harness config for repositories that never adopted the-loop (#195)

## v9.5.1 (2026-08-10)

### Fix

- **issue-194**: derive the work-item ref, and stop swallowing outbound-hook failures (#196)

## v9.5.0 (2026-08-10)

### Feat

- **issue-191**: poll start runs as a proper daemon (#192)

## v9.4.0 (2026-08-10)

### Feat

- **issue-188**: an opt-in critic review of the locked design (#190)

## v9.3.0 (2026-08-10)

### Feat

- **issue-186**: clean up a work item's local resources when it ends (#189)

## v9.2.0 (2026-08-09)

### Feat

- **issue-185**: the contribution loop — join an existing work item with a goal and success criteria (#187)

## v9.1.0 (2026-08-09)

### Feat

- **issue-183**: the outer loop runs in the origin repo, and its surface is declared (#184)

## v9.0.0 (2026-08-08)

### BREAKING CHANGE

- `security-review` and `human-approval` are no longer
`required: true` in `pdlc-work-item-loop`. An authorized human may declare them
skipped at `phase-selection`, and `graph force` no longer emits its
bypasses-a-required-node warning for them. The inner `pdlc-pr-loop` is
unchanged.

### Feat

- **issue-179**: every phase is selectable — the floor moves from the graph to the human (#180)

## v8.1.0 (2026-08-08)

### Feat

- **issue-177**: declared skips — the loop asks which phases a work item needs (#178)

## v8.0.0 (2026-08-07)

### BREAKING CHANGE

- PR events now land in a PR-specific session by default
rather than the work item's; set routing.tmux.sessionPerPr: false for the
previous shape.

### Feat

- **issue-172**: one record per work item, one session per PR — and the PDLC as two loops (#173)

## v7.4.1 (2026-08-06)

### Fix

- **issue-167**: six review gates stopped reporting success without running (#170)

## v7.4.0 (2026-08-06)

### Feat

- **issue-165**: write the-loop's artifacts for a human reader (#168)

## v7.3.0 (2026-08-06)

### Feat

- **issue-163**: test and verification as nodes in the PDLC (#166)

## v7.2.0 (2026-08-06)

### Feat

- **issue-161**: control plane and API layer — core → API → clients (#162)

## v7.1.1 (2026-08-05)

### Fix

- **issue-159**: make stopping and restarting the poller invisible (#160)

## v7.1.0 (2026-08-05)

### Feat

- **issue-152**: `the-loop install` / `upgrade` — the CLI and the Claude Code plugin, at user or project scope (#153)

## v7.0.0 (2026-08-05)

### BREAKING CHANGE

- the routing.runner config key and the headless process
runner are gone; tmux is required for the daemon. Session records no longer
carry a runner field; sessions list drops the Runner column.

### Feat

- **issue-156**: remove the process runner — tmux is the only runner (#158)

## v6.2.1 (2026-08-05)

### Fix

- **issue-154**: record and post the tmux session name tmux actually gave the session (#155)

## v6.2.0 (2026-08-04)

### Feat

- **issue-148**: the graph runs the PDLC — completion claims, consult-first dispatch, session inheritance (#149)

## v6.1.1 (2026-08-04)

### Fix

- **cli**: never spawn over a live tmux session; resolve duplicate-session collisions (issue #146) (#147)

## v6.1.0 (2026-08-04)

### Feat

- **issue-143**: enable the-loop's own plugin before a spawned session starts (#145)

## v6.0.0 (2026-08-04)

### BREAKING CHANGE

- `webhooks.ghWebhook.routing` moved to the top-level `routing`
key. A CLI config still declaring the old path is refused rather than silently
ignored, because `routing.authorizedUsers` decides which GitHub logins may
drive the daemon. Run `/the-loop:upgrade-the-loop` (or `the-loop
migrate-config`) to move it; nothing inside the block changed.

### Feat

- **issue-142**: promote `routing` out from under `webhooks.ghWebhook` — it governs both ingresses (#144)

## v5.2.1 (2026-08-04)

### Fix

- **issue-136**: trust the spawn directory itself, not only its workspace root (#140)

## v5.2.0 (2026-08-04)

### Feat

- **issue-134**: tell a spawned session where its answers come from — CLI or the work item (#139)

## v5.1.0 (2026-08-04)

### Feat

- **issue-137**: reset the-loop CLI's state for a work item (#141)

## v5.0.0 (2026-08-04)

### BREAKING CHANGE

- an operator relying on the shipped default keywords (never
configured `keywords` explicitly) must now comment `the-loop start` (etc.)
instead of `the-loop:start-execution` (etc.). Pin the old value explicitly
in `webhooks.ghWebhook.routing.control.keywords` to keep the previous
comment phrase.

### Feat

- **issue-135**: change the default session-control keywords to a short command form (#138)

## v4.2.0 (2026-08-03)

### Feat

- **issue-132**: make a custom-instruction registration verifiable, and findable (#133)

## v4.1.0 (2026-08-01)

### Feat

- **issue-130**: index the portable directory, and give a ref a URL (and a host) (#131)

## v4.0.0 (2026-07-31)

### BREAKING CHANGE

- polling.stateFile is removed and the CLI refuses a config that
still declares it; run `the-loop migrate-config`. On-disk state is not moved —
the old locations are read until each work item is written forward.

### Fix

- **issue-128**: classify generated state as portable or local, and document it (#129)

## v3.0.3 (2026-07-31)

### Fix

- **issue-124**: a `produces` entry names an artifact, not a filename (#127)

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
