# Decision Log

Index of architecture/process decisions for the-loop. Each entry links a detailed
record (`decision-<nnn>.md`). Newest first.

| # | Title | Status | Date |
|---|-------|--------|------|
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
| [021](decision-021.md) | tmux runner for observable/interactive webhook-spawned sessions | accepted | 2026-07-17 |
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
