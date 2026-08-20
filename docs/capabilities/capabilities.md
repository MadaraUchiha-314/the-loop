# Capabilities — the-loop

The **organized view of the specs** (issue-25): one living doc per capability, each the
single source of truth for that capability's *current* behaviour, with history rows
tracing every behaviour back to the raw specs (`docs/specs/<id>/`) and decisions that
produced it. Product-feature and architecture shaped capabilities are both valid; the
taxonomy evolves through PR-review feedback. Affected docs are updated **in the same
PR** as the work item that changes behaviour (a ready-to-ship gate item).

| Capability | What it covers |
|------------|----------------|
| [spec-workflow](spec-workflow.md) | The (brainstorm →) requirements → design → testing plan → tasks → implementation → verification loop, phase state machine, commands. |
| [process-graph](process-graph.md) | The same loop made executable: nodes, entry/exit hooks, declared edges, the human gate, and the forced-transition escape hatch. |
| [review-loop](review-loop.md) | Self and critic review rounds before a human: the procedure, and how a configured critic harness is actually invoked. |
| [capability-docs](capability-docs.md) | This layer itself: the organized view of specs and its fold-in gate. |
| [distribution](distribution.md) | Shipping the-loop as a Claude Code and Cursor plugin from one repo. |
| [cli](cli.md) | The `the-loop` Python CLI companion and its commands. |
| [control-plane](control-plane.md) | The core → API → clients layering: the HTTP API service, the service-routed CLI, the MCP endpoint, and the statically-hostable UI. |
| [sdk](sdk.md) | the-loop as a component of somebody else's Python service: the importable capability surface, the mountable router, and the environment contract. |
| [webhook-triggers](webhook-triggers.md) | GitHub webhook receiver and event → session routing. |
| [interactive-sessions](interactive-sessions.md) | tmux-hosted harness sessions humans can watch/steer live (local, SSH, browser). |
| [standing-sessions](standing-sessions.md) | Named, long-lived sessions that belong to no work item — the ones the-loop keeps for itself, addressed by name on the control plane and in Slack. |
| [observability](observability.md) | Structured JSONL event log of the CLI's actions and the `events` query command. |
| [channels](channels.md) | Back-and-forth conversation surfaces (the Slack bot) mirroring every reply onto the work item. |
| [self-diagnosis](self-diagnosis.md) | the-loop filing redacted issues for its own failures: event-log detection, an isolated diagnosis agent, never-armed issue creation (opt-in, default off). |
| [testing-and-contracts](testing-and-contracts.md) | The testing plan and the verification node (test-type matrix, environment, committed evidence), Gherkin scenario docstrings, the queryable scenario view, contract-first APIs. |
| [design-artifacts](design-artifacts.md) | UI/UX design artifacts (Figma / HTML prototypes) in the design phase. |
| [release-publishing](release-publishing.md) | Automatic semantic releases and PyPI publishing of the CLI. |
| [documentation](documentation.md) | The docs site: its information architecture, the authored-not-generated rule, and the docs↔code parity test. |
| [token-economy](token-economy.md) | Token/cost-reduction levers (model routing, output verbosity, disclosure, sub-agents, telemetry); advisory, never at the expense of rigor. |
| [writing-style](writing-style.md) | How the artifacts a human reads are written: the `the-loop:writing` skill, the document spine, the diagram-first rule and the formal-language carve-out. No length limits. |

Related views: [`docs/architecture/architecture.md`](../architecture/architecture.md)
(how it's built) · [`docs/decisions/decisions.md`](../decisions/decisions.md) (why) ·
[`docs/specs/`](../specs/) (per-work-item history).
