# Decision Log

Index of architecture/process decisions for the-loop. Each entry links a detailed
record (`decision-<nnn>.md`). Newest first.

| # | Title | Status | Date |
|---|-------|--------|------|
| [078](decision-078.md) | Agent questions travel through a verb; the loop-prevention marker is stamped centrally | proposed | 2026-08-12 |
| [077](decision-077.md) | The published dashboard's origin is allowed to read the service by default | proposed | 2026-08-12 |
| [076](decision-076.md) | The lock and the heartbeat are two files — and only the lock names the process | proposed | 2026-08-11 |
| [075](decision-075.md) | A credential's secrecy is the operator's call — Slack's webhook URL may be configured inline | proposed | 2026-08-10 |
| [074](decision-074.md) | On the poll path, the item's author gates only spawning | proposed | 2026-08-10 |
| [073](decision-073.md) | the-loop adopts an unconfigured repository with a packaged default — except as a guest | proposed | 2026-08-10 |
| [072](decision-072.md) | `poll start --daemon` is opt-in, not the default | proposed | 2026-08-10 |
| [071](decision-071.md) | A phase may be offered rather than imposed (`optIn`), and the design critic round | proposed | 2026-08-10 |
| [070](decision-070.md) | Joining existing work is a third loop, armed by a keyword and gated on a stated goal | proposed | 2026-08-09 |
| [069](decision-069.md) | The outer loop runs in the origin repository, and each work item declares its surface | proposed | 2026-08-09 |
| [068](decision-068.md) | Every phase is selectable — the floor moves from the graph to the human | proposed | 2026-08-08 |
| [067](decision-067.md) | Skips are declared — the graph fixes the vocabulary, a human selects, the runtime never forges | proposed | 2026-08-08 |
| [066](decision-066.md) | User-facing documentation is a completion gate, on the node that already reads the log | proposed | 2026-08-07 |
| [065](decision-065.md) | The PDLC is two loops — pdlc-work-item-loop outside, pdlc-pr-loop per pull request | proposed | 2026-08-07 |
| [064](decision-064.md) | One session record per work item carries its pull requests — each PR an endpoint with its own session | proposed | 2026-08-07 |
| [063](decision-063.md) | A node may `validates:` an artifact it did not author — and a content gate with nothing to read fails closed | proposed | 2026-08-06 |
| [062](decision-062.md) | Third-party writing skills are registered, not vendored — and their ban-lists are not adopted | proposed | 2026-08-06 |
| [061](decision-061.md) | Writing for humans is a sibling skill — with no length limits | proposed | 2026-08-06 |
| [060](decision-060.md) | Testing is planned and verified as two nodes; the plan is the record, and a skip is not a decision | proposed | 2026-08-06 |
| [059](decision-059.md) | The control-plane service carries no in-app authentication — the gateway owns auth | proposed | 2026-08-05 |
| [058](decision-058.md) | Re-layer the CLI as core → HTTP API → clients; the service is the CLI's only execution path | proposed | 2026-08-05 |
| [057](decision-057.md) | `the-loop install`/`upgrade` drive the harness's own installer (Claude Code first); fallback only to a documented route | proposed | 2026-08-05 |
| [056](decision-056.md) | tmux is the only runner — the headless process runner is removed | proposed | 2026-08-05 |
| [055](decision-055.md) | the-loop never spawns over a live `loop-<slug>` tmux session — it routes the event into it | proposed | 2026-08-04 |
| [054](decision-054.md) | The CLI enables the-loop's own plugin in the harness's user settings before a spawn | proposed | 2026-08-04 |
| [053](decision-053.md) | A config key is nested under what owns it — `routing` governs both ingresses, so it is top-level | proposed | 2026-08-04 |
| [052](decision-052.md) | Trust the spawn directory itself under every scope — `harnessTrust.scope` only widens | proposed | 2026-08-04 |
| [051](decision-051.md) | The interaction channel is declared (two values); artifact iteration on the PR is an invariant | proposed | 2026-08-04 |
| [050](decision-050.md) | A reset erases the-loop's memory of a work item, and nothing else — and it is not a control verb | proposed | 2026-08-04 |
| [049](decision-049.md) | An instruction registration is verified by a command, not by a graph gate | proposed | 2026-08-03 |
| [048](decision-048.md) | A work-item ref names its host when it is not the default one | proposed | 2026-07-31 |
| [047](decision-047.md) | The portable directory carries a derived index, and derived means nothing may read it | proposed | 2026-07-31 |
| [046](decision-046.md) | State is organised by portability — facts about the work travel; handles to a machine do not | proposed | 2026-07-31 |
| [045](decision-045.md) | `produces` names an artifact, not a filename — several accepted names, exactly one present | proposed | 2026-07-31 |
| [044](decision-044.md) | A repository's harness config configures work on that repository, never the daemon itself | proposed | 2026-07-30 |
| [043](decision-043.md) | A critic is a declared executable the CLI spawns; the harness keeps the loop | proposed | 2026-07-29 |
| [042](decision-042.md) | Route on hook outcomes; the-loop owns its integrations; MCP by delegation | proposed | 2026-07-28 |
| [041](decision-041.md) | Model the-loop's PDLC as a graph of nodes with entry/exit hooks | proposed | 2026-07-28 |
| [040](decision-040.md) | The auto-execute label arms a work item; an authorized user's explicit command starts it | proposed | 2026-07-26 |
| [039](decision-039.md) | A PR closing ends only its own session — a work item may be delivered by several PRs | proposed | 2026-07-25 |
| [038](decision-038.md) | PyYAML is a required runtime dependency; the zero-runtime-dependency guarantee is retired | proposed | 2026-07-25 |
| [036](decision-036.md) | An event on a PR routes to the PR's linked issue first (one session per work item) | accepted | 2026-07-25 |
| [037](decision-037.md) | Pre-seed the harness's own config before spawning (trust the workspace root, configurable; accept the bypass disclaimer only when already requested) | proposed | 2026-07-25 |
| [035](decision-035.md) | collaborators.yaml is the single source for people + notification config; plugin config renamed harness-config.yaml | accepted | 2026-07-24 |
| [034](decision-034.md) | Clone each event's repo into a per-work-item git worktree under a configurable workspace root | accepted | 2026-07-23 |
| [033](decision-033.md) | Documentation site reads `docs/` in place; no duplicated `docs-site/` mirror | accepted | 2026-07-23 |
| [032](decision-032.md) | Split the-loop's config into a per-repo plugin config and an independently-configurable CLI config | accepted | 2026-07-23 |
| [031](decision-031.md) | Self-reply marker guard — an embedded body marker, not GitHub metadata | accepted | 2026-07-23 |
| [030](decision-030.md) | Stay on Python for the CLI — a rewrite in Go/Rust/Bun buys nothing measurable | proposed | 2026-07-23 |
| [029](decision-029.md) | Register user instruction docs inline in config (guidance counterpart of externalTools) | accepted | 2026-07-23 |
| [028](decision-028.md) | Version plugin manifests in lockstep via commitizen `version_files` (no second release tool) | accepted | 2026-07-23 |
| [027](decision-027.md) | Checkpoint-then-reset context management (clear at phase boundaries, compact at task boundaries) | accepted | 2026-07-23 |
| [026](decision-026.md) | Security is a gated, per-phase concern of the spec workflow (not a separate step) | accepted | 2026-07-23 |
| [025](decision-025.md) | JSONL event log as the CLI's observability source of truth (not SQLite) | accepted | 2026-07-22 |
| [024](decision-024.md) | Schema-driven grouped onboarding for `/init` (x-onboarding annotations) | accepted | 2026-07-22 |
| [023](decision-023.md) | Authorized-actor guard on both trigger paths (prompt-injection remediation) | accepted | 2026-07-22 |
| [022](decision-022.md) | Poll as a provider-agnostic pull ingress reusing the webhook dispatch stack | accepted | 2026-07-21 |
| [021](decision-021.md) | tmux runner for observable/interactive webhook-spawned sessions | partly superseded (by 056: the runner choice) | 2026-07-17 |
| [020](decision-020.md) | Capability docs are the organized view of specs (SoT for current behaviour) | accepted | 2026-07-07 |
| [019](decision-019.md) | Publish the CLI to PyPI as `the-loopy-one` via Trusted Publishing | accepted | 2026-07-04 |
| [018](decision-018.md) | UI/UX design artifacts are first-class, tracked design-phase artifacts | accepted | 2026-07-04 |
| [017](decision-017.md) | Add an optional brainstorm phase (the root artifact) before requirements | accepted | 2026-07-04 |
| [016](decision-016.md) | Route GitHub webhooks to harness sessions via the CLI receiver, not GitHub MCP | accepted | 2026-07-02 |
| [015](decision-015.md) | Ship the-loop as a Cursor plugin from the same repo | accepted | 2026-07-02 |
| [014](decision-014.md) | Gherkin scenario docstrings on integration tests + contract-first API specs | accepted | 2026-07-02 |
| [013](decision-013.md) | Trigger mandatory user-education via a required PR-briefing gate | accepted | 2026-07-01 |
| [012](decision-012.md) | Adopt eight review-driven robustness features (issues #3–#10) | accepted | 2026-07-01 |
| [011](decision-011.md) | Expose granular per-phase commands (with /work-on as superset) | accepted | 2026-07-01 |
| [010](decision-010.md) | Keep the-loop's internal roadmap out of the published skill | accepted | 2026-07-01 |
| [009](decision-009.md) | Dogfood uv (workspace + uv.lock) for the-loop's own tooling | accepted | 2026-07-01 |
| [008](decision-008.md) | Use commitizen for Conventional Commits (not custom code) | accepted | 2026-07-01 |
| [007](decision-007.md) | Enforce Conventional Commits | superseded (by 008) | 2026-06-30 |
| [006](decision-006.md) | Dogfood the-loop's own quality gates (pre-commit + CI parity) | accepted | 2026-06-30 |
| [005](decision-005.md) | Provide a lightweight, extensible Python CLI (`the-loop`) | accepted | 2026-06-30 |
| [004](decision-004.md) | Adopt Kiro's 3-phase spec workflow for the loop | accepted | 2026-06-30 |
| [003](decision-003.md) | Bootstrap a v0 skeleton first, defer runtime automation | accepted | 2026-06-27 |
| [002](decision-002.md) | Track the-loop's footprint via `.the-loop/manifest.yaml` and a config schema | accepted | 2026-06-27 |
| [001](decision-001.md) | Ship the-loop as a Claude plugin installable from GitHub | accepted | 2026-06-27 |
