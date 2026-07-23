# Operating model

This is the reference detail behind the `the-loop` skill — the operating model an
agent harness follows once a work item's phase is underway. Each page below is read by
the harness at the point in the loop where it's relevant (progressive disclosure — see
[token economy](/operating-model/reference/token-economy)); read them here for the
same detail, up front.

| Reference | Covers |
|-----------|--------|
| [Workflow](/operating-model/reference/workflow) | The loop, phases, TDD, reviews, autonomy, DAG, resumability. |
| [Context](/operating-model/reference/context) | Context-window management: clearing vs. compaction, the checkpoint-then-reset protocol, per-harness mechanics. |
| [Onboarding](/operating-model/reference/onboarding) | The guided, schema-driven config onboarding `/the-loop:init` runs. |
| [Instructions](/operating-model/reference/instructions) | User-provided custom instruction docs: when to read them, precedence, what they can and cannot override. |
| [Design artifacts](/operating-model/reference/design-artifacts) | UI/UX design artifacts (Figma / HTML prototypes) in the design phase and the designer iteration loop. |
| [Reviewing](/operating-model/reference/reviewing) | The self/critic review procedure the review counts drive. |
| [Security](/operating-model/reference/security) | The security lens on every phase gate: threat-model-lite, security design, the security-review gate, human sign-off tiers. |
| [Tooling](/operating-model/reference/tooling) | Repo management, per-language tooling matrix, hooks, CI parity. |
| [Testing](/operating-model/reference/testing) | Gherkin scenario docstrings on integration tests, the queryable scenario view, OpenAPI/GraphQL contract conventions. |
| [Minimalism](/operating-model/reference/minimalism) | The generation-time decision ladder to counter code bloat. |
| [Token economy](/operating-model/reference/token-economy) | Token/cost levers (model routing, verbosity, disclosure, sub-agents, telemetry); advisory, never at the expense of rigor. |
| [Collaboration](/operating-model/reference/collaboration) | Personas/roles, paper trail, conflict log, messaging, MCP. |
| [Observability](/operating-model/reference/observability) | Dev==runtime logging, levels, browser logging. |
| [Automation](/operating-model/reference/automation) | Distribution, the CLI, webhooks, predictability, learnings lifecycle. |

The source `SKILL.md` that ties these together lives at
[`skills/the-loop/SKILL.md`](https://github.com/MadaraUchiha-314/the-loop/blob/main/skills/the-loop/SKILL.md)
in the repository.
