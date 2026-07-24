# Capability: token economy

> The-loop's opinion on **token/cost reduction** — a set of config-driven levers plus the
> skill guidance that makes them real — so an inherently iterative, verbose harness spends
> fewer tokens **without** spending less rigor. Single source of truth for the capability's
> current behaviour; the raw specs under `docs/specs/issue-37/` are the historical record.

## What it is

the-loop iterates (brainstorm → 3-phase spec → implement → self/critic review → evidence →
fold-in → briefing), is verbose by design (a `SKILL.md` + ten `reference/*.md` + rich
templates), and — in the default `process` runner — re-primes the harness on every webhook
event. That makes it token-hungry. This capability packages the field's token-reduction
practices (Anthropic context engineering, the caveman/ponytail projects, loop-engineering
guidance) as the `tokenEconomy` config section and `reference/token-economy.md`, keyed so
mechanical stages don't pay frontier-model prices and verbose output doesn't crowd the
window. It is used by every work item the loop runs, and by operators tuning cost.

## Current behaviour

All statements are **advisory**: the levers inform how the loop works and **never gate a
merge**. The rigor floor — validation, error handling, security, accessibility, test-first
discipline, the paper trail, review depth — is never traded for tokens.

- The system SHALL expose token-economy levers under `config.tokenEconomy`, master-switched
  by `tokenEconomy.enabled` and defaulted safe.
- **Model routing:** WHEN `modelRouting.enabled`, the loop SHALL route each pipeline stage
  to an abstract tier (`economy | standard | frontier`) per `modelRouting.stages`, where
  operators bind each tier to a concrete per-harness model id via `modelRouting.tiers`
  (empty = harness default). Reasoning-heavy stages (brainstorm/requirements/design/
  critic-review) default to `frontier`; mechanical stages (evidence, capability-docs,
  reviewer-briefing, status, learnings) default to `economy`. `modelRouting.riskTierFloor`
  SHALL lift high-risk work (tier 4/5) to a minimum tier regardless of stage. Routing is
  advisory where a harness cannot switch models programmatically.
- **Thinking effort:** WHEN `thinkingEffort.enabled`, the loop SHALL cap extended-thinking
  effort per stage (`none | low | medium | high`) so mechanical steps don't bill reasoning
  tokens.
- **Output verbosity:** WHEN `outputVerbosity.mode: concise`, the loop SHALL compress its
  own **narration** (drop filler, prefer fragments) and SHALL NEVER compress anything listed
  in `outputVerbosity.preserve` (code, commands, diffs, errors, paper-trail comments, the
  reviewer briefing, specs, decisions, capability docs) — so the educate-the-reviewer
  mandate is preserved.
- **Progressive disclosure:** WHEN `progressiveDisclosure.phaseScoped`, a step SHALL load
  only the reference doc(s) its phase needs (the loading map in `reference/token-economy.md`).
- **Sub-agent delegation:** WHEN `subAgentDelegation.enabled`, verbose work (tests, doc
  fetches, log/file scans) SHOULD run in a fresh-context sub-agent that returns a summary.
- **Compaction:** WHEN `compaction.enabled`, long runs SHALL checkpoint durable state to
  `execution-log.md` and compact/reset the window preserving the spec + open threads, leaning
  on the-loop's filesystem-as-memory.
- **Telemetry:** WHEN `telemetry.enabled`, the loop SHALL parse token/cost usage best-effort
  from each harness's JSON output (`DispatchResult.usage`) and surface it per dispatch/work
  item, so later levers are tuned against a real baseline. The loop SHALL set **no headline
  reduction target** until it has measured one.
- **External plugins:** the loop SHALL express caveman's (output compression) and ponytail's
  (generation minimalism) techniques **natively** and **register** — not vendor — those
  plugins in `config.externalTools` (decision-005: no bundled runtime).

## Design

Pointers, not copies:

- Levers & loading map: [`skills/the-loop/reference/token-economy.md`](../../skills/the-loop/reference/token-economy.md).
- Generation-side rung: [`skills/the-loop/reference/minimalism.md`](../../skills/the-loop/reference/minimalism.md).
- Config contract: `.the-loop/harness-config.schema.json` (`tokenEconomy`, `$defs.modelTier`) and
  the annotated `.the-loop/templates/harness-config.yaml`.
- Telemetry parsing: `cli/the_loop/harness/base.py` (`Usage`, `_usage_from_output`) with
  per-dispatch logging in `cli/the_loop/webhook/dispatcher.py`.
- Runner interplay (resident tmux vs. cold `-p --resume` re-priming):
  [`interactive-sessions`](interactive-sessions.md) and `docs/specs/issue-32/`.
- Research digest & rejected alternatives: [`docs/specs/issue-37/brainstorm.md`](../specs/issue-37/brainstorm.md).

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-37 | Introduced the token-economy capability: `tokenEconomy` config (model routing, thinking effort, output verbosity, progressive disclosure, sub-agents, compaction, telemetry), the `token-economy.md` reference, best-effort usage telemetry in the CLI, and registration of caveman/ponytail. | [spec](../specs/issue-37/), PR #41 |
