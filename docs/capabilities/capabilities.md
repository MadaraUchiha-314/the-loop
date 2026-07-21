# Capabilities — the-loop

The **organized view of the specs** (issue-25): one living doc per capability, each the
single source of truth for that capability's *current* behaviour, with history rows
tracing every behaviour back to the raw specs (`docs/specs/<id>/`) and decisions that
produced it. Product-feature and architecture shaped capabilities are both valid; the
taxonomy evolves through PR-review feedback. Affected docs are updated **in the same
PR** as the work item that changes behaviour (a ready-to-ship gate item).

| Capability | What it covers |
|------------|----------------|
| [spec-workflow](spec-workflow.md) | The (brainstorm →) requirements → design → tasks → implementation loop, phase state machine, commands. |
| [capability-docs](capability-docs.md) | This layer itself: the organized view of specs and its fold-in gate. |
| [distribution](distribution.md) | Shipping the-loop as a Claude Code and Cursor plugin from one repo. |
| [cli](cli.md) | The `the-loop` Python CLI companion and its commands. |
| [webhook-triggers](webhook-triggers.md) | GitHub webhook receiver and event → session routing. |
| [interactive-sessions](interactive-sessions.md) | tmux-hosted harness sessions humans can watch/steer live (local, SSH, browser). |
| [testing-and-contracts](testing-and-contracts.md) | Gherkin scenario docstrings, the queryable scenario view, contract-first APIs. |
| [design-artifacts](design-artifacts.md) | UI/UX design artifacts (Figma / HTML prototypes) in the design phase. |
| [release-publishing](release-publishing.md) | Automatic semantic releases and PyPI publishing of the CLI. |

Related views: [`docs/architecture/architecture.md`](../architecture/architecture.md)
(how it's built) · [`docs/decisions/decisions.md`](../decisions/decisions.md) (why) ·
[`docs/specs/`](../specs/) (per-work-item history).
